import json
import os
import tempfile
import unittest
from unittest import mock

from library import draft

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


class ParseTest(unittest.TestCase):
    def setUp(self):
        self.players = {p.name: p for p in (draft.parse_player(e, 2027) for e in fixture("espn_players_2027.json")["players"]) if p}

    def test_league_settings(self):
        league = draft.parse_league(fixture("espn_league_2027.json"), 1, 2027)
        self.assertEqual((league.teams, league.budget, league.draft_type), (12, 200, "AUCTION"))
        self.assertEqual(sorted(league.categories), sorted(["PTS", "REB", "AST", "STL", "BLK", "3PM", "TO", "FG%", "FT%"]))
        self.assertEqual(league.reverse, ["TO"])
        self.assertEqual(league.slot_counts["BE"], 5)
        self.assertEqual(league.rank_type, "ROTO")

    def test_last_season_and_projection(self):
        k = self.players["Walker Kessler"]
        self.assertEqual(k.last_gp, 5)
        self.assertGreater(k.proj_gp, 50)
        self.assertEqual(k.default_exp_gp, round((k.last_gp + 2 * k.proj_gp) / 3))  # leans on ESPN
        self.assertIn("C", k.eligible_slots)
        self.assertGreater(k.base_pg["BLK"], 1.5)
        self.assertFalse(k.base_is_projection)

    def test_minutes_defaults(self):
        flagg = self.players["Cooper Flagg"]
        self.assertEqual(flagg.rate_source, "last")  # a full season: his own per-minute rates
        self.assertEqual(flagg.rate_min, flagg.last_pg["MIN"])
        self.assertEqual(flagg.default_exp_min, round(flagg.proj_pg["MIN"], 1))  # ESPN's minutes
        kessler = self.players["Walker Kessler"]
        self.assertLess(kessler.last_gp, draft.MIN_SAMPLE_GP)
        self.assertEqual(kessler.rate_source, "espn")  # 5 games is too small a sample
        self.assertIs(kessler.rate_line, kessler.proj_pg)

    def test_draft_costs(self):
        j = self.players["Nikola Jokic"]
        self.assertGreater(j.espn_value, 50)
        self.assertGreater(j.avg_paid, 50)
        self.assertEqual(j.espn_rank, 1)

    def test_no_last_season_falls_back_to_projection(self):
        h = self.players["Tyrese Haliburton"]
        self.assertEqual(h.last_gp, 0)
        self.assertTrue(h.base_is_projection)
        self.assertEqual(h.base_pg, h.proj_pg)
        self.assertEqual(h.default_exp_gp, h.proj_gp)

    def test_only_needed_stats_kept(self):
        keys = set(self.players["Cooper Flagg"].last_pg)
        self.assertTrue({"PTS", "FGA", "FG%", "GP", "TO"} <= keys)
        self.assertTrue(keys <= draft.KEPT_STATS)

    def test_cache_round_trip(self):
        league = draft.parse_league(fixture("espn_league_2027.json"), 1, 2027)
        players = list(self.players.values())
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "pool.json")
            draft.save_pool(path, league, players)
            loaded_league, loaded, _ = draft.load_pool(path)
        self.assertEqual(loaded_league.categories, league.categories)
        self.assertEqual([p.name for p in loaded], [p.name for p in players])
        self.assertEqual(loaded[0].last_pg, players[0].last_pg)

    def test_placeholder_cookies_are_not_sent(self):
        self.assertIsNone(draft._cookie_header("456", "{123}"))
        self.assertEqual(draft._cookie_header("abc", "{X}"), "espn_s2=abc; SWID={X}")


class BoardTest(unittest.TestCase):
    """DraftBoard end to end on the fixture, with ESPN mocked out."""

    def setUp(self):
        from gui.board import DraftBoard

        self.tmp = tempfile.TemporaryDirectory()
        settings = os.path.join(self.tmp.name, "settings.txt")
        with open(settings, "w") as f:
            json.dump({"leagueId": 1, "draftSeason": 2027, "ignoredStats": ["TO"], "ignorePlayers": 3}, f)
        league = draft.parse_league(fixture("espn_league_2027.json"), 1, 2027)
        players = [p for p in (draft.parse_player(e, 2027) for e in fixture("espn_players_2027.json")["players"]) if p]
        with mock.patch.object(draft, "fetch_league", return_value=league), mock.patch.object(draft, "fetch_pool", return_value=players):
            self.board = DraftBoard(settings, os.path.join(self.tmp.name, "pool.json"), os.path.join(self.tmp.name, "state.json"))
            self.board.load()
        self.ids = {p.name: p.id for p in players}

    def tearDown(self):
        self.tmp.cleanup()

    def test_snapshot_shape(self):
        snap = self.board.snapshot()
        self.assertEqual(snap["meta"]["seasonLabel"], "2026-27")
        self.assertEqual(snap["meta"]["statsLabel"], "2025-26")
        self.assertEqual(len(snap["meta"]["slots"]), 12)
        self.assertNotIn("TO", snap["meta"]["rated"])
        self.assertIn("TO", [c["cat"] for c in snap["team"]["categories"]])
        self.assertTrue(all("ours" in r and "edge" in r for r in snap["rows"]))

    def test_roster_flow_and_persistence(self):
        b, ids = self.board, self.ids
        self.assertIsNone(b.move(ids["Walker Kessler"], 1, price=15))
        self.assertEqual(b.move(ids["Cooper Flagg"], 1), "Cooper Flagg can't play C.")
        self.assertIsNone(b.pick(ids["Cooper Flagg"], "mine", 34))
        self.assertIsNone(b.pick(ids["Nikola Jokic"], "taken", 76))
        snap = b.snapshot()
        self.assertEqual(snap["me"]["spent"], 49)
        self.assertEqual(snap["me"]["count"], 2)
        self.assertEqual(snap["market"]["drafted"], 3)

        before = json.loads(json.dumps(b.state))
        b.clear_roster()
        self.assertEqual(b.snapshot()["me"]["count"], 0)
        b.replace_state(before)  # undo
        self.assertEqual(b.snapshot()["me"]["count"], 2)

        # Without a price, a player costs the average paid in ESPN auctions.
        white = ids["Derrick White"]
        self.assertIsNone(b.move(white, 0))
        avg = next(r["avg"] for r in b.snapshot()["rows"] if r["id"] == white)  # already league-scaled
        self.assertEqual(b.state["picks"][str(white)]["price"], max(1, round(avg)))
        b.pick(white, None)
        self.assertIsNone(b.pick(white, "taken"))
        self.assertEqual(b.state["picks"][str(white)]["price"], max(1, round(avg)))
        b.pick(white, None)

        # A new board reading the same files gets the same state back.
        from gui.board import DraftBoard

        again = DraftBoard(b.settings_path, b.pool_path, b.state_path)
        again.load()
        self.assertEqual(again.state["filled"], b.state["filled"])

    def test_market_prices_scaled_to_league_budget(self):
        b = self.board
        snap = b.snapshot()
        k = b.market_scale  # the snapshot shows it rounded
        self.assertAlmostEqual(snap["meta"]["marketScale"], k, places=3)
        top = sorted((p.avg_paid for p in b.players), reverse=True)[: b.shape.pool_size]
        self.assertAlmostEqual(sum(top) * k, b.shape.teams * b.shape.budget, places=6)
        jokic = next(r for r in snap["rows"] if r["name"] == "Nikola Jokic")
        self.assertAlmostEqual(jokic["avg"], round(jokic["avgRaw"] * k, 1), places=1)
        self.assertAlmostEqual(jokic["edge"], round(jokic["ours"] - jokic["avgRaw"] * k, 2), places=1)
        # Default prices use the scaled market price.
        self.assertIsNone(b.pick(self.ids["Nikola Jokic"], "taken"))
        self.assertEqual(b.state["picks"][str(self.ids["Nikola Jokic"])]["price"], round(jokic["avgRaw"] * k))

    def test_adjustments(self):
        b, kid = self.board, self.ids["Walker Kessler"]
        row = lambda: next(r for r in b.snapshot()["rows"] if r["id"] == kid)
        default_gp = row()["expGp"]
        before = row()["projPg"]
        b.adjust(kid, delta=5, expGp=62, note="healthy")
        r = row()
        self.assertEqual((r["delta"], r["expGp"], r["gpSet"], r["note"]), (5, 62, True, "healthy"))
        self.assertAlmostEqual(r["projPg"], before + 5, places=0)  # Δ is rating points
        b.adjust(kid, expGp=None)
        self.assertEqual(row()["expGp"], default_gp)
        b.adjust(kid, expMin=34.3)
        r = row()
        self.assertEqual((r["expMin"], r["minSet"]), (34.5, True))  # rounded to half minutes
        b.adjust(kid, expMin=None)
        self.assertFalse(row()["minSet"])
        b.reset_adjustments()
        r = row()
        self.assertEqual((r["delta"], r["note"]), (0, "healthy"))


class ServerTest(unittest.TestCase):
    """Static files are served only from gui/static."""

    @classmethod
    def setUpClass(cls):
        import threading

        from gui.server import serve

        cls.httpd = serve(mock.MagicMock(), port=0)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def status(self, path):
        import http.client

        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_address[1], timeout=5)
        try:
            conn.request("GET", path)  # sent as-is, no client-side normalization
            response = conn.getresponse()
            response.read()
            return response.status
        finally:
            conn.close()

    def test_serves_app(self):
        self.assertEqual(self.status("/"), 200)
        self.assertEqual(self.status("/static/app.js"), 200)

    def test_blocks_escapes(self):
        for path in ["/static/../board.py", "/static//etc/passwd", "/static/%2e%2e/board.py", "/static/../../settings.txt"]:
            self.assertEqual(self.status(path), 404, path)


if __name__ == "__main__":
    unittest.main()
