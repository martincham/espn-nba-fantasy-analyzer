import gspread
import json
from datetime import datetime
import library.loading as loading
import library.rating as rating
import gspread_formatting as gsf

ROSTER_POSITIONS = ["PG", "F", "SG/SF", "SG/SF", "SG/SF", "PF/C", "U"]
IGNORESTATS = ["FTM", "FTA", "TO", "FGA", "FGM", "GP"]
TIMEFRAMES = ["2024_total", "2024_last_30", "2024_last_15", "2024_last_7"]
SETTINGFILE = "settings.txt"
RED_RGB = [1, 0.07, 0.7]
WHITE_RGB = [1, 1, 1]
GREEN_RGB = [0.3, 0.8, 0.6]

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


# columns=number of data columns
def formatWorksheet(worksheet, columns=4):
    columnsRange = "A:" + chr(64 + columns)  # 65 = ascii "A"
    topRowRange = "A1:" + chr(64 + columns) + "1"
    numberRange = "A2:" + chr(64 + columns) + "1000"

    # Top Row Formatting
    topRowFormat = gsf.CellFormat(textFormat=gsf.TextFormat(bold=True))
    gsf.set_frozen(worksheet=worksheet, rows=1)
    # Format Numbers
    gsf.set_column_width(worksheet, columnsRange, 40)
    numberFormat = gsf.CellFormat(
        numberFormat=gsf.NumberFormat(type="NUMBER", pattern="#,##0"),
    )
    gsf.format_cell_ranges(
        worksheet=worksheet,
        ranges=[(topRowRange, topRowFormat), (numberRange, numberFormat)],
    )

    minPoint = gsf.InterpolationPoint(
        color=gsf.Color(RED_RGB[0], RED_RGB[1], RED_RGB[2]),
        type="NUMBER",
        value="0",
    )
    midPoint = gsf.InterpolationPoint(
        color=gsf.Color(WHITE_RGB[0], WHITE_RGB[1], WHITE_RGB[2]),
        type="NUMBER",
        value="100",
    )
    maxPoint = gsf.InterpolationPoint(
        color=gsf.Color(GREEN_RGB[0], GREEN_RGB[1], GREEN_RGB[2]),
        type="NUMBER",
        value="200",
    )
    rule = gsf.ConditionalFormatRule(
        ranges=[gsf.GridRange.from_a1_range(numberRange, worksheet)],
        gradientRule=gsf.GradientRule(
            minpoint=minPoint, midpoint=midPoint, maxpoint=maxPoint
        ),
    )
    rules = gsf.get_conditional_format_rules(worksheet)
    rules.clear()
    rules.append(rule)
    rules.save()
    
def initializeSpreadsheet()
    gc = gspread.service_account()
    spreadsheet = gc.open(getGoogleSheetName())
    totalWorksheet = spreadsheet.get_worksheet(0)
    avgWorksheet = spreadsheet.get_worksheet(1)
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
    remainingValueWorksheet = spreadsheet.get_worksheet(12)
    remainingFAWorksheet = spreadsheet.get_worksheet(13)
    infoWorksheet = spreadsheet.get_worksheet(14)
    
    # names
    totalWorksheet.update_title("total")
    avgWorksheet.title = "pG"
    freeAgentWorksheet.title = "FA"
    freeAgentAvgWorksheet.title = "FApG"
    teamMatrixTotalWorksheet.title = "cats"
    teamMatrixSevenWorksheet.title = "cats7"
    teamMatrixFifteenWorksheet.title = "cats15"
    teamMatrixThirtyWorksheet = "cats30"
    faMatrixTotalWorksheet.title = "FAcats"
    faMatrixSevenWorksheet.title = "FA7"
    faMatrixFifteenWorksheet.title = "FA15"
    faMatrixThirtyWorksheet.title = "FA15"
    remainingValueWorksheet.title = "remValue"
    remainingFAWorksheet.title = "remFA"
    infoWorksheet.title = "info"
    
    formatWorksheet(worksheet=avgWorksheet)
    formatWorksheet(worksheet=totalWorksheet)
    formatWorksheet(worksheet=freeAgentWorksheet)
    formatWorksheet(worksheet=freeAgentAvgWorksheet)
    formatWorksheet(worksheet=teamMatrixTotalWorksheet, columns=13)
    formatWorksheet(worksheet=teamMatrixSevenWorksheet, columns=13)
    formatWorksheet(worksheet=teamMatrixFifteenWorksheet, columns=13)
    formatWorksheet(worksheet=teamMatrixThirtyWorksheet, columns=13)
    formatWorksheet(worksheet=faMatrixTotalWorksheet, columns=13)
    formatWorksheet(worksheet=faMatrixSevenWorksheet, columns=13)
    formatWorksheet(worksheet=faMatrixFifteenWorksheet, columns=13)
    formatWorksheet(worksheet=faMatrixThirtyWorksheet, columns=13)

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
    totalWorksheet = spreadsheet.get_worksheet(0)
    avgWorksheet = spreadsheet.get_worksheet(1)
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
    remainingValueWorksheet = spreadsheet.get_worksheet(12)
    remainingFAWorksheet = spreadsheet.get_worksheet(13)
    infoWorksheet = spreadsheet.get_worksheet(14)
    
    

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
