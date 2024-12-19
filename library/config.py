import json

###################
# Not Adjustable
POSITION_HEIRARCHY = ["SG/SF", "SG/SF", "SG/SF", "PG", "F", "PF/C", "UT"]
NEGATIVE_STATS = ["TO"]
INJURY_MAP = {
    "ACTIVE": "H",
    "OUT": "OUT",
    "DAY_TO_DAY": "D2D",
}
PERCENT_MAP = {
    "FG%": ["FGM", "FGA"],
    "AFG%": ["FGM", "FGA"],
    "FT%": ["FTM", "FTA"],
    "3P%": ["3PM", "3PA"],
    "A/TO": ["AST", "TO"],
    "STR": ["STL", "TO"],
    "FTR": ["FTA", "FGA"],
}
VALID_POSITIONS = ["PG", "SG", "SF", "PF", "C"]
VALID_CATEGORIES = [
    "PTS",
    "BLK",
    "STL",
    "AST",
    "OREB",
    "DREB",
    "REB",
    "EJ",
    "FF",
    "PF",
    "TF",
    "TO",
    "DQ",
    "FGM",
    "FGA",
    "FTM",
    "FTA",
    "3PM",
    "3PA",
    "FG%",
    "FT%",
    "3PT%",
    "AFG%",
    "FGMI",
    "FTMI",
    "3PMI",
    "APG",
    "BPG",
    "MPG",
    "PPG",
    "RPG",
    "SPG",
    "TOPG",
    "3PG",
    "PPM",
    "A/TO",
    "STR",
    "DD",
    "TD",
    "QD",
    "MIN",
    "GS",
    "GP",
    "TW",
    "FTR",
]
TIMEFRAMES = ["_total", "_last_30", "_last_15", "_last_7"]  # suffixes
PERCENT_STATS = ["FG%", "AFG%", "FT%", "3P%", "A/TO", "STR", "FTR"]

####################
# Perhaps Adjustable
# File Names
SETTING_FILE = "settings.txt"
LEAGUE_FILE = "league.pickle"
FREE_AGENTS_FILE = "freeAgents.pickle"
# Spreadsheet Settings
RED_RGB = [0.91, 0.49, 0.45]
WHITE_RGB = [1, 1, 1]
GREEN_RGB = [0.3, 0.8, 0.6]
YELLOW_RGB = [1, 1, 0.8]
GRAY_RGB = [0.8, 0.8, 0.8]
BLUE_RGB = [0.522, 0.601, 1]
ORANGE_RGB = [1, 0.878, 0.545]

############
# Defaults
ROSTER_POSITIONS = []
IGNORE_STATS = ["FTM", "FTA", "TO", "FGA", "FGM", "GP"]  # default
CATEGORIES = [
    "PTS",
    "BLK",
    "STL",
    "AST",
    "REB",
    "3PM",
    "TO",
    "FG%",
    "FT%",
    "GP",
]  # default


# load from setting file, or make default settings
def init() -> int:
    try:
        with open(SETTING_FILE, "r") as file:
            fileInfo = file.read()
            settings = json.loads(fileInfo)
            file.close()
    except Exception as ex:  # file not found, initialize
        print("Creating settings.txt file:")
        settings = {
            "SWID": "{123}",
            "espn_s2": "456",
            "leagueId": 1640258594,
            "seasonId": 2025,
            "teamNumber": 8,
            "googleSheet": "SheetNameHere",
            "categories": [
                "PTS",
                "BLK",
                "STL",
                "AST",
                "REB",
                "3PM",
                "TO",
                "FT%",
                "FG%",
            ],
            "ignoredStats": ["FTM", "FTA", "FGA", "FGM", "GP", "MIN"],
            "rosterPositions": ["PG", "F", "SG/SF", "SG/SF", "SG/SF", "PF/C", "UT"],
            "teamSize": 12,
            "ignorePlayers": 3,
            "dailyPlayers": 7,
        }
        with open(SETTING_FILE, "w") as file:
            json.dump(
                settings, file, indent=4
            )  # `indent=4` formats JSON for readability
    global SEASON_ID
    SEASON_ID = int(settings.get("seasonId"))
    global SWID
    SWID = settings.get("SWID")
    global ESPN_S2
    ESPN_S2 = settings.get("espn_s2")
    global LEAGUE_ID
    LEAGUE_ID = settings.get("leagueId")
    global TIMEFRAMES
    TIMEFRAMES = [str(SEASON_ID) + suffix for suffix in TIMEFRAMES]
    global ROSTER_POSITIONS
    ROSTER_POSITIONS = settings.get("rosterPositions")
    global TEAM_SIZE
    TEAM_SIZE = settings.get("teamSize")
    global CATEGORIES
    CATEGORIES = settings.get("categories")
    if "GP" not in CATEGORIES:
        CATEGORIES += ["GP"]  # must contain Games Played for per-game calculations
    if "MIN" not in CATEGORIES:
        CATEGORIES += ["MIN"]  # must contain Minutes for per-minute calculations
    IGNORE_STATS = settings.get("ignoredStats")
    if "MIN" not in IGNORE_STATS:
        IGNORE_STATS += ["MIN"]  # must contain Minutes Played
    if "GP" not in IGNORE_STATS:
        IGNORE_STATS += ["GP"]  # and why not
    global TEAM_NUMBER
    TEAM_NUMBER = int(settings.get("teamNumber")) - 1  # switch to 0 indexing
    global IGNORE_PLAYERS
    IGNORE_PLAYERS = settings.get("ignorePlayers")
    global MAX_PLAYERS
    MAX_PLAYERS = int(settings.get("dailyPlayers"))

    validateCategories()


def validateCategories():
    for category in CATEGORIES:
        if category not in VALID_CATEGORIES:
            print("Invalid category:", category)
            quit()


init()
