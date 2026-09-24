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
        ), mock.patch.object(draft, "fetch_schedule", return_value=schedule):
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
