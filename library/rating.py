import pandas as pd

import library.schedule as schedule


# 1. get all players,
#     - loop over all players, create total values
#     - calculate averages
# 2. loop over players again
#     - calculate value rating
CATEGORIES = {
    "PTS": 0,
    "BLK": 0,
    "STL": 0,
    "AST": 0,
    "REB": 0,
    "3PTM": 0,
    "TO": 0,
    "FTM": 0,
    "FTA": 0,
    "FGM": 0,
    "FGA": 0,
    "GP": 0,
}


def calculateLeagueAverages(league, timeframe="2024_total", totalOrAvg="total"):
    averages = CATEGORIES.copy()
    totals = averages.copy()
    count = 0

    teams = league.teams
    for team in teams:
        roster = team.roster
        for player in roster:
            stats = player.stats
            total = stats.get(timeframe)
            mergeStats(totals, total)
            count += 1
    averages = averageStats(
        totals=totals, averages=averages, count=count, totalOrAvg=totalOrAvg
    )
    return averages


def ratePlayer(playerStats, averages, ignoreStats):
    totalRating = 0
    for stat in averages:
        if stat in ignoreStats:
            continue
        playerStat = playerStats.get(stat)
        averageStat = averages.get(stat)
        statRating = playerStat / averageStat
        totalRating += statRating
    remainingNumStats = len(averages) - len(ignoreStats)
    totalRating = (totalRating / remainingNumStats) * 100
    return totalRating


def averageStats(totals, averages, count, totalOrAvg):
    if totalOrAvg == "avg":
        divisor = totals.get("GP")
    else:
        divisor = count
    for stat in totals:
        statAverage = totals.get(stat) / divisor
        averages.update({stat: statAverage})
    return averages


def mergeStats(resultList, adderList):
    totalValues = adderList.get("total")
    if totalValues is None:
        return
    for item in resultList:
        value = totalValues.get(item)
        update = resultList.get(item) + value
        resultList.update({item: update})


def rosterRater(timeframe, totalOrAvg, team, averages, ignoreStats):
    teamMatrix = []
    roster = team.roster
    for player in roster:
        playerMatrix = []
        stats = player.stats.get(timeframe)
        playerAverages = stats.get(totalOrAvg)
        if playerAverages is None:
            rating = 0
        else:
            rating = ratePlayer(playerAverages, averages, ignoreStats)
        name = player.name
        rosterRatings.update({name: rating})
    ratingFrame = pd.DataFrame(rosterRatings, [timeframe])
    ratingFrame = ratingFrame.T
    return ratingFrame


def combineAverageRatingTimeframes(team, averages, totalOrAvg, ignoreStats):
    seasonRatings = rosterRater("2024_total", totalOrAvg, team, averages, ignoreStats)
    sevenRatings = rosterRater("2024_last_7", totalOrAvg, team, averages, ignoreStats)
    fifteenRatings = rosterRater(
        "2024_last_15", totalOrAvg, team, averages, ignoreStats
    )
    thirtyRating = rosterRater("2024_last_30", totalOrAvg, team, averages, ignoreStats)

    result = pd.concat(
        [seasonRatings, thirtyRating, fifteenRatings, sevenRatings], axis=1
    )

    result["Player"] = result.index

    teamNameList = [team.team_name] * len(team.roster)
    result["Team"] = teamNameList
    return result


def combineTotalRatingTimeframes(
    team,
    ignoreStats,
    averagesWhole=None,
    averagesSeven=None,
    averagesFifteen=None,
    averagesThirty=None,
):
    seasonRatings = rosterRater("2024_total", "total", team, averagesWhole, ignoreStats)
    sevenRatings = rosterRater("2024_last_7", "total", team, averagesSeven, ignoreStats)
    fifteenRatings = rosterRater(
        "2024_last_15", "total", team, averagesFifteen, ignoreStats
    )
    thirtyRating = rosterRater(
        "2024_last_30", "total", team, averagesThirty, ignoreStats
    )
    result = []
    result.extend(seasonRatings, thirtyRating, fifteenRatings, sevenRatings)

    # result["Player"] = result.index

    teamNameList = [team.team_name] * len(team.roster)
    result["Team"] = teamNameList
    return result


def leagueTeamRatings(league, totalOrAvg="total", ignoreStats=["GP"]):
    frames = []
    teams = league.teams
    if totalOrAvg == "total":
        averagesWhole = calculateLeagueAverages(
            league, "2024_total", totalOrAvg=totalOrAvg
        )
        averagesSeven = calculateLeagueAverages(
            league, "2024_last_7", totalOrAvg=totalOrAvg
        )
        averagesFifteen = calculateLeagueAverages(
            league, "2024_last_15", totalOrAvg=totalOrAvg
        )
        averagesThirty = calculateLeagueAverages(
            league, "2024_last_30", totalOrAvg=totalOrAvg
        )
        for team in teams:
            teamRating = combineTotalRatingTimeframes(
                team,
                ignoreStats,
                averagesWhole,
                averagesSeven,
                averagesFifteen,
                averagesThirty,
            )
            frames.extend(teamRating)
    else:
        averages = calculateLeagueAverages(league, totalOrAvg=totalOrAvg)
        for team in teams:
            teamRating = combineAverageRatingTimeframes(
                team, averages, totalOrAvg, ignoreStats
            )
            frames.extend(teamRating)
    return frames


def leagueFreeAgentRatings(league, freeAgents, totalOrAvg="total", ignoreStats=["GP"]):
    frames = []
    if totalOrAvg == "total":
        timeframes = ["2024_total", "2024_last_30", "2024_last_15", "2024_last_7"]
        for timeframe in timeframes:
            averages = calculateLeagueAverages(league, timeframe, totalOrAvg=totalOrAvg)
            frame = rateFreeAgents(
                timeframe, "total", freeAgents, averages, ignoreStats
            )
            frames.append(frame)
    else:
        averages = calculateLeagueAverages(league, "2024_total", totalOrAvg=totalOrAvg)
        timeframes = ["2024_total", "2024_last_30", "2024_last_15", "2024_last_7"]
        for timeframe in timeframes:
            frame = rateFreeAgents(timeframe, "avg", freeAgents, averages, ignoreStats)
            frames.append(frame)
    ratingFrame = pd.concat(frames, axis=1)
    ratingFrame["Player"] = ratingFrame.index
    return ratingFrame


def rateFreeAgents(timeframe, totalOrAvg, freeAgents, averages, ignoreStats):
    freeAgentRating = {}
    for player in freeAgents:
        stats = player.stats.get(timeframe)
        playerStats = stats.get(totalOrAvg)
        if playerStats is None:
            rating = 0
        else:
            rating = ratePlayer(playerStats, averages, ignoreStats)
        name = player.name
        freeAgentRating.update({name: rating})
    ratingFrame = pd.DataFrame(freeAgentRating, [timeframe])
    ratingFrame = ratingFrame.T
    return ratingFrame


def compositeRateTeamCats(league, timeFrames, totalOrAvg, categoryList, ignoreStats):
    resultMatrix = [categoryList]
    if totalOrAvg == "total":
        for timeframe in timeFrames:
            averages = calculateLeagueAverages(
                league=league, timeframe=timeframe, totalOrAvg=totalOrAvg
            )
    else:
        averages = calculateLeagueAverages(
            league=league, timeframe=timeframe, totalOrAvg=totalOrAvg
        )

    return resultMatrix


def categoryRateTeams(league, timeframe, totalOrAvg, categoryList, ignoreStats=["GP"]):
    averages = calculateLeagueAverages(
        league=league, timeframe=timeframe, totalOrAvg=totalOrAvg
    )
    titles = categoryList.copy()
    titles.append("Rating")
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
            ignoreStats,
            team.team_name,
        )

        resultMatrix.extend(teamMatrix)

    return resultMatrix


def categoryRateFreeAgents(
    league, freeAgents, timeframe, totalOrAvg, categoryList, ignoreStats=["GP"]
):
    averages = calculateLeagueAverages(
        league=league, timeframe=timeframe, totalOrAvg=totalOrAvg
    )
    resultMatrix = [categoryList]
    freeAgentMatrix = categoryRatePlayerList(
        freeAgents, timeframe, totalOrAvg, averages, categoryList, ignoreStats
    )
    resultMatrix.extend(freeAgentMatrix)
    return resultMatrix


def categoryRatePlayerList(
    playerList, timeframe, totalOrAvg, averages, categoryList, ignoreStats, teamName="?"
):
    resultMatrix = []
    categoryNum = len(categoryList)

    for player in playerList:
        stats = player.stats.get(timeframe)
        playerStats = stats.get(totalOrAvg)
        if playerStats is None:
            playerMatrix = [0] * (categoryNum + 1)

        else:
            playerMatrix = createPlayerMatrix(
                playerStats, averages, categoryList, ignoreStats
            )
            player
        playerMatrix.append(player.name)
        injuryStatus = player.injuryStatus
        if not isinstance(injuryStatus, str):
            injuryStatus = "?"
        if teamName is not None:
            playerMatrix.append(teamName)
        resultMatrix.append(playerMatrix)
    return resultMatrix


def createPlayerMatrix(playerStats, averages, categoryList, ignoreStats):
    playerMatrix = []
    for cat in categoryList:
        stat = playerStats.get(cat)
        if stat is None:
            playerMatrix.append(0)
        else:
            statAverage = averages.get(cat)
            statRating = (stat / statAverage) * 100
            playerMatrix.append(statRating)
    playerMatrix.append(ratePlayer(playerStats, averages, ignoreStats))
    return playerMatrix


## Rates remaining value of players on teams
## Value is altered by playing schedule, and compared against league average production.
## Playes who play on days where your roster is full will have less value then players with games on empty days.
def remainingRateTeams(league, timeframes, totalOrAvg="avg", ignoreStats=["GP"]):
    averages = calculateLeagueAverages(
        league=league, timeframe="2024_total", totalOrAvg=totalOrAvg
    )
    resultMatrix = []
    resultMatrix.append(
        ["total", "t diff", "30", "30diff", "15", "15diff", "7", "7diff"]
    )
    teams = league.teams

    remaningGames = schedule.calculateRemainingGames(league=league)
    remainingExtraGames = schedule.calculateExtraRemainingGames(league=league)
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
                    ignoreStats=ignoreStats,
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
    league, freeAgents, timeframes, totalOrAvg="avg", ignoreStats=["GP"]
):
    averages = calculateLeagueAverages(
        league=league, timeframe="2024_total", totalOrAvg=totalOrAvg
    )
    resultMatrix = []
    resultMatrix.append(
        ["total", "t diff", "30", "30diff", "15", "15diff", "7", "7diff"]
    )

    remaningGames = schedule.calculateRemainingGames(league=league)
    remainingExtraGames = schedule.calculateExtraRemainingGames(league=league)
    for player in freeAgents:
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
                ignoreStats=ignoreStats,
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
        playerRatingList.append(proTeam)
        resultMatrix.append(playerRatingList)
    return resultMatrix
