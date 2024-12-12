from typing import Dict, List, Any
from espn_api.basketball import League, Team, Player
import library.config as config

SEASON_ID = config.SEASON_ID
CATEGORIES = {cat: 0 for cat in config.CATEGORIES}
PERCENT_MAP = config.PERCENT_MAP
PERCENT_STATS = config.PERCENT_STATS
TIMEFRAMES = config.TIMEFRAMES


def calculateLeagueAverages(
    league: League,
    timeframe: str = str(SEASON_ID) + "_total",
    totalOrAvg: str = "total",
) -> Dict[str, int]:
    averages = CATEGORIES.copy()
    for percentStat in PERCENT_MAP.keys():
        if percentStat in averages:
            averages.update({cat: 0 for cat in PERCENT_MAP.get(percentStat)})
    totals = averages.copy()
    playerCount = 0

    teams = league.teams
    for team in teams:
        roster = team.roster
        for player in roster:
            if player.lineupSlot == "IR":  # Ignore Injury Reserve players
                continue
            stats = player.stats
            total = stats.get(timeframe)
            playerCount += mergeStats(totals, total)
    averages = averageStats(
        totals=totals, averages=averages, playerCount=playerCount, totalOrAvg=totalOrAvg
    )
    return averages


def averageStats(
    totals: Dict[str, int],
    averages: Dict[str, float],
    playerCount: int,
    totalOrAvg: str,
) -> Dict[str, float]:
    if totalOrAvg == "avg":
        divisor = totals.get("GP")
    else:
        divisor = playerCount
    for stat in totals:
        if stat in PERCENT_STATS or stat == "GP":
            statAverage = totals.get(stat) / playerCount
        else:
            statAverage = totals.get(stat) / divisor
        averages.update({stat: statAverage})
    return averages


def createLeagueAverages(
    league: League, totalOrAvg: str = "total"
) -> List[Dict[str, float]]:
    averageList = []
    for timeframe in TIMEFRAMES:
        averages = calculateLeagueAverages(
            league=league, timeframe=timeframe, totalOrAvg=totalOrAvg
        )
        averageList.append(averages)
    return averageList


# returns 1 if player has stats, 0 otherwise
def mergeStats(resultList: Dict[str, int], adderList) -> int:
    totalValues = adderList.get("total", None)
    if totalValues is None:
        return 0
    for item in resultList:
        value = totalValues.get(item)

        update = resultList.get(item) + value
        resultList.update({item: update})
    return 1
