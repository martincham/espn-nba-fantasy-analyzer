import json

ROSTER_POSITIONS = []
IGNORE_STATS = []
CATEGORIES = ["FG%", "FT%", "3PM", "REB", "AST", "STL", "BLK", "TO", "PTS"]  # default
TIMEFRAMES = ["_total", "_last_30", "_last_15", "_last_7"]  # suffixes
# files
SETTING_FILE = "settings.txt"
LEAGUE_FILE = "league.pickle"
FREE_AGENTS_FILE = "freeagents.pickle"
# spreadsheet settings
RED_RGB = [0.91, 0.49, 0.45]
WHITE_RGB = [1, 1, 1]
GREEN_RGB = [0.3, 0.8, 0.6]
# load from setting file
file = open(SETTING_FILE, "r")
fileInfo = file.read()
settings = json.loads(fileInfo)
file.close()

ROSTER_POSITIONS = settings.get("rosterPositions")
CATEGORIES = settings.get("categories")
IGNORE_STATS = settings.get("ignoredStats")
TEAM_NUMBER = int(settings.get("teamNumber")) - 1  # switch to 0 indexing
IGNORE_PLAYERS = settings.get("ignorePlayers")
MAX_PLAYERS = int(settings.get("maxPlayers"))
SEASON_ID = int(settings.get("seasonId"))
TIMEFRAMES = [SEASON_ID + word for word in TIMEFRAMES]
