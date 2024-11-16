from datetime import date
from copy import deepcopy
from typing import Dict
from espn_api.basketball import League, Team
import library.config as config

ROSTER_POSITIONS = config.ROSTER_POSITIONS
MAX_PLAYERS = config.MAX_PLAYERS


def calculateExtraRemainingGames(
    league: League, teamNumber: int, ignorePlayers: int = 0
) -> Dict[str, int]:
    remainingGames = {}
    teamCount = 0
    now = date.today()

    if teamNumber > len(league.teams) - 1:
        return 0
    myTeam = deepcopy(league.teams[teamNumber])
    del myTeam.roster[-ignorePlayers:]  # removes last X players from list
    mySchedule = myTeamSchedule(myTeam)

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
                        if mySchedule.get(gameDay) < MAX_PLAYERS:
                            gameCount += 1
            remainingGames[proTeam] = gameCount
            teamCount += 1
            if teamCount > 29:
                break
        if teamCount > 29:
            break
    return remainingGames


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


def myTeamSchedule(team: Team) -> Dict[date, int]:
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
