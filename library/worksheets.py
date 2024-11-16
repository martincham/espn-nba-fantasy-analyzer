import json
from datetime import datetime
import gspread
import gspread_formatting as gsf
import library.loading as loading
import library.rating as rating
import library.config as config
import library.matchups as matchups


ROSTER_POSITIONS = config.ROSTER_POSITIONS
IGNORE_STATS = config.IGNORE_STATS
TIMEFRAMES = config.TIMEFRAMES
SETTING_FILE = config.SETTING_FILE
RED_RGB = config.RED_RGB
WHITE_RGB = config.WHITE_RGB
GREEN_RGB = config.GREEN_RGB
YELLOW_RGB = config.YELLOW_RGB
GRAY_RGB = config.GRAY_RGB
CATEGORIES = config.CATEGORIES

NAMES = [
    "total",  # 0
    "pG",  # 1
    "FA",  # 2
    "FApG",
    "cats",
    "7",
    "15",
    "30",
    "FAcats",
    "FA7",
    "FA15",
    "FA30",
    "rem",
    "remFA",
    "info",
    "matchups",
]

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


def numberToColumnLetter(num: int):
    letters = ""
    while num:
        mod = (num - 1) % 26
        letters += chr(mod + 65)
        num = (num - 1) // 26
    return "".join(reversed(letters))


# columns=number of data columns
def formatWorksheet(
    batch: gsf.SpreadsheetBatchUpdater,
    worksheet: gspread.worksheet,
    columns: int = 4,
    minValue: str = "0",
    midValue: str = "100",
    maxValue: str = "200",
):
    columnsRange = "A:" + chr(64 + columns)  # 65 = ascii "A"
    textColumns = (
        numberToColumnLetter(columns + 1) + ":" + numberToColumnLetter(columns + 4)
    )

    topRowRange = (
        "A1:" + chr(64 + columns + 3) + "1"
    )  # plus 2 for  name and team columns
    numberRange = "A2:" + chr(64 + columns + 2) + "1000"

    # Top Row Formatting
    topRowFormat = gsf.CellFormat(textFormat=gsf.TextFormat(bold=True))
    batch.set_frozen(worksheet=worksheet, rows=1)
    # Format Numbers
    batch.set_column_width(worksheet, columnsRange, 40)
    numberFormat = gsf.CellFormat(
        numberFormat=gsf.NumberFormat(type="NUMBER", pattern="#,##0"),
    )
    # Format Text Columns
    batch.set_column_width(worksheet, textColumns, 120)
    # Format Cells
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


def formatRemainingValueWorksheet(
    batch: gsf.SpreadsheetBatchUpdater, worksheet: gspread.Worksheet, columns: int = 8
):
    columnsRange = "A:" + chr(64 + columns)  # 65 = ascii "A"
    topRowRange = "A1:" + chr(64 + columns) + "1"
    # For some reason, gspread-formatting does not like compound ranges
    numberRange = "A2:" + chr(64 + columns + 2) + "1000"
    remRange = ["A2:A400", "C2:C400", "E2:E400", "G2:G400"]
    differentialRange = ["B2:B400", "D2:D400", "F2:F400", "H2:H400"]

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
    # Normal Green-to-Red gradient
    minPoint = gsf.InterpolationPoint(
        color=gsf.Color(RED_RGB[0], RED_RGB[1], RED_RGB[2]),
        type="MIN",
    )
    midPoint = gsf.InterpolationPoint(
        color=gsf.Color(WHITE_RGB[0], WHITE_RGB[1], WHITE_RGB[2]),
        type="PERCENT",
        value="50",
    )
    maxPoint = gsf.InterpolationPoint(
        color=gsf.Color(GREEN_RGB[0], GREEN_RGB[1], GREEN_RGB[2]),
        type="MAX",
    )

    # Yellow-to-Gray gradient for differential
    dminPoint = gsf.InterpolationPoint(
        color=gsf.Color(YELLOW_RGB[0], YELLOW_RGB[1], YELLOW_RGB[2]),
        type="MIN",
    )
    dmidPoint = gsf.InterpolationPoint(
        color=gsf.Color(WHITE_RGB[0], WHITE_RGB[1], WHITE_RGB[2]),
        type="PERCENT",
        value="50",
    )
    dmaxPoint = gsf.InterpolationPoint(
        color=gsf.Color(GRAY_RGB[0], GRAY_RGB[1], GRAY_RGB[2]),
        type="MAX",
    )

    # Apply conditional formatting gradients
    rules = gsf.get_conditional_format_rules(worksheet)
    rules.clear()
    for numRange in remRange:
        rule = gsf.ConditionalFormatRule(
            ranges=[gsf.GridRange.from_a1_range(numRange, worksheet)],
            gradientRule=gsf.GradientRule(
                minpoint=minPoint, midpoint=midPoint, maxpoint=maxPoint
            ),
        )
        rules.append(rule)
    for diffRange in differentialRange:
        rule = gsf.ConditionalFormatRule(
            ranges=[gsf.GridRange.from_a1_range(diffRange, worksheet)],
            gradientRule=gsf.GradientRule(
                minpoint=dminPoint, midpoint=dmidPoint, maxpoint=dmaxPoint
            ),
        )
        rules.append(rule)
    rules.save()


def formatMatchupWorksheet(
    batch: gsf.SpreadsheetBatchUpdater, worksheet: gspread.Worksheet
):

    numberRange = "B4:ZZ14"

    # Top Row Formatting, Left Column Formatting
    batch.set_frozen(worksheet=worksheet, rows=2, cols=1)
    batch.set_column_width(worksheet, "A", 70)
    rowLabelRange = "1:3"
    leftColumnRange = "A"
    labelFormat = gsf.CellFormat(textFormat=gsf.TextFormat(bold=True))

    # Format Numbers
    batch.set_column_width(worksheet, "B:ZZ", 50)
    numberFormat = gsf.CellFormat(
        numberFormat=gsf.NumberFormat(type="NUMBER", pattern="#,##0"),
    )

    # Roster Foramtting
    rosterRange = "16:30"
    rosterFormat = gsf.CellFormat(textFormat=gsf.TextFormat(fontSize=7))
    # Format Cells
    batch.format_cell_ranges(
        worksheet=worksheet,
        ranges=[
            (numberRange, numberFormat),
            (rowLabelRange, labelFormat),
            ("6", labelFormat),
            ("9", labelFormat),
            ("23", labelFormat),
            (leftColumnRange, labelFormat),
            (rosterRange, rosterFormat),
        ],
    )

    minPoint = gsf.InterpolationPoint(
        color=gsf.Color(RED_RGB[0], RED_RGB[1], RED_RGB[2]),
        type="MIN",
    )
    midPoint = gsf.InterpolationPoint(
        color=gsf.Color(WHITE_RGB[0], WHITE_RGB[1], WHITE_RGB[2]),
        type="PERCENT",
        value="50",
    )
    maxPoint = gsf.InterpolationPoint(
        color=gsf.Color(GREEN_RGB[0], GREEN_RGB[1], GREEN_RGB[2]),
        type="MAX",
    )
    rule = gsf.ConditionalFormatRule(
        ranges=[gsf.GridRange.from_a1_range("B4:ZZ8", worksheet)],
        gradientRule=gsf.GradientRule(
            minpoint=minPoint, midpoint=midPoint, maxpoint=maxPoint
        ),
    )
    rule2 = gsf.ConditionalFormatRule(
        ranges=[gsf.GridRange.from_a1_range("B10:ZZ14", worksheet)],
        gradientRule=gsf.GradientRule(
            minpoint=minPoint, midpoint=midPoint, maxpoint=maxPoint
        ),
    )
    rules = gsf.get_conditional_format_rules(worksheet)
    rules.clear()
    rules.append(rule)
    rules.append(rule2)
    rules.save()


def createWorksheet(
    spreadsheet: gspread.Spreadsheet, title: str, rows: int = 500, cols: int = 20
):
    try:
        sheet = spreadsheet.worksheet(title=title)
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)
    except Exception as ex:
        print("Error:", ex)
    return sheet


def initializeSpreadsheet():
    gc = gspread.service_account()
    spreadsheet = gc.open(getGoogleSheetName())
    totalWorksheet = spreadsheet.get_worksheet(0)
    totalWorksheet.update_title(NAMES[0])
    avgWorksheet = createWorksheet(spreadsheet=spreadsheet, title=NAMES[1])
    freeAgentWorksheet = createWorksheet(spreadsheet=spreadsheet, title=NAMES[2])
    freeAgentAvgWorksheet = createWorksheet(spreadsheet=spreadsheet, title=NAMES[3])
    teamMatrixTotalWorksheet = createWorksheet(spreadsheet=spreadsheet, title=NAMES[4])
    teamMatrixSevenWorksheet = createWorksheet(spreadsheet=spreadsheet, title=NAMES[5])
    teamMatrixFifteenWorksheet = createWorksheet(
        spreadsheet=spreadsheet, title=NAMES[6]
    )
    teamMatrixThirtyWorksheet = createWorksheet(spreadsheet=spreadsheet, title=NAMES[7])
    faMatrixTotalWorksheet = createWorksheet(spreadsheet=spreadsheet, title=NAMES[8])
    faMatrixSevenWorksheet = createWorksheet(spreadsheet=spreadsheet, title=NAMES[9])
    faMatrixFifteenWorksheet = createWorksheet(spreadsheet=spreadsheet, title=NAMES[10])
    faMatrixThirtyWorksheet = createWorksheet(spreadsheet=spreadsheet, title=NAMES[11])
    remainingValueWorksheet = createWorksheet(spreadsheet=spreadsheet, title=NAMES[12])
    remainingFAWorksheet = createWorksheet(spreadsheet=spreadsheet, title=NAMES[13])
    infoWorksheet = createWorksheet(spreadsheet=spreadsheet, title=NAMES[14])
    matchupWorksheet = createWorksheet(spreadsheet=spreadsheet, title=NAMES[15])

    # names
    """"
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
    """
    columns = len(CATEGORIES) + 1
    with gsf.batch_updater(spreadsheet) as batch:
        formatWorksheet(batch=batch, worksheet=avgWorksheet)
        formatWorksheet(batch=batch, worksheet=totalWorksheet)
        formatWorksheet(batch=batch, worksheet=freeAgentWorksheet)
        formatWorksheet(batch=batch, worksheet=freeAgentAvgWorksheet)
        formatWorksheet(
            batch=batch, worksheet=teamMatrixTotalWorksheet, columns=columns
        )
        formatWorksheet(
            batch=batch, worksheet=teamMatrixSevenWorksheet, columns=columns
        )
        formatWorksheet(
            batch=batch, worksheet=teamMatrixFifteenWorksheet, columns=columns
        )
        formatWorksheet(
            batch=batch, worksheet=teamMatrixThirtyWorksheet, columns=columns
        )
        formatWorksheet(batch=batch, worksheet=faMatrixTotalWorksheet, columns=columns)
        formatWorksheet(batch=batch, worksheet=faMatrixSevenWorksheet, columns=columns)
        formatWorksheet(
            batch=batch, worksheet=faMatrixFifteenWorksheet, columns=columns
        )
        formatWorksheet(batch=batch, worksheet=faMatrixThirtyWorksheet, columns=columns)
        formatRemainingValueWorksheet(
            batch=batch, worksheet=remainingValueWorksheet, columns=8
        )
        formatRemainingValueWorksheet(
            batch=batch, worksheet=remainingFAWorksheet, columns=8
        )
        formatMatchupWorksheet(batch=batch, worksheet=matchupWorksheet)


def pushGoogleSheets():
    league = loading.loadLeague()
    freeAgents = loading.loadFreeAgents()

    matchupData = matchups.createMatchupSchedule(league=league)

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
    totalWorksheet = spreadsheet.worksheet(NAMES[0])
    avgWorksheet = spreadsheet.worksheet(NAMES[1])
    freeAgentWorksheet = spreadsheet.worksheet(NAMES[2])
    freeAgentAvgWorksheet = spreadsheet.worksheet(NAMES[3])
    teamMatrixTotalWorksheet = spreadsheet.worksheet(NAMES[4])
    teamMatrixSevenWorksheet = spreadsheet.worksheet(NAMES[5])
    teamMatrixFifteenWorksheet = spreadsheet.worksheet(NAMES[6])
    teamMatrixThirtyWorksheet = spreadsheet.worksheet(NAMES[7])
    faMatrixTotalWorksheet = spreadsheet.worksheet(NAMES[8])
    faMatrixSevenWorksheet = spreadsheet.worksheet(NAMES[9])
    faMatrixFifteenWorksheet = spreadsheet.worksheet(NAMES[10])
    faMatrixThirtyWorksheet = spreadsheet.worksheet(NAMES[11])
    remainingValueWorksheet = spreadsheet.worksheet(NAMES[12])
    remainingFAWorksheet = spreadsheet.worksheet(NAMES[13])
    infoWorksheet = spreadsheet.worksheet(NAMES[14])
    matchupWorksheet = spreadsheet.worksheet(NAMES[15])

    transposed_data = [list(row) for row in zip(*matchupData)]
    matchupWorksheet.update(values=transposed_data)

    now = datetime.now()
    updateTime = now.strftime("%m/%d/%Y, %H:%M:%S")
    info = [["Last updated", updateTime]]
    infoWorksheet.update(values=info)

    titles = ["Total", "30", "15", "7", "Player", "Team"]
    avgWorksheet.update(values=[titles] + avgLeagueRatings.values.tolist())
    totalWorksheet.update(values=[titles] + totalLeagueRatings.values.tolist())
    freeAgentWorksheet.update(values=[titles] + freeAgentRatings.values.tolist())
    freeAgentAvgWorksheet.update(values=[titles] + freeAgentAvgRatings.values.tolist())

    categoryList = CATEGORIES

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
        league, TIMEFRAMES[0], "total", categoryList, IGNORE_STATS
    )
    teamRatingMatrixSeven = rating.categoryRateTeams(
        league, TIMEFRAMES[1], "total", categoryList, IGNORE_STATS
    )
    teamRatingMatrixFifteen = rating.categoryRateTeams(
        league, TIMEFRAMES[2], "total", categoryList, IGNORE_STATS
    )
    teamRatingMatrixThirty = rating.categoryRateTeams(
        league, TIMEFRAMES[3], "total", categoryList, IGNORE_STATS
    )

    teamMatrixTotalWorksheet.update(values=teamRatingMatrixTotal)
    teamMatrixSevenWorksheet.update(values=teamRatingMatrixSeven)
    teamMatrixFifteenWorksheet.update(values=teamRatingMatrixFifteen)
    teamMatrixThirtyWorksheet.update(values=teamRatingMatrixThirty)

    faRatingMatrixTotal = rating.categoryRateFreeAgents(
        league, freeAgents, TIMEFRAMES[0], "total", categoryList, IGNORE_STATS
    )
    faRatingMatrixSeven = rating.categoryRateFreeAgents(
        league, freeAgents, TIMEFRAMES[1], "total", categoryList, IGNORE_STATS
    )
    faRatingMatrixFifteen = rating.categoryRateFreeAgents(
        league, freeAgents, TIMEFRAMES[2], "total", categoryList, IGNORE_STATS
    )
    faRatingMatrixThirty = rating.categoryRateFreeAgents(
        league, freeAgents, TIMEFRAMES[3], "total", categoryList, IGNORE_STATS
    )

    faMatrixTotalWorksheet.update(values=faRatingMatrixTotal)
    faMatrixSevenWorksheet.update(values=faRatingMatrixSeven)
    faMatrixFifteenWorksheet.update(values=faRatingMatrixFifteen)
    faMatrixThirtyWorksheet.update(values=faRatingMatrixThirty)
