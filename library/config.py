import json

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
    "FTM",
    "FTA",
    "FGM",
    "FGA",
    "GP",
]  # default
TIMEFRAMES = ["_total", "_last_30", "_last_15", "_last_7"]  # suffixes
PERCENT_STATS = ["FG%", "AFG%", "FT%", "3P%", "A/TO", "STR", "FTR"]
# files
SETTING_FILE = "settings.txt"
LEAGUE_FILE = "league.pickle"
FREE_AGENTS_FILE = "freeAgents.pickle"
# spreadsheet settings
RED_RGB = [0.91, 0.49, 0.45]
WHITE_RGB = [1, 1, 1]
GREEN_RGB = [0.3, 0.8, 0.6]
YELLOW_RGB = [1, 1, .8]
GRAY_RGB = [0.8, 0.8, 0.8]

# load from setting file
try:
    with open(SETTING_FILE, "r") as file:
        fileInfo = file.read()
        settings = json.loads(fileInfo)
        file.close()
except Exception as ex: # file not found, initialize
    print("Could not find login file:", ex)
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
        "FTM",
        "FTA",
        "FGM",
        "FGA",
        "GP"
    ],
    "ignoredStats": [
        "FTM",
        "FTA",
        "TO",
        "FGA",
        "FGM",
        "GP"
    ],
    "rosterPositions": [
        "PG",
        "F",
        "SG/SF",
        "SG/SF",
        "SG/SF",
        "PF/C",
        "U"
    ],
    "ignorePlayers": 3,
    "maxPlayers": 8
    }
    with open(SETTING_FILE, "w") as file:
        json.dump(settings, file, indent=4)  # `indent=4` formats JSON for readability
        


SEASON_ID = int(settings.get("seasonId"))
SWID = settings.get("SWID")
ESPN_S2 = settings.get("espn_s2")
LEAGUE_ID = settings.get("leagueId")
TIMEFRAMES = [str(SEASON_ID) + suffix for suffix in TIMEFRAMES]

ROSTER_POSITIONS = settings.get("rosterPositions")
CATEGORIES = settings.get("categories")
if "GP" not in CATEGORIES:
    CATEGORIES += ["GP"]  # must contain Games Played
IGNORE_STATS = settings.get("ignoredStats")
TEAM_NUMBER = int(settings.get("teamNumber")) - 1  # switch to 0 indexing
IGNORE_PLAYERS = settings.get("ignorePlayers")
MAX_PLAYERS = int(settings.get("maxPlayers"))
