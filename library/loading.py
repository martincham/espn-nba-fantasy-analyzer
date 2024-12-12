from typing import List
import json
import pickle
import os
import time
from espn_api.basketball import League, Player
import library.config as c

LEAGUE_FILE = c.LEAGUE_FILE
FREE_AGENTS_FILE = c.FREE_AGENTS_FILE
SETTING_FILE = c.SETTING_FILE


def saveFile(filename: str, data):
    try:
        with open(filename, "wb") as f:
            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as ex:
        print("Error during pickling object (Possibly unsupported):", ex)


def loadFile(filename: str):
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
            league_id=c.LEAGUE_ID,
            year=c.SEASON_ID,
            espn_s2=c.ESPN_S2,
            swid=c.SWID,
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


def saveLeague(league: League):
    saveFile(LEAGUE_FILE, league)


def reloadFreeAgents(league: League):
    freeAgents = league.free_agents(size=500)
    saveFreeAgents(freeAgents)
    return freeAgents


def saveFreeAgents(freeAgents: List[Player]):
    saveFile(FREE_AGENTS_FILE, freeAgents)


def loadFreeAgents():
    return loadFile(FREE_AGENTS_FILE)


def getLeagueSavedTime():
    modifiedTime = os.path.getmtime(LEAGUE_FILE)
    return time.ctime(modifiedTime)
