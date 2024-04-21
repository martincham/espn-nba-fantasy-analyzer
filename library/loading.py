from espn_api.basketball import League
import json
import pickle
import os
import time

LEAGUEFILE = "league.pickle"
FREEAGENTSFILE = "freeagents.pickle"
SETTINGFILE = "settings.txt"


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
        file = open(SETTINGFILE, "rb")
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
    return loadFile(LEAGUEFILE)


def saveLeague(league):
    saveFile(LEAGUEFILE, league)


def reloadFreeAgents(league=League):
    freeAgents = league.free_agents(size=500)
    saveFreeAgents(freeAgents)
    return freeAgents


def saveFreeAgents(freeAgents):
    saveFile(FREEAGENTSFILE, freeAgents)


def loadFreeAgents():
    return loadFile(FREEAGENTSFILE)


def getLeagueSavedTime():
    modifiedTime = os.path.getmtime(LEAGUEFILE)
    return time.ctime(modifiedTime)
