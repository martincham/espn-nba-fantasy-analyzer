from datetime import date, timedelta
import json

import library.schedule as schedule
import library.config as config
import library.rating as rating


SCHEDULE_FILE = "2025.txt"
TEAM_NUMBER = config.TEAM_NUMBER
ROSTER_POSITIONS = config.ROSTER_POSITIONS
TEAM_SIZE = config.TEAM_SIZE


# 1. League matchup schedule
# 2. For each matchup, get games each team will play on each day, and value of players playing
# 3. Create projected value for each team in the matchup
# 4. Maybe also calculate each of the 9 categories for each team


def createMatchupSchedule(league):
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
    schedule = team.schedule
    # Setup Labels in first Column
    matchupSheet[0] = [
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
    matchupSheet[0].extend(ROSTER_POSITIONS)
    matchupSheet[0].extend([""])
    matchupSheet[0].extend(["Bench"] * (TEAM_SIZE - len(ROSTER_POSITIONS)))
    matchupSheet[0].extend([""])
    matchupSheet[0].extend(ROSTER_POSITIONS)
    matchupSheet[0].extend([""])
    matchupSheet[0].extend(["Bench"] * (TEAM_SIZE - len(ROSTER_POSITIONS)))

    for index, matchup in enumerate(schedule):
        opponent = schedule.away_team
        opponentRoster = opponent.roster
        # Loop over days in the matchup
        dateRange = scheduleDates[index + 1]  # whoops i made schedule 1 starting
        startDate = date.fromisoformat(dateRange[0])
        endDate = date.fromisoformat(dateRange[1])
        for singleDate in range((endDate - startDate).days + 1):
            currentDate = startDate + timedelta(days=singleDate)
            # For each day, calculate each teams on-court value
            # User PerGame values, skip injury, check roster positions
