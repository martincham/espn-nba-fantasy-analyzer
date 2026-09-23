# Draft Room

A local web app for your fantasy basketball auction draft. It pulls your league's settings plus every player's last-season stats and ESPN auction prices, then lets you plan and track your draft in the browser.

- **Board:** search and filter the player pool. Each player gets two ratings, per game and full season, and you can set your own **Δ %** (expected improvement or decline) and **expected games**. Compare **Ours** (our dollar value) with **Avg paid** (the average price in ESPN auctions) to find bargains.
- **My Team:** drag players into your roster slots and see how your team ranks in each category against a simulated 12-team league.
- **During the draft:** mark players as yours or taken at the price paid, and follow your budget, max bid and inflation.

Everything runs on your computer. The app listens on `127.0.0.1` only, so other devices on your network can't reach it.

## Requirements

- **Python 3.9 or newer** (tested on 3.9, 3.11 and 3.12), with **espn-api** installed. That's the same requirement as the spreadsheet tool (`main.py`), and no other packages are needed.

  ```
  python3 -m pip install espn-api
  ```

- **A browser.** Any current Chrome, Firefox, Safari or Edge works.
- **An internet connection** for the first load and for refreshes. After that the player pool is cached.

## Setup

1. **Get the code** (skip this if you already have the repo):

   ```
   git clone https://github.com/martincham/espn-nba-fantasy-analyzer
   cd espn-nba-fantasy-analyzer
   ```

2. **Point it at your league.** The app reads `settings.txt` in the repo folder, the same file the spreadsheet tool uses. It only needs these fields:

   | Setting | Used for |
   |---|---|
   | `leagueId` | Your ESPN league: team count, budget, categories and roster slots |
   | `espn_s2`, `SWID` | **Private leagues only.** Your ESPN login cookies (see the [project Wiki](https://github.com/martincham/espn-nba-fantasy-analyzer/wiki)) |
   | `ignoredStats` | Categories left out of player values (e.g. `"TO"`) |
   | `ignorePlayers` | How many of your worst players don't count toward team totals (default 3) |
   | `draftSeason` | *Optional.* Force a season, e.g. `2027` for 2026-27. By default it uses the season ESPN is currently set up for |

   Without a `settings.txt`, the app uses ESPN's default 12-team league. It never creates or edits `settings.txt`.

## Run it

From the repo folder:

```
python3 -m gui
```

You'll see something like:

```
Loading player pool...
Your League Name · 440 players · Draft Room running at http://127.0.0.1:8000  (Ctrl+C to stop)
```

Your browser opens to the app. Press **Ctrl+C** in the terminal to stop it.

### Options

| Option | What it does |
|---|---|
| `--port 8001` | Use a different port (default 8000) |
| `--settings path/to/settings.txt` | Read settings from somewhere else |
| `--refresh` | Download a fresh player pool from ESPN before starting |
| `--no-browser` | Don't open a browser tab |

## Your data

The app keeps two files in the repo folder. Both are gitignored.

- **`draftPool.json`** holds the ESPN data: league settings, players, stats and prices. It's downloaded once and reused. Click **Refresh from ESPN** (or start with `--refresh`) to update prices and injuries, e.g. on draft day.
- **`draftState.json`** holds your work: Δ values, expected games, notes, the weight slider, picks, prices and roster slots. It saves on every change, so you can close the app and pick up where you left off.

To start over, stop the app and delete `draftState.json`.

## Using it

- **Search:** press **/** to jump to the search box. It matches player names and NBA team abbreviations, ignoring accents.
- **Edit a player:** type in the **Exp GP** or **Δ %** cells, or select a row and use the sliders in the side panel.
  - Type Δ however is natural: `+5`, `5%`, `-10` and `−10` all work. Press ↑/↓ to step by 1, or hold Shift to step by 5.
  - Edited values are highlighted in marigold. They save the moment you press Enter or leave the box.
  - Clear the Exp GP cell to reset it to the default.
  - **Use ESPN's** copies ESPN's projection.
- **Value weighs:** slide toward per game to judge players on how good they are when they play. Slide toward season to penalize missed games.
- **Add players:** drag a player's name onto a slot in the **My roster** strip. You can also use **Add to my team** in the side panel, or select a player and click an empty slot.
  - New players are priced at **Avg paid** by default. You can edit the price in the side panel or on the My Team tab.
- **Team ratings row:** under the budget row, each league category has a column and a rating. 100 means the average team in the simulated league, and the badge shows your rank.
  - Bars point up when you beat the average team and down when you trail it. TO is inverted, so up is always better.
  - Whenever a change moves a rating, a small +/− chip shows by how much for a few seconds. Click the row to open My Team.
- **Rearrange:** on **My Team**, drag between slots or click one slot and then another.
  - **×** removes a player and **Clear roster** empties every slot.
  - Both show an **Undo** message.
- **Other teams' picks:** select the player, enter the price, and click **Mark taken**. Inflation and Bid to update for everyone left.

## Troubleshooting

**"espn-api isn't installed for this Python"**
Your `python3` is a different Python from the one with espn-api. This is common when other tools add their own Python to your PATH. Install espn-api for it (`python3 -m pip install espn-api`), or run the app with the Python you use for `main.py`, e.g. `python3.12 -m gui`.

**"Couldn't start on port 8000"**
Something else is using the port. Run `python3 -m gui --port 8001`.

**A yellow note says "Using default league settings…"**
The app couldn't read your league, so it's using ESPN's default 12-team league instead. Players and prices still load. The note says why:
- **"ESPN refused the request"**: your league is private. Add `espn_s2` and `SWID` to `settings.txt`.
- **"ESPN couldn't find that league or season"**: check `leagueId`, and make sure the league has been renewed on ESPN for the new season.

After fixing it, click **Refresh from ESPN**.

**The page says it can't reach the server**
The terminal running `python3 -m gui` was stopped or closed. Start it again. Your work is saved.

**Prices look out of date**
Click **Refresh from ESPN**. The Avg paid column moves as more ESPN auction drafts happen.

## For developers

- **Code layout:**
  - `gui/server.py` is a standard-library HTTP server.
  - `gui/board.py` holds the state and builds the snapshot.
  - `gui/static/` is the frontend, with no build step.
  - The math lives in `library/valuation.py` and `library/roster.py`, and ESPN access in `library/draft.py`.
  - The design and model are described in [`docs/GUI_PLAN.md`](../docs/GUI_PLAN.md), and colors and type in `gui/static/tokens.css` ([style reference](../docs/style-reference.html)).
- **Tests:** these run offline against a saved ESPN fixture.

  ```
  python3 -m unittest tests.valuation_test tests.roster_test tests.draft_test
  ```

  (`tests/rating_test.py` and `tests/loading_test.py` are older tests that call ESPN live.)
