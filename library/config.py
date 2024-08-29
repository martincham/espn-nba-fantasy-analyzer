import json

ROSTER_POSITIONS = []
IGNORE_STATS = []
TIMEFRAMES = ["2024_total", "2024_last_30", "2024_last_15", "2024_last_7"]
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
IGNORE_STATS = settings.get("ignoredStats")
TEAM_NUMBER = int(settings.get("teamNumber")) - 1
IGNORE_PLAYERS = settings.get("ignorePlayers")
MAX_PLAYERS = int(settings.get("maxPlayers"))
