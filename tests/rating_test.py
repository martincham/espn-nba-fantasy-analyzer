import library.rating as rating
from espn_api.basketball import League
from unittest import TestCase
from unittest import main


class RatingTest(TestCase):
    def setupTests(self):
        self.league = League(league_id=1640258594)

    def testCalculateLeagueAverages(self):
        totalAverages = rating.calculateLeagueAverages(
            league=self.league, timeframe="2024_total", totalOrAvg="total"
        )
        avgAverages = rating.calculateLeagueAverages(
            league=self.league, timeframe="2024_last_30", totalOrAvg="avg"
        )

    def testRatePlayer(self):
        # wemby = league.
        self.assertEqual(3, 3)

    def testAverageStats(self):
        self.assertEqual(3, 3)

    def testMergeStats(self):
        self.assertEqual(3, 3)

    def testRosterRater(self):
        self.assertEqual(3, 3)

    def testAverageRatingTimeFrame(self):
        self.assertEqual(3, 3)

    def testTotalRatingTimeframe(self):
        self.assertEqual(3, 3)

    def testLeagueTeamRatings(self):
        self.assertEqual(3, 3)

    def testLeagueFreeAgentRatings(self):
        self.assertEqual(3, 3)

    def testRateFreeAgents(self):
        self.assertEqual(3, 3)

    def testCompositeRateTeamCats(self):
        self.assertEqual(3, 3)

    def testCategoryRateTeams(self):
        self.assertEqual(3, 3)

    def testCategoryRateFreeAgents(self):
        self.assertEqual(3, 3)

    def testCategoryRatePlayerList(self):
        self.assertEqual(3, 3)

    def testCreatePlayerMatrix(self):
        self.assertEqual(3, 3)

    def testRemainingRateTeams(self):
        self.assertEqual(3, 3)

    def testRemainingRateFreeAgents(self):
        self.assertEqual(3, 3)


if __name__ == "__main__":
    main()
