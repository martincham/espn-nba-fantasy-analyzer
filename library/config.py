ROSTER_POSITIONS = []
IGNORESTATS = ["FTM", "FTA", "TO", "FGA", "FGM", "GP"]
TIMEFRAMES = ["2024_total", "2024_last_30", "2024_last_15", "2024_last_7"]
SETTINGFILE = "settings.txt"
RED_RGB = [1, 0.7, 0.7]
WHITE_RGB = [1, 1, 1]
GREEN_RGB = [0.3, 0.8, 0.6]

file = open(SETTINGFILE, "r")
fileInfo = file.read()
settings = json.loads(fileInfo)
file.close()

ROSTER_POSITIONS = settings.get("rosterPositions")
IGNORESTATS = settings.get("ignoredStats")
TEAMID = settings.get("teamId")
