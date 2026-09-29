# Draft Room

A local web app for your fantasy basketball auction draft. It pulls your league's settings plus every player's last-season stats and ESPN auction prices, then lets you plan and track your draft in the browser.

- **Board:** search and filter the player pool. Each player gets a per-game rating and a **Value** (per-game rating × expected games), and you can set your own **expected minutes** (role), **Δ** (skill change, in rating points) and **GP Δ** (games more or fewer than ESPN projects: health). Compare **Ours** (our dollar value) with **Avg paid** (the average price in ESPN auctions, scaled to your league's budget) to find bargains.
- **My Team:** drag players into your roster slots and see how your team ranks in each category against a simulated 12-team league.
- **During the draft:** mark players as yours (at the price you paid) or taken by another team, and follow your budget and max bid.
- **Settings:** tune the replacement player, how many core players share the money, the Avg paid scale, which categories count, and how many players count toward team totals.

Everything runs on your computer. The app listens on `127.0.0.1` only, so other devices on your network can't reach it. To share it with friends, see [Host it online](#host-it-online).

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
| `--host 0.0.0.0` | Listen on every network interface, not just this computer (default `127.0.0.1`). Refuses to start unless `DRAFTROOM_PASSWORD` is set |
| `--data-dir path/` | Keep `draftPool.json` and `draftState.json` in another folder (default the repo folder, or `$DRAFTROOM_DATA`) |
| `--settings path/to/settings.txt` | Read settings from somewhere else (default `settings.txt` in the data folder) |
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
- **Categories:** click **Categories ▸** above the Rk column to open a column for each league category, right after the player's name. Each shows his projected per-game rating in that category (100 = average; hover for the stat itself), tinted green above average and red below. **◂ Hide categories** closes them again; the app remembers which you chose.
  - **Sort by one or more categories:** click category headers to pick them (they're underlined), and the board sorts by **Mix**, best first. Click a picked header again to drop it; click Mix to reverse.
  - **Mix** is the player's average percentile in the picked categories among the top 144 players: 90 means better than 90% of them. Percentiles keep one extreme category (a 578 in blocks) from drowning out the others.
- **Only affordable:** hides undrafted players whose Avg paid is more than your max bid. The label shows your current max bid.
- **Max cost, Min MIN, Min value:** sliders that hide undrafted players above a Cost, below an Exp MIN (minutes a game), or below a Value. Drag Max cost to the right end, or the Min sliders to the left end, to show everyone.
- **Filter by team:** the row of team-colored buttons under the search box shows one NBA team at a time (**FA** is unsigned players). Click the selected team again, or **All**, to clear it. Arrow keys move between teams.
- **Edit a player:** drag sideways on a **GP Δ**, **Exp MIN** or **Δ** cell to change it (hold Shift for bigger steps), or click the cell to type. You can also select a row and use the sliders in the side panel.
  - **Exp MIN defaults to ESPN's projected minutes.** Production starts from ESPN's projected per-game line and scales with minutes, keeping ESPN's per-minute rates. (Settings → Rating model can use last season's per-minute rates instead.) Clear the cell to go back to ESPN's minutes.
  - **Δ is in rating points** on the per-game scale where 100 is the average player: `+10` turns a 133 into a 143. It's applied on top of the minutes change, so use it for real improvement or decline, not role. The change spreads across categories in proportion to what the player already produces.
  - **Exp GP** is ESPN's projected games plus your **GP Δ**: type `-10` for a player you think misses ten more games than ESPN expects.
  - Type Δ however is natural: `+5`, `-10` and `−10` all work. Press ↑/↓ to step by 1, or hold Shift to step by 5.
  - Edited values are highlighted in marigold. They save the moment you press Enter or leave the box.
  - Clear the GP Δ cell to go back to ESPN's games.
  - **Use ESPN's** copies ESPN's projection.
- **Cost:** what a player should cost. It starts at ESPN's Avg paid, scaled to your league. If you disagree, type your own price or drag the cell. Your price is highlighted, and it drives Edge, Fit edge, "Only affordable" and the default price when you add him to your team. Clear the cell to go back to ESPN's. **Clear adjustments** keeps your prices.
- **Value** is the player's per-game rating across an 82-game season. His expected games count at his rating, and the games he misses count at the **replacement rating** (default 95): the free agent you pick up while he's out. The ideas behind the model are in [`docs/PHILOSOPHY.md`](../docs/PHILOSOPHY.md).
- **My roster strip:** each filled slot shows what you paid, so you can see what dropping him frees up. The label shows your total spent and what's left.
- **Add players:** drag a player's name onto a slot in the **My roster** strip. You can also use **Add to my team** in the side panel, or select a player and click an empty slot.
  - New players are priced at **Avg paid** by default. You can edit the price in the side panel or on the My Team tab.
- **Team ratings row:** under the budget row, each league category has a column and a rating. 100 means the average team in the simulated league, and the badge shows your rank.
  - Bars point up when you beat the average team and down when you trail it. TO is inverted, so up is always better.
  - Each category shows how far you're ahead of or behind the average team (+15, −6), your chance of winning it in a given week, and your rank. The first box counts the categories you're winning and your expected weekly record, e.g. 5.8–3.2. In an each-category league like this one, every category is a win or loss in the standings, so 8–1 beats 5–4.
  - Whenever a change moves a rating, a small +/− chip shows by how much for a few seconds. **Open My Team** in the row's first box shows the details.
  - **Punt** checkboxes: tick one to give up that category on purpose. The Fit column then ignores it. Nothing is ever punted unless you tick it.
- **Fit:** each player's value to *your current team*, on the same scale as Value. It's how much he raises your weekly category win chances, so categories you're already winning count less. Steady categories (PTS, FG%, FT%) reach a sure win sooner than swingy ones (BLK, STL). Settings → Fit can switch to a simple fade instead: full weight up to 110, nothing past 140. Sort by Fit during the draft to find who helps you most.
  - Fit follows the NBA schedule. Each day only 7 players start, so a player whose games fall on nights your roster is already full adds less, and one who plays on nights your core is idle adds more. Your streaming spots fill open slots at the replacement rating. The player panel shows **Starts**: the share of his games that would make your lineup.
  - **Fit edge** = Fit $ − Avg paid: the bargain *for your team*, where Edge is the bargain for anyone. **Fit $** (Fit converted to dollars) and **Fit rank** are in the player panel. ESPN's own suggested price is also in the panel now.
- **Plan tab:** click **Build plan** for the team that wins the most categories per week at expected prices (Cost: Avg paid or your own price). It keeps the players already on your roster, skips taken players, fits your budget, and ignores categories you punt. Only your best 9 count, so it buys up to 9 and leaves $1 streaming spots. It takes 10–30 seconds on a laptop, a floor plan about twice that, and longer on a small hosted machine; the tab shows the time so far and how long the last one took.
  - Each recommended player has **alternatives**: the best players who could take his spot within your budget, and how many categories per week you'd gain or lose.
  - **Other builds** are different rosters that finished close behind, with what goes in and out and which categories move.
  - **Leave out** a player you won't buy (say, one whose games you don't trust): click **Leave out** on his Plan row, which rebuilds right away, or **Leave out of plan** in his side panel. The plan never recommends him, but the simulated opponents can still draft him. The **Left out** list at the top of the tab brings players back with ×.
  - The plan doesn't update by itself. When you mark a pick or change a price or setting, it says it's out of date: click **Rebuild**.
  - **Optimize for** picks the weeks it wins: **Season** (every week the same), **Playoffs** (only the fantasy playoff weeks), or **Season + playoffs** (the playoff weeks count as much as the whole regular season).
- **Playoffs tab:** when the fantasy playoffs land (from the league's ESPN settings: here the top 4 of 12, weeks 21–24, as two 2-week rounds), and how to build for them. Four weeks is a small sample of each player's schedule, so it matters much more there than over a season.
  - **Each playoff week, night by night:** how many NBA teams play (green nights are light: fewer than half play, so games fit into lineups easily), and how many of your players have a game. Red means more of them than your starting slots, so someone sits.
  - **Your team in the playoffs:** categories won per week against the average team over just those weeks, your chance of winning a matchup, and each player's games, starts and **Playoff Fit**.
  - **Playoff Fit** is Fit counted over the playoff weeks alone, on Fit's scale: 100 is an average player with an average playoff schedule. A player whose team plays more then, on nights your lineup has room, rates above his Fit. **Best for the playoffs** lists the players you can still get by it.
  - **Plan a playoff team** runs the Plan tab's search for **Playoffs** or **Season + playoffs**.
  - **NBA schedules in the playoffs:** every team's games in each playoff week, and its games on light nights.
  - Matchup weeks follow ESPN's: opening night to the first Sunday, then Monday to Sunday, with the All-Star week joined to the next. Before the season ESPN leaves the NBA Cup knockout games off the schedule; **Refresh from ESPN** picks them up once they're set. Late-season rest for stars isn't in the schedule.
- **Rearrange:** on **My Team**, drag between slots or click one slot and then another.
  - **×** removes a player and **Clear roster** empties every slot.
  - Both show an **Undo** message.
- **Other teams' picks:** flip the switch at the left of the player's row (or click **Mark taken** in the side panel). There's no price to enter: it only records that you can't get them. Flip it back to undo. Your own players show an orange dot there instead.
  - **Pool left** counts how many core players (the top 84 by value with 7 per team) are still available.
- **Settings tab:**
  - **Replacement player:** the per-game rating of the free agent who fills a hurt player's games. Lower it to make health count more; 0 counts missed games as lost.
  - **Core players:** how many players per team share the money (default 7) under *Worth* pricing. The rest of the roster are priced at $1.
  - **Rating model:** the per-game line (*ESPN projection* or *Last season per minute*), category weights (*Weekly win impact* or *Equal*) and dollars (*Worth* or *League price curve*). The default line and weights tested better on this league's past seasons; see [`docs/BACKTEST_PLAN.md`](../docs/BACKTEST_PLAN.md).
    - *Worth* (default): the core players split the league's money in proportion to their value above the last of them, with no cap, so Ours says what a player is worth rather than what the room will pay (that's Cost).
    - *League price curve*: the Nth most valuable player gets what this league has paid for its Nth most expensive player, which caps Ours near $80. The backtest's dollar check favored the curve by about $1 a pick, but it scored against prices set on that same curve. The formula put the top player at $97–168.
  - **Fit:** *Win chances* (default) or *Simple fade*, with the fade's start (110) and end (140).
  - **Avg paid scale:** Auto fits ESPN's prices to your league's budget. Drag the slider to set your own multiplier.
  - **Categories in player value:** starts from `ignoredStats` in settings.txt. Team ranks always show every category.
  - **Players who count:** how many of your best players count toward team totals. The rest are streaming spots. Starts at your whole roster; settings.txt's `ignorePlayers` isn't used here.
  - **Default expected games:** the blend of ESPN's projected games and last season's. Default ⅔ ESPN.
  - **Reset draft:** unmarks every taken player and empties your roster, with Undo.
  - Changes save to `draftState.json`; settings.txt is never edited.

## Host it online

To share the board with friends, and keep it up while your computer is off, run it on [Fly.io](https://fly.io). It costs roughly $2 a month: the smallest machine, which stops when nobody's using it and starts on the next visit, plus a 1 GB disk for your draft. The repo has the `Dockerfile` and `fly.toml` it needs.

**What keeps it private:**
- A shared password. Every page and request needs it. After you enter it, a cookie keeps that browser signed in for 90 days, and opening the board extends that.
- HTTPS, so the password and your draft are encrypted on the way.
- Your ESPN cookies are stored as Fly secrets. They stay on the server and never reach the browser. The image holds only `gui/` and `library/` (see `.dockerignore`), never `settings.txt` or your JSON files.

**Everyone shares one board.** That suits co-managers of one team. Anyone with the password can change your draft, click **Refresh from ESPN** (which uses your cookies) or **Reset draft**, so give it only to people you trust. Your valuations and notes are your draft strategy.

### Setup

1. Install `flyctl` and sign in: `brew install flyctl`, then `fly auth login`. Fly asks for a card.
2. From the repo folder, create the app. Pick a name; it becomes `https://NAME.fly.dev`:

   ```
   fly launch --copy-config --no-deploy --name NAME
   ```

   Say no if it offers databases or other extras. It keeps `fly.toml`'s settings and writes your app name into it. Change `primary_region` in `fly.toml` if `iad` (Virginia) isn't close to you (`fly platform regions` lists them).

3. Create the disk, in the same region:

   ```
   fly volumes create draftroom_data --size 1 --region iad
   ```

4. Set the password. Use a long passphrase, since anyone on the internet can try to guess it:

   ```
   fly secrets set DRAFTROOM_PASSWORD='a long passphrase you share with friends'
   ```

5. Copy your league and ESPN cookies from `settings.txt` into Fly secrets. This pipes them straight to Fly, so they don't end up in your shell history:

   ```
   python3 -c "import json; s = json.load(open('settings.txt')); print(f\"ESPN_LEAGUE_ID={s['leagueId']}\nESPN_S2={s['espn_s2']}\nESPN_SWID={s['SWID']}\")" | fly secrets import
   ```

   A public league only needs `ESPN_LEAGUE_ID`. To force a season, also set `DRAFT_SEASON` (e.g. `2027`).

6. Deploy. Keep it to one machine, because the board lives in that machine's memory and on its disk:

   ```
   fly deploy --ha=false
   ```

7. Open `https://NAME.fly.dev`, enter any username and the password. On first start it downloads the player pool from ESPN.

### Bring your local draft along (optional)

Copy your `draftState.json` (and `draftPool.json` and `draftPoolHistory.json`, to skip the download) to the disk, then restart so the app reads them:

```
fly ssh sftp shell
» put draftState.json /data/draftState.json
» put draftPool.json /data/draftPool.json
» put draftPoolHistory.json /data/draftPoolHistory.json
fly apps restart NAME
```

(Press Ctrl+D to leave the sftp shell.) Restart right after the upload: the running app saves over `draftState.json` on the next change. `fly ssh sftp get /data/draftState.json` copies it back down.

### Keeping it running

- **Update the code:** `fly deploy --ha=false`. Your draft stays on the disk.
- **Draft day:** set `min_machines_running = 1` in `fly.toml` and deploy, so nobody waits for the machine to start. Set it back to 0 afterwards.
- **Change the password:** `fly secrets set DRAFTROOM_PASSWORD=...` (the app restarts). This signs every browser out, and everyone enters the new one.
- **New ESPN cookies:** rerun step 5. They expire every few months, or when you sign out of ESPN everywhere.
- **Logs:** `fly logs`.
- **Remove it:** `fly apps destroy NAME` deletes the app, its disk and its secrets.

### Keeping costs down

Fly has no spending cap and no billing alerts. Prepaid credits don't cap it either: when they run out, the rest goes on your card. You're billed once a month, for the month before.

- **After the first deploy, check what you're paying for:**
  - `fly machines list` shows one machine. A second one doubles the compute and splits your draft; destroy it with `fly machines destroy ID`.
  - `fly volumes list` shows one volume.
  - `fly ips list` shows a *shared* IPv4. A dedicated one costs about $2 a month; `fly ips release ADDRESS` removes it.
- **Watch the bill:** look at the Billing page in the Fly dashboard during the first couple of weeks.
- **Card alerts:** set your bank to alert you on any purchase over about $10. For a hard limit, give Fly a virtual card with a monthly limit (e.g. [Privacy.com](https://privacy.com)), which declines anything over it.
- **Snapshots:** Fly snapshots the disk daily and bills for the storage, a few cents a month for 1 GB. `fly volumes update ID --scheduled-snapshots=false` turns them off, but then there's no backup.
- **After the draft:** `fly apps destroy NAME`. A stopped app still pays for its disk.

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
  - `gui/server.py` is a standard-library HTTP server. With `DRAFTROOM_PASSWORD` set it requires the password (HTTP Basic auth) or the 90-day session cookie it hands out after a login on every request. Without one it only answers requests addressed to `127.0.0.1` or `localhost`, so another site can't reach it through DNS rebinding. It always refuses POSTs from other sites' pages.
  - `gui/board.py` holds the state and builds the snapshot.
  - `gui/static/` is the frontend, with no build step.
  - The math lives in `library/valuation.py`, `library/roster.py`, `library/planner.py` and `library/playoffs.py` (matchup weeks and playoff rounds), and ESPN access in `library/draft.py`.
  - The design and model are described in [`docs/GUI_PLAN.md`](../docs/GUI_PLAN.md), and colors and type in `gui/static/tokens.css` ([style reference](../docs/style-reference.html)).
- **Live editing:** run `python3 -m gui --reload`.
  - Saving a Python file restarts the server, and the page refreshes itself. Your data is kept, because it lives in `draftState.json`.
  - If a change breaks the server (e.g. a syntax error), the terminal shows the error and restarts when you save a fix.
  - Without `--reload`, CSS, JS and HTML edits only need a browser refresh, and Python edits need a restart.
- **Tests:** these run offline against a saved ESPN fixture.

  ```
  python3 -m unittest tests.valuation_test tests.roster_test tests.draft_test tests.hosting_test tests.planner_test tests.playoffs_test
  ```

  (`tests/rating_test.py` and `tests/loading_test.py` are older tests that call ESPN live.)
