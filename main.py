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
    exitMainMenu = False
    mainMenu = [
        "[1] Refresh League",  # 0 index
        "[2] Push Google Worksheets",  # 1 index
        "[3] Generate Excel Worksheets",  # 2 index
        "[4] Clear Google Worksheets",  # 3 index
        "[5] Settings",  # 4 index
        "[6] Exit",  # 5 index
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
    while not exitMainMenu:
        mainMenuEntry = terminalMainMenu.show()

        if mainMenuEntry == 0:
            print("Refreshing league from ESPN\n...")
            if refreshLeague() == 1:
                print("Successfully refreshed league \n")

        elif mainMenuEntry == 1:
            print("Pushing Google Worksheet...")
            worksheets.pushGoogleSheets()

        elif mainMenuEntry == 3:
            print("Clearing Google Worksheet\n...")
            worksheets.clearWorksheets()
            print("Worksheets Cleared!")

        elif mainMenuEntry == 4:
            settingsMenu()

        elif mainMenuEntry == 5:
            exitMainMenu = True
            print("Quit Selected")


def settingsMenu():
    exitSettingsMenu = False
    settingsMenu = [
        "[1] Set ESPN Info",  # 0 index
        "[2] Set Season",  # 1 index
        "[3] Set Ignored Stats",  # 2 index
        "[4] Set Roster Positions",  # 3 index
        "  ",  # 4 index
        "[6] Exit",  # 5 index
    ]
    terminalSettingsMenu = TerminalMenu(menu_entries=settingsMenu, title="Settings:")

    while not exitSettingsMenu:
        settingsMenuEntry = terminalSettingsMenu.show()

        if settingsMenuEntry == 0:
            espnInfoMenu()
        elif settingsMenuEntry == 5:
            exitSettingsMenu = True


def espnInfoMenu():
    exitEspnMenu = False
    espnMenu = [
        "[1] Set SWID",  # 0 index
        "[2] Set espn_s2",  # 1 index
        "[3] Set league_id",  # 2 index
        "  ",
        "  ",
        "[6] Exit",  # 3 index
    ]
    terminalEspnMenu = TerminalMenu(menu_entries=espnMenu, title="Settings:")

    while not exitEspnMenu:
        espnMenuEntry = terminalEspnMenu.show()

        if espnMenuEntry == 5:
            exitEspnMenu = True


# Returns 1 if refresh work. 0 otherwise
def refreshLeague():
    league = loading.reloadLeague()
    if league == 0:
        return 0
    loading.reloadFreeAgents(league)
    return 1


if __name__ == "__main__":
    main()
