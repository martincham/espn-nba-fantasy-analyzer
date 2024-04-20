from espn_api.basketball import League
import library.rating as rating
import library.schedule as schedule
import library.loading as loading
import library.worksheets as worksheets
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
        "[4] Clear Google Worksheets",
        "[5] Exit",
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
        print("Selected Google Sheet:", end=" ")
        print(worksheets.getGoogleSheetName())
    # MENU
    while not mainMenuExit:
        mainMenuEntry = terminalMainMenu.show()

        if mainMenuEntry == 0:
            print("Refreshing league from ESPN\n...")
            if refreshLeague() == 1:
                print("Successfully refreshed league \n")

        elif mainMenuEntry == 3:
            print("Clearing Google Worksheet")

        elif mainMenuEntry == 4:
            mainMenuExit = True
            print("Quit Selected")


# Returns 1 if refresh work. 0 otherwise
def refreshLeague():
    league = loading.reloadLeague()
    if league == 0:
        return 0
    loading.reloadFreeAgents(league)
    return 1


if __name__ == "__main__":
    main()
