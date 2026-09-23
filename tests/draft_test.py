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
        self.assertEqual(k.default_exp_gp, k.proj_gp)  # ESPN's projected games
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
        self.assertEqual(snap["pool"]["taken"], 1)
        self.assertNotIn("price", b.state["picks"][str(ids["Nikola Jokic"])])  # taken players have no price

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
        self.assertIsNone(b.pick(self.ids["Nikola Jokic"], "mine"))
        self.assertEqual(b.state["picks"][str(self.ids["Nikola Jokic"])]["price"], round(jokic["avgRaw"] * k))

    def test_settings(self):
        b, ids = self.board, self.ids
        row = lambda name: next(r for r in b.snapshot()["rows"] if r["name"] == name)
        auto = b.market_scale
        # A custom price scale changes Avg paid and Edge; None goes back to automatic.
        b.update_settings(marketScale=2.0)
        jokic = row("Nikola Jokic")
        self.assertAlmostEqual(jokic["avg"], round(jokic["avgRaw"] * 2, 1), places=1)
        self.assertEqual(b.snapshot()["meta"]["autoMarketScale"], round(auto, 3))
        b.update_settings(marketScale=None)
        self.assertAlmostEqual(b.market_scale, auto)
        # Counting a category changes values; an empty list keeps the default.
        before = row("Nikola Jokic")["lastPg"]
        b.update_settings(rated=b.shape.categories)
        self.assertIn("TO", b.snapshot()["meta"]["rated"])
        self.assertNotEqual(row("Nikola Jokic")["lastPg"], before)
        b.update_settings(rated=[])
        self.assertNotIn("TO", b.snapshot()["meta"]["rated"])
        # Bench players not counted, and the expected-games blend.
        b.update_settings(ignorePlayers=5)
        self.assertEqual(b.snapshot()["meta"]["counted"], 7)
        # Settings persist with the draft state.
        from gui.board import DraftBoard

        again = DraftBoard(b.settings_path, b.pool_path, b.state_path)
        again.load()
        self.assertEqual(again.shape.ignore_players, 5)

    def test_replacement_and_core_settings(self):
        b = self.board
        self.assertEqual((b.shape.replacement, b.shape.core), (95, 7))  # defaults
        self.assertEqual(b.snapshot()["pool"]["size"], min(len(b.players), b.shape.teams * 7))
        b.update_settings(replacement=0, core=12)
        meta = b.snapshot()["meta"]
        self.assertEqual((meta["replacement"], meta["core"], meta["pricedSize"]), (0, 12, b.shape.teams * 12))
        b.update_settings(replacement=None, core=None)
        self.assertEqual((b.shape.replacement, b.shape.core), (95, 7))

    def test_old_expected_games_become_a_delta(self):
        b, kid = self.board, self.ids["Walker Kessler"]
        espn_gp = b.by_id[kid].default_exp_gp
        b.replace_state({"adjustments": {str(kid): {"expGp": espn_gp - 7}}, "picks": {}, "filled": []})
        self.assertEqual(b.state["adjustments"][str(kid)], {"gpDelta": -7})

    def test_fit_and_punt(self):
        b, ids = self.board, self.ids
        snap = b.snapshot()
        self.assertTrue(all(r["fit"] is not None for r in snap["rows"]))
        for r in snap["rows"]:
            self.assertAlmostEqual(r["fitEdge"], r["fitDollars"] - r["avg"], places=0)  # Fit $ − Avg paid
        self.assertEqual(snap["meta"]["punt"], [])  # never punts on its own
        # Punting a category takes it out of Fit only.
        before = {r["id"]: r["value"] for r in snap["rows"]}
        b.update_settings(punt=["BLK", "NOT_A_CAT"])
        snap = b.snapshot()
        self.assertEqual(snap["meta"]["punt"], ["BLK"])
        self.assertNotIn("BLK", snap["meta"]["fitCategories"])
        self.assertTrue(next(c for c in snap["team"]["categories"] if c["cat"] == "BLK")["punt"])
        self.assertEqual({r["id"]: r["value"] for r in snap["rows"]}, before)
        b.update_settings(punt=[])
        # With every category already "enough", nobody adds much.
        spread = lambda: (lambda f: max(f) - min(f))([r["fit"] for r in b.snapshot()["rows"]])
        normal = spread()
        b.update_settings(fitModel="fade")
        normal = spread()
        b.update_settings(fadeStart=80, fadeEnd=81)
        self.assertLess(spread(), normal / 2)

    def test_win_chances(self):
        b = self.board
        snap = b.snapshot()
        self.assertEqual(snap["meta"]["fitModel"], "wins")
        team = snap["team"]
        for c in team["categories"]:
            self.assertTrue(0 <= c["win"] <= 1)
            if abs(c["rating"] - 100) > 1:
                self.assertEqual(c["win"] > 0.5, c["rating"] > 100)
        self.assertAlmostEqual(team["expectedWins"], sum(c["win"] for c in team["categories"]), places=1)
        self.assertTrue(0 <= team["matchupWin"] <= 1)
        b.update_settings(fitModel="nonsense")
        self.assertEqual(b.fit_model, "wins")

    def test_reset_draft(self):
        b, ids = self.board, self.ids
        b.pick(ids["Nikola Jokic"], "taken")
        b.pick(ids["Cooper Flagg"], "mine", 30)
        b.reset_draft()
        snap = b.snapshot()
        self.assertEqual((snap["me"]["count"], snap["pool"]["taken"]), (0, 0))
        self.assertTrue(all(r["status"] is None for r in snap["rows"]))

    def test_adjustments(self):
        b, kid = self.board, self.ids["Walker Kessler"]
        row = lambda: next(r for r in b.snapshot()["rows"] if r["id"] == kid)
        espn_gp = row()["espnGp"]
        self.assertEqual(row()["expGp"], espn_gp)
        before = row()["projPg"]
        b.adjust(kid, delta=5, gpDelta=-10, note="healthy")
        r = row()
        self.assertEqual((r["delta"], r["gpDelta"], r["expGp"], r["note"]), (5, -10, espn_gp - 10, "healthy"))
        self.assertAlmostEqual(r["projPg"], before + 5, places=0)  # Δ is rating points
        # Value is per-game rating × games, with missed games filled at the replacement rating.
        rep = b.shape.replacement
        self.assertAlmostEqual(r["value"], (r["projPg"] * r["expGp"] + rep * (82 - r["expGp"])) / 82, places=0)
        b.adjust(kid, gpDelta=200)
        self.assertEqual(row()["expGp"], 82)  # capped at a full season
        b.adjust(kid, gpDelta=0)
        self.assertEqual(row()["expGp"], espn_gp)
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
