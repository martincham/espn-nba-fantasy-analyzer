from espn_api.basketball import League
import json
import library.rating as rating
import library.schedule as schedule
import library.loading as loading
import library.worksheets as worksheets
from simple_term_menu import TerminalMenu


ROSTER_POSITIONS = ["PG", "F", "SG/SF", "SG/SF", "SG/SF", "PF/C", "U"]

IGNORESTATS = ["FTM", "FTA", "TO", "FGA", "FGM", "GP"]
TIMEFRAMES = ["2024_total", "2024_last_30", "2024_last_15", "2024_last_7"]
SETTINGFILE = "settings.txt"


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
        print(worksheets.getGoogleSheetName(), "\n")

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
        "[5] Set Worksheet Name",  # 4 index
        "[6] Exit",  # 5 index
    ]
    terminalSettingsMenu = TerminalMenu(
        menu_entries=settingsMenu, title="Settings:", skip_empty_entries=True
    )

    while not exitSettingsMenu:
        settingsMenuEntry = terminalSettingsMenu.show()

        if settingsMenuEntry == 0:
            espnInfoMenu()
        elif settingsMenuEntry == 1:
            changeSetting("seasonId")
        elif settingsMenuEntry == 2:
            ignoredStatsMenu()
        elif settingsMenuEntry == 3:
            rosterPositionMenu()
        elif settingsMenuEntry == 4:
            changeSetting("googleSheet")
        elif settingsMenuEntry == 5:
            exitSettingsMenu = True


def espnInfoMenu():
    exitEspnMenu = False
    espnMenu = [
        "[1] Set SWID",  # 0 index
        "[2] Set espn_s2",  # 1 index
        "[3] Set league_id",  # 2 index
        None,
        None,
        "[6] Exit",  # 5 index
    ]
    terminalEspnMenu = TerminalMenu(
        menu_entries=espnMenu, title="Change ESPN Info:", skip_empty_entries=True
    )

    while not exitEspnMenu:
        espnMenuEntry = terminalEspnMenu.show()

        if espnMenuEntry == 0:
            changeSetting("SWID")
        if espnMenuEntry == 1:
            changeSetting("espn_s2")
        if espnMenuEntry == 1:
            changeSetting("league_id")
        elif espnMenuEntry == 5:
            exitEspnMenu = True


def ignoredStatsMenu():
    print("Not implemented yet. Edit your settings.txt manually.")
    return 0


def rosterPositionMenu():
    print("Not implemented yet. Edit your settings.txt manually.")
    return 0


def changeSetting(settingName):
    try:
        file = open(SETTINGFILE, "r")
        fileInfo = file.read()
        settings = json.loads(fileInfo)
        file.close()

        settingValue = settings.get(settingName)
        print(settingName, " : ", settingValue)
        print("Enter your new", settingName, end=" ")
        newValue = input(": ")
        print("Change", settingName, "to", newValue, end="  ")
        if newValue != "":
            confirm = input("Confirm(y/n)")
            if confirm.lower() == "y":
                file = open(SETTINGFILE, "w")
                settings.update({settingName: newValue})
                json.dump(settings, file, indent=4)
                print("Updated.")
                file.close()
            else:
                print("Not updated.")
        else:
            print("Not updated.")
        file.close()

    except FileNotFoundError as ex:
        print("Could not find login file:", ex)
        return 0
    except Exception as ex:
        print("Error: ", ex)
        return 0


# Returns 1 if refresh work. 0 otherwise
def refreshLeague():
    league = loading.reloadLeague()
    if league == 0:
        return 0
    loading.reloadFreeAgents(league)
    return 1


if __name__ == "__main__":
    main()
