from typing import List, Any, Dict
from datetime import date, timedelta
import json
from espn_api.basketball import League, Team

import library.schedule as schedule
import library.config as config
import library.rating as rating


SCHEDULE_FILE = "2025.txt"
TEAM_NUMBER = config.TEAM_NUMBER
ROSTER_POSITIONS = config.ROSTER_POSITIONS
POSITION_HEIRARCHY = config.POSITION_HEIRARCHY
TEAM_SIZE = config.TEAM_SIZE
TIMEFRAMES = config.TIMEFRAMES
IGNORE_STATS = config.IGNORE_STATS

PER_GAME_AVERAGES = rating.PER_GAME_AVERAGES
TOTAL_AVERAGES = rating.TOTAL_AVERAGES


# 1. League matchup schedule
# 2. For each matchup, get games each team will play on each day, and value of players playing
# 3. Create projected value for each team in the matchup
# 4. Maybe also calculate each of the 9 categories for each team


def createMatchupSchedule(league: League) -> List[List[Any]]:
    averages = {
        "total": PER_GAME_AVERAGES[0],
        "30": PER_GAME_AVERAGES[1],
        "15": PER_GAME_AVERAGES[2],
        "7": PER_GAME_AVERAGES[3],
    }

    matchupSheet = []

    try:
        with open(SCHEDULE_FILE, "r") as file:
            fileInfo = file.read()
            scheduleDates = json.loads(fileInfo)
            file.close()
    except Exception as ex:  # file not found, initialize
        print("Could not find schedule file:", ex)

    team = league.teams[TEAM_NUMBER]
    teamRatings = teamRating(team=team, averages=averages)
    schedule = team.schedule
    # Setup Labels in first Column
    matchupSheet.append(
        [
            "Date",
            "Day",
            "You",
            "Season",
            "Last 15",
            "Opponent",
            "Season",
            "Last 15",
            "",
            "",
            "",
            "",
            "Season",
            "Last 15",
            team.team_name,
        ]
    )
    matchupSheet[0].extend(ROSTER_POSITIONS)
    matchupSheet[0].extend(["Opponent"])
    matchupSheet[0].extend(ROSTER_POSITIONS)

    for index, matchup in enumerate(schedule):
        opponent = (
            matchup.away_team
            if matchup.home_team.team_name == team.team_name
            else matchup.home_team
        )
        opponentRatings = teamRating(team=opponent, averages=averages)
        # Loop over days in the matchup
        dateRange = scheduleDates[str(index + 1)]  # whoops i made schedule 1 starting
        startDate = date.fromisoformat(dateRange[0])
        endDate = date.fromisoformat(dateRange[1])
        runningSeasonDiff = 0
        running15Diff = 0
        for singleDate in range((endDate - startDate).days + 1):
            # Today Information
            currentDate = startDate + timedelta(days=singleDate)
            columnData = [currentDate.strftime("%m/%d/%Y")]
            columnData.append(currentDate.strftime("%A"))
            # Team Rating
            columnData.append(team.team_name if singleDate == 0 else "")
            teamSeason = teamDayRating(teamRatings=teamRatings, date=currentDate)
            team15 = teamDayRating(
                teamRatings=teamRatings, date=currentDate, timeframe=TIMEFRAMES[2]
            )
            columnData.extend([teamSeason.get("rating"), team15.get("rating")])
            # Opponent Rating
            columnData.append(opponent.team_name if singleDate == 0 else "")
            opponentSeason = teamDayRating(
                teamRatings=opponentRatings, date=currentDate
            )
            opponent15 = teamDayRating(
                teamRatings=opponentRatings, date=currentDate, timeframe=TIMEFRAMES[2]
            )
            columnData.extend([opponentSeason.get("rating"), opponent15.get("rating")])
            # Diff Rating
            columnData.append("Diff" if singleDate == 0 else "")
            seasonDiff = teamSeason.get("rating") - opponentSeason.get("rating")
            diff15 = team15.get("rating") - opponent15.get("rating")
            columnData.extend([seasonDiff, diff15])
            runningSeasonDiff += seasonDiff
            running15Diff += diff15
            # Matchup Total
            columnData.append("Total Diff" if currentDate == endDate else "")
            columnData.append(runningSeasonDiff if currentDate == endDate else "")
            columnData.append(running15Diff if currentDate == endDate else "")
            columnData.append("")
            # Roster Positions
            for slot in team15.get("roster"):
                columnData.append(slot)
            columnData.append(opponent.team_name if singleDate == 0 else "")
            for slot in opponent15.get("roster"):
                columnData.append(slot)
            matchupSheet.append(columnData)

    return matchupSheet


def teamRating(team: Team, averages: Dict[str, float]) -> List[Dict[str, Any]]:
    teamRatings = []
    for player in team.roster:
        stats = player.stats
        playerSeasonRating = rating.ratePlayer(
            stats.get(TIMEFRAMES[0]).get("avg"), averages.get("total"), IGNORE_STATS
        )
        player15Rating = rating.ratePlayer(
            stats.get(TIMEFRAMES[2]).get("avg"), averages.get("15"), IGNORE_STATS
        )
        # making a set of datetime.dates for easier lookup
        gameDays = {game["date"].date() for game in player.schedule.values()}
        playerRating = {
            "name": player.name,
            "eligibleSlots": player.eligibleSlots,
            "injuryStatus": player.injuryStatus,
            "lineupSlot": player.lineupSlot,
            "gameDays": gameDays,
            TIMEFRAMES[0]: playerSeasonRating,
            TIMEFRAMES[2]: player15Rating,
        }
        teamRatings.append(playerRating)
    # Sort descending by Last 15 days per-game rating, trying to esitmate who to play first
    teamRatings.sort(key=lambda x: x[TIMEFRAMES[2]], reverse=True)
    return teamRatings


def teamDayRating(
    teamRatings: List[Dict[str, Any]], date: date, timeframe: str = TIMEFRAMES[0]
) -> Dict[str, Any]:
    # team ratings must be sorted descending
    # we will greedily place best players first
    dayRating = 0
    playingToday = ROSTER_POSITIONS.copy()
    placed = 0
    for player in teamRatings:
        if placed >= len(ROSTER_POSITIONS):
            break
        if player.get("lineupSlot") == "IR" or player.get("injuryStatus") == "OUT":
            continue
        if date not in player.get("gameDays"):
            continue
        # eligibleSlots are sorted by most restricive to least restrictive
        # we want to place in most restrictive first in order to approximate optimal lineups
        slots = player.get("eligibleSlots")
        slots.sort(
            key=lambda x: (
                POSITION_HEIRARCHY.index(x) if x in POSITION_HEIRARCHY else 999
            )
        )
        for slot in slots:
            if slot in playingToday:
                playingToday[playingToday.index(slot)] = player.get("name")
                placed += 1
                dayRating += player.get(timeframe)
                break

    result = {"rating": dayRating, "roster": playingToday}
    return result
