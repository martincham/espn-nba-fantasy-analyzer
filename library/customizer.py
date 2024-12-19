from simple_term_menu import TerminalMenu
from espn_api.basketball import League, Team, Player

import library.config as c
import library.globals as g
import library.loading as loading


def customizeMenu():
    exitMenu = False
    menu = [
        "[1] Trade Players",  # 0 index
        "[2] Save League",  # 1 index
        None,  # 2 index
        None,  # 3 index
        None,  # 4 index
        "[6] Back",  # 5 index,
    ]
    terminalMenu = TerminalMenu(
        menu_entries=menu, title="Customize Team:", skip_empty_entries=True
    )

    while not exitMenu:
        menuEntry = terminalMenu.show()

        if menuEntry == 0:
            tradeMenu()
        elif menuEntry == 1:
            loading.saveLeague(g.LEAGUE)
        elif menuEntry == 2:
            pass
        elif menuEntry == 5:
            exitMenu = True


def tradeMenu():
    exitMenu = False
    menu = ["[1] Back"]
    for index, team in enumerate(g.LEAGUE.teams):
        menu.append("[" + str(index + 2) + "] " + team.team_name)

    terminalMenu = TerminalMenu(
        menu_entries=menu, title="Trade Players:", skip_empty_entries=True
    )

    while not exitMenu:
        menuEntry = terminalMenu.show()

        if menuEntry == 0:
            exitMenu = True

        elif menuEntry > 0 and menuEntry <= len(g.LEAGUE.teams):
            if teamTradeMenu(teamIndex=menuEntry - 1) == 1:
                return 1


def teamTradeMenu(teamIndex: int):
    exitMenu = False
    team: Team = g.LEAGUE.teams[teamIndex]
    menu = ["[1] Back"]
    for index, player in enumerate(team.roster):
        menu.append("[" + str(index + 2) + "] " + player.name)

    terminalMenu = TerminalMenu(
        menu_entries=menu,
        title=team.team_name,
        skip_empty_entries=True,
    )

    while not exitMenu:
        menuEntry = terminalMenu.show()

        if menuEntry == 0:
            exitMenu = True

        elif menuEntry > 0 and menuEntry <= len(team.roster):
            if tradeForMenu(teamIndex=teamIndex, oppIndex=menuEntry - 1) == 1:
                return 1


def tradeForMenu(teamIndex: int, oppIndex: int) -> int:
    exitMenu = False
    menu = ["[1] Back"]
    myTeam = g.LEAGUE.teams[c.TEAM_NUMBER]
    for index, player in enumerate(myTeam.roster):
        menu.append("[" + str(index + 2) + "] " + player.name)

    terminalMenu = TerminalMenu(
        menu_entries=menu, title="Trade Players:", skip_empty_entries=True
    )

    while not exitMenu:
        menuEntry = terminalMenu.show()

        if menuEntry == 0:
            exitMenu = True
            return 0

        elif menuEntry > 0 and menuEntry <= len(g.LEAGUE.teams):
            return tradePlayers(
                teamIndex=teamIndex, oppIndex=oppIndex, myIndex=menuEntry - 1
            )


def tradePlayers(teamIndex: int, oppIndex: int, myIndex: int):
    temp: Player = g.LEAGUE.teams[c.TEAM_NUMBER].roster[myIndex]
    # copy their player to my team
    g.LEAGUE.teams[c.TEAM_NUMBER].roster[myIndex] = g.LEAGUE.teams[teamIndex].roster[
        oppIndex
    ]
    # copy my player to their team
    g.LEAGUE.teams[teamIndex].roster[oppIndex] = temp
    # Recalculate extra games
    g.initExtraGames()
    print(
        "Traded "
        + temp.name
        + " for "
        + g.LEAGUE.teams[c.TEAM_NUMBER].roster[myIndex].name
    )
    return 1
