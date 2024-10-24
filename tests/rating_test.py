from library import rating
from espn_api.basketball import League
import unittest



class TestRating(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        self.league = League(league_id=1640258594, year=2024)

    def testCalculateLeagueAverages(self):
        league = self.league
        tTotalAverages = {
            "PTS": 1086.27950310559,
            "BLK": 43.46583850931677,
            "STL": 62.975155279503106,
            "AST": 257.7391304347826,
            "REB": 368.87577639751555,
            "3PTM": 114.14285714285714,
            "TO": 119.64596273291926,
            "FTM": 173.1801242236025,
            "FTA": 216.65217391304347,
            "FGM": 399.4782608695652,
            "FGA": 827.2857142857143,
            "GP": 67.15527950310559,
        }
        tAvgAverages = {
            "PTS": 16.51620947630923,
            "BLK": 0.6508728179551122,
            "STL": 1.0399002493765586,
            "AST": 4.017456359102244,
            "REB": 5.800498753117207,
            "3PTM": 1.7905236907730673,
            "TO": 1.8927680798004987,
            "FTM": 2.482294264339152,
            "FTA": 3.0887780548628427,
            "FGM": 6.121695760598504,
            "FGA": 12.693765586034912,
            "GP": 1.0,
        }
        totalAverages = rating.calculateLeagueAverages(
            league=league, timeframe="2024_total", totalOrAvg="total"
        )
        avgAverages = rating.calculateLeagueAverages(
            league=league, timeframe="2024_last_30", totalOrAvg="avg"
        )

        self.assertEqual(totalAverages, tTotalAverages)
        self.assertEqual(avgAverages, tAvgAverages)

    def testRatePlayer(self):
        league = self.league
        oakland = league.teams[7]
        wemby = oakland.roster[0]
        ignoreStats = ["FTM", "FTA", "TO", "FGA", "FGM", "GP"]

        # total
        wembyStats = wemby.stats["2024_total"]["total"]
        totalAverages = rating.calculateLeagueAverages(
            league=league, timeframe="2024_total", totalOrAvg="total"
        )

        wembyRating = rating.ratePlayer(
            playerStats=wembyStats, averages=totalAverages, ignoreStats=ignoreStats
        )
        tWembyRating = 214.55684085848188
        self.assertEqual(wembyRating, tWembyRating)

        # last 30
        wembyStats = wemby.stats["2024_last_30"]["total"]
        totalAverages = rating.calculateLeagueAverages(
            league=league, timeframe="2024_last_30", totalOrAvg="total"
        )
        wembyRating = rating.ratePlayer(
            playerStats=wembyStats, averages=totalAverages, ignoreStats=ignoreStats
        )
        tWembyRating = 229.92030828036908
        self.assertEqual(wembyRating, tWembyRating)

        # last 15
        wembyStats = wemby.stats["2024_last_15"]["total"]
        totalAverages = rating.calculateLeagueAverages(
            league=league, timeframe="2024_last_15", totalOrAvg="total"
        )
        wembyRating = rating.ratePlayer(
            playerStats=wembyStats, averages=totalAverages, ignoreStats=ignoreStats
        )
        tWembyRating = 247.83054948499736
        self.assertEqual(wembyRating, tWembyRating)

        # last 7
        wembyStats = wemby.stats["2024_last_7"]["total"]
        totalAverages = rating.calculateLeagueAverages(
            league=league, timeframe="2024_last_7", totalOrAvg="total"
        )
        wembyRating = rating.ratePlayer(
            playerStats=wembyStats, averages=totalAverages, ignoreStats=ignoreStats
        )
        tWembyRating = 167.0336897619162
        self.assertEqual(wembyRating, tWembyRating)

        # averages
        wembyStats = wemby.stats["2024_total"]["avg"]
        totalAverages = rating.calculateLeagueAverages(
            league=league, timeframe="2024_total", totalOrAvg="avg"
        )
        wembyRating = rating.ratePlayer(
            playerStats=wembyStats, averages=totalAverages, ignoreStats=ignoreStats
        )
        tWembyRating = 202.93837488950274
        self.assertEqual(wembyRating, tWembyRating)

        # zero stats test
        grant = oakland.roster[6]
        grantStats = grant.stats["2024_last_15"].get("total")
        totalAverages = rating.calculateLeagueAverages(
            league=league, timeframe="2024_last_15", totalOrAvg="total"
        )
        grantRating = rating.ratePlayer(
            playerStats=grantStats, averages=totalAverages, ignoreStats=ignoreStats
        )
        tGrantRating = 0
        self.assertEqual(grantRating, tGrantRating)

    def testAverageStats(self):
        league = self.league
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
    unittest.main()
