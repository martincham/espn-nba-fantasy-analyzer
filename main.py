from espn_api.basketball import League
import library.rating as rating
import library.schedule as schedule
import library.loading as loading
import gspread
from datetime import datetime
import os
from simple_term_menu import TerminalMenu


ROSTER_POSITIONS = ["PG", "F", "SG/SF", "SG/SF", "SG/SF", "PF/C", "U"]

IGNORESTATS = ["FTM", "FTA", "TO", "FGA", "FGM", "GP"]
TIMEFRAMES = ["2024_total", "2024_last_30", "2024_last_15", "2024_last_7"]


def main():
    mainMenu = [
        "[1] Refresh League",
        "[2] Push Google Worksheets",
        "[3] Generate Excel Worksheets",
        "[4] Exit",
    ]
    terminal_menu = TerminalMenu(
        menu_entries=mainMenu, title="ESPN Fantasy BBALL Analyzer"
    )


if __name__ == "__main__":
    main()
