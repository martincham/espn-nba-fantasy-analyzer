import library.config as config
import library.loading as loading
import library.averages as averages
import library.schedule as schedule

TEAM_NUMBER = config.TEAM_NUMBER
IGNORE_PLAYERS = config.IGNORE_PLAYERS
EXTRA_GAMES = None
REMAINING_GAMES = None
TOTAL_AVERAGES = None
PER_GAME_AVERAGES = None

SETTING_FILE = config.SETTING_FILE
LEAGUE = loading.loadLeague()

if LEAGUE is not None:
    TOTAL_AVERAGES = averages.createLeagueAverages(league=LEAGUE, totalOrAvg="total")
    PER_GAME_AVERAGES = averages.createLeagueAverages(league=LEAGUE, totalOrAvg="avg")
    EXTRA_GAMES = schedule.calculateExtraRemainingGames(
        league=LEAGUE, teamNumber=TEAM_NUMBER, ignorePlayers=IGNORE_PLAYERS
    )
    REMAINING_GAMES = schedule.calculateRemainingGames(league=LEAGUE)


def init():
    global LEAGUE
    LEAGUE = loading.reloadLeague()
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
            league=LEAGUE, teamNumber=TEAM_NUMBER, ignorePlayers=IGNORE_PLAYERS
        )
        global REMAINING_GAMES
        REMAINING_GAMES = schedule.calculateRemainingGames(league=LEAGUE)
