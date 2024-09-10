<a target="_blank" href="https://www.python.org/downloads/" title="Python version"><img src="https://img.shields.io/badge/pthon-%3E=_3.8-teal.svg"></a>

# ESPN NBA Fantasy Basketball Analyzer

# \*\*WIP\*\*

### Generates overall, and category player valuations over various timespans

Thanks to [cwendt94/espn-api](https://github.com/cwendt94/espn-api) for fetching data from ESPN.

## Setup:

Requires pandas, gspread, gspread-formatting, espn-api, and simple-term-menu packages:

```
python3 -m pip install pandas gspread gspread-formatting espn-api simple-term-menu
```

Required [Google gspread setup](https://docs.gspread.org/en/latest/oauth2.html) to allow pushing to Google Sheet. Local Excel spreadhsheets not yet implemented.

to run:

```
  python3 main.py
```

```
ESPN Fantasy League: YOUR_LEAGUE_NAME_HERE
Season: 2024
Last refreshed: Sat Apr 20 19:34:39 2024
Selected Google Sheet: testSheet

ESPN Fantasy BBALL Analyzer
> [1] Refresh League
  [2] Push Google Worksheets
  [3] Generate Excel Worksheets
  [4] Clear Google Worksheets
  [5] Settings
  [6] Exit
```

Refreshing, pushing to Google, clearing Google, and settings work. Excel not working yet.

```
Settings:
> [1] Set ESPN Info
  [2] Set Season
  [3] Set Ignored Stats
  [4] Set Roster Positions
  [5] Set Worksheet Name
  [6] Exit
```

You can either manually edit the json in settings.txt, or you can use this settings menu.

```
Change ESPN Info:
> [1] Set SWID
  [2] Set espn_s2
  [3] Set league_id
  [2] Set team number

  [6] Exit
```

SWID and espn_s2 required for private leagues, but it doesn't hurt to put yours, league_id is required for all leagues.

This utility scores players where 100 is the average production of players rostered in your league, over the specified timespan. A score of 200 will have double the production, 50 will have half.

<img src="assets/exampleESPN.png" alt="worksheet example" width="400"/>
