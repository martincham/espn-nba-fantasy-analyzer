import unittest
from datetime import date

from library import draft, playoffs
from library import valuation as v

OPENING = date(2026, 10, 20)  # a Tuesday


def season_days(skip=()):
    """Days 1-174 with games, less the days in `skip`."""
    return [d for d in range(1, 175) if d not in set(skip)]


DECEMBER = range(46, 54)  # Dec 4-11: NBA Cup games not scheduled yet
ALL_STAR = range(123, 129)  # Feb 19-24


class MatchupWeeksTest(unittest.TestCase):
    def test_first_week_ends_on_sunday_and_all_star_week_joins_the_next(self):
        weeks = playoffs.matchup_weeks(season_days(list(DECEMBER) + list(ALL_STAR)), OPENING, 24)
        self.assertEqual(len(weeks), 24)
        self.assertEqual(weeks[0], (1, 6))  # Tue Oct 20 to Sun Oct 25
        self.assertEqual(weeks[1], (7, 13))  # then Monday to Sunday
        joined = [w for w in weeks if w[1] - w[0] != 6 and w != weeks[0]]
        self.assertEqual(joined, [(119, 132)])  # Feb 15-28: the week of the break and the next
        self.assertEqual(weeks[-1], (168, 174))

    def test_without_a_count_or_opening(self):
        self.assertEqual(len(playoffs.matchup_weeks(season_days(ALL_STAR), OPENING)), 25)
        self.assertEqual(playoffs.matchup_weeks(range(1, 15), None), [(1, 7), (8, 14)])


class CalendarTest(unittest.TestCase):
    def setUp(self):
        self.team_days = {"AAA": season_days(ALL_STAR)[::2], "BBB": season_days(ALL_STAR)[1::2], "CCC": season_days(ALL_STAR)}

    def test_rounds_from_league_settings(self):
        periods = {p: [p] for p in range(1, 21)}
        periods.update({21: [21, 22], 22: [23, 24]})
        cal = playoffs.calendar(self.team_days, OPENING, 20, periods, 4)
        self.assertTrue(cal.known)
        self.assertEqual([(r.period, r.weeks) for r in cal.rounds], [(21, [21, 22]), (22, [23, 24])])
        self.assertEqual((cal.date(cal.rounds[0].first), cal.date(cal.rounds[-1].last)), (date(2027, 3, 15), date(2027, 4, 11)))
        self.assertEqual(len(cal.playoff_days), 28)
        self.assertEqual(cal.week_of()[1], 0)
        self.assertEqual(cal.week_of()[174], 23)

    def test_unknown_settings_assume_the_last_four_weeks(self):
        cal = playoffs.calendar(self.team_days, OPENING)
        self.assertFalse(cal.known)
        self.assertEqual(cal.playoff_weeks, [22, 23, 24, 25])  # no merge without the league's week count

    def test_team_games_and_light_nights(self):
        cal = playoffs.calendar(self.team_days, OPENING, 20, {21: [21, 22], 22: [23, 24]}, 4)
        teams = {t.team: t for t in playoffs.team_playoffs(self.team_days, cal)}
        self.assertEqual(teams["CCC"].weeks, [7, 7, 7, 7])
        self.assertEqual(teams["CCC"].games, 28)
        self.assertEqual(teams["AAA"].games + teams["BBB"].games, 28)
        self.assertEqual(teams["CCC"].light, 0)  # two of three teams play every night: never light
        self.assertEqual(playoffs.team_playoffs(self.team_days, cal)[0].team, "CCC")  # most games first


class FocusTest(unittest.TestCase):
    """Schedule.focus: count only some days, but keep each player's season games."""

    def setUp(self):
        # Two teams, 20 days, weeks of 5. A plays days 0-9 and 15-19; B plays days 10-19.
        self.sched = v.Schedule({"A": list(range(10)) + list(range(15, 20)), "B": list(range(10, 20))},
                                {d: d // 5 for d in range(20)})
        self.stats = {"PTS": 100.0}

    def weights(self, sched, starters=2):
        lineup = v.Lineup(counted=2, schedule=sched, starters=starters)
        members = [v.Member(self.stats, 110.0, "A"), v.Member(self.stats, 100.0, "B")]
        return [round(w, 4) for _, w in lineup.weights(members)]

    def test_games_stay_the_seasons(self):
        late = self.sched.focus(range(15, 20))
        self.assertEqual(late.games("A"), 15)
        self.assertEqual(late.games("B"), 10)
        self.assertEqual(late.average_games, self.sched.average_games)
        # A starts his 5 games of the last week out of 15; B his 5 out of 10.
        self.assertEqual(self.weights(late), [round(5 / 15, 4), 0.5])

    def test_repeat_and_rest(self):
        late = range(15, 20)
        self.assertEqual(self.weights(self.sched.focus(late, repeat=3)), [1.0, 1.5])
        both = self.sched.focus(late, repeat=2, rest=True)
        self.assertEqual(both.days, 25)  # every day once, and the last week again
        self.assertEqual(self.weights(both), [round(20 / 15, 4), 1.5])

    def test_a_team_without_games_there_counts_nothing(self):
        early = self.sched.focus(range(5))
        self.assertEqual(early.presence("B"), [])
        self.assertEqual(self.weights(early), [round(5 / 15, 4), 0.0])


class OpeningTest(unittest.TestCase):
    def test_opening_from_game_dates(self):
        # Day 2 is Oct 21: a 7:30 pm Eastern game is past midnight UTC.
        game = {"date": 1792629000000, "scoringPeriodId": 2}  # 2026-10-22 00:30 UTC
        data = {"settings": {"proTeams": [{"id": 1, "proGamesByScoringPeriod": {"2": [game]}}]}}
        self.assertEqual(draft.parse_opening(data), "2026-10-20")
        self.assertEqual(draft.parse_opening({"settings": {"proTeams": []}}), "")


if __name__ == "__main__":
    unittest.main()
