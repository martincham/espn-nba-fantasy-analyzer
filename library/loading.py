from espn_api.basketball import League
import json
import pickle
import os
import time
import library.config as config

LEAGUE_FILE = config.LEAGUE_FILE
FREE_AGENTS_FILE = config.FREE_AGENTS_FILE
SETTING_FILE = config.SETTING_FILE


def saveFile(filename, data):
    try:
        with open(filename, "wb") as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as ex:
        print("Error during pickling object (Possibly unsupported):", ex)


def loadFile(filename):
    try:
        with open(filename, "rb") as f:
            return pickle.load(f)
    except Exception as ex:
        print("Error during unpickling object (Possibly unsupported):", ex)


# Returns league, or 0 if error
def reloadLeague():
    try:
        file = open(SETTING_FILE, "rb")
        fileInfo = file.read()
        leagueInfo = json.loads(fileInfo)
        league = League(
            league_id=leagueInfo.get("leagueId"),
            year=2024,
            espn_s2=leagueInfo.get("espn_s2"),
            swid=leagueInfo.get("SWID"),
            debug=False,
        )
        file.close()
    except FileNotFoundError as ex:
        print("Could not find login file:", ex)
        return 0
    except Exception as ex:
        print("Error loading league: ", ex)
        return 0
    saveLeague(league)
    return league


def loadLeague():
    return loadFile(LEAGUE_FILE)


def saveLeague(league):
    saveFile(LEAGUE_FILE, league)


def reloadFreeAgents(league=League):
    freeAgents = league.free_agents(size=500)
    saveFreeAgents(freeAgents)
    return freeAgents


def saveFreeAgents(freeAgents):
    saveFile(FREE_AGENTS_FILE, freeAgents)


def loadFreeAgents():
    return loadFile(FREE_AGENTS_FILE)


def getLeagueSavedTime():
    modifiedTime = os.path.getmtime(LEAGUE_FILE)
    return time.ctime(modifiedTime)
