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
    "FG%",
    "FT%",
    "GP",
]  # default
TIMEFRAMES = ["_total", "_last_30", "_last_15", "_last_7"]  # suffixes
PERCENT_STATS = ["FG%", "AFG%", "FT%", "3P%", "A/TO", "STR", "FTR"]
PERCENT_MAP = {
    "FG%": ["FGM", "FGA"],
    "AFG%": ["FGM", "FGA"],
    "FT%": ["FTM", "FTA"],
    "3P%": ["3PM", "3PA"],
    "A/TO": ["AST", "TO"],
    "STR": ["STL", "TO"],
    "FTR": ["FTA", "FGA"],
}
NEGATIVE_STATS = ["TO"]
INJURY_MAP = {
    "ACTIVE": "H",
    "OUT": "OUT",
    "DAY_TO_DAY": "D2D",
}
VALID_POSITIONS = ["PG", "SG", "SF", "PF", "C"]
# files
SETTING_FILE = "settings.txt"
LEAGUE_FILE = "league.pickle"
FREE_AGENTS_FILE = "freeAgents.pickle"
# spreadsheet settings
RED_RGB = [0.91, 0.49, 0.45]
WHITE_RGB = [1, 1, 1]
GREEN_RGB = [0.3, 0.8, 0.6]
YELLOW_RGB = [1, 1, 0.8]
GRAY_RGB = [0.8, 0.8, 0.8]
BLUE_RGB = [0.522, 0.601, 1]
ORANGE_RGB = [1, 0.878, 0.545]

# load from setting file
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
            "GP",
        ],
        "ignoredStats": ["FTM", "FTA", "TO", "FGA", "FGM", "GP"],
        "rosterPositions": ["PG", "F", "SG/SF", "SG/SF", "SG/SF", "PF/C", "UT"],
        "teamSize": 12,
        "ignorePlayers": 3,
        "maxPlayers": 7,
    }
    with open(SETTING_FILE, "w") as file:
        json.dump(settings, file, indent=4)  # `indent=4` formats JSON for readability

POSITION_HEIRARCHY = ["SG/SF", "SG/SF", "SG/SF", "PG", "F", "PF/C", "UT"]
SEASON_ID = int(settings.get("seasonId"))
SWID = settings.get("SWID")
ESPN_S2 = settings.get("espn_s2")
LEAGUE_ID = settings.get("leagueId")
TIMEFRAMES = [str(SEASON_ID) + suffix for suffix in TIMEFRAMES]

ROSTER_POSITIONS = settings.get("rosterPositions")
TEAM_SIZE = settings.get("teamSize")
CATEGORIES = settings.get("categories")
if "GP" not in CATEGORIES:
    CATEGORIES += ["GP"]  # must contain Games Played for per-game calculations
if "MIN" not in CATEGORIES:
    CATEGORIES += ["MIN"]  # must contain Minutes for per-minute calculations
IGNORE_STATS = settings.get("ignoredStats")
if "MIN" not in IGNORE_STATS:
    IGNORE_STATS += ["MIN"]  # must contain Minutes Played
TEAM_NUMBER = int(settings.get("teamNumber")) - 1  # switch to 0 indexing
IGNORE_PLAYERS = settings.get("ignorePlayers")
MAX_PLAYERS = int(settings.get("maxPlayers"))
