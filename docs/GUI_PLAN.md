# GUI Frontend Plan

Branch: `gui` · Worktree: `../espn-nba-fantasy-analyzer-gui`

## Goal

A local web GUI, starting with a **Draft Board** for the 2026-27 season (ESPN `seasonId` 2027):

1. Search for any player.
2. See each player's **last-season ratings**, both **per game** and **full season**, from the existing `rating.ratePlayer` formula.
3. Enter one **Δ adjustment** (how much we expect them to improve or decline) and **expected games played**. These update the projected ratings, rank, and our dollar value.
4. Compare with **ESPN auction cost**: ESPN's suggested value and the average price paid in real ESPN auction drafts.

In-season features (league ratings, free agents, trade machine) can come later on the same app.

## ESPN data (checked 2026-09-23)

A single unauthenticated request returns everything the draft board needs:

```
GET https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/2027/segments/0/leaguedefaults/3?view=kona_player_info
x-fantasy-filter: {"players":{"limit":500,"sortDraftRanks":{"sortPriority":1,"sortAsc":true,"value":"ROTO"}}}
```

Per player (`players[].player`):

| Field | Meaning |
|---|---|
| `stats[id="002026"]` | Last season actuals: `stats` (totals) and `averageStats` (per game). Keys map through `espn_api.basketball.constant.STATS_MAP` |
| `stats[id="102027"]` | ESPN's projection for the coming season, including projected GP |
| `draftRanksByRankType.ROTO / STANDARD` | ESPN rank and **suggested auction value** (`auctionValue`) |
| `ownership.auctionValueAverage` | **Average price paid** in live ESPN auction drafts |
| `ownership.averageDraftPosition` | ADP (snake drafts) |
| `ownership.percentOwned`, `injuryStatus`, `eligibleSlots`, `proTeamId` | Metadata |

`espn_api`'s `Player` class drops all of this: it keeps only the current season's stats and ignores `draftRanksByRankType` and `ownership`. So we parse the raw JSON ourselves. For league-specific data (keepers, live draft picks), the same request works against the league endpoint through `league.espn_request.league_get(...)` with the `espn_s2`/`SWID` credentials.

## Stack

**FastAPI backend + a plain-JS frontend with no build step.** This changed from Streamlit because of drag and drop.

- Streamlit reruns the whole script on every interaction, and dragging players into roster slots needs a third-party component (`streamlit-sortables`). That's a poor fit for a live auction screen.
- The mockup is already a working vanilla-JS frontend: search, inline edits, sliders, drag and drop, and category ranks. The backend just has to serve the player pool and save your edits.
- **Backend** (`gui/server.py`, FastAPI + uvicorn):
  - Imports `library/` directly.
  - `GET /api/pool` returns the cached ESPN pool plus pool averages.
  - `POST /api/refresh` re-pulls from ESPN.
  - `GET/PUT /api/state` loads and saves Δ, Exp GP, notes, picks and slots.
  - Later: `GET /api/draft` for live picks.
- **Frontend** (`gui/static/`): `index.html`, `app.js` and `styles.css`, served by FastAPI.
  - The valuation math runs in the browser so sliders stay instant.
  - `library/valuation.py` is the Python reference, and tests keep the two in sync.
- Run with `python3 -m gui` and open `http://localhost:8000`.

## Architecture

```
library/
  draft.py          NEW  fetch + parse ESPN player pool → DraftPlayer records; cache to draftPool.json
  valuation.py      NEW  pure functions: pool averages, rating, replacement level, auction $
  rating.py         (reuse ratePlayer / categoryRatePlayer / ratePercentStat)
gui/
  __main__.py       NEW  starts uvicorn
  server.py         NEW  FastAPI: /api/pool, /api/refresh, /api/state
  static/           NEW  index.html, app.js, styles.css (from the mockup)
draftState.json         gitignored: {adjustments: {playerId: {delta, expGp, note}}, picks: {playerId: {status, price}}, slots: [playerId|null × teamSize]}
draftPool.json          gitignored: cached ESPN pull with fetchedAt timestamp
```

### Required refactor

`rating.py` imports `library.globals`, which loads `league.pickle` at import time and can call `quit()` in `validate()`. The GUI must not trigger that.

- Move the pure math (`ratePlayer`, `ratePercentStat`, `categoryRatePlayer`) into `valuation.py`, or make `globals` lazy.
- Leave the existing CLI's behavior unchanged.
- While in there, guard `playerStat / averageStat` against division by zero.

## Rating and value model

The league is an **auction** draft: 12 teams, $200 each, 12-man rosters (read from `league.settings` and `settings.txt`).

1. **Pool averages.** Pre-draft there are no rosters, so average over the *draftable pool*: the top `numTeams × teamSize` players.
   - **Per-game averages** are Σ totals ÷ Σ GP, the same way `averages.py` computes `avg`.
   - **Season averages** are Σ totals ÷ player count, the same way `averages.py` computes `total`.
2. **Two last-season ratings per player**, both from `ratePlayer`:
   - **Per game** rates the player's per-game stats. This is how good they are when they play.
   - **Season** rates the season totals. Missed games pull it down, so health is built in.
   - Example: Walker Kessler is 131 per game but 34 for the season on 5 GP.
3. **Δ: one number, spread across categories.**
   - Δ is a production change. Every counting stat *and* shot attempts (FGM/FGA/FTM/FTA) are multiplied by `(1 + Δ)`, and shooting percentages stay the same.
   - Each category moves in proportion to what the player already produces: a shot-blocker gains the most in BLK.
   - FG%/FT% ratings move more for good or bad shooters, because more volume amplifies efficiency in the existing `pow(pctDiff, attemptDiff × 2)` formula.
   - The detail panel shows each category before and after.
   - Later (optional): per-category tilts on top of the overall Δ.
4. **Expected games (Exp GP): per player and editable.**
   - The default is `round((last GP + ESPN projected GP) / 2)`. ESPN's projection (`stats[id="102027"]`) includes GP.
   - Later: use a 3-season GP history for a better default, from the player card view, which returns earlier seasons.
   - Override it when you believe in a player's health, e.g. Kessler at 62.
5. **Projected ratings.**
   - `projPerGame = rate(stats × (1+Δ), pgAvg)`
   - `projSeason = rate(stats × (1+Δ) × ExpGP, seasonAvg)`
6. **Value** = `w × projPerGame + (1 − w) × projSeason`. `w` is one global slider, default 50/50, that sets how much per-game quality counts against availability.
7. **Ours $.**
   - `repl` is the value of player #144.
   - `$/pt = (12 × $200 − 144) / Σ surplus of the top 144`.
   - `Ours = $1 + max(0, value − repl) × $/pt`.
   - Recomputed across the whole pool on every edit.
8. **Edge** = `Ours − Avg paid` (ESPN `auctionValueAverage`). This shows who's underpriced in the market.
9. **Inflation** (during the draft) = `(money left in league − roster spots left × $1) / Σ(Ours − 1) of undrafted players`.
   - **Bid to** = `1 + (Ours − 1) × inflation`.
   - The price box defaults to Bid to.

## Screens

### Draft Board (v1)

- **Top bar:** league name, season, pool fetched time, **Refresh from ESPN** button.
- **Controls:** player search (name, case- and accent-insensitive), position chips (PG/SG/SF/PF/C), and toggles for *Hide drafted* and *Only adjusted*.
- **Global control:** a *Value weighs* slider, from per game to season.
- **Table** (grouped headers):
  - Rk · Player (team, position, injury, low-GP badge)
  - *2025-26:* GP · Per game · Season
  - *2026-27 outlook:* **Exp GP (editable)** · **Δ % (editable)** · Proj per game · Value
  - *Auction $:* ESPN · Avg paid · **Ours** · **Edge** · **Bid to**
  - Edge uses green/red. Edited cells are highlighted amber.
- **Player detail** (on row select):
  - A ratings table: per game and season, for 2025-26 and 2026-27.
  - Before/after category bars that show how Δ spreads.
  - Δ and Exp GP sliders.
  - ESPN's implied Δ and GP, with a *Use ESPN's* button.
  - Note field, and Mark mine/taken with a price.
- Δ, Exp GP and notes save on edit to `draftAdjustments.json` (`{playerId: {delta, expGp, note}}`), so they survive restarts.

### My Team

- **Slots** come from `rosterPositions` in `settings.txt` (PG, F, F, SG/SF, SG/SF, C, UT), plus bench slots up to `teamSize`.
- **Eligibility:** `F` = SF or PF, `G` = PG or SG, `X/Y` = either, and `UT` and bench take anyone.
- **Adding players:**
  - Drag a player from the board onto the roster strip.
  - Or use *Add to my team* in the player panel, which picks the first open eligible slot, starters before bench.
  - Or select a player and click an empty slot.
- **Moving players:**
  - Drag between slots, or click one slot and then another. This works from the keyboard too.
  - Dropping on an occupied slot swaps the two players if both fit. Otherwise the displaced player goes to the next open eligible slot.
  - An ineligible drop is rejected with a message like "Flagg (SF/PF) can't play C".
- **Picks:** adding a player marks them *Mine* with a price, defaulting to Bid to and editable in the slot.
- **Removing:**
  - Every filled slot has an **×**, both on the Board strip and in My Team, that sends the player back to the board.
  - **Clear roster** (on both) empties every slot.
  - Neither asks for confirmation. Both show a message with an **Undo** button for 6 seconds, which restores the players to their slots and prices.
- **Category ranks:**
  - My team's projected season totals (`stats × (1+Δ) × ExpGP`) are compared with 11 simulated opponents.
  - Opponents are dealt Taken players first, then the best remaining players by value, in snake order.
  - Only each team's best `teamSize − ignorePlayers` (9) players count, ranked by per-game rating like `schedule.py`. Empty slots count as the average of players ranked #133–144 by value.
- **The view shows:**
  - For each category: a strip with all 12 teams (mine highlighted), my rank, my total, and the difference from the league average.
  - Overall rank by roto points, and expected H2H categories won per week.
  - A callout for strong and weak categories, with the best-value available players for the weakest category.
- **Once live sync lands:** replace the simulated opponents with the real rosters from the ESPN draft, simulating only the rest of the draft.
- **Include TO** (lower is better) once the pool data has it. It's in `categories` and missing from the mockup.

### Draft Tracker

- Mark a player as *Taken* with the price paid. The scoreline shows budget left, max bid, inflation, and the best edge still available.
- **Live sync:** poll the league draft endpoint (`get_league_draft`, `mDraftDetail`) every ~10 s during the draft to mark picks automatically, both mine (into slots) and other teams'.

### Later

- Port the Google Sheet views: team ratings, free agents, and the remaining-schedule (+Gms) value.
- Trade machine UI on top of `customizer.py`.
- Settings page that edits `settings.txt`: categories, teams, budget, credentials.

## Milestones

1. **Data layer:** `draft.py` + `valuation.py`, the rating refactor, and tests against a saved ESPN JSON fixture (no network in tests).
2. **Draft Board:** search, filters, editable Δ, persistence, Our $, and Edge.
3. **Player detail** panel and category bars.
4. **My Team:** slots, drag and drop, and category ranks against simulated opponents.
5. **Draft Tracker:** manual marking first, then live ESPN sync that feeds real opponent rosters into My Team.
6. **In-season pages.**

## Decisions

- **Auction** league. Edge is in dollars, and ADP is dropped from the board.
- **Δ** is one overall % per player, spread by scaling volume. Per-category tilts can come later.
- Each player has **both per-game and season ratings**, blended by a global weight.
- **Health** is handled by the per-player Exp GP, whose default weighs last season's games.

## Open questions

- Stack: confirm FastAPI + plain JS instead of Streamlit (see Stack).
- Exp GP default: is a midpoint with ESPN's projection right, or should it lean more on history, like a 3-season average?
- Worktree setup: `settings.txt` and the pickles are gitignored, so they aren't in this worktree. Symlink or copy `settings.txt` over before running.
