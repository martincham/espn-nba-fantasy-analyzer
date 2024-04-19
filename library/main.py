from espn_api.basketball import League
import rating
import schedule
import loading
import gspread
from datetime import datetime
import os
from simple_term_menu import TerminalMenu


ROSTER_POSITIONS = ["PG", "F", "SG/SF", "SG/SF", "SG/SF", "PF/C", "U"]

IGNORESTATS = ["FTM", "FTA", "TO", "FGA", "FGM", "GP"]
TIMEFRAMES = ["2024_total", "2024_last_30", "2024_last_15", "2024_last_7"]


def main():
    mainMenu = [
        "[1] Refresh League",
        "[2] Push Google Worksheets",
        "[3] Generate Excel Worksheets",
        "[4] Exit",
    ]
    terminal_menu = TerminalMenu(
        menu_entries=mainMenu, title="ESPN Fantasy BBALL Analyzer"
    )


if __name__ == "__main__":
    main()


def refreshGoogleSheets():
    league = loading.loadLeague()

    freeAgents = loading.loadFreeAgents()

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
    infoWorksheet.update(range_name=info)

    avgWorksheet.update(
        range_name=[avgLeagueRatings.columns.values.tolist()]
        + avgLeagueRatings.values.tolist()
    )
    totalWorksheet.update(
        range_name=[totalLeagueRatings.columns.values.tolist()]
        + totalLeagueRatings.values.tolist()
    )
    freeAgentWorksheet.update(
        range_name=[freeAgentRatings.columns.values.tolist()]
        + freeAgentRatings.values.tolist()
    )
    freeAgentAvgWorksheet.update(
        range_name=[freeAgentAvgRatings.columns.values.tolist()]
        + freeAgentAvgRatings.values.tolist()
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

    remainingValueWorksheet.update(range_name=remRatingMatrix)

    remFARatingMatrix = rating.remainingRateFreeAgents(
        league=league,
        freeAgents=freeAgents,
        timeframes=TIMEFRAMES,
        ignoreStats=IGNORESTATS,
    )

    remainingFAWorksheet.update(range_name=remFARatingMatrix)

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

    teamMatrixTotalWorksheet.update(range_name=teamRatingMatrixTotal)
    teamMatrixSevenWorksheet.update(range_name=teamRatingMatrixSeven)
    teamMatrixFifteenWorksheet.update(range_name=teamRatingMatrixFifteen)
    teamMatrixThirtyWorksheet.update(range_name=teamRatingMatrixThirty)

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

    faMatrixTotalWorksheet.update(range_name=faRatingMatrixTotal)
    faMatrixSevenWorksheet.update(range_name=faRatingMatrixSeven)
    faMatrixFifteenWorksheet.update(range_name=faRatingMatrixFifteen)
    faMatrixThirtyWorksheet.update(range_name=faRatingMatrixThirty)
