import json
import os
from simple_term_menu import TerminalMenu
import library.config as config
import library.loading as loading
import library.worksheets as worksheets
import library.customizer as customizer
import library.globals as g

SETTING_FILE = config.SETTING_FILE
TOTAL_AVERAGES = None
PER_GAME_AVERAGES = None
IGNORE_PLAYERS = config.IGNORE_PLAYERS


def clear_screen():
    # Check if the system is Windows
    if os.name == "nt":
        os.system("cls")  # Windows
    else:
        os.system("clear")  # macOS and Linux


def main():
    league = g.LEAGUE
    clear_screen()
    exitMainMenu = False
    mainMenu = [
        "[1] Load/Refresh League",  # 0 index
        "[2] Google Sheets Menu",  # 1 index
        "[3] Trade Machine",  # 2 index
        "[4] Settings",  # 3 index
        None,  # 4 index
        "[6] Exit",  # 5 index
    ]
    terminalMainMenu = TerminalMenu(
        menu_entries=mainMenu,
        title="ESPN Fantasy BBALL Analyzer",
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
                g.init()
                league = g.LEAGUE
                print("Successfully refreshed league \n")
                print("ESPN Fantasy League:", end=" ")
                print(league.settings.name)
                print("Season:", end=" ")
                print(league.year)
                print("Last refreshed:", end=" ")
                print(loading.getLeagueSavedTime())

            else:
                print("League could not load")

        elif mainMenuEntry == 1:
            googleSheetsMenu()

        elif mainMenuEntry == 2:
            customizer.customizeMenu()

        elif mainMenuEntry == 3:
            settingsMenu()

        elif mainMenuEntry == 5:
            exitMainMenu = True
            print("Quit Selected")


def googleSheetsMenu():
    exitMenu = False
    menu = [
        "[1] Push Google Sheet",  # 0 index
        "[2] Initialize/Reformat Google Sheet",  # 1 index
        "[3] Clear Google Sheet",  # 2 index
        "[4] Set Sheet Name",  # 3 index
        None,  # 4 index
        "[6] Back",  # 5 index,  # 5 index
    ]
    terminalMenu = TerminalMenu(
        menu_entries=menu, title="Google Sheet:", skip_empty_entries=True
    )

    while not exitMenu:
        menuEntry = terminalMenu.show()

        if menuEntry == 0:
            if g.LEAGUE is None:
                print("NO LEAGUE LOADED. Please refresh league.")
                return
            print("Pushing Google Sheet...")
            g.validate()
            worksheets.pushGoogleSheets()
            print("Sheet pushed.")
        elif menuEntry == 1:
            print("Formatting Google Sheet\n...")
            worksheets.initializeSpreadsheet()
            print("Worksheets formatted!")
        elif menuEntry == 2:
            print("Clearing Google Sheet\n...")
            worksheets.clearWorksheets()
            print("Sheet Cleared!")
        elif menuEntry == 3:
            changeSetting("googleSheet")

        elif menuEntry == 5:
            exitMenu = True


def settingsMenu():
    exitSettingsMenu = False
    settingsMenu = [
        "[1] Set ESPN Info",  # 0 index
        "[2] Set Season",  # 1 index
        None,  # 2 index Ignored Stats
        None,  # 3 index Roster Positions
        None,  # 4 index
        "[6] Back",  # 5 index
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
        elif settingsMenuEntry == 5:
            exitSettingsMenu = True


def espnInfoMenu():
    exitEspnMenu = False
    espnMenu = [
        "[1] Set SWID",  # 0 index
        "[2] Set espn_s2",  # 1 index
        "[3] Set leagueId",  # 2 index
        "[2] Set team number",  # 3 index
        None,
        "[6] Back",  # 5 index
    ]
    terminalEspnMenu = TerminalMenu(
        menu_entries=espnMenu, title="Change ESPN Info:", skip_empty_entries=True
    )

    while not exitEspnMenu:
        espnMenuEntry = terminalEspnMenu.show()

        if espnMenuEntry == 0:
            changeSetting("SWID")
        elif espnMenuEntry == 1:
            changeSetting("espn_s2")
        elif espnMenuEntry == 2:
            changeSetting("leagueId")
        elif espnMenuEntry == 3:
            changeSetting("teamNumber")
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
        file = open(SETTING_FILE, "r")
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
                file = open(SETTING_FILE, "w")
                settings.update({settingName: newValue})
                json.dump(settings, file, indent=4)
                print("Updated.")
                file.close()
                config.init()
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
