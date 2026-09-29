import json
import os
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from library import draft, planner
from library import valuation as v

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")
OPENING = "2026-10-20"  # opening night of the fixture's schedule (day 1)


def fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


class KnapsackTest(unittest.TestCase):
    def test_most_value_for_the_money(self):
        rows = [SimpleNamespace(id=i, value=val) for i, val in [(1, 200), (2, 130), (3, 125), (4, 120), (5, 96)]]
        costs = {1: 60, 2: 30, 3: 25, 4: 20, 5: 1}
        # $80 for 3: three mid-priced players; $61 for 2: the star plus a $1 filler beats two mid-priced ones.
        self.assertEqual(sorted(planner._knapsack(rows, costs, 3, 80, 95.0)), [2, 3, 4])
        self.assertEqual(sorted(planner._knapsack(rows, costs, 2, 61, 95.0)), [1, 5])
        self.assertEqual(planner._knapsack(rows, costs, 3, 2, 95.0), [])  # can't afford 3 players


class BoardPlanTest(unittest.TestCase):
    def setUp(self):
        from gui.board import DraftBoard

        self.tmp = tempfile.TemporaryDirectory()
        settings = os.path.join(self.tmp.name, "settings.txt")
        with open(settings, "w") as f:
            json.dump({"leagueId": 1, "draftSeason": 2027, "ignorePlayers": 3}, f)
        league = draft.parse_league(fixture("espn_league_2027.json"), 1, 2027)
        players = [p for p in (draft.parse_player(e, 2027) for e in fixture("espn_players_2027.json")["players"]) if p]
        schedule = draft.parse_schedule(fixture("espn_schedule_2027.json"))
        with mock.patch.object(draft, "fetch_league", return_value=league), mock.patch.object(
            draft, "fetch_pool", return_value=players
        ), mock.patch.object(draft, "fetch_schedule", return_value=(schedule, OPENING)), mock.patch.object(
            draft, "fetch_past", return_value={}
        ), mock.patch.object(draft, "fetch_birth_dates", return_value={3112335: "1995-02-19"}):
            self.board = DraftBoard(settings, os.path.join(self.tmp.name, "pool.json"), os.path.join(self.tmp.name, "state.json"))
            self.board.load()
        self.players = players

    def tearDown(self):
        self.tmp.cleanup()

    def wait(self):
        for _ in range(600):
            plan = self.board.snapshot()["plan"]
            if plan["status"] != "building":
                return plan
            time.sleep(0.05)
        self.fail("the plan never finished")

    def test_plan_respects_roster_budget_and_taken(self):
        b = self.board
        ranked = sorted(self.players, key=lambda p: -p.avg_paid)
        for p in ranked[12:]:  # the fixture has only the top 30, so make a cheap tier to fill a roster
            b.adjust(p.id, cost=4)
        mine, taken = ranked[3], ranked[0]
        b.pick(mine.id, "mine", 40)
        b.pick(taken.id, "taken", None)
        self.assertIsNone(b.snapshot()["plan"])
        b.build_plan()
        plan = self.wait()
        self.assertEqual(plan["status"], "ready")
        self.assertFalse(plan["stale"])
        r = plan["result"]
        best = r["best"]
        self.assertEqual(r["mine"], [mine.id])
        self.assertEqual(len(best["ids"]) + 1 + r["streamers"], b.shape.roster_size)
        self.assertEqual(len(best["ids"]), b.shape.counted - 1)  # the rest are $1 streaming spots
        self.assertNotIn(taken.id, best["ids"])
        self.assertNotIn(mine.id, best["ids"])
        self.assertLessEqual(best["cost"] + r["streamers"], r["budgetLeft"])
        self.assertEqual(r["budgetLeft"], b.shape.budget - 40)
        self.assertTrue(0 < best["wins"] <= len(b.shape.categories))
        self.assertEqual(set(best["chances"]), set(b.shape.categories))
        # Every alternative fits the budget in that player's place.
        for out_id, options in r["swaps"].items():
            for s in options:
                self.assertNotIn(s["id"], best["ids"])
                self.assertLessEqual(best["cost"] + s["costChange"] + r["streamers"], r["budgetLeft"])
        for build in r["builds"]:
            self.assertGreaterEqual(len(build["adds"]), 3)
            self.assertEqual(len(build["adds"]), len(build["drops"]))
        # Any change to the draft makes it stale.
        b.pick(ranked[1].id, "taken", None)
        self.assertTrue(b.snapshot()["plan"]["stale"])

    def test_left_out_players_are_never_recommended(self):
        b = self.board
        for p in sorted(self.players, key=lambda p: -p.avg_paid)[12:]:
            b.adjust(p.id, cost=4)
        b.build_plan()
        first = self.wait()["result"]["best"]["ids"]
        out = first[:2]
        for pid in out:
            b.set_avoid(pid)
        self.assertTrue(b.snapshot()["plan"]["stale"])
        b.build_plan()
        r = self.wait()["result"]
        everywhere = set(r["best"]["ids"]) | {s["id"] for opts in r["swaps"].values() for s in opts}
        everywhere |= {i for build in r["builds"] for i in build["ids"]}
        self.assertFalse(everywhere & set(out))
        # Saved with the draft, and undone one at a time.
        from gui.board import DraftBoard

        again = DraftBoard(b.settings_path, b.pool_path, b.state_path)
        again.load()
        self.assertEqual(again.state["avoid"], sorted(out))
        b.set_avoid(out[0], False)
        self.assertEqual(b.state["avoid"], [out[1]])

    def test_too_expensive_buys_what_it_can(self):
        b = self.board  # the fixture's cheapest player costs $13: nine won't fit in $200
        b.build_plan()
        r = self.wait()["result"]
        self.assertLess(len(r["best"]["ids"]), b.shape.counted)
        self.assertGreater(len(r["best"]["ids"]), 0)
        self.assertEqual(len(r["best"]["ids"]) + r["streamers"], b.shape.roster_size)
        self.assertLessEqual(r["best"]["cost"] + r["streamers"], b.shape.budget)

    def test_floor_objective(self):
        b = self.board
        for p in sorted(self.players, key=lambda p: -p.avg_paid)[12:]:
            b.adjust(p.id, cost=4)
        results = {}
        for objective in ("wins", "floor", "floor20"):
            b.update_settings(planObjective=objective)
            b.build_plan()
            results[objective] = self.wait()["result"]
            self.assertEqual(results[objective]["objective"], objective)
        for r in results.values():
            best = r["best"]
            self.assertGreater(best["winsSd"], 0)
            self.assertLessEqual(best["floor20"], best["floor10"])  # a 1-in-20 season is worse than a 1-in-10 one
            self.assertLess(best["floor10"], best["wins"] + 0.5)
        # Aiming for a floor doesn't give a worse floor, and aiming for wins doesn't give fewer wins.
        self.assertGreaterEqual(results["floor"]["best"]["floor10"], results["wins"]["best"]["floor10"] - 0.02)
        self.assertGreaterEqual(results["floor20"]["best"]["floor20"], results["wins"]["best"]["floor20"] - 0.02)
        self.assertGreaterEqual(results["wins"]["best"]["wins"], results["floor"]["best"]["wins"] - 0.02)
        b.update_settings(planObjective="bogus")
        self.assertEqual(b.snapshot()["meta"]["planObjective"], "wins")

    def test_switch_in_an_alternative_then_save_to_team(self):
        b = self.board
        for p in sorted(self.players, key=lambda p: -p.avg_paid)[12:]:
            b.adjust(p.id, cost=4)
        b.build_plan()
        r = self.wait()["result"]
        self.assertIsNone(r["switched"])
        out_id = r["best"]["ids"][0]
        alt = r["swaps"][str(out_id)][0]
        started = time.time()
        self.assertIsNone(b.switch_plan(out_id, alt["id"]))
        self.assertLess(time.time() - started, 5)
        s = b.snapshot()["plan"]["result"]
        self.assertIn(alt["id"], s["best"]["ids"])
        self.assertNotIn(out_id, s["best"]["ids"])
        self.assertEqual(s["best"]["cost"], r["best"]["cost"] + alt["costChange"])
        self.assertEqual(s["switched"]["in"], [alt["id"]])
        self.assertEqual(s["switched"]["out"], [out_id])
        self.assertEqual(s["switched"]["wins"], r["best"]["wins"])
        self.assertIsNotNone(s["best"]["floor10"])
        self.assertIn(str(alt["id"]), s["swaps"])  # the new player has alternatives of his own
        for build in s["builds"]:
            self.assertNotEqual(set(build["ids"]), set(s["best"]["ids"]))
        # Players already in the plan, drafted, or unaffordable can't be switched in.
        self.assertIsNotNone(b.switch_plan(s["best"]["ids"][1], s["best"]["ids"][2]))
        self.assertIsNotNone(b.switch_plan(out_id, alt["id"]))
        # Switching back is the recommendation again.
        self.assertIsNone(b.switch_plan(alt["id"], out_id))
        self.assertIsNone(b.snapshot()["plan"]["result"]["switched"])
        b.switch_plan(out_id, alt["id"])
        self.assertIsNone(b.restore_plan())
        self.assertEqual(b.snapshot()["plan"]["result"], r)
        # Saving puts the planned players on my team at their planned prices.
        b.switch_plan(out_id, alt["id"])
        self.assertIsNone(b.save_plan())
        planned = b.snapshot()["plan"]["result"]
        for pid in planned["best"]["ids"]:
            self.assertEqual(b.state["picks"][str(pid)], {"status": "mine", "price": planned["costs"][str(pid)]})
            self.assertIn(pid, b.state["filled"])
        self.assertTrue(b.snapshot()["plan"]["stale"])
        self.assertIsNotNone(b.save_plan())  # they're drafted now

    def test_use_another_build(self):
        b = self.board
        for p in sorted(self.players, key=lambda p: -p.avg_paid)[12:]:
            b.adjust(p.id, cost=4)
        b.build_plan()
        self.wait()
        # The fixture is too small for the search to find distinct builds: give it one, from two alternatives.
        inputs, recommended, _ = b._plan_work
        ids = list(recommended.best.ids)
        for pos in (0, 1):
            ids[pos] = next(s.in_id for s in recommended.swaps[ids[pos]] if s.in_id not in ids)
        recommended.builds = [planner.score_team(**inputs, ids=ids).best]
        b.plan["result"] = b._plan_payload(recommended, inputs["costs"])
        r = b.snapshot()["plan"]["result"]
        other = r["builds"][0]
        self.assertEqual(other["n"], 0)
        self.assertIsNone(b.use_plan(other["ids"]))
        s = b.snapshot()["plan"]["result"]
        self.assertEqual(set(s["best"]["ids"]), set(other["ids"]))
        self.assertEqual(s["best"]["cost"], other["cost"])
        self.assertEqual(s["switched"]["build"], other["n"])
        self.assertEqual(s["switched"]["wins"], r["best"]["wins"])
        self.assertTrue(all(str(i) in s["swaps"] for i in other["ids"]))  # alternatives for every spot
        self.assertNotIn(other["n"], [x["n"] for x in s["builds"]])  # it's the plan now, not another build
        # Undo goes back to what was shown before; players already drafted or over budget are refused.
        self.assertIsNone(b.use_plan(r["best"]["ids"]))
        self.assertEqual(b.snapshot()["plan"]["result"], r)
        self.assertIsNotNone(b.use_plan([self.players[0].id] * 3 + [123456789]))
        self.assertIsNotNone(b.use_plan([p.id for p in sorted(self.players, key=lambda p: -p.avg_paid)[:9]]))  # over budget
        # A build in use can go on My Team.
        self.assertIsNone(b.use_plan(other["ids"]))
        self.assertIsNone(b.save_plan())
        for pid in other["ids"]:
            self.assertEqual(b.state["picks"][str(pid)]["status"], "mine")

    def test_playoffs_tab(self):
        b = self.board
        ranked = sorted(self.players, key=lambda p: -p.avg_paid)
        mine = ranked[2]
        b.pick(mine.id, "mine", 40)
        b.pick(ranked[0].id, "taken", None)
        po = b.snapshot()["playoffs"]
        self.assertTrue(po["known"])
        self.assertEqual([r["weeks"] for r in po["rounds"]], [[21, 22], [23, 24]])
        self.assertEqual((po["rounds"][0]["first"], po["rounds"][-1]["last"]), ("2027-03-15", "2027-04-11"))
        self.assertEqual([len(w["days"]) for w in po["weeks"]], [7, 7, 7, 7])
        self.assertEqual(len(po["nba"]), 30)
        self.assertEqual(po["nba"][0]["games"], max(t["games"] for t in po["nba"]))
        me = po["team"]["players"]
        self.assertEqual([p["id"] for p in me], [mine.id])
        self.assertEqual(me[0]["games"], next(t["games"] for t in po["nba"] if t["team"] == mine.pro_team))
        self.assertLessEqual(me[0]["starts"], me[0]["games"])
        ids = {p["id"] for p in po["players"]}
        self.assertNotIn(mine.id, ids)
        self.assertNotIn(ranked[0].id, ids)  # taken
        self.assertTrue(all(p["pfit"] is not None for p in po["players"]))
        self.assertEqual(b.snapshot()["meta"]["playoffWeeks"], [21, 22, 23, 24])

    def test_plan_for_the_playoffs(self):
        b = self.board
        for p in sorted(self.players, key=lambda p: -p.avg_paid)[12:]:
            b.adjust(p.id, cost=4)
        b.build_plan()
        season = self.wait()
        self.assertEqual(season["focus"], "season")
        b.update_settings(planFocus="playoffs")
        self.assertTrue(b.snapshot()["plan"]["stale"])
        b.build_plan()
        plan = self.wait()
        self.assertEqual((plan["status"], plan["focus"]), ("ready", "playoffs"))
        self.assertTrue(plan["result"]["best"]["ids"])
        self.assertIs(b.focus_schedules["season"], b.schedule)
        self.assertEqual(b.focus_schedules["playoffs"].days, len(set(b.calendar.playoff_days) & set(b.schedule.day_ids)))
        b.update_settings(planFocus="bogus")
        self.assertEqual(b.snapshot()["meta"]["planFocus"], "season")

    def test_old_cache_gets_the_playoff_calendar(self):
        from gui.board import DraftBoard

        b = self.board
        league = draft.LeagueInfo(**{**b.league.__dict__, "matchup_weeks": None, "opening": None})
        draft.save_pool(b.pool_path, league, b.players, b.team_days, b.fetched_at, True)
        with mock.patch.object(draft, "fetch_league", return_value=b.league) as fetch_league, mock.patch.object(
            draft, "fetch_schedule", return_value=(b.team_days, OPENING)
        ) as fetch_schedule, mock.patch.object(draft, "fetch_past", return_value={}):
            again = DraftBoard(b.settings_path, b.pool_path, b.state_path)
            again.load()
            DraftBoard(b.settings_path, b.pool_path, b.state_path).load()  # now cached
        fetch_league.assert_called_once()
        fetch_schedule.assert_called_once()
        self.assertEqual(again.league.opening, OPENING)
        self.assertEqual(again.calendar.playoff_weeks, [21, 22, 23, 24])

    def test_full_roster_has_nothing_to_plan(self):
        b = self.board
        for p in sorted(self.players, key=lambda p: -p.avg_paid)[: b.shape.roster_size]:
            b.pick(p.id, "mine", 1)
        b.build_plan()
        plan = self.wait()
        self.assertEqual(plan["status"], "ready")
        self.assertIsNone(plan["result"])


if __name__ == "__main__":
    unittest.main()
