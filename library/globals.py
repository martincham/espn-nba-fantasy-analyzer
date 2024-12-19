import library.config as c
import library.loading as loading
import library.averages as averages
import library.schedule as schedule


EXTRA_GAMES = None
REMAINING_GAMES = None
TOTAL_AVERAGES = None
PER_GAME_AVERAGES = None

SETTING_FILE = c.SETTING_FILE
LEAGUE = loading.loadLeague()

if LEAGUE is not None:
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
        global TOTAL_AVERAGES
        TOTAL_AVERAGES = averages.createLeagueAverages(
            league=LEAGUE, totalOrAvg="total"
        )
        global PER_GAME_AVERAGES
        PER_GAME_AVERAGES = averages.createLeagueAverages(
            league=LEAGUE, totalOrAvg="avg"
        )
        global EXTRA_GAMES
        EXTRA_GAMES = schedule.calculateExtraRemainingGames(
            league=LEAGUE,
            averages=PER_GAME_AVERAGES[0],
            teamNumber=c.TEAM_NUMBER,
            ignorePlayers=c.IGNORE_PLAYERS,
        )
        global REMAINING_GAMES
        REMAINING_GAMES = schedule.calculateRemainingGames(league=LEAGUE)
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


def validate():
    if c.TEAM_NUMBER > len(LEAGUE.teams):
        print(
            "Invalid team number:",
            c.TEAM_NUMBER,
            "(league has",
            len(LEAGUE.teams),
            " teams)",
        )
        quit()
    elif c.TEAM_NUMBER < 1:
        print("Invalid team number:", c.TEAM_NUMBER)
        quit()

    validateCategories()
    initExtraGames()  # in case teamNumber changed


def validateCategories():
    for category in c.CATEGORIES:
        if category not in c.VALID_CATEGORIES:
            print("Invalid category:", category)
            quit()
