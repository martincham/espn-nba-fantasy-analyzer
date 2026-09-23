# Draft Room

A local web app for your fantasy basketball auction draft. It pulls your league's settings plus every player's last-season stats and ESPN auction prices, then lets you plan and track your draft in the browser.

- **Board:** search and filter the player pool. Each player gets a per-game rating and a **Value** (per-game rating × expected games), and you can set your own **expected minutes** (role), **Δ** (skill change, in rating points) and **GP Δ** (games more or fewer than ESPN projects: health). Compare **Ours** (our dollar value) with **Avg paid** (the average price in ESPN auctions, scaled to your league's budget) to find bargains.
- **My Team:** drag players into your roster slots and see how your team ranks in each category against a simulated 12-team league.
- **During the draft:** mark players as yours (at the price you paid) or taken by another team, and follow your budget and max bid.
- **Settings:** tune the replacement player, how many core players share the money, the Avg paid scale, which categories count, and how many players count toward team totals.

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
   | `ignoredStats` | Categories left out of player values (e.g. `"TO"`). You can change this on the Settings tab |
   | `ignorePlayers` | How many of your worst players don't count toward team totals (default 3). You can change this on the Settings tab |
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
| `--reload` | For development: restart the server when a `.py` file in `gui/` or `library/` changes, and refresh the open page after a restart or an edit in `gui/static/` |

## Your data

The app keeps two files in the repo folder. Both are gitignored.

- **`draftPool.json`** holds the ESPN data: league settings, players, stats and prices. It's downloaded once and reused. Click **Refresh from ESPN** (or start with `--refresh`) to update prices and injuries, e.g. on draft day.
- **`draftState.json`** holds your work: Δ values, GP Δ, expected minutes, notes, picks, your prices, roster slots and the Settings tab. It saves on every change, so you can close the app and pick up where you left off.

To start over, stop the app and delete `draftState.json`.

## Using it

- **Search:** press **/** to jump to the search box. It matches player names and NBA team abbreviations, ignoring accents.
- **Filter by team:** the row of team-colored buttons under the search box shows one NBA team at a time (**FA** is unsigned players). Click the selected team again, or **All**, to clear it. Arrow keys move between teams.
- **Edit a player:** drag sideways on a **GP Δ**, **Exp MIN** or **Δ** cell to change it (hold Shift for bigger steps), or click the cell to type. You can also select a row and use the sliders in the side panel.
  - **Exp MIN defaults to ESPN's projected minutes.** Production scales with minutes, keeping the player's per-minute rates from last season. With fewer than 20 games last season, ESPN's projected line is used instead. Clear the cell to go back to ESPN's minutes.
  - **Δ is in rating points** on the per-game scale where 100 is the average player: `+10` turns a 133 into a 143. It's applied on top of the minutes change, so use it for real improvement or decline, not role. The change spreads across categories in proportion to what the player already produces.
  - **Exp GP** is ESPN's projected games plus your **GP Δ**: type `-10` for a player you think misses ten more games than ESPN expects.
  - Type Δ however is natural: `+5`, `-10` and `−10` all work. Press ↑/↓ to step by 1, or hold Shift to step by 5.
  - Edited values are highlighted in marigold. They save the moment you press Enter or leave the box.
  - Clear the GP Δ cell to go back to ESPN's games.
  - **Use ESPN's** copies ESPN's projection.
- **Value** is the player's per-game rating across an 82-game season. His expected games count at his rating, and the games he misses count at the **replacement rating** (default 95): the free agent you pick up while he's out. The ideas behind the model are in [`docs/PHILOSOPHY.md`](../docs/PHILOSOPHY.md).
- **Add players:** drag a player's name onto a slot in the **My roster** strip. You can also use **Add to my team** in the side panel, or select a player and click an empty slot.
  - New players are priced at **Avg paid** by default. You can edit the price in the side panel or on the My Team tab.
- **Team ratings row:** under the budget row, each league category has a column and a rating. 100 means the average team in the simulated league, and the badge shows your rank.
  - Bars point up when you beat the average team and down when you trail it. TO is inverted, so up is always better.
  - Whenever a change moves a rating, a small +/− chip shows by how much for a few seconds. **Open My Team** in the row's first box shows the details.
  - **Punt** checkboxes: tick one to give up that category on purpose. The Fit column then ignores it. Nothing is ever punted unless you tick it.
- **Fit:** each player's value to *your current team*, on the same scale as Value. Categories you're already winning count less: your team's rating in a category counts in full up to 110, then less and less, and not at all past 140 (Settings → Enough in a category). Sort by Fit during the draft to find who helps you most.
  - **Fit edge** = Fit $ − Avg paid: the bargain *for your team*, where Edge is the bargain for anyone. **Fit $** (Fit converted to dollars) and **Fit rank** are in the player panel. ESPN's own suggested price is also in the panel now.
- **Rearrange:** on **My Team**, drag between slots or click one slot and then another.
  - **×** removes a player and **Clear roster** empties every slot.
  - Both show an **Undo** message.
- **Other teams' picks:** flip the switch at the left of the player's row (or click **Mark taken** in the side panel). There's no price to enter: it only records that you can't get them. Flip it back to undo. Your own players show an orange dot there instead.
  - **Pool left** counts how many core players (the top 84 by value with 7 per team) are still available.
- **Settings tab:**
  - **Replacement player:** the per-game rating of the free agent who fills a hurt player's games. Lower it to make health count more; 0 counts missed games as lost.
  - **Core players:** how many players per team share the money (default 7). The rest of the roster are priced at $1.
  - **Enough in a category:** where Fit starts fading a category you're winning (110) and where more stops counting (140).
  - **Avg paid scale:** Auto fits ESPN's prices to your league's budget. Drag the slider to set your own multiplier.
  - **Categories in player value:** starts from `ignoredStats` in settings.txt. Team ranks always show every category.
  - **Players who count:** how many of your best players count toward team totals. Starts from `ignorePlayers`.
  - **Default expected games:** the blend of ESPN's projected games and last season's. Default ⅔ ESPN.
  - **Reset draft:** unmarks every taken player and empties your roster, with Undo.
  - Changes save to `draftState.json`; settings.txt is never edited.

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

**Why Avg paid is higher than on ESPN**
ESPN averages prices across leagues of every size, so for the top players it adds up to less than a 12-team, $200 league spends. The app scales it to your league's budget. The factor (about ×1.31) is in the column's tooltip and on the Settings tab, where you can change it. The raw ESPN price is in the player panel's tooltip.

## For developers

- **Code layout:**
  - `gui/server.py` is a standard-library HTTP server.
  - `gui/board.py` holds the state and builds the snapshot.
  - `gui/static/` is the frontend, with no build step.
  - The math lives in `library/valuation.py` and `library/roster.py`, and ESPN access in `library/draft.py`.
  - The design and model are described in [`docs/GUI_PLAN.md`](../docs/GUI_PLAN.md), and colors and type in `gui/static/tokens.css` ([style reference](../docs/style-reference.html)).
- **Live editing:** run `python3 -m gui --reload`.
  - Saving a Python file restarts the server, and the page refreshes itself. Your data is kept, because it lives in `draftState.json`.
  - If a change breaks the server (e.g. a syntax error), the terminal shows the error and restarts when you save a fix.
  - Without `--reload`, CSS, JS and HTML edits only need a browser refresh, and Python edits need a restart.
- **Tests:** these run offline against a saved ESPN fixture.

  ```
  python3 -m unittest tests.valuation_test tests.roster_test tests.draft_test
  ```

  (`tests/rating_test.py` and `tests/loading_test.py` are older tests that call ESPN live.)
