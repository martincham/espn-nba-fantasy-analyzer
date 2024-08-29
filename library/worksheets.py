import json
from datetime import datetime
import gspread
import gspread_formatting as gsf
import library.loading as loading
import library.rating as rating
import library.config as config


ROSTER_POSITIONS = config.ROSTER_POSITIONS
IGNORE_STATS = config.IGNORE_STATS
TIMEFRAMES = config.TIMEFRAMES
SETTING_FILE = config.SETTING_FILE
RED_RGB = config.RED_RGB
WHITE_RGB = config.WHITE_RGB
GREEN_RGB = config.GREEN_RGB

now = datetime.now()
updateTime = now.strftime("%m/%d/%Y, %H:%M:%S")
info = [["Last updated", updateTime]]


def getGoogleSheetName():
    try:
        file = open(SETTING_FILE, "rb")
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
def formatWorksheet(
    batch, worksheet, columns=4, minValue="0", midValue="100", maxValue="200"
):
    columnsRange = "A:" + chr(64 + columns)  # 65 = ascii "A"
    topRowRange = (
        "A1:" + chr(64 + columns + 3) + "1"
    )  # plus 2 for  name and team columns
    numberRange = "A2:" + chr(64 + columns) + "1000"

    # Top Row Formatting
    topRowFormat = gsf.CellFormat(textFormat=gsf.TextFormat(bold=True))
    batch.set_frozen(worksheet=worksheet, rows=1)
    # Format Numbers
    batch.set_column_width(worksheet, columnsRange, 40)
    numberFormat = gsf.CellFormat(
        numberFormat=gsf.NumberFormat(type="NUMBER", pattern="#,##0"),
    )
    batch.format_cell_ranges(
        worksheet=worksheet,
        ranges=[(topRowRange, topRowFormat), (numberRange, numberFormat)],
    )

    minPoint = gsf.InterpolationPoint(
        color=gsf.Color(RED_RGB[0], RED_RGB[1], RED_RGB[2]),
        type="NUMBER",
        value=minValue,
    )
    midPoint = gsf.InterpolationPoint(
        color=gsf.Color(WHITE_RGB[0], WHITE_RGB[1], WHITE_RGB[2]),
        type="NUMBER",
        value=midValue,
    )
    maxPoint = gsf.InterpolationPoint(
        color=gsf.Color(GREEN_RGB[0], GREEN_RGB[1], GREEN_RGB[2]),
        type="NUMBER",
        value=maxValue,
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


def formatRemainingValueWorksheet(batch, worksheet, columns=8):
    columnsRange = "A:" + chr(64 + columns)  # 65 = ascii "A"
    topRowRange = "A1:" + chr(64 + columns) + "1"
    numberRange = "A2:" + chr(64 + columns) + "1000"

    # Top Row Formatting
    topRowFormat = gsf.CellFormat(textFormat=gsf.TextFormat(bold=True))
    batch.set_frozen(worksheet=worksheet, rows=1)
    # Format Numbers
    batch.set_column_width(worksheet, columnsRange, 40)
    numberFormat = gsf.CellFormat(
        numberFormat=gsf.NumberFormat(type="NUMBER", pattern="#,##0"),
    )
    batch.format_cell_ranges(
        worksheet=worksheet,
        ranges=[(topRowRange, topRowFormat), (numberRange, numberFormat)],
    )


def initializeSpreadsheet():
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
    avgWorksheet.update_title("pG")
    freeAgentWorksheet.update_title("FA")
    freeAgentAvgWorksheet.update_title("FApG")
    teamMatrixTotalWorksheet.update_title("cats")
    teamMatrixSevenWorksheet.update_title("cats7")
    teamMatrixFifteenWorksheet.update_title("cats15")
    teamMatrixThirtyWorksheet.update_title("cats30")
    faMatrixTotalWorksheet.update_title("FAcats")
    faMatrixSevenWorksheet.update_title("FA7")
    faMatrixFifteenWorksheet.update_title("FA15")
    faMatrixThirtyWorksheet.update_title("FA30")
    remainingValueWorksheet.update_title("remValue")
    remainingFAWorksheet.update_title("remFA")
    infoWorksheet.update_title("info")

    with gsf.batch_updater(spreadsheet) as batch:
        formatWorksheet(batch=batch, worksheet=avgWorksheet)
        formatWorksheet(batch=batch, worksheet=totalWorksheet)
        formatWorksheet(batch=batch, worksheet=freeAgentWorksheet)
        formatWorksheet(batch=batch, worksheet=freeAgentAvgWorksheet)
        formatWorksheet(batch=batch, worksheet=teamMatrixTotalWorksheet, columns=13)
        formatWorksheet(batch=batch, worksheet=teamMatrixSevenWorksheet, columns=13)
        formatWorksheet(batch=batch, worksheet=teamMatrixFifteenWorksheet, columns=13)
        formatWorksheet(batch=batch, worksheet=teamMatrixThirtyWorksheet, columns=13)
        formatWorksheet(batch=batch, worksheet=faMatrixTotalWorksheet, columns=13)
        formatWorksheet(batch=batch, worksheet=faMatrixSevenWorksheet, columns=13)
        formatWorksheet(batch=batch, worksheet=faMatrixFifteenWorksheet, columns=13)
        formatWorksheet(batch=batch, worksheet=faMatrixThirtyWorksheet, columns=13)
        formatWorksheet(batch=batch, worksheet=remainingValueWorksheet, columns=8)
        formatWorksheet(batch=batch, worksheet=remainingValueWorksheet, columns=8)


def pushGoogleSheets():
    league = loading.loadLeague()
    freeAgents = loading.loadFreeAgents()

    avgLeagueRatings = rating.leagueTeamRatings(league, "avg", IGNORE_STATS)
    totalLeagueRatings = rating.leagueTeamRatings(league, "total", IGNORE_STATS)

    freeAgentRatings = rating.leagueFreeAgentRatings(
        league, freeAgents, "total", IGNORE_STATS
    )
    freeAgentAvgRatings = rating.leagueFreeAgentRatings(
        league, freeAgents, "avg", IGNORE_STATS
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

    titles = ["Total", "30", "15", "7", "Player", "Team"]
    avgWorksheet.update(values=[titles] + avgLeagueRatings.values.tolist())
    totalWorksheet.update(values=[titles] + totalLeagueRatings.values.tolist())
    freeAgentWorksheet.update(values=[titles] + freeAgentRatings.values.tolist())
    freeAgentAvgWorksheet.update(values=[titles] + freeAgentAvgRatings.values.tolist())

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
        league=league,
        timeframes=TIMEFRAMES,
        totalOrAvg="avg",
        IGNORE_STATS=IGNORE_STATS,
    )

    remainingValueWorksheet.update(values=remRatingMatrix)

    remFARatingMatrix = rating.remainingRateFreeAgents(
        league=league,
        freeAgents=freeAgents,
        timeframes=TIMEFRAMES,
        IGNORE_STATS=IGNORE_STATS,
    )

    remainingFAWorksheet.update(values=remFARatingMatrix)

    teamRatingMatrixTotal = rating.categoryRateTeams(
        league, "2024_total", "total", categoryList, IGNORE_STATS
    )
    teamRatingMatrixSeven = rating.categoryRateTeams(
        league, "2024_last_7", "total", categoryList, IGNORE_STATS
    )
    teamRatingMatrixFifteen = rating.categoryRateTeams(
        league, "2024_last_15", "total", categoryList, IGNORE_STATS
    )
    teamRatingMatrixThirty = rating.categoryRateTeams(
        league, "2024_last_30", "total", categoryList, IGNORE_STATS
    )

    teamMatrixTotalWorksheet.update(values=teamRatingMatrixTotal)
    teamMatrixSevenWorksheet.update(values=teamRatingMatrixSeven)
    teamMatrixFifteenWorksheet.update(values=teamRatingMatrixFifteen)
    teamMatrixThirtyWorksheet.update(values=teamRatingMatrixThirty)

    faRatingMatrixTotal = rating.categoryRateFreeAgents(
        league, freeAgents, "2024_total", "total", categoryList, IGNORE_STATS
    )
    faRatingMatrixSeven = rating.categoryRateFreeAgents(
        league, freeAgents, "2024_last_7", "total", categoryList, IGNORE_STATS
    )
    faRatingMatrixFifteen = rating.categoryRateFreeAgents(
        league, freeAgents, "2024_last_15", "total", categoryList, IGNORE_STATS
    )
    faRatingMatrixThirty = rating.categoryRateFreeAgents(
        league, freeAgents, "2024_last_30", "total", categoryList, IGNORE_STATS
    )

    faMatrixTotalWorksheet.update(values=faRatingMatrixTotal)
    faMatrixSevenWorksheet.update(values=faRatingMatrixSeven)
    faMatrixFifteenWorksheet.update(values=faRatingMatrixFifteen)
    faMatrixThirtyWorksheet.update(values=faRatingMatrixThirty)
