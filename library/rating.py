from typing import Dict, List, Any
import library.schedule as schedule
import library.config as config
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


def combineTotalRatingTimeframes(
    team: Team,
    IGNORE_STATS: List[str],
    averagesWhole: Dict[str, float] = None,
    averagesSeven: Dict[str, float] = None,
    averagesFifteen: Dict[str, float] = None,
    averagesThirty: Dict[str, float] = None,
) -> pd.DataFrame:
    seasonRatings = rosterRater(
        TIMEFRAMES[0], "total", team, averagesWhole, IGNORE_STATS
    )
    thirtyRating = rosterRater(
        TIMEFRAMES[1], "total", team, averagesThirty, IGNORE_STATS
    )
    fifteenRatings = rosterRater(
        TIMEFRAMES[2], "total", team, averagesFifteen, IGNORE_STATS
    )
    sevenRatings = rosterRater(
        TIMEFRAMES[3], "total", team, averagesSeven, IGNORE_STATS
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
        # must calculate averages seperately for totals
        # e.g. total points scored over 2 weeks is higher than over 1 week
        averagesWhole = calculateLeagueAverages(
            league, TIMEFRAMES[0], totalOrAvg=totalOrAvg
        )
        averagesThirty = calculateLeagueAverages(
            league, TIMEFRAMES[1], totalOrAvg=totalOrAvg
        )
        averagesFifteen = calculateLeagueAverages(
            league, TIMEFRAMES[2], totalOrAvg=totalOrAvg
        )
        averagesSeven = calculateLeagueAverages(
            league, TIMEFRAMES[3], totalOrAvg=totalOrAvg
        )

        for team in teams:
            teamRating = combineTotalRatingTimeframes(
                team,
                IGNORE_STATS,
                averagesWhole,
                averagesSeven,
                averagesFifteen,
                averagesThirty,
            )
            frames.append(teamRating)
    else:
        # on the other hand, this just uses season averages
        averages = calculateLeagueAverages(league, totalOrAvg=totalOrAvg)
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
        for timeframe in TIMEFRAMES:
            averages = calculateLeagueAverages(league, timeframe, totalOrAvg=totalOrAvg)
            frame = rateFreeAgents(
                timeframe, "total", freeAgents, averages, IGNORE_STATS
            )
            frames.append(frame)
    else:
        averages = calculateLeagueAverages(league, TIMEFRAMES[0], totalOrAvg=totalOrAvg)
        for timeframe in TIMEFRAMES:
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


def compositeRateTeamCats(
    league: League,
    timeFrames,
    totalOrAvg: str,
    categoryList: List[str],
    IGNORE_STATS: List[str],
) -> List[List[Any]]:
    resultMatrix = [categoryList]
    if totalOrAvg == "total":
        for timeframe in timeFrames:
            averages = calculateLeagueAverages(
                league=league, timeframe=timeframe, totalOrAvg=totalOrAvg
            )
    else:
        averages = calculateLeagueAverages(
            league=league, timeframe=timeFrames, totalOrAvg=totalOrAvg
        )

    return resultMatrix


def categoryRateTeams(
    league: League,
    timeframe: str,
    totalOrAvg: str,
    categoryList: List[str],
    IGNORE_STATS: List[str] = ["GP"],
) -> List[List[Any]]:
    averages = calculateLeagueAverages(
        league=league, timeframe=timeframe, totalOrAvg=totalOrAvg
    )
    averages.update({"FG%": averages.get("FGM") / averages.get("FGA")})
    averages.update({"FT%": averages.get("FTM") / averages.get("FTA")})
    titles = categoryList.copy()
    titles.extend(["Rating", "Player Name", "Team", "Pro Team"])
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
    averages = calculateLeagueAverages(
        league=league, timeframe=timeframe, totalOrAvg=totalOrAvg
    )
    titles = categoryList.copy()
    titles.extend(["Rating", "Player Name", "Team", "Pro Team"])
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
        resultMatrix.append(playerMatrix)

    return resultMatrix


def createPlayerMatrix(
    playerStats: Dict[str, float],
    averages: Dict[str.float],
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
    timeframes: List[str],
    totalOrAvg: str = "avg",
    IGNORE_STATS: List[str] = ["GP"],
) -> List[List[Any]]:
    averages = calculateLeagueAverages(
        league=league, timeframe=TIMEFRAMES[0], totalOrAvg=totalOrAvg
    )
    resultMatrix = []
    resultMatrix.append(
        [
            "total",
            "t diff",
            "30",
            "30diff",
            "15",
            "15diff",
            "7",
            "7diff",
            "Player Name",
            "Team",
            "Pro Team",
        ]
    )
    teams = league.teams

    remaningGames = schedule.calculateRemainingGames(league=league)
    remainingExtraGames = schedule.calculateExtraRemainingGames(
        league=league, teamNumber=TEAM_NUMBER, ignorePlayers=IGNORE_PLAYERS
    )
    for team in teams:
        roster = team.roster
        for player in roster:
            playerRatingList = []
            proTeam = player.proTeam
            for timeframe in timeframes:
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
                remGames = remaningGames.get(proTeam)
                extraGames = remainingExtraGames.get(proTeam)
                notExtraGames = remGames - extraGames

                totalRating = remGames * rating
                extraGamesRating = extraGames * rating
                notExtraGamesRating = notExtraGames * (rating - 80)
                adjustedRating = extraGamesRating + notExtraGamesRating
                scheduleValue = adjustedRating - totalRating
                playerRatingList.append(adjustedRating)
                playerRatingList.append(scheduleValue)
            playerRatingList.append(player.name)
            playerRatingList.append(team.team_name)
            playerRatingList.append(proTeam)
            resultMatrix.append(playerRatingList)
    return resultMatrix


def remainingRateFreeAgents(
    league: League,
    freeAgents: List[Player],
    timeframes: List[str],
    totalOrAvg: str = "avg",
    IGNORE_STATS: List[str] = ["GP"],
) -> List[List[Any]]:
    averages = calculateLeagueAverages(
        league=league, timeframe=TIMEFRAMES[0], totalOrAvg=totalOrAvg
    )
    resultMatrix = []
    resultMatrix.append(
        [
            "total",
            "t diff",
            "30",
            "30diff",
            "15",
            "15diff",
            "7",
            "7diff",
            "Player Name",
            "Pro Team",
        ]
    )

    remaningGames = schedule.calculateRemainingGames(league=league)
    remainingExtraGames = schedule.calculateExtraRemainingGames(
        league=league, teamNumber=TEAM_NUMBER, ignorePlayers=IGNORE_PLAYERS
    )
    for player in freeAgents:
        playerRatingList = []
        proTeam = player.proTeam
        remGames = remaningGames.get(proTeam)
        if remGames is None:
            continue  # Player is a free agent (in the real NBA, not fantasy) ond not on a team
        extraGames = remainingExtraGames.get(proTeam)
        notExtraGames = remGames - extraGames
        for timeframe in timeframes:
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
            notExtraGamesRating = notExtraGames * (rating - 80)
            adjustedRating = extraGamesRating + notExtraGamesRating
            scheduleValue = adjustedRating - totalRating
            playerRatingList.append(adjustedRating)
            playerRatingList.append(scheduleValue)
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
    totalOrAvg: str = "total",
    IGNORE_STATS: List[str] = ["GP"],
) -> List[List[Any]]:
    pass
