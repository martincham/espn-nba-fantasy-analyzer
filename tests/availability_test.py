import unittest

from library import availability as av
from library import valuation as v


class GamesRangeTest(unittest.TestCase):
    def test_distribution_sums_to_one(self):
        for proj in (20, 55, 70, 82):
            self.assertAlmostEqual(sum(av.games_range(proj).pmf), 1.0, places=9)

    def test_quantiles_are_ordered(self):
        g = av.games_range(72)
        p10, p50, p90 = av.quantiles(g)
        self.assertLess(p10, p50)
        self.assertLess(p50, p90)
        self.assertLessEqual(p90, av.FULL)

    def test_higher_projection_shifts_up_and_cuts_risk(self):
        low, high = av.games_range(60), av.games_range(78)
        self.assertGreater(high.mean, low.mean)
        self.assertLess(high.p_half, low.p_half)

    def test_centered_below_espn(self):
        # ESPN projections run high: the fitted mean sits below a typical projection
        self.assertLess(av.games_range(72).mean, 72)

    def test_out_only_removes_games_from_the_top(self):
        g = av.games_range(72, out=20)
        self.assertAlmostEqual(sum(g.pmf), 1.0, places=9)
        self.assertEqual(sum(g.pmf[av.FULL - 20 + 1:]), 0.0)
        self.assertLess(g.mean, av.games_range(72).mean)

    def test_shift_moves_the_whole_range(self):
        base, down = av.games_range(70), av.games_range(70, shift=-10)
        self.assertAlmostEqual(sum(down.pmf), 1.0, places=9)
        self.assertEqual(av.quantiles(down, (0.5,))[0], av.quantiles(base, (0.5,))[0] - 10)
        self.assertEqual(down.projected, 60)
        # a shift is your judgment, not ESPN's signal: it doesn't raise the chance of a long injury like a low projection does
        self.assertLess(down.p_half, av.games_range(60).p_half)

    def test_projection_is_clamped(self):
        self.assertEqual(av.games_range(120).pmf, av.games_range(82).pmf)
        self.assertEqual(av.games_range(-5).pmf, av.games_range(0).pmf)


class ValueRangeTest(unittest.TestCase):
    def test_value_quantiles_are_ordered_and_wider_than_games_alone(self):
        g = av.games_range(72)
        full = av.value_range(130, g, 95)
        still = av.value_range(130, g, 95, av.Params(rating_var=(1e-6, 0.0), rating_slope=0.0, rating_bias=0.0))
        lo, mid, hi = av.quantiles(full)
        self.assertLess(lo, mid)
        self.assertLess(mid, hi)
        s_lo, _, s_hi = av.quantiles(still)
        self.assertGreater(hi - lo, s_hi - s_lo)

    def test_certain_games_and_rating_gives_season_value(self):
        exact = av.GamesRange(pmf=[0.0] * 60 + [1.0] + [0.0] * 22, projected=60)
        still = av.Params(rating_var=(1e-9, 0.0), rating_slope=0.0, rating_bias=0.0)
        self.assertAlmostEqual(av.value_range(120, exact, 95, still).mean, v.season_value(120, 60, 95), places=6)

    def test_zero_games_is_replacement(self):
        none = av.GamesRange(pmf=[1.0] + [0.0] * 82, projected=0)
        dist = av.value_range(140, none, 95)
        self.assertAlmostEqual(dist.quantile(0.1), 95, places=3)
        self.assertAlmostEqual(dist.quantile(0.9), 95, places=3)

    def test_below_replacement_player_gains_from_missed_games(self):
        # a 90-rated player is worth more the fewer games he plays (95 fills them)
        few = av.GamesRange(pmf=[0.0] * 20 + [1.0] + [0.0] * 62, projected=20)
        many = av.GamesRange(pmf=[0.0] * 80 + [1.0] + [0.0] * 2, projected=80)
        still = av.Params(rating_var=(1e-9, 0.0), rating_slope=0.0, rating_bias=0.0)
        self.assertGreater(av.value_range(90, few, 95, still).mean, av.value_range(90, many, 95, still).mean)


class LeagueCase(unittest.TestCase):
    """A small league shared by the team-level tests."""

    def setUp(self):
        from tests.valuation_test import CATS, Player, line
        self.shape = v.LeagueShape(teams=2, budget=100, roster_size=3, ignore_players=1,
                                   categories=CATS + ["TO"], rated=CATS, replacement=95)
        self.players = [Player(i, line(pts=30 - 2 * i, reb=10 - 0.5 * i), 70, exp_gp=exp)
                        for i, exp in zip(range(1, 11), (78, 50, 72, 72, 72, 72, 72, 72, 72, 72))]
        self.base = v.compute_baseline(self.players, self.shape)
        self.rows = v.value_players(self.players, self.base, self.shape, {})

    def team(self, mine):
        mean_rows = [av.mean_row(r, self.base.per_game, self.shape) for r in self.rows]
        sim = v.simulate_league(mean_rows, mine, [], self.shape)
        by_id = {r.id: r for r in self.rows}
        return av.team_range([by_id[i] for i in mine], sim, self.base.per_game, self.shape, draws=200)


class TeamRangeTest(LeagueCase):
    def test_quantiles_are_ordered_and_stable(self):
        a, b = self.team([1, 3]), self.team([1, 3])
        self.assertEqual(a.wins, b.wins)  # fixed seed
        self.assertLessEqual(a.quantile(0.1), a.quantile(0.5))
        self.assertLessEqual(a.quantile(0.5), a.quantile(0.9))
        self.assertLess(a.quantile(0.1), a.quantile(0.9))

    def test_better_roster_ranks_higher(self):
        self.assertGreater(self.team([1, 3]).quantile(0.5), self.team([9, 10]).quantile(0.5))

    def test_half_season_count_adds_up(self):
        t = self.team([1, 2])
        by_id = {r.id: r for r in self.rows}
        expected = sum(av.games_range(av.center(by_id[i])[0], shift=av.center(by_id[i])[1]).p_half for i in (1, 2))
        self.assertAlmostEqual(t.half_season, expected, places=9)

    def test_mean_row_lowers_games_and_keeps_identity(self):
        r = self.rows[0]
        m = av.mean_row(r, self.base.per_game, self.shape)
        self.assertEqual(m.id, r.id)
        self.assertLess(m.exp_gp, r.exp_gp)


class PlusMinusTest(LeagueCase):
    def test_games_sd_is_wider_for_low_projections(self):
        self.assertGreater(av.games_sd(55), av.games_sd(76))
        self.assertGreater(av.games_sd(76), 0)

    def test_value_at_replacement_has_no_spread(self):
        r = self.rows[0]
        self.assertEqual(av.plus_minus(95.0, 95.0, r), 0.0)
        self.assertAlmostEqual(av.plus_minus(r.value, 95.0, r), abs(r.value - 95) * av.row_games_sd(r) / r.exp_gp)

    def test_team_spread(self):
        sim = v.simulate_league(self.rows, [1, 3], [], self.shape)
        by_id = {r.id: r for r in self.rows}
        spread = av.team_spread([by_id[1], by_id[3]], sim, self.shape)
        self.assertEqual(set(spread.categories), set(self.shape.categories))
        self.assertTrue(all(x >= 0 for x in spread.categories.values()))
        self.assertGreater(spread.categories["PTS"], 0)
        self.assertGreater(spread.wins, 0)
        self.assertGreaterEqual(spread.winning, 0)
        self.assertLessEqual(spread.winning, len(self.shape.categories) / 2)

    def test_empty_roster_has_no_spread(self):
        spread = av.team_spread([], v.simulate_league(self.rows, [], [], self.shape), self.shape)
        self.assertTrue(all(x == 0 for x in spread.categories.values()))
        self.assertEqual((spread.wins, spread.winning), (0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
