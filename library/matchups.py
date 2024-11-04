from datetime import date, timedelta
import json

import library.schedule as schedule
import library.config as config
import library.rating as rating


SCHEDULE_FILE = "2025.txt"
TEAM_NUMBER = config.TEAM_NUMBER
ROSTER_POSITIONS = config.ROSTER_POSITIONS
TEAM_SIZE = config.TEAM_SIZE
TIMEFRAMES = config.TIMEFRAMES
IGNORE_STATS = config.IGNORE_STATS


# 1. League matchup schedule
# 2. For each matchup, get games each team will play on each day, and value of players playing
# 3. Create projected value for each team in the matchup
# 4. Maybe also calculate each of the 9 categories for each team


def createMatchupSchedule(league):
    averagesWhole = rating.calculateLeagueAverages(
        league, TIMEFRAMES[0], totalOrAvg="avg"
    )
    averagesThirty = rating.calculateLeagueAverages(
        league, TIMEFRAMES[1], totalOrAvg="avg"
    )
    averagesFifteen = rating.calculateLeagueAverages(
        league, TIMEFRAMES[2], totalOrAvg="avg"
    )
    averagesSeven = rating.calculateLeagueAverages(
        league, TIMEFRAMES[3], totalOrAvg="avg"
    )
    averages = {
        "total": averagesWhole,
        "30": averagesThirty,
        "15": averagesFifteen,
        "7": averagesSeven,
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
    roster = team.roster
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
    matchupSheet[0].extend([""])
    matchupSheet[0].extend(["Bench"] * (TEAM_SIZE - len(ROSTER_POSITIONS)))
    matchupSheet[0].extend([""])
    matchupSheet[0].extend(ROSTER_POSITIONS)
    matchupSheet[0].extend([""])
    matchupSheet[0].extend(["Bench"] * (TEAM_SIZE - len(ROSTER_POSITIONS)))

    for index, matchup in enumerate(schedule):
        opponent = matchup.away_team
        opponentRoster = opponent.roster
        opponentRatings = teamRating(team=opponent, averages=averages)
        # Loop over days in the matchup
        dateRange = scheduleDates[str(index + 1)]  # whoops i made schedule 1 starting
        startDate = date.fromisoformat(dateRange[0])
        endDate = date.fromisoformat(dateRange[1])
        for singleDate in range((endDate - startDate).days + 1):
            currentDate = startDate + timedelta(days=singleDate)
            columnData = [currentDate.strftime("%m/%d/%Y")]
            columnData.append(currentDate.strftime("%A"))
            columnData.append(team.team_name if index == 0 else "")
            teamSeason = teamDayRating(
                teamRatings=teamRatings, team=team, date=currentDate
            )
            team15 = teamDayRating(team=team, date=currentDate, timeframe="15")
            columnData.append(teamSeason.rating)
            columnData.append(team15.rating)
            columnData.append(opponent.team_name if index == 0 else "")
            opponentSeason = teamDayRating(team=opponent, date=currentDate)
            opponent15 = teamDayRating(team=opponent, date=currentDate, timeframe="15")
            columnData.append(opponentSeason)
            columnData.append(opponent15)
            columnData.append("Diff" if index == 0 else "")
            diff = team15 - opponent15
            columnData.append(diff)
            # Roster Positions
            # For each day, calculate each teams on-court value
            # User PerGame values, skip injury, check roster positions


def teamRating(team, averages):
    teamRatings = []
    for player in team.roster:
        stats = player.stats
        playerSeasonRating = rating.ratePlayer(
            stats.get(TIMEFRAMES[0]).get("avg"), averages.get("total"), IGNORE_STATS
        )
        player15Rating = rating.ratePlayer(
            stats.get(TIMEFRAMES[2]).get("avg"), averages.get("15"), IGNORE_STATS
        )
        playerRating = {
            "name": player.name,
            "slot": player.eligibleSlots,
            "total": playerSeasonRating,
            "15": player15Rating,
        }
        teamRatings.append(playerRating)
    return teamRatings


def teamDayRating(teamRatings, team, date, timeframe="total"):
    pass
    # TODO sort by rating, place by position
