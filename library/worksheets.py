import gspread
import json
import os
from datetime import datetime
import library.loading as loading
import library.rating as rating
import library.schedule as schedule

ROSTER_POSITIONS = ["PG", "F", "SG/SF", "SG/SF", "SG/SF", "PF/C", "U"]
IGNORESTATS = ["FTM", "FTA", "TO", "FGA", "FGM", "GP"]
TIMEFRAMES = ["2024_total", "2024_last_30", "2024_last_15", "2024_last_7"]
SETTINGFILE = "settings.txt"

now = datetime.now()
updateTime = now.strftime("%m/%d/%Y, %H:%M:%S")
info = [["Last updated", updateTime]]


def getGoogleSheetName():
    try:
        file = open(SETTINGFILE, "rb")
        fileInfo = file.read()
        loginInfo = json.loads(fileInfo)
        sheetName = loginInfo.get("googleSheet")
        file.close()
    except FileNotFoundError as ex:
        print("Could not find login file:", ex)
        return 0
    except Exception as ex:
        print("Error: ", ex)
        return 0
    return sheetName


def clearWorksheets():
    try:
        gc = gspread.service_account()
        spreadsheet = gc.open(getGoogleSheetName())
        for worksheet in spreadsheet:
            worksheet.clear()
    except Exception as ex:
        print("Error: ", ex)


def pushGoogleSheets():
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
    spreadsheet = gc.open(getGoogleSheetName())
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
    infoWorksheet.update(values=info)

    avgWorksheet.update(
        values=[avgLeagueRatings.columns.values.tolist()]
        + avgLeagueRatings.values.tolist()
    )
    totalWorksheet.update(
        values=[totalLeagueRatings.columns.values.tolist()]
        + totalLeagueRatings.values.tolist()
    )
    freeAgentWorksheet.update(
        values=[freeAgentRatings.columns.values.tolist()]
        + freeAgentRatings.values.tolist()
    )
    freeAgentAvgWorksheet.update(
        values=[freeAgentAvgRatings.columns.values.tolist()]
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

    remainingValueWorksheet.update(values=remRatingMatrix)

    remFARatingMatrix = rating.remainingRateFreeAgents(
        league=league,
        freeAgents=freeAgents,
        timeframes=TIMEFRAMES,
        ignoreStats=IGNORESTATS,
    )

    remainingFAWorksheet.update(values=remFARatingMatrix)

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

    teamMatrixTotalWorksheet.update(values=teamRatingMatrixTotal)
    teamMatrixSevenWorksheet.update(values=teamRatingMatrixSeven)
    teamMatrixFifteenWorksheet.update(values=teamRatingMatrixFifteen)
    teamMatrixThirtyWorksheet.update(values=teamRatingMatrixThirty)

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

    faMatrixTotalWorksheet.update(values=faRatingMatrixTotal)
    faMatrixSevenWorksheet.update(values=faRatingMatrixSeven)
    faMatrixFifteenWorksheet.update(values=faRatingMatrixFifteen)
    faMatrixThirtyWorksheet.update(values=faRatingMatrixThirty)
