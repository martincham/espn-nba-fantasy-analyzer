from espn_api.basketball import League
import library.rating as rating
import library.schedule as schedule
import library.loading as loading
from simple_term_menu import TerminalMenu


ROSTER_POSITIONS = ["PG", "F", "SG/SF", "SG/SF", "SG/SF", "PF/C", "U"]

IGNORESTATS = ["FTM", "FTA", "TO", "FGA", "FGM", "GP"]
TIMEFRAMES = ["2024_total", "2024_last_30", "2024_last_15", "2024_last_7"]
LEAGUEFILE = "league.pickle"
FREEAGENTSFILE = "freeagents.pickle"


def main():
    league = loading.loadLeague()
    freeAgents = loading.loadFreeAgents()
    mainMenuExit = False
    mainMenu = [
        "[1] Refresh League",
        "[2] Push Google Worksheets",
        "[3] Generate Excel Worksheets",
        "[4] Exit",
    ]
    terminalMainMenu = TerminalMenu(
        menu_entries=mainMenu, title="ESPN Fantasy BBALL Analyzer"
    )

    # Intro Messages
    print("ESPN Fantasy League:", end=" ")
    if league is None:
        print("*no league saved*")
    else:
        print(league.settings.name)
        print("Season:", end=" ")
        print(league.year)
        print("Last refreshed:", end=" ")
        print(loading.getLeagueSavedTime())
    # MENU
    while not mainMenuExit:
        mainMenuEntry = terminalMainMenu.show()
        if mainMenuEntry == 0:
            print("Refreshing league from ESPN...")
            refreshLeague()
        elif mainMenuEntry == 3:
            mainMenuExit = True
            print("Quit Selected")


def refreshLeague():
    league = loading.reloadLeague()
    loading.reloadFreeAgents(league)


if __name__ == "__main__":
    main()
