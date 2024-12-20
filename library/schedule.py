# schedule.py calculates games remaining for each pro team, and how it affects your teams schedule.


from datetime import date
from copy import deepcopy
from typing import Dict, List
from espn_api.basketball import League, Team, Player
import library.config as c


# Extra games is the number of games a team will play on days where you have space for an extra game.
def calculateExtraRemainingGames(
    league: League,
    averages: Dict[str, float],
    teamNumber: int,
    ignorePlayers: int = 0,
) -> Dict[str, int]:
    remainingGames = {}
    teamCount = 0
    now = date.today()

    if teamNumber > len(league.teams) - 1:
        print("Error: teamNumber is greater than number of teams in league")
        return {"ALL": 0}
    myTeam = deepcopy(league.teams[teamNumber])
    # Sorts roster by whole season per-game rating, then remove the worst IGNORE_PLAYERS from roster
    ratedRoster = {
        player: (
            0
            if player.stats.get(c.TIMEFRAMES[0]) is None
            else ratePlayer(
                playerStats=player.stats.get(c.TIMEFRAMES[0]).get("avg"),
                averages=averages,
            )
        )
        for player in myTeam.roster
    }
    sortedRoster = sorted(ratedRoster.items(), key=lambda x: x[1], reverse=True)
    finalRoster = [player for (player, rating) in sortedRoster]
    if ignorePlayers > 0:
        del finalRoster[-ignorePlayers:]  # removes last X players from list
    mySchedule = myTeamSchedule(finalRoster)

    teams = league.teams
    for team in teams:
        roster = team.roster
        for player in roster:
            proTeam = player.proTeam
            if proTeam in remainingGames:
                continue
            gameCount = 0
            schedule = player.schedule
            for game in schedule.values():
                gameTime = game.get("date")
                gameDay = gameTime.date()
                if gameDay > now:
                    if gameDay in mySchedule:
                        if mySchedule.get(gameDay) < c.MAX_PLAYERS:
                            gameCount += 1
            remainingGames[proTeam] = gameCount
            teamCount += 1
            if teamCount > 29:
                break
        if teamCount > 29:
            break
    return remainingGames


# Remaining games is the number of games remaining for each team in the league.
def calculateRemainingGames(league: League) -> Dict[str, int]:
    remainingGames = {}
    teamCount = 0
    now = date.today()

    teams = league.teams
    for team in teams:
        roster = team.roster
        for player in roster:
            proTeam = player.proTeam
            if proTeam in remainingGames:
                continue
            gameCount = 0
            schedule = player.schedule
            for game in schedule.values():
                gameTime = game.get("date")
                gameDay = gameTime.date()
                if gameDay > now:
                    gameCount += 1
            remainingGames[proTeam] = gameCount
            teamCount += 1
            if teamCount > 29:  # found all 30 teams in league
                break
        if teamCount > 29:
            break
    return remainingGames


def myTeamSchedule(playerList: List[Player]) -> Dict[date, int]:
    teamSchedule = {}
    for player in playerList:
        schedule = player.schedule
        for game in schedule.values():
            gameTime = game.get("date")
            gameDay = gameTime.date()
            if gameDay in teamSchedule:
                newGames = teamSchedule[gameDay] + 1
                teamSchedule[gameDay] = newGames
            else:
                teamSchedule[gameDay] = 1
    return teamSchedule


# Duplicate rating code from rating.py. Needed here to sort players on the rosters by value, and to avoid circular imports.
# Least X valued players can be dropped. X = "ignoredPlayers" in settings.txt


def ratePercentStat(
    playerStats: Dict[str, float], averages: Dict[str, float], stat: str
) -> float:
    rawStats = c.PERCENT_MAP.get(stat, None)
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


def ratePlayer(playerStats: Dict[str, float], averages: Dict[str, float]) -> float:
    totalRating = 0
    statCount = 0
    if playerStats is None:
        return 0
    for stat in averages:
        if stat in c.IGNORE_STATS:
            continue
        if stat in c.PERCENT_STATS:
            totalRating += ratePercentStat(playerStats, averages, stat)
            statCount += 1
        else:
            playerStat = playerStats.get(stat)
            averageStat = averages.get(stat)
            statRating = playerStat / averageStat
            if statRating != 0 and stat in c.NEGATIVE_STATS:
                statRating = 2 - statRating
            totalRating += statRating
            statCount += 1
    totalRating = (totalRating / statCount) * 100
    return totalRating
