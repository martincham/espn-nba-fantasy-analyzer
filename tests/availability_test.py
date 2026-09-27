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


if __name__ == "__main__":
    unittest.main()
