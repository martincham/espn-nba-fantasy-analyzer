from espn_api.basketball import League
import rating
import schedule
import loading
import gspread
from datetime import datetime


ROSTER_POSITIONS = ["PG", "F", "SG/SF", "SG/SF", "SG/SF", "PF/C", "U"]

IGNORESTATS = ["FTM", "FTA", "TO", "FGA", "FGM", "GP"]
TIMEFRAMES = ["2024_total", "2024_last_30", "2024_last_15", "2024_last_7"]


league = loading.loadLeague()

freeAgents = loading.loadFreeAgents()

remaningGames = schedule.calculateRemainingGames(league=league)
extraRemainingGames = schedule.calculateExtraRemainingGames(league=league)

myTeam = league.teams[7]


avgLeagueRatings = rating.leagueTeamRatings(league, "avg", IGNORESTATS)
totalLeagueRatings = rating.leagueTeamRatings(league, "total", IGNORESTATS)

freeAgentRatings = rating.leagueFreeAgentRatings(
    league, freeAgents, "total", IGNORESTATS
)
freeAgentAvgRatings = rating.leagueFreeAgentRatings(
    league, freeAgents, "avg", IGNORESTATS
)


# Publish to Google Sheet
gc = gspread.service_account()
spreadsheet = gc.open("AutoFantasyStats24")
avgWorksheet = spreadsheet.get_worksheet(1)
totalWorksheet = spreadsheet.get_worksheet(0)
freeAgentWorksheet = spreadsheet.get_worksheet(2)
freeAgentAvgWorksheet = spreadsheet.get_worksheet(3)
teamMatrixTotalWorksheet = spreadsheet.get_worksheet(4)
teamMatrixSevenWorksheet = spreadsheet.get_worksheet(5)
teamMatrixFifteenWorksheet = spreadsheet.get_worksheet(6)
teamMatrixThirtyWorksheet = spreadsheet.get_worksheet(7)
faMatrixTotalWorksheet = spreadsheet.get_worksheet(8)
faMatrixSevenWorksheet = spreadsheet.get_worksheet(9)
faMatrixFifteenWorksheet = spreadsheet.get_worksheet(10)
faMatrixThirtyWorksheet = spreadsheet.get_worksheet(11)

infoWorksheet = spreadsheet.get_worksheet(12)
remainingValueWorksheet = spreadsheet.get_worksheet(13)
remainingFAWorksheet = spreadsheet.get_worksheet(14)


now = datetime.now()
updateTime = now.strftime("%m/%d/%Y, %H:%M:%S")
info = [["Last updated", updateTime]]
infoWorksheet.update(info)

avgWorksheet.update(
    [avgLeagueRatings.columns.values.tolist()] + avgLeagueRatings.values.tolist()
)
totalWorksheet.update(
    [totalLeagueRatings.columns.values.tolist()] + totalLeagueRatings.values.tolist()
)
freeAgentWorksheet.update(
    [freeAgentRatings.columns.values.tolist()] + freeAgentRatings.values.tolist()
)
freeAgentAvgWorksheet.update(
    [freeAgentAvgRatings.columns.values.tolist()] + freeAgentAvgRatings.values.tolist()
)

freeAgentRatings.to_excel(
    "freeAgentRatings.xlsx",
)

categoryList = [
    "PTS",
    "BLK",
    "STL",
    "AST",
    "REB",
    "3PTM",
    "TO",
    "FTM",
    "FTA",
    "FGM",
    "FGA",
    "GP",
]


remRatingMatrix = rating.remainingRateTeams(
    league=league, timeframes=TIMEFRAMES, totalOrAvg="avg", ignoreStats=IGNORESTATS
)

remainingValueWorksheet.update(remRatingMatrix)

remFARatingMatrix = rating.remainingRateFreeAgents(
    league=league, freeAgents=freeAgents, timeframes=TIMEFRAMES, ignoreStats=IGNORESTATS
)

remainingFAWorksheet.update(
    remFARatingMatrix,
)


teamRatingMatrixTotal = rating.categoryRateTeams(
    league, "2024_total", "total", categoryList, IGNORESTATS
)
teamRatingMatrixSeven = rating.categoryRateTeams(
    league, "2024_last_7", "total", categoryList, IGNORESTATS
)
teamRatingMatrixFifteen = rating.categoryRateTeams(
    league, "2024_last_15", "total", categoryList, IGNORESTATS
)
teamRatingMatrixThirty = rating.categoryRateTeams(
    league, "2024_last_30", "total", categoryList, IGNORESTATS
)


teamMatrixTotalWorksheet.update(teamRatingMatrixTotal)
teamMatrixSevenWorksheet.update(teamRatingMatrixSeven)
teamMatrixFifteenWorksheet.update(teamRatingMatrixFifteen)
teamMatrixThirtyWorksheet.update(teamRatingMatrixThirty)

faRatingMatrixTotal = rating.categoryRateFreeAgents(
    league, freeAgents, "2024_total", "total", categoryList, IGNORESTATS
)
faRatingMatrixSeven = rating.categoryRateFreeAgents(
    league, freeAgents, "2024_last_7", "total", categoryList, IGNORESTATS
)
faRatingMatrixFifteen = rating.categoryRateFreeAgents(
    league, freeAgents, "2024_last_15", "total", categoryList, IGNORESTATS
)
faRatingMatrixThirty = rating.categoryRateFreeAgents(
    league, freeAgents, "2024_last_30", "total", categoryList, IGNORESTATS
)


faMatrixTotalWorksheet.update(faRatingMatrixTotal)
faMatrixSevenWorksheet.update(faRatingMatrixSeven)
faMatrixFifteenWorksheet.update(faRatingMatrixFifteen)
faMatrixThirtyWorksheet.update(faRatingMatrixThirty)
