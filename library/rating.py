from typing import Dict, List, Any
from espn_api.basketball import League, Team, Player
import library.config as config
import library.globals as g

CATEGORIES = {cat: 0 for cat in config.CATEGORIES}
CATEGORY_LIST = config.CATEGORIES
TEAM_NUMBER = config.TEAM_NUMBER
IGNORE_PLAYERS = config.IGNORE_PLAYERS
PERCENT_STATS = config.PERCENT_STATS
NEGATIVE_STATS = config.NEGATIVE_STATS
PERCENT_MAP = config.PERCENT_MAP
INJURY_MAP = config.INJURY_MAP
VALID_POSITIONS = config.VALID_POSITIONS
SEASON_ID = config.SEASON_ID
TIMEFRAMES = config.TIMEFRAMES
IGNORE_STATS = config.IGNORE_STATS


def getPlayerPosition(player: Player) -> str:
    slots = player.eligibleSlots
    result = ""
    for slot in slots:
        if slot in VALID_POSITIONS:
            result += "/" + slot
    result = result[1:]
    return result


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
            if statRating != 0 and stat in NEGATIVE_STATS:
                statRating = 2 - statRating
            totalRating += statRating
            statCount += 1
    totalRating = (totalRating / statCount) * 100
    return totalRating


def leagueTeamRatings(league: League, totalOrAvg: str = "total") -> List[List[Any]]:
    resultMatrix = [
        ["Total", "30", "15", "7", "Player", "Team", "ProT", "Inj", "Pos", "+Gms"]
    ]
    teams = league.teams
    for team in teams:
        roster = team.roster
        teamMatrix = ratePlayerList(
            playerList=roster, totalOrAvg=totalOrAvg, teamName=team.team_abbrev
        )
        resultMatrix.extend(teamMatrix)
    return resultMatrix


def ratePlayerList(
    playerList: List[Player],
    totalOrAvg: str,
    teamName: str = "?",
) -> List[List[Any]]:
    resultMatrix = []
    for player in playerList:
        playerMatrix = []
        for index, timeframe in enumerate(TIMEFRAMES):
            if totalOrAvg == "total":
                averages = g.TOTAL_AVERAGES[index]
            else:
                averages = g.PER_GAME_AVERAGES[index]
            stats = player.stats.get(timeframe)
            playerStats = stats.get(totalOrAvg)
            proTeam = player.proTeam
            if playerStats is None:
                playerRating = 0
            else:
                playerRating = ratePlayer(
                    playerStats=playerStats,
                    averages=averages,
                    IGNORE_STATS=IGNORE_STATS,
                )
            playerMatrix.append(playerRating)
        playerMatrix.append(player.name)
        injuryStatus = player.injuryStatus
        if not isinstance(injuryStatus, str):
            injuryStatus = "?"

        playerMatrix.append(teamName if teamName is not None else "")
        playerMatrix.append(proTeam if proTeam is not None else "")
        injuryCode = INJURY_MAP.get(str(player.injuryStatus))
        playerMatrix.append(injuryCode if injuryCode is not None else "")
        playerMatrix.append(getPlayerPosition(player=player))
        playerMatrix.append(g.EXTRA_GAMES.get(proTeam, ""))
        resultMatrix.append(playerMatrix)

    return resultMatrix


def leagueFreeAgentRatings(
    freeAgents: List[Player],
    totalOrAvg: str = "total",
) -> List[List[Any]]:
    resultMatrix = [
        ["Total", "30", "15", "7", "Player", "Team", "ProT", "Inj", "Pos", "+Gms"]
    ]
    resultMatrix.extend(ratePlayerList(playerList=freeAgents, totalOrAvg=totalOrAvg))
    return resultMatrix


def categoryRateTeams(
    league: League,
    timeframe: str,
    totalOrAvg: str,
    categoryList: List[str],
    IGNORE_STATS: List[str] = ["GP"],
) -> List[List[Any]]:
    if totalOrAvg == "avg":
        averages = g.PER_GAME_AVERAGES[TIMEFRAMES.index(timeframe)]
    else:
        averages = g.TOTAL_AVERAGES[TIMEFRAMES.index(timeframe)]
    titles = categoryList.copy()
    titles.extend(["Rating", "Player Name", "Team", "ProT", "Inj", "Pos", "+Gms"])
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
            team.team_abbrev,
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
        averages = g.PER_GAME_AVERAGES[TIMEFRAMES.index(timeframe)]
    else:
        averages = g.TOTAL_AVERAGES[TIMEFRAMES.index(timeframe)]

    titles = categoryList.copy()
    titles.extend(["Rating", "Player Name", "Team", "ProT", "Inj", "Pos", "+Gms"])
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
            playerMatrix = categoryRatePlayer(
                playerStats, averages, categoryList, IGNORE_STATS
            )
            player
        playerMatrix.append(player.name)
        injuryStatus = player.injuryStatus
        if not isinstance(injuryStatus, str):
            injuryStatus = "?"

        playerMatrix.append(teamName if teamName is not None else "")
        playerMatrix.append(proTeam if proTeam is not None else "")
        injuryCode = INJURY_MAP.get(str(player.injuryStatus))
        playerMatrix.append(injuryCode if injuryCode is not None else "")
        playerMatrix.append(getPlayerPosition(player=player))
        playerMatrix.append(g.EXTRA_GAMES.get(proTeam, ""))
        resultMatrix.append(playerMatrix)

    return resultMatrix


def categoryRatePlayer(
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
            statRating = stat / statAverage
            if statRating != 0 and cat in NEGATIVE_STATS:
                statRating = 2 - statRating
            statRating = statRating * 100
            playerMatrix.append(statRating)
    playerMatrix.append(ratePlayer(playerStats, averages, IGNORE_STATS))
    return playerMatrix


def remainingRateTeams(league: League) -> List[List[Any]]:
    resultMatrix = []
    resultMatrix.append(
        [
            "Total",
            "T+",
            "30",
            "30+",
            "15",
            "15+",
            "7",
            "7+",
            "+Gms",
            "Player Name",
            "Team",
            "ProT",
        ]
    )
    teams = league.teams

    for team in teams:
        roster = team.roster
        teamMatrix = remainingRatePlayerList(roster, teamName=team.team_abbrev)
        resultMatrix.extend(teamMatrix)
    return resultMatrix


def remainingRatePlayerList(
    playerList: List[Player], teamName: str = "?"
) -> List[List[Any]]:
    averages = g.PER_GAME_AVERAGES[0]
    remainingGames = g.REMAINING_GAMES
    remainingExtraGames = g.EXTRA_GAMES
    avgExtraGames = sum(remainingExtraGames.values()) / len(remainingExtraGames)
    resultMatrix = []
    for player in playerList:
        playerMatrix = []
        proTeam = player.proTeam
        remGames = remainingGames.get(proTeam)
        if remGames is None:
            continue  # Player is a free agent (in the real NBA, not fantasy) ond not on a team
        extraGames = remainingExtraGames.get(proTeam)
        for timeframe in TIMEFRAMES:
            playerStats = player.stats.get(timeframe)
            playerAvgStats = playerStats.get("avg")
            if playerAvgStats is None:
                playerMatrix.append(0)
                playerMatrix.append(0)
                continue
            rating = ratePlayer(
                playerStats=playerAvgStats,
                averages=averages,
                IGNORE_STATS=IGNORE_STATS,
            )
            adjustedRating = rating * (extraGames / avgExtraGames)
            scheduleValue = adjustedRating - rating
            playerMatrix.append(adjustedRating)
            playerMatrix.append(scheduleValue)
        # Don't add player if they have no data
        if all(x == 0 for x in playerMatrix):
            continue
        playerMatrix.append(extraGames)
        playerMatrix.append(player.name)
        playerMatrix.append(teamName)
        playerMatrix.append(proTeam)
        resultMatrix.append(playerMatrix)
    return resultMatrix


def remainingRateFreeAgents(freeAgents: List[Player]) -> List[List[Any]]:
    resultMatrix = []
    resultMatrix.append(
        [
            "Total",
            "T+",
            "30",
            "30+",
            "15",
            "15+",
            "7",
            "7+",
            "+Gms",
            "Name",
            "Team",
            "ProT",
        ]
    )
    resultMatrix.extend(remainingRatePlayerList(playerList=freeAgents))
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
    resultMatrix = minuteRateFreeAgents(freeAgents, averagesList=g.TOTAL_AVERAGES)

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
            "ProT",
            "Inj",
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
