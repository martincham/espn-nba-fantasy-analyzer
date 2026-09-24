import unittest

from library import valuation as v


def line(pts=10.0, reb=5.0, ast=3.0, stl=1.0, blk=0.5, tpm=1.5, to=2.0, fgm=4.0, fga=9.0, ftm=2.0, fta=2.5):
    return v.with_percentages(
        {"PTS": pts, "REB": reb, "AST": ast, "STL": stl, "BLK": blk, "3PM": tpm, "TO": to,
         "FGM": fgm, "FGA": fga, "FTM": ftm, "FTA": fta}
    )


CATS = ["PTS", "REB", "AST", "STL", "BLK", "3PM", "FG%", "FT%"]


class Player:
    def __init__(self, pid, pg, gp, rank=None, exp_gp=None):
        self.id, self.base_pg, self.base_gp = pid, pg, gp
        self.espn_rank = rank or pid
        self.default_exp_gp = exp_gp if exp_gp is not None else gp


class RatingTest(unittest.TestCase):
    def test_average_player_rates_100(self):
        avg = line()
        self.assertAlmostEqual(v.rate(avg, avg, CATS), 100.0)

    def test_weighted_rating(self):
        avg = line()
        self.assertAlmostEqual(v.rate(avg, avg, CATS, v.CATEGORY_WEIGHTS), 100.0)  # average is still 100
        blocker = line(blk=1.5)  # 3x the average blocks, everything else average
        shooter = line(fgm=5.0)  # better FG% on the same attempts
        equal = v.rate(blocker, avg, CATS), v.rate(shooter, avg, CATS)
        weighted = v.rate(blocker, avg, CATS, v.CATEGORY_WEIGHTS), v.rate(shooter, avg, CATS, v.CATEGORY_WEIGHTS)
        self.assertLess(weighted[0], equal[0])  # blocks count less
        self.assertGreater(weighted[1], equal[1])  # FG% counts more
        self.assertAlmostEqual(v.rate(blocker, avg, ["BLK", "PTS"], {"BLK": 1.0}), v.rate(blocker, avg, ["BLK", "PTS"]))

    def test_percent_stat_neutral_at_average_percentage(self):
        avg = line()
        # Same FG% on double the attempts is still exactly average.
        self.assertAlmostEqual(v.rate_percent_stat(line(fgm=8, fga=18), avg, "FG%"), 1.0)

    def test_volume_amplifies_shooting(self):
        avg = line()
        good_low = v.rate_percent_stat(line(fgm=5, fga=9), avg, "FG%")
        good_high = v.rate_percent_stat(line(fgm=10, fga=18), avg, "FG%")
        self.assertGreater(good_high, good_low)
        self.assertGreater(good_low, 1.0)

    def test_negative_stat_inverts(self):
        avg = line()
        self.assertAlmostEqual(v.category_rating(line(to=1.0), avg, "TO"), 1.5)
        self.assertAlmostEqual(v.category_rating(line(to=3.0), avg, "TO"), 0.5)

    def test_zero_average_is_skipped_not_a_crash(self):
        avg = line(blk=0.0)
        self.assertNotIn("BLK", v.category_ratings(line(), avg, CATS))
        self.assertEqual(v.rate_percent_stat(line(), line(fga=0, fgm=0), "FG%"), 1.0)

    def test_rate_player_matches_cli_semantics(self):
        avg = dict(line(), GP=60.0)
        stats = dict(line(pts=20), GP=70.0)
        ignore = ["FGM", "FGA", "FTM", "FTA", "GP", "TO"]
        expected = v.rate(stats, avg, [s for s in avg if s not in ignore])
        self.assertAlmostEqual(v.rate_player(stats, avg, ignore), expected)
        self.assertEqual(v.rate_player(None, avg, ignore), 0)


class ScaleTest(unittest.TestCase):
    def test_delta_scales_volume_and_keeps_percentages(self):
        base = line()
        up = v.scale(base, 1.10)
        self.assertAlmostEqual(up["PTS"], 11.0)
        self.assertAlmostEqual(up["FGA"], 9.9)
        self.assertAlmostEqual(up["FG%"], base["FG%"])
        self.assertAlmostEqual(up["FT%"], base["FT%"])

    def test_delta_moves_counting_categories_proportionally(self):
        avg = line()
        before = v.category_ratings(line(blk=2.0), avg, CATS)
        after = v.category_ratings(v.scale(line(blk=2.0), 1.2), avg, CATS)
        for cat in ["PTS", "REB", "AST", "STL", "BLK", "3PM"]:
            self.assertAlmostEqual(after[cat] / before[cat], 1.2)

    def test_pool_averages(self):
        pg, season = v.pool_averages([(line(pts=10), 50), (line(pts=20), 50)])
        self.assertAlmostEqual(pg["PTS"], 15.0)
        self.assertAlmostEqual(season["PTS"], 750.0)


class DraftValueTest(unittest.TestCase):
    def setUp(self):
        self.shape = v.LeagueShape(teams=2, budget=100, roster_size=3, ignore_players=1,
                                   categories=CATS + ["TO"], rated=CATS)
        # 10 players, better players have lower ids
        self.players = [Player(i, line(pts=30 - 2 * i, reb=10 - 0.5 * i), 70, exp_gp=70) for i in range(1, 11)]
        self.baseline = v.compute_baseline(self.players, self.shape)

    def value(self, adjustments=None):
        return {r.id: r for r in v.value_players(self.players, self.baseline, self.shape, adjustments or {})}

    def test_values_sum_to_league_budget(self):
        rows = self.value()
        top = sorted(rows.values(), key=lambda r: r.rank)[: self.shape.pool_size]
        self.assertAlmostEqual(sum(r.ours for r in top), self.shape.teams * self.shape.budget)
        self.assertEqual(rows[1].rank, 1)
        self.assertAlmostEqual(min(r.ours for r in rows.values()), 1.0)

    def test_delta_is_rating_points(self):
        plain = self.value()
        boosted = self.value({5: v.Adjustment(delta=10)})
        self.assertAlmostEqual(boosted[5].proj_pg, plain[5].last_pg + 10, places=4)
        self.assertGreater(boosted[5].ours, plain[5].ours)
        self.assertEqual(boosted[5].last_pg, plain[5].last_pg)
        cut = self.value({5: v.Adjustment(delta=-15)})
        self.assertAlmostEqual(cut[5].proj_pg, plain[5].last_pg - 15, places=4)

    def test_delta_keeps_percentages_and_spreads_proportionally(self):
        boosted = self.value({5: v.Adjustment(delta=10)})[5].proj_stats
        base = self.players[4].base_pg
        ratio = boosted["PTS"] / base["PTS"]
        self.assertAlmostEqual(boosted["REB"] / base["REB"], ratio)
        self.assertAlmostEqual(boosted["FG%"], base["FG%"])

    def test_minutes_scale_production(self):
        for p in self.players:
            p.rate_line, p.rate_min, p.default_exp_min = dict(p.base_pg, MIN=30.0), 30.0, 30.0
        plain = self.value()
        more = self.value({5: v.Adjustment(exp_min=36)})[5]
        self.assertAlmostEqual(more.proj_stats["PTS"], self.players[4].base_pg["PTS"] * 1.2)
        self.assertAlmostEqual(more.proj_stats["FG%"], self.players[4].base_pg["FG%"])
        self.assertGreater(more.proj_pg, plain[5].proj_pg)
        self.assertEqual((more.exp_min, more.min_set), (36, True))
        # Δ is applied on top of the minutes change.
        both = self.value({5: v.Adjustment(exp_min=36, delta=10)})[5]
        self.assertAlmostEqual(both.proj_pg, more.proj_pg + 10, places=4)

    def test_scale_for_rating_bounds(self):
        avg = line()
        self.assertEqual(v.scale_for_rating(line(), avg, CATS, 0), 0.0)  # unreachably low clamps to 0
        s = v.scale_for_rating(line(), avg, CATS, 300)
        self.assertAlmostEqual(v.rate(v.scale(line(), s), avg, CATS), 300, places=3)

    def test_win_chances(self):
        self.assertAlmostEqual(v.win_chance(100, "PTS"), 0.5)
        self.assertGreater(v.win_chance(110, "PTS"), v.win_chance(110, "BLK"))  # PTS is steadier
        self.assertAlmostEqual(v.win_chance(120, "XYZ"), v.normal_cdf(20 / v.OVERALL_SPREAD))
        # Above 100 strength fades; below 100 it keeps full weight (no automatic punting).
        slope = lambda r: v.win_utility(r + 1, "PTS") - v.win_utility(r, "PTS")
        self.assertLess(slope(140), slope(100) / 4)
        self.assertAlmostEqual(slope(60), slope(99), places=6)

    def test_matchup_win(self):
        self.assertAlmostEqual(v.matchup_win([0.5] * 9), 0.5)
        self.assertAlmostEqual(v.matchup_win([1.0] * 5 + [0.0] * 4), 1.0)
        self.assertAlmostEqual(v.matchup_win([1.0] * 4 + [0.0] * 5), 0.0)
        self.assertAlmostEqual(v.matchup_win([0.5, 0.5]), 0.5)  # a 1-1 split counts half
        self.assertGreater(v.matchup_win([0.6] * 9), 0.6)  # small edges add up over 9 categories

    def test_fade(self):
        fade = v.Fade(110, 140)
        self.assertEqual(fade.useful(90), 90)
        self.assertEqual(fade.useful(110), 110)
        self.assertAlmostEqual(fade.useful(125), 110 + 15 - 15 * 15 / 60)  # each point above 110 counts less
        self.assertAlmostEqual(fade.useful(140), 125)
        self.assertAlmostEqual(fade.useful(500), 125)  # past the end, more is worth nothing

    def test_season_value(self):
        self.assertAlmostEqual(v.season_value(100, 82), 100)
        self.assertAlmostEqual(v.season_value(140, 41), 70)  # no replacement: rating × games / 82
        # Missed games are filled at the replacement rating.
        self.assertAlmostEqual(v.season_value(140, 41, 90), 115)
        self.assertAlmostEqual(v.season_value(90, 10, 90), 90)  # a replacement player is worth replacement
        self.assertAlmostEqual(v.season_value(100, 120), 100)  # games capped at a season

    def test_value_is_per_game_rating_times_games(self):
        plain = self.value()
        self.assertAlmostEqual(plain[3].value, plain[3].proj_pg * 70 / 82)
        hurt = self.value({3: v.Adjustment(gp_delta=-35)})
        self.assertEqual(hurt[3].exp_gp, 35)
        self.assertAlmostEqual(hurt[3].proj_pg, plain[3].proj_pg)
        self.assertAlmostEqual(hurt[3].value, plain[3].proj_pg * 35 / 82)
        self.assertLess(hurt[3].ours, plain[3].ours)
        self.assertEqual(self.value({3: v.Adjustment(gp_delta=50)})[3].exp_gp, 82)  # capped

    def test_replacement_softens_missed_games(self):
        plain_loss = self.value()[3].value - self.value({3: v.Adjustment(gp_delta=-35)})[3].value
        self.shape.replacement = 90.0
        filled_loss = self.value()[3].value - self.value({3: v.Adjustment(gp_delta=-35)})[3].value
        self.assertGreater(filled_loss, 0)
        self.assertLess(filled_loss, plain_loss / 2)

    def test_price_curve(self):
        self.shape.price_curve = list(v.PRICE_CURVE)
        rows = sorted(self.value().values(), key=lambda r: r.rank)
        top = rows[: self.shape.pool_size]
        self.assertAlmostEqual(sum(r.ours for r in top), self.shape.teams * self.shape.budget)
        prices = [r.ours for r in rows]
        self.assertEqual(prices, sorted(prices, reverse=True))  # never more for a lower value
        self.assertGreaterEqual(min(prices), 1.0)
        curve = v.league_curve(self.shape)
        self.assertAlmostEqual(rows[0].ours, curve[0])
        rate = v.pricing(list(self.value().values()), self.shape)
        self.assertAlmostEqual(rate.dollars(rows[0].value + 50), curve[0])  # above the best: the top price
        between = rate.dollars((rows[0].value + rows[1].value) / 2)
        self.assertTrue(rows[1].ours <= between <= rows[0].ours)

    def test_curve_dollars(self):
        values, curve = [130.0, 120.0, 110.0], [60.0, 30.0, 10.0]
        self.assertEqual(v.curve_dollars(140, values, curve), 60.0)
        self.assertAlmostEqual(v.curve_dollars(125, values, curve), 45.0)
        self.assertEqual(v.curve_dollars(100, values, curve), 1.0)  # past the curve: $1

    def test_core_players_share_the_money(self):
        self.shape.core = 2  # 2 teams × 2 core players are priced; the other 2 roster spots cost $1
        rows = sorted(self.value().values(), key=lambda r: r.rank)
        self.assertEqual([round(r.ours, 6) for r in rows[3:]], [1.0] * (len(rows) - 3))
        self.assertAlmostEqual(sum(r.ours for r in rows[: self.shape.pool_size]), self.shape.teams * self.shape.budget)
        self.shape.core = None
        spread = sorted(self.value().values(), key=lambda r: r.rank)
        self.assertGreater(rows[0].ours, spread[0].ours)  # stars get more when fewer players share

    def test_team_ratings(self):
        avg = line()
        self.assertAlmostEqual(v.team_ratings(avg, avg, CATS + ["TO"], ["TO"])["PTS"], 100.0)
        better = v.team_ratings(line(pts=12, to=1.0), avg, ["PTS", "TO", "FG%"], ["TO"])
        self.assertAlmostEqual(better["PTS"], 120.0)
        self.assertAlmostEqual(better["TO"], 150.0)  # fewer turnovers rate higher
        self.assertAlmostEqual(better["FG%"], 100.0)

    def test_simulate_league_ratings_follow_roster(self):
        rows = list(self.value().values())
        stars = v.simulate_league(rows, [1, 2, 3], [], self.shape)
        empty = v.simulate_league(rows, [], [], self.shape)
        self.assertEqual(set(stars.ratings), set(self.shape.categories))
        self.assertGreater(stars.ratings["PTS"], 100)
        self.assertGreater(stars.ratings["PTS"], empty.ratings["PTS"])

    def test_simulate_league_ranks(self):
        rows = list(self.value().values())
        best = [1, 2, 3]
        sim = v.simulate_league(rows, best, [], self.shape)
        self.assertEqual(sim.ranks["PTS"], 1)
        self.assertEqual(sim.overall, 1)
        worst = v.simulate_league(rows, [], [1, 2, 3, 4, 5, 6], self.shape)
        self.assertEqual(worst.filled, 0)
        self.assertGreaterEqual(worst.ranks["PTS"], 1)


class LineupTest(unittest.TestCase):
    """Daily lineups: games past the starting slots are lost; streamers fill open slots."""

    def setUp(self):
        # Two weeks. Team A plays days 1-4 of each week, team B days 5-7.
        self.sched = v.Schedule({"A": [1, 2, 3, 4, 8, 9, 10, 11], "B": [5, 6, 7, 12, 13, 14]})
        self.stats = line()

    def member(self, team, rating=100.0, count=1):
        return v.Member(v.scale(self.stats, v.GAMES_IN_SEASON), rating, team, count)

    def test_schedule_shares_and_weeks(self):
        self.assertEqual(self.sched.days, 14)
        self.assertEqual(self.sched.weeks, 2)
        self.assertEqual(self.sched.share, [0.5] * 14)  # one of two teams plays each day
        self.assertEqual(self.sched.games("A"), 8)
        self.assertEqual(self.sched.games(None), 7)  # average schedule

    def test_games_past_the_slots_are_benched(self):
        lineup = v.Lineup(counted=3, schedule=self.sched, starters=2)
        weights = dict((m.rating, w) for m, w in lineup.weights([self.member("A", 120), self.member("A", 110), self.member("A", 90)]))
        self.assertEqual(weights[120], 1.0)
        self.assertEqual(weights[110], 1.0)
        self.assertEqual(weights[90], 0.0)  # every game is on a full day
        spread_out = dict((m.rating, w) for m, w in lineup.weights([self.member("A", 120), self.member("A", 110), self.member("B", 90)]))
        self.assertEqual(spread_out[90], 1.0)

    def test_streamers_fill_open_slots_up_to_a_weekly_cap(self):
        streamer = self.member(None, 95, count=1)
        lineup = v.Lineup(counted=1, schedule=self.sched, starters=1, streamer=streamer)
        weights = lineup.weights([self.member("A", 120)])
        # Team A fills days 1-4 of each week; days 5-7 are open (6 slot-days).
        # One streaming spot plays like an average player: 3.5 games a week.
        self.assertAlmostEqual(weights[-1][1], 6 / 7)

    def test_without_a_schedule_the_best_count_in_full(self):
        lineup = v.Lineup(counted=2)
        self.assertEqual([w for _, w in lineup.weights([self.member("A", 120), self.member("A", 110, count=3)])], [1.0, 1.0])
        self.assertEqual(lineup.size([self.member("A", 120, count=5)]), 2)

    def test_fit_prefers_games_on_open_days(self):
        shape = v.LeagueShape(teams=2, roster_size=3, ignore_players=0, categories=CATS, rated=CATS, starters=2)
        players = [Player(1, line(pts=16), 82), Player(2, line(pts=16), 82), Player(3, line(pts=14), 82), Player(4, line(pts=14), 82)]
        for p, team in zip(players, ["A", "A", "A", "B"]):
            p.pro_team = team
        base = v.compute_baseline(players, shape)
        rows = v.value_players(players, base, shape, {})
        sim = v.simulate_league(rows, [1, 2], [], shape, self.sched)
        starts = {}
        fits = v.team_fit(rows, [1, 2], shape, sim, base, CATS, v.fit_by_wins, starts)
        # Same player; 3 plays on the days my two A players fill, 4 on open days.
        self.assertEqual(rows[2].value, rows[3].value)
        self.assertGreater(fits[4], fits[3])
        self.assertEqual(starts[3], 0.0)
        self.assertEqual(starts[4], 1.0)


if __name__ == "__main__":
    unittest.main()
