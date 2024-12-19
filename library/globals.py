import library.config as c
import library.loading as loading
import library.averages as averages
import library.schedule as schedule


# globals.py keeps the League, Averages, and Remaining/Extra Games in memory.
# It 1. Loads league, 2. Validates settings, 3. Creates averages, 4. Calculates extra/remaining games

EXTRA_GAMES = None
REMAINING_GAMES = None
TOTAL_AVERAGES = None
PER_GAME_AVERAGES = None

SETTING_FILE = c.SETTING_FILE
LEAGUE = loading.loadLeague()


def validate():
    if c.TEAM_NUMBER >= len(LEAGUE.teams):
        print(
            "Invalid team number:",
            c.TEAM_NUMBER,
            "(league has",
            len(LEAGUE.teams),
            " teams)",
        )
        quit()
    elif c.TEAM_NUMBER < 0:
        print("Invalid team number:", c.TEAM_NUMBER)
        quit()

    validateCategories()


def validateCategories():
    for category in c.CATEGORIES:
        if category not in c.VALID_CATEGORIES:
            print("Invalid category:", category)
            quit()


if LEAGUE is not None:
    validate()
    TOTAL_AVERAGES = averages.createLeagueAverages(league=LEAGUE, totalOrAvg="total")
    PER_GAME_AVERAGES = averages.createLeagueAverages(league=LEAGUE, totalOrAvg="avg")
    EXTRA_GAMES = schedule.calculateExtraRemainingGames(
        league=LEAGUE,
        averages=PER_GAME_AVERAGES[0],
        teamNumber=c.TEAM_NUMBER,
        ignorePlayers=c.IGNORE_PLAYERS,
    )
    REMAINING_GAMES = schedule.calculateRemainingGames(league=LEAGUE)


def init() -> int:
    global LEAGUE
    LEAGUE = loading.loadLeague()
    if LEAGUE is not None:
        validate()
        global TOTAL_AVERAGES
        TOTAL_AVERAGES = averages.createLeagueAverages(
            league=LEAGUE, totalOrAvg="total"
        )
        global PER_GAME_AVERAGES
        PER_GAME_AVERAGES = averages.createLeagueAverages(
            league=LEAGUE, totalOrAvg="avg"
        )
        initExtraGames()
        return 1
    else:
        return 0


def initExtraGames():
    global EXTRA_GAMES
    EXTRA_GAMES = schedule.calculateExtraRemainingGames(
        league=LEAGUE,
        averages=PER_GAME_AVERAGES[0],
        teamNumber=c.TEAM_NUMBER,
        ignorePlayers=c.IGNORE_PLAYERS,
    )
    global REMAINING_GAMES
    REMAINING_GAMES = schedule.calculateRemainingGames(league=LEAGUE)
