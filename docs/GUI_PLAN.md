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

**Python standard-library HTTP server + a plain-JS frontend with no build step.** No new dependencies: the GUI needs only `espn_api`, which the CLI already uses.

- Streamlit was dropped because of drag and drop. It reruns the whole script on every interaction and needs a third-party component for sortable slots.
- FastAPI was planned but not needed. The API is a handful of JSON endpoints, and `http.server` avoids a `pip install` for anyone running the tool.
- **All math runs on the server** (`gui/board.py` → `library/valuation.py`). The browser only renders, so there's one implementation of the model and it's tested in Python.
  - A full recalculation takes about 15 ms. Slider drags send at most one request at a time.
- Run with `python3 -m gui` (options: `--port`, `--settings`, `--refresh`, `--no-browser`). It listens on `127.0.0.1` only.

### API

| Route | Does |
|---|---|
| `GET /api/board` | Full snapshot: league meta, every player row, market, my team, category ranks |
| `POST /api/adjust` | `{id, delta?, expGp?, note?}`. `expGp: null` resets to the default |
| `POST /api/weight` | `{weight}` from 0 to 1 (per game ↔ season) |
| `POST /api/pick` | `{id, status: "mine" or "taken" or null, price?}`. "mine" auto-slots the player |
| `POST /api/move` | `{id, slot, price?}`. Drag and drop, with swaps and bumps |
| `POST /api/price` | `{id, price}` |
| `POST /api/clear-roster`, `/api/reset-adjustments` | Bulk clears |
| `POST /api/state` | `{state}`. Restores a previous state (Undo) |
| `POST /api/refresh` | Re-download the pool from ESPN |

Every POST returns `{board, error}`. Errors are user-facing sentences, e.g. "Cooper Flagg can't play C."

## Architecture

```
library/
  valuation.py      pure math: rating (shared with the CLI), Δ scaling, pool averages,
                    auction $, inflation, simulated-league category ranks
  roster.py         slot eligibility (ESPN eligibleSlots), add / move / swap / remove
  draft.py          ESPN fetch + parse (league settings, player pool), JSON cache
  rating.py, schedule.py, config.py   now import the shared math and constants from valuation.py
gui/
  __main__.py       CLI entry: python3 -m gui
  server.py         stdlib HTTP server, static files + JSON API
  board.py          DraftBoard: pool + your edits → snapshot
  static/           index.html, app.js, styles.css, tokens.css
tests/
  valuation_test.py, roster_test.py, draft_test.py (+ fixtures/)  offline, 34 tests
draftPool.json      gitignored: cached ESPN pull
draftState.json     gitignored: {weight, adjustments, picks, filled}
```

### Refactor (done)

- `rating.ratePlayer`/`ratePercentStat` and `schedule`'s duplicate copies now delegate to `valuation.py`, and `config.py` re-exports its constants from there.
- Checked against the saved league: 1,238 ratings, maximum difference 6×10⁻¹⁴.
- Zero league averages are now skipped instead of raising `ZeroDivisionError`.
- The GUI never imports `library.globals` or `library.config`, so it never loads `league.pickle` and never creates `settings.txt`.

### Data details found while building

- `https://…/games/fba` returns `currentSeasonId`, which is used as the draft season unless `settings.txt` sets `"draftSeason"`.
- Public leagues need no cookies.
  - The league endpoint gives size, auction budget, draft type, scoring categories (TO has `isReverseItem`) and roster slot counts.
  - The league player endpoint also gives `draftAuctionValue`, ESPN's league-specific $, which is shown as "ESPN".
- Players with no last-season games (injured all year, or rookies) fall back to ESPN's projection and get an "ESPN proj" badge. They're excluded from the pool averages.
- Older `espn_api` releases (the one installed for Python 3.9) name three-pointers `3PTM`/`3PTA`. `draft.stat_name` normalizes them.

## Rating and value model

The league is an **auction** draft: 12 teams, $200 each, 12-man rosters (read from `league.settings` and `settings.txt`).

1. **Pool averages.** Pre-draft there are no rosters, so average over the *draftable pool*: the top `numTeams × teamSize` players.
   - **Per-game averages** are Σ totals ÷ Σ GP, the same way `averages.py` computes `avg`.
   - **Season averages** are Σ totals ÷ player count, the same way `averages.py` computes `total`.
2. **Two last-season ratings per player**, both from `ratePlayer`:
   - **Per game** rates the player's per-game stats. This is how good they are when they play.
   - **Season** rates the season totals. Missed games pull it down, so health is built in.
   - Example: Walker Kessler is 131 per game but 34 for the season on 5 GP.
3. **Expected minutes (Exp MIN): per player and editable. This is role.**
   - Defaults to ESPN's projected minutes (`stats[id="102027"].MIN`).
   - The projection keeps the player's per-minute production from `rate_line` and scales it to Exp MIN: `stats × ExpMIN / rateMIN`.
   - `rate_line` is last season, or ESPN's projected line when there were fewer than 20 games last season (e.g. Kessler's 5).
   - ESPN builds its own projections the same way: per-36 rates are unchanged and the minutes change. So the default matches ESPN for most players.
   - "Use ESPN's" sets minutes and games to ESPN's and Δ to ESPN's projected rating change *beyond* minutes (about 0 for most players).
4. **Δ: one number, spread across categories. This is skill, applied on top of minutes.**
   - Δ is entered in **rating points** on the per-game scale (100 = average player): `+10` turns a 133 into a 143.
   - `valuation.scale_for_rating` solves, by bisection, for the single multiplier on every counting stat *and* shot attempt (FGM/FGA/FTM/FTA) that reaches the target rating. Shooting percentages stay the same.
   - Each category moves in proportion to what the player already produces: a shot-blocker gains the most in BLK.
   - FG%/FT% ratings move more for good or bad shooters, because more volume amplifies efficiency in the existing `pow(pctDiff, attemptDiff × 2)` formula.
   - The detail panel shows each category before and after.
   - Later (optional): per-category tilts on top of the overall Δ.
5. **Expected games (Exp GP): per player and editable. This is health.**
   - The default is `round((last GP + 2 × ESPN projected GP) / 3)`, leaning on ESPN's projection, which (`stats[id="102027"]`) includes GP. It was halfway at first, but that priced players who missed time (Giannis, Tatum) far below the market.
   - Later: use a 3-season GP history for a better default, from the player card view, which returns earlier seasons.
   - Override it when you believe in a player's health.
6. **Projected ratings.**
   - `role = rateLine × ExpMIN / rateMIN`
   - `s = scale_for_rating(role, rate(role) + Δ)`
   - `projPerGame = rate(role × s, pgAvg)` (= role rating + Δ)
   - `projSeason = rate(role × s × ExpGP, seasonAvg)`
7. **Value** = `w × projPerGame + (1 − w) × projSeason`. `w` is one global slider, default 50/50, that sets how much per-game quality counts against availability.
8. **Ours $.**
   - `repl` is the value of player #144.
   - `$/pt = (12 × $200 − 144) / Σ surplus of the top 144`.
   - `Ours = $1 + max(0, value − repl) × $/pt`.
   - Recomputed across the whole pool on every edit.
9. **Edge** = `Ours − Avg paid`. This shows who's underpriced in the market.
   - Avg paid is ESPN's `auctionValueAverage` × a market scale. ESPN averages across leagues of all sizes, so its top-N prices add up to less than this league's budget: $1,827 vs $2,400 at the time of writing.
   - The scale (`teams × budget / Σ top-N avg`, about ×1.31) puts both sides on the same dollars.
   - After scaling, mid-tier Edge averages about +1 to +3. The top 12 average about −21, the market's star premium over a linear dollar curve.
10. **Inflation** (during the draft) = `(money left in league − roster spots left × $1) / Σ(Ours − 1) of undrafted players`.
   - **Bid to** = `1 + (Ours − 1) × inflation`.
   - Bid to is shown for reference. Prices default to Avg paid.

## Screens

### Draft Board (v1)

- **Top bar:** league name, season, pool fetched time, **Refresh from ESPN** button.
- **Controls:** player search (name, case- and accent-insensitive), position chips (PG/SG/SF/PF/C), and toggles for *Hide drafted* and *Only adjusted*.
- **Global control:** a *Value weighs* slider, from per game to season.
- **Table** (grouped headers):
  - Rk · Player (team, position, injury, low-GP badge)
  - *2025-26:* GP · Per game · Season
  - *2026-27 outlook:* **Exp GP** · **Exp MIN** · **Δ** (all editable by typing or click-and-drag scrubbing) · Proj per game · Value
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
- **Picks:** adding a player marks them *Mine* with a price, defaulting to **Avg paid** (ESPN's `auctionValueAverage`, minimum $1) and editable in the slot. *Mark taken* uses the same default.
- **Removing:**
  - Every filled slot has an **×**, both on the Board strip and in My Team, that sends the player back to the board.
  - **Clear roster** (on both) empties every slot.
  - Neither asks for confirmation. Both show a message with an **Undo** button for 6 seconds, which restores the players to their slots and prices.
- **Category ranks:**
  - My team's projected season totals (`stats × s × ExpGP`) are compared with 11 simulated opponents.
  - Opponents are dealt Taken players first, then the best remaining players by value, in snake order.
  - Only each team's best `teamSize − ignorePlayers` (9) players count, ranked by per-game rating like `schedule.py`. Empty slots count as the average of players ranked #133–144 by value.
- **The view shows:**
  - For each category: a strip with all 12 teams (mine highlighted), my rank, my total, and the difference from the league average.
  - Overall rank by roto points, and expected H2H categories won per week.
  - A callout for strong and weak categories, with the best-value available players for the weakest category.
- **Team ratings row** (under the scoreline, visible on both tabs):
  - One column per league category with a rating on the player scale, where 100 is the average simulated team. It uses `valuation.team_ratings`: the same volume-weighted formula for percentages, with TO inverted.
  - Columns diverge from the 100 line, and ±40 fills a half-column.
  - Each column shows a rank badge. A +/− chip flashes whenever a change moves a rating.
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

Status as of 2026-09-23: milestones 1–4 are built, and 5 is next.

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

- Exp GP default: is a midpoint with ESPN's projection right, or should it lean more on history, like a 3-season average?
- Worktree setup: `settings.txt` and the pickles are gitignored, so they aren't in this worktree. Symlink or copy `settings.txt` over before running.
