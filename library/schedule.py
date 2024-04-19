from datetime import datetime
from datetime import date
from copy import deepcopy

ROSTER_POSITIONS = ["PG", "F", "SG/SF", "SG/SF", "SG/SF", "PF/C", "UT"]


def calculateExtraRemainingGames(league):
    remainingGames = {}
    teamCount = 0
    now = date.today()

    oakland = deepcopy(league.teams[7])
    del oakland.roster[-3]
    oaklandSchedule = myTeamSchedule(oakland)

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
                if gameDay < now:
                    if gameDay in oaklandSchedule:
                        if oaklandSchedule.get(gameDay) < 8:
                            gameCount += 1
            remainingGames[proTeam] = gameCount
            teamCount += 1
            if teamCount > 29:
                break
        if teamCount > 29:
            break
    return remainingGames


def calculateRemainingGames(league):
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
                if gameDay < now:
                    gameCount += 1
            remainingGames[proTeam] = gameCount
            teamCount += 1
            if teamCount > 29:
                break
        if teamCount > 29:
            break
    return remainingGames


def myTeamSchedule(team):
    teamSchedule = {}
    roster = team.roster
    for player in roster:
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
