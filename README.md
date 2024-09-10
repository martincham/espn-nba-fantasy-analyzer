<a target="_blank" href="https://www.python.org/downloads/" title="Python version"><img src="https://img.shields.io/badge/pthon-%3E=_3.8-teal.svg"></a>

# ESPN NBA Fantasy Basketball Analyzer  \*\*WIP\*\*
### Generates overall, and category player valuations over various timespans

Thanks to [cwendt94/espn-api](https://github.com/cwendt94/espn-api) for fetching data from ESPN.

## Setup:

Requires pandas, gspread, gspread-formatting, espn-api, and simple-term-menu packages:

```
python3 -m pip install pandas gspread gspread-formatting espn-api simple-term-menu
```

Required [Google gspread setup](https://docs.gspread.org/en/latest/oauth2.html) to allow pushing to Google Sheet.

To install, either download and unpack the .zip, or run:

```
git clone https://github.com/martincham/espn-nba-fantasy-analyzer
```


## Using the tool:

to run (while [in the folder](https://www.geeksforgeeks.org/cd-command-in-linux-with-examples/)):

```
  python3 main.py
```
### Main Menu
```
ESPN Fantasy League: YOUR_LEAGUE_NAME_HERE
Season: 2024
Last refreshed: Sat Apr 20 19:34:39 2024
Selected Google Sheet: testSheet

ESPN Fantasy BBALL Analyzer                                                                   
> [1] Refresh League                                                                        
  [2] Google Sheets Menu                                                                      
  [3] Excel Spreadsheets Menu                                                                 
  [4] Settings                                                                                
                                                                                              
  [6] Exit     
```

*[1] Refresh League* will pull data for your league from ESPN. The data will be stored in the folder. You only need to refresh when new games have been played. 

### Google Sheet Menu
```
Google Sheet:                                                                                 
> [1] Push Google Sheet                                                                       
  [2] Format Google Sheet                                                                     
  [3] Clear Google Sheet                                                                      
  [4] Set Sheet Name                                                                          
                                                                                              
  [6] Exit    
```
*[1] Push* will resend the data to your GSheet.

*[2] Format* You only need to run once to intialize your GSheet. Will setup color coding and other formatting.

*[3 Clear]* Will delete all the data from your sheets.

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

SWID and espn_s2 required for private leagues, ([finding SWID and espn_s2](https://github.com/cwendt94/espn-api/discussions/150)), league_id is required for all leagues. Your team number is required to calculate remaining value.

## Reading the Data:

This utility scores players where 100 is the average production of players rostered in your league, over the specified timespan. A score of 200 will have double the production, 50 will have half.

<img src="assets/exampleESPN.png" alt="worksheet example" width="400"/>
