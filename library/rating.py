from typing import Dict, List, Any
import library.schedule as schedule
import library.config as config
import library.loading as loading
import pandas as pd
from espn_api.basketball import League, Team, Player


# 1. get all players,
#     - loop over all players, create total values
#     - calculate averages
# 2. loop over players again
#     - calculate value rating
CATEGORIES = {cat: 0 for cat in config.CATEGORIES}
TEAM_NUMBER = config.TEAM_NUMBER
IGNORE_PLAYERS = config.IGNORE_PLAYERS
PERCENT_STATS = config.PERCENT_STATS
PERCENT_MAP = config.PERCENT_MAP
SEASON_ID = config.SEASON_ID
TIMEFRAMES = config.TIMEFRAMES
IGNORE_STATS = config.IGNORE_STATS
LEAGUE = loading.loadLeague()


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


def ratePercentStat(
    playerStats: Dict[str, float], averages: Dict[str, float], stat: str
) -> float:
    rawStats = PERCENT_MAP.get(stat, None)
    if rawStats is None:
        return 0
    attempts = playerStats.get(rawStats[1])
    avgAttempts = averages.get(rawStats[1])
    avgMakes = averages.get(rawStats[0])
    percent = playerStats.get(stat)
    # Percent diff will be > 1 if better than average, < 1 if worse
    avgPercent = avgMakes / avgAttempts
    percentDiff = percent / avgPercent
    # Differential gets taken to the power of attempts over/under average
    # E.G. League average % on any attempts will still be rated 100.
    # And +5% percent on 10 attempts is better than +20% on 1 attempt.
    attemptDiff = attempts / avgAttempts
    # Adjust weighting ratio to get normal ranges from 0 to 200
    weightingRatio = 2
    statRating = pow(percentDiff, attemptDiff * weightingRatio)
    return statRating


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
        if stat in PERCENT_STATS:
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


###############
#  AVERAGES  #
##############
TOTAL_AVERAGES = createLeagueAverages(league=LEAGUE, totalOrAvg="total")
PER_GAME_AVERAGES = createLeagueAverages(league=LEAGUE, totalOrAvg="avg")


def ratePlayer(
    playerStats: Dict[str, float], averages: Dict[str, float], IGNORE_STATS: List[str]
) -> float:
    totalRating = 0
    statCount = 0
    if playerStats is None:
        return 0
    for stat in averages:
        if stat in IGNORE_STATS:
            continue
        if stat in PERCENT_STATS:
            totalRating += ratePercentStat(playerStats, averages, stat)
            statCount += 1
        else:
            playerStat = playerStats.get(stat)
            averageStat = averages.get(stat)
            statRating = playerStat / averageStat
            totalRating += statRating
            statCount += 1
    totalRating = (totalRating / statCount) * 100
    return totalRating


def rosterRater(
    timeframe: str,
    totalOrAvg: str,
    team: Team,
    averages: Dict[str, float],
    IGNORE_STATS: List[str],
) -> pd.DataFrame:
    rosterRatings = {}
    roster = team.roster
    for player in roster:
        stats = player.stats.get(timeframe)
        playerAverages = stats.get(totalOrAvg)
        if playerAverages is None:
            rating = 0
        else:
            rating = ratePlayer(playerAverages, averages, IGNORE_STATS)
        name = player.name
        rosterRatings.update({name: rating})
    ratingFrame = pd.DataFrame(rosterRatings, [timeframe])
    ratingFrame = ratingFrame.T
    return ratingFrame


def combineAverageRatingTimeframes(
    team: Team, averages: Dict[str, float], totalOrAvg: str, IGNORE_STATS: List[str]
) -> pd.DataFrame:
    seasonRatings = rosterRater(TIMEFRAMES[0], totalOrAvg, team, averages, IGNORE_STATS)
    thirtyRating = rosterRater(TIMEFRAMES[1], totalOrAvg, team, averages, IGNORE_STATS)
    fifteenRatings = rosterRater(
        TIMEFRAMES[2], totalOrAvg, team, averages, IGNORE_STATS
    )
    sevenRatings = rosterRater(TIMEFRAMES[3], totalOrAvg, team, averages, IGNORE_STATS)

    result = pd.concat(
        [seasonRatings, thirtyRating, fifteenRatings, sevenRatings], axis=1
    )

    result["Player"] = result.index

    teamNameList = [team.team_name] * len(team.roster)
    # teamPositionList = [team.roster[i].position for i in range(len(team.roster))]
    # result["Position"] = teamPositionList
    result["Team"] = teamNameList
    return result


def combineTotalRatingTimeframes(team: Team, IGNORE_STATS: List[str]) -> pd.DataFrame:
    seasonRatings = rosterRater(
        TIMEFRAMES[0], "total", team, TOTAL_AVERAGES[0], IGNORE_STATS
    )
    thirtyRating = rosterRater(
        TIMEFRAMES[1], "total", team, TOTAL_AVERAGES[1], IGNORE_STATS
    )
    fifteenRatings = rosterRater(
        TIMEFRAMES[2], "total", team, TOTAL_AVERAGES[2], IGNORE_STATS
    )
    sevenRatings = rosterRater(
        TIMEFRAMES[3], "total", team, TOTAL_AVERAGES[3], IGNORE_STATS
    )

    result = pd.concat(
        [seasonRatings, thirtyRating, fifteenRatings, sevenRatings], axis=1
    )

    result["Player"] = result.index

    teamNameList = [team.team_name] * len(team.roster)
    result["Team"] = teamNameList
    return result


def leagueTeamRatings(
    league: League, totalOrAvg: str = "total", IGNORE_STATS: List[str] = ["GP"]
) -> pd.DataFrame:
    frames = []
    teams = league.teams
    if totalOrAvg == "total":

        for team in teams:
            teamRating = combineTotalRatingTimeframes(team, IGNORE_STATS)
            frames.append(teamRating)
    else:
        # on the other hand, this just uses season averages
        averages = PER_GAME_AVERAGES[0]
        for team in teams:
            teamRating = combineAverageRatingTimeframes(
                team, averages, totalOrAvg, IGNORE_STATS
            )
            frames.append(teamRating)
    resultFrame = pd.concat(frames)
    return resultFrame


def leagueFreeAgentRatings(
    league: League,
    freeAgents: List[Player],
    totalOrAvg: str = "total",
    IGNORE_STATS: List[str] = ["GP"],
) -> pd.DataFrame:
    frames = []
    if totalOrAvg == "total":
        for index, timeframe in enumerate(TIMEFRAMES):
            averages = TOTAL_AVERAGES[index]
            frame = rateFreeAgents(
                timeframe, "total", freeAgents, averages, IGNORE_STATS
            )
            frames.append(frame)
    else:
        for index, timeframe in enumerate(TIMEFRAMES):
            averages = PER_GAME_AVERAGES[index]
            frame = rateFreeAgents(timeframe, "avg", freeAgents, averages, IGNORE_STATS)
            frames.append(frame)
    ratingFrame = pd.concat(frames, axis=1)
    ratingFrame["Player"] = ratingFrame.index
    return ratingFrame


def rateFreeAgents(
    timeframe: str,
    totalOrAvg: str,
    freeAgents: List[Player],
    averages: Dict[str, float],
    IGNORE_STATS: List[str],
) -> pd.DataFrame:
    freeAgentRating = {}
    for player in freeAgents:
        stats = player.stats.get(timeframe)
        playerStats = stats.get(totalOrAvg)
        if playerStats is None:
            rating = 0
        else:
            rating = ratePlayer(playerStats, averages, IGNORE_STATS)
        name = player.name
        freeAgentRating.update({name: rating})
    ratingFrame = pd.DataFrame(freeAgentRating, [timeframe])
    ratingFrame = ratingFrame.T
    return ratingFrame


def categoryRateTeams(
    league: League,
    timeframe: str,
    totalOrAvg: str,
    categoryList: List[str],
    IGNORE_STATS: List[str] = ["GP"],
) -> List[List[Any]]:
    if totalOrAvg == "avg":
        averages = PER_GAME_AVERAGES[TIMEFRAMES.index(timeframe)]
    else:
        averages = TOTAL_AVERAGES[TIMEFRAMES.index(timeframe)]
    titles = categoryList.copy()
    titles.extend(["Rating", "Player Name", "Team", "Pro Team", "Injury Status"])
    resultMatrix = [titles]
    teams = league.teams
    for team in teams:
        roster = team.roster
        teamMatrix = categoryRatePlayerList(
            roster,
            timeframe,
            totalOrAvg,
            averages,
            categoryList,
            IGNORE_STATS,
            team.team_name,
        )

        resultMatrix.extend(teamMatrix)

    return resultMatrix


def categoryRateFreeAgents(
    league: League,
    freeAgents: List[Player],
    timeframe: str,
    totalOrAvg: str,
    categoryList: List[str],
    IGNORE_STATS: List[str] = ["GP"],
) -> List[List[Any]]:
    if totalOrAvg == "avg":
        averages = PER_GAME_AVERAGES[TIMEFRAMES.index(timeframe)]
    else:
        averages = TOTAL_AVERAGES[TIMEFRAMES.index(timeframe)]

    titles = categoryList.copy()
    titles.extend(["Rating", "Player Name", "Team", "Pro Team", "Injury Status"])
    resultMatrix = [titles]
    freeAgentMatrix = categoryRatePlayerList(
        freeAgents, timeframe, totalOrAvg, averages, categoryList, IGNORE_STATS
    )
    resultMatrix.extend(freeAgentMatrix)
    return resultMatrix


def categoryRatePlayerList(
    playerList: List[Player],
    timeframe: str,
    totalOrAvg: str,
    averages: Dict[str, float],
    categoryList: List[str],
    IGNORE_STATS: List[str],
    teamName: str = "?",
) -> List[List[Any]]:
    resultMatrix = []
    categoryNum = len(categoryList)

    for player in playerList:
        stats = player.stats.get(timeframe)
        playerStats = stats.get(totalOrAvg)
        proTeam = player.proTeam
        if playerStats is None:
            playerMatrix = [0] * (categoryNum + 1)

        else:
            playerMatrix = createPlayerMatrix(
                playerStats, averages, categoryList, IGNORE_STATS
            )
            player
        playerMatrix.append(player.name)
        injuryStatus = player.injuryStatus
        if not isinstance(injuryStatus, str):
            injuryStatus = "?"

        playerMatrix.append(teamName if teamName is not None else "")
        playerMatrix.append(proTeam if proTeam is not None else "")
        playerMatrix.append(str(player.injuryStatus))
        resultMatrix.append(playerMatrix)

    return resultMatrix


def createPlayerMatrix(
    playerStats: Dict[str, float],
    averages: Dict[str, float],
    categoryList: List[str],
    IGNORE_STATS: List[str],
) -> List[float]:
    playerMatrix = []
    for cat in categoryList:
        stat = playerStats.get(cat)
        if stat is None:
            playerMatrix.append(0)
        elif cat in PERCENT_STATS:
            statRating = ratePercentStat(playerStats, averages, cat) * 100
            playerMatrix.append(statRating)
        else:
            statAverage = averages.get(cat)
            statRating = (stat / statAverage) * 100
            playerMatrix.append(statRating)
    playerMatrix.append(ratePlayer(playerStats, averages, IGNORE_STATS))
    return playerMatrix


def remainingRateTeams(
    league: League,
    IGNORE_STATS: List[str] = ["GP"],
) -> List[List[Any]]:
    averages = PER_GAME_AVERAGES[0]

    resultMatrix = []
    resultMatrix.append(
        [
            "total",
            "t bonus",
            "30",
            "30bonus",
            "15",
            "15bonus",
            "7",
            "7diff",
            "Games",
            "Player Name",
            "Team",
            "Pro Team",
        ]
    )
    teams = league.teams

    remainingGames = schedule.calculateRemainingGames(league=league)
    remainingExtraGames = schedule.calculateExtraRemainingGames(
        league=league, teamNumber=TEAM_NUMBER, ignorePlayers=IGNORE_PLAYERS
    )
    for team in teams:
        roster = team.roster
        for player in roster:
            playerRatingList = []
            proTeam = player.proTeam
            remGames = remainingGames.get(proTeam)
            if remGames is None:
                continue  # Player is a free agent (in the real NBA, not fantasy) ond not on a team
            extraGames = remainingExtraGames.get(proTeam)
            redundantGames = remGames - extraGames
            for timeframe in TIMEFRAMES:
                playerStats = player.stats.get(timeframe)
                playerAvgStats = playerStats.get("avg")
                if playerAvgStats is None:
                    playerRatingList.append(0)
                    playerRatingList.append(extraGames)
                    continue
                rating = ratePlayer(
                    playerStats=playerAvgStats,
                    averages=averages,
                    IGNORE_STATS=IGNORE_STATS,
                )

                totalRating = remGames * rating
                extraGamesRating = extraGames * rating
                redundantGamesRating = redundantGames * (rating - 80)
                adjustedRating = extraGamesRating + redundantGamesRating
                scheduleValue = adjustedRating - totalRating
                playerRatingList.append(adjustedRating)
                playerRatingList.append(extraGamesRating)
            playerRatingList.append(extraGames)
            playerRatingList.append(player.name)
            playerRatingList.append(team.team_name)
            playerRatingList.append(proTeam)
            resultMatrix.append(playerRatingList)
    return resultMatrix


def remainingRateFreeAgents(
    league: League,
    freeAgents: List[Player],
    IGNORE_STATS: List[str] = ["GP"],
) -> List[List[Any]]:
    averages = TOTAL_AVERAGES[0]
    resultMatrix = []
    resultMatrix.append(
        [
            "total",
            "t bonus",
            "30",
            "30bonus",
            "15",
            "15bonus",
            "7",
            "7diff",
            "Games",
            "Player Name",
            "Team",
            "Pro Team",
        ]
    )

    remainingGames = schedule.calculateRemainingGames(league=league)
    remainingExtraGames = schedule.calculateExtraRemainingGames(
        league=league, teamNumber=TEAM_NUMBER, ignorePlayers=IGNORE_PLAYERS
    )
    for player in freeAgents:
        playerRatingList = []
        proTeam = player.proTeam
        remGames = remainingGames.get(proTeam)
        if remGames is None:
            continue  # Player is a free agent (in the real NBA, not fantasy) ond not on a team
        extraGames = remainingExtraGames.get(proTeam)
        redundantGames = remGames - extraGames
        for timeframe in TIMEFRAMES:
            playerStats = player.stats.get(timeframe)
            playerAvgStats = playerStats.get("avg")
            if playerAvgStats is None:
                playerRatingList.append(0)
                playerRatingList.append(0)
                continue
            rating = ratePlayer(
                playerStats=playerAvgStats,
                averages=averages,
                IGNORE_STATS=IGNORE_STATS,
            )

            totalRating = remGames * rating
            extraGamesRating = extraGames * rating
            redundantGamesRating = redundantGames * (rating - 80)
            adjustedRating = extraGamesRating + redundantGamesRating
            scheduleValue = adjustedRating - totalRating
            playerRatingList.append(adjustedRating)
            playerRatingList.append(extraGamesRating)
        playerRatingList.append(extraGames)
        playerRatingList.append(player.name)
        playerRatingList.append(proTeam)
        resultMatrix.append(playerRatingList)
    return resultMatrix


def minuteTeamRatings(
    league: League, totalOrAvg: str = "total", IGNORE_STATS: List[str] = ["GP"]
) -> List[List[Any]]:
    pass


def minuteFreeAgentRatings(
    league: League,
    freeAgents: List[Player],
) -> List[List[Any]]:
    CATEGORIES.update({"MIN": 0})
    resultMatrix = minuteRateFreeAgents(freeAgents, averagesList=TOTAL_AVERAGES)

    CATEGORIES.pop("MIN", None)
    return resultMatrix


def minuteRateFreeAgents(
    freeAgents: List[Player],
    averagesList: List[Dict[str, float]],
) -> List[List[Any]]:
    resultMatrix = [
        [
            "total",
            "tMPG",
            "30",
            "30MPGs",
            "15",
            "15MPG",
            "7",
            "7MPG",
            "Player Name",
            "Pro Team",
            "Injury Status",
        ]
    ]
    for player in freeAgents:
        playerMatrix = []
        for index, timeframe in enumerate(TIMEFRAMES):
            averages = averagesList[index]
            stats = player.stats.get(timeframe)
            playerStats = stats.get("total")
            if playerStats is None:
                playerMatrix += [0] * 2
            else:
                playerMatrix += [minuteRatePlayer(playerStats, averages)]
                playerMatrix += [playerStats.get("MIN") / playerStats.get("GP")]
        playerMatrix.append(player.name)
        playerMatrix.append(player.proTeam)
        injuryStatus = player.injuryStatus
        if not isinstance(injuryStatus, str):
            injuryStatus = "?"
        playerMatrix.append(injuryStatus)
        resultMatrix.append(playerMatrix)
    return resultMatrix


def minuteRatePlayer(
    playerStats: Dict[str, float], averages: Dict[str, float]
) -> float:
    totalRating = 0
    statCount = 0
    playerMinutes = playerStats.get("MIN")
    averageMinutes = averages.get("MIN")
    if playerMinutes is None or averageMinutes is None:
        return 0
    if playerMinutes == 0 or averageMinutes == 0:
        return 0
    for stat in averages:
        if stat in IGNORE_STATS:
            continue
        if stat in PERCENT_STATS:
            totalRating += ratePercentStat(playerStats, averages, stat)
            statCount += 1
        else:
            playerStat = playerStats.get(stat)
            averageStat = averages.get(stat)
            playerStatPerMinute = playerStat / playerMinutes
            averageStatPerMinute = averageStat / averageMinutes
            statRating = playerStatPerMinute / averageStatPerMinute
            totalRating += statRating
            statCount += 1
    totalRating = (totalRating / statCount) * 100
    return totalRating
