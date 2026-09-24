# Rating Backtest Plan

Branch: `gui` · Data: `history/` (fetched by `history/fetch_history.py`, untracked)

## Goal

Change the rating and projection so that a player's **preseason value** predicts **what he actually adds to category wins** better than today, without fitting noise in a handful of seasons.

## Why the current 0.75 isn't the target

`history/analyze.py` found r = 0.75 between Projected $ and Earned $ across 431 drafted players (2023-24 to 2025-26). Both sides use the same rating formula, so changing the formula moves the target too. A change could raise that number without predicting wins any better.

The target has to be fixed and independent of the rating formula.

### The target: category wins added (CWA)

For each player-season, take his actual per-game line and games played, add him to a league-average team, and count the extra weekly category wins he produces:

- The average team and how much each category's weekly total varies come from this league's real weekly matchup totals (`matchups.json`, regular season).
- Per week, the player's stats are his per-game line × his games that week. Compare against the average team with a replacement player in his place.
- FG% and FT% are computed from makes and attempts, TO counts against, exactly as the league scores them.
- It doesn't depend on who rostered him or on any rating formula.

**Check before using it:** sum CWA over what each team's players actually counted (the weekly box scores). That should predict the team's all-play category wins at r ≈ 0.95 or better. If it doesn't, the target is wrong.

## What the diagnostic shows (431 drafted players, 3 seasons)

| Test | r |
|---|---|
| Current: projected $ vs earned $ | 0.75 |
| If games played had been known exactly | 0.80 |
| If per-game quality had been known exactly | 0.96 |
| ESPN projected games vs actual games | 0.29 |

- Per-game quality is where most of the error is. Under the current value formula games matter less, because missed games are filled at a 95 rating.
- ESPN projected 70.2 games per drafted player on average; they played 61.1. That's a consistent 9-game bias.
- The diagnostic used ESPN's per-game projection directly. The draft board uses last season's per-minute production scaled to ESPN's projected minutes, so the baseline has to be re-run through the board's actual pipeline (`DraftPlayer.rate_line`).

## Guarding against overfitting

1. **Double the data first.** ESPN has three older seasons of this league (2020-21 to 2022-23): the same $200 auction, 12 teams and 9 categories, with preseason projections. That makes 6 seasons and about 850 drafted player-seasons. 2020-21 was a 72-game season, so games need scaling. Last-season stats come from the previous season's `players.json`; 2019-20 comes from ESPN's league-independent `leaguedefaults` endpoint.
2. **Hold 2025-26 back.** Tune only on 2020-21 to 2024-25, and score 2025-26 once at the very end.
3. **Leave one season out.** Fit on the other tuning seasons, score the held-out one, and repeat. A change counts only if it wins in at least 4 of 5 held-out seasons (3 of 4 for changes that use ESPN's projection; see step 3).
4. **Few parameters.** At most one free parameter per change and five changes in total. Prefer values measured directly from the data (the replacement rating, the games bias) over values found by search.
5. **Shrink toward the defaults.** Pull fitted values halfway toward today's values, as `CATEGORY_SPREAD` already does.
6. **Require a real gain.** A paired bootstrap (resampling players within each season) gives a 95% interval on Δr. Ignore gains under about 0.02 or inside the interval.
7. **Log every variant tried**, including failures, so the number of attempts is visible.
8. **Measure the ceiling.** Correlate CWA from odd weeks against even weeks. That shows how much of a season is predictable at all, and when to stop.

## Candidate changes, in order

**Does the rating measure what wins?** Tested on actual stats against CWA.

1. **Category weights from the league's win curves.** Weight each category by how much a unit of it moves the weekly win chance, instead of equal weight on each stat's ratio to the pool average. The ratio-to-average scale is how Wembanyama got a projected 186 rating from blocks. Extends the existing `CATEGORY_SPREAD` fit; no new free parameters.
2. **Simpler shooting percentages.** Replace the exponential formula with makes above an average shooter on the same attempts, weighted like the other categories.
3. **TO.** Measure what turnovers are actually worth, to decide whether leaving them out by default costs anything.

**Does preseason value predict the season?** Run through the draft board's real pipeline.

4. **Correct ESPN's games projection** toward the pool average (one parameter).
5. **Set the replacement rating from the data**, about 92 instead of 95 (no parameter).
6. **Blend ESPN's per-game projection with last season's per-minute rates** (one weight).

**Draft check.** The model's projected-vs-paid gaps should still line up with earned minus paid, and its top 84 should be ranked better.

## Metrics

- **Primary:** Spearman rank correlation between preseason value and CWA, over players with projections. For an auction, getting the order right is what counts.
- **Secondary:** dollar error on players who cost $5 or more.
- **Reference only:** Pearson r, for comparison with the old 0.75. It will start lower on the stricter target.

## Deliverables

- `fetch_history.py 2021 2022 2023`: the older seasons.
- `history/backtest.py`: builds CWA, holds the list of variants, runs the season-by-season tests.
- A results page listing every variant tried.
- Accepted changes go into `library/valuation.py` behind settings, with tests. Defaults change only after the 2025-26 check passes.

## Status

- [x] Step 1: fetch 2020-21 to 2022-23 (plus 2019-20 players via `fetch_history.py --players-only 2020`)
- [x] Step 2: build CWA and validate it against all-play wins
- [x] Step 3: baseline through the draft board's pipeline
- [x] Step 4: candidate changes, season by season
- [x] Step 5: one check on 2025-26, then implemented

## Results so far

### Step 2: the target works (2026-09-24)

`history/backtest.py` writes each season's CWA to `history/<season>/cwa.json`.

Summed CWA of what each team counted, plus the team's games volume, against its all-play category wins:

| Season | r | Players only (no volume term) |
|---|---|---|
| 2020-21 | 0.982 | 0.620 |
| 2021-22 | 0.987 | 0.415 |
| 2022-23 | 0.991 | 0.878 |
| 2023-24 | 0.989 | 0.903 |
| 2024-25 | 0.988 | 0.840 |
| 2025-26 | 0.984 | 0.885 |
| Pooled, within season | 0.988 | |

- The volume term matters: teams differ in how many games they fill, and in 2020-21 and 2021-22 that difference was large. For player value, CWA compares a player with a replacement on the same games, which is the right comparison for pricing him. Games volume is the manager's doing, not the player's.
- The replacement line is the games-weighted average of every pickup stint that season. A player in an active week plays the league's average games per counted player-week (2.6–2.8).
- CWA has no fitted parameters, so validating it on 2025-26 doesn't use up the held-back season.
- 2020-21 had 72 games and 18 matchup weeks, so its CWA totals run lower. Compare seasons with within-season correlations, never pooled raw values.

### First look: the rating already describes production well (2020-21 to 2024-25 only)

Today's rating formula on a player's actual stats, against CWA, for each season's top 200 by CWA:

| | Spearman |
|---|---|
| Per-game rating vs CWA per game | 0.977–0.983 |
| Season value (95 replacement fill) vs CWA | 0.929–0.961 |

**This changes the priorities.** Candidates 1–3 (category weights, percentage math, TO) can gain at most about 0.02 in how the rating describes a season. They're still worth one test each, but the room is small. The season-value gap comes from how games are counted, which candidate 5 addresses. The biggest lever is the projection itself: the preseason per-game projection correlates only 0.79 with the actual per-game rating, and ESPN's games projection runs 9 games high (candidates 4 and 6). Step 3 should start there.

### Step 3: the draft board's baseline (2026-09-24)

`python3.12 history/backtest.py baseline` rebuilds the board's inputs for each past season from what was known before it: last season's stats (`00{season-1}`, from the previous season's `players.json`) and ESPN's preseason projection (`10{season}`). They go through the board's own code: `draft.parse_player`, `compute_baseline` and `value_players`. Settings are the saved Draft Room: all 9 categories rated, 95 replacement, 7-player core, 12-man roster.

**2022-23 can't be used for projection tests.** ESPN's stored 2022-23 projection is a mid-season rest-of-season projection: Markkanen at 21.5 points over 39 games, Brunson over 30 games. It leaks the answer (that season scored a suspicious 0.815), and ESPN returns only that version. It stays usable for tests that don't read ESPN's projection. Projection tests therefore run on 4 tuning seasons, and a change must win in at least 3 of them.

2020-21 was a 72-game season. The harness scales its projected games to an 82-game basis so the board sees a normal season.

| Season | Board ρ | Board r | Room ρ (price paid) | Board top-200 ρ | Board $ error | Room $ error |
|---|---|---|---|---|---|---|
| 2020-21 | 0.675 | 0.678 | 0.689 | 0.620 | $13.1 | $11.4 |
| 2021-22 | 0.643 | 0.659 | 0.666 | 0.602 | $14.6 | $13.3 |
| 2023-24 | 0.730 | 0.756 | 0.704 | 0.700 | $14.0 | $12.5 |
| 2024-25 | 0.617 | 0.667 | 0.682 | 0.660 | $14.5 | $11.4 |
| **Mean** | **0.666** | **0.690** | **0.685** | **0.645** | **$14.1** | **$12.1** |

ρ is Spearman against CWA over the 144 players the league drafted. Dollar error covers picks that cost $5+, against CWA's rank on that season's price curve.

- **On the stricter target, the board is slightly worse than the room**, both at ordering drafted players and in dollars. The earlier 0.75 vs 0.70 edge came from scoring the model against its own formula.
- **The board's top prices are too high.** Its most expensive player was $116 (Jaren Jackson Jr., 2023-24) and $129 (Wembanyama, 2024-25). Blocks inflate the rating (candidate 1), and the price formula passes that straight into dollars.

**Where the error is.** Swapping in actual values for one input at a time (drafted players, Spearman against CWA):

| Season | Board | Actual games | Actual per-game rating | Both | Per-game r (projection vs actual) | Projected games (avg) | Actual games (avg) |
|---|---|---|---|---|---|---|---|
| 2020-21 | 0.675 | 0.718 | 0.956 | 0.984 | 0.732 | 63.0 of 72 | 53.7 |
| 2021-22 | 0.643 | 0.671 | 0.934 | 0.976 | 0.734 | 72.7 | 58.8 |
| 2023-24 | 0.730 | 0.761 | 0.954 | 0.969 | 0.807 | 68.5 | 64.2 |
| 2024-25 | 0.617 | 0.657 | 0.943 | 0.972 | 0.772 | 71.0 | 60.5 |

**The ceiling.** `python3.12 history/backtest.py ceiling`: CWA per game in odd weeks against even weeks gives a full-season reliability of 0.88–0.92. Nothing can correlate with a season's per-game CWA much above r ≈ 0.94–0.96.

**What this means for step 4.**

1. **The per-game projection is almost all of the error.** Knowing each player's actual per-game rating would lift the board from 0.67 to about 0.95. Knowing his actual games would add only 0.03–0.04. Today's per-game projection reaches r = 0.73–0.81 against a ceiling near 0.95. Start with candidate 6 (how to build the per-game line: ESPN's projection, last season's per-minute rates, or a blend).
2. **Games still run 4–14 high** (candidate 4). It's worth fixing for the dollar values, but it moves the ranking less.
3. **The top-end prices need a look** (candidate 1, then the price formula), since they cost the board most of its dollar error.

### Step 4: candidate changes (2026-09-24)

`python3.12 history/experiments.py` runs the whole sequence in about 10 seconds and logs every variant to `history/experiments_log.json`. Nothing in `library/` changed: variants swap the board's inputs, or patch valuation functions only while they run.

Rules, fixed before running:
- Anything measured or fitted comes from the other seasons only.
- Fitted parameters are pulled halfway toward today's value.
- A change is accepted on ranking if it wins in at least 3 of 4 seasons, gains at least 0.02 Spearman on average, and its 95% bootstrap interval is above 0. It's accepted on dollars if ranking doesn't get worse, dollar error drops in at least 3 of 4 seasons by at least $0.50 on average, and the interval is above 0.
- Accepted changes stack, so each later candidate is tested on top of them.

| # | Change | Ranking change [95% CI], seasons won | Dollar error change, seasons won | Result |
|---|---|---|---|---|
| 6a | Use ESPN's per-game projection directly (no parameter) | +0.024 [+0.003, +0.046], 4/4 | −$0.72, 4/4 | **Accepted** |
| 6b | Blend ESPN with the board's line (weight fitted, shrunk) | −0.008 [−0.020, +0.004], 2/4 | +$0.31, 1/4 | Rejected |
| 4 | Games × measured actual/projected (0.84–0.88) | +0.001, 2/4 | ≈ $0 | Rejected |
| 4b | Games pulled toward the average (fitted, shrunk) | 0.000 | $0 | Rejected: the best setting was always "leave ESPN's games alone" |
| 5 | Replacement = measured pickup rating (92.4–93.1) | +0.001, 4/4 | ≈ $0 | Rejected |
| 1 | Category weights from the league's win curves (measured) | **+0.032 [+0.016, +0.048], 4/4** | −$0.98, 4/4 | **Accepted** |
| 2 | Linear FG%/FT% impact | +0.005 [+0.001, +0.010], 4/4 | −$0.17, 3/4 | Rejected: too small |
| 3 | Leave TO out of the rating | **−0.021** [−0.040, −0.004], 1/4 | +$0.50, 1/4 | Rejected |
| 7 | Dollars by value rank on the league's average price curve | 0 | **−$0.98 [0.25, 1.71], 4/4** | **Accepted** (dollars) |

**All accepted changes together, against the board as saved:**

| | Board as saved | With the changes | Prices paid |
|---|---|---|---|
| Ranking of drafted players (Spearman) | 0.666 | **0.722** (+0.056 [+0.028, +0.083], 4/4) | 0.685 |
| Dollar error, picks $5+ | $14.1 | **$11.4** (−$2.68 [1.48, 3.87], 4/4) | $12.1 |
| Board's own top 84 (Spearman) | 0.577 | 0.653 | |
| Most expensive player | $97–168 | $77–80 | |

Draft check: average (CWA $ − paid), 4 seasons pooled, by the model's edge (Ours − paid):

| Model's edge | Before | After |
|---|---|---|
| $10+ above paid | +4.1 (n 93) | +4.7 (n 60) |
| $3 to $10 above | +0.5 (n 68) | +2.6 (n 100) |
| Within $3 | +0.5 (n 211) | +0.2 (n 243) |
| $3 to $10 below | −1.5 (n 107) | −3.9 (n 121) |
| $10+ below paid | −10.0 (n 97) | −14.0 (n 52) |

**The win-curve weights** (weekly category wins per rating point, normalized to mean 1) are stable in every single season:

| | PTS | REB | AST | STL | BLK | 3PM | TO | FG% | FT% |
|---|---|---|---|---|---|---|---|---|---|
| Range over 5 single seasons | 1.07–1.24 | 1.01–1.18 | 0.90–1.00 | 0.77–0.85 | 0.55–0.61 | 0.67–0.75 | 0.82–0.89 | 1.36–1.54 | 1.36–1.55 |

The equal-weight rating counts a block as much as ~1.7 blocks are worth, and it undercounts shooting percentages by about 40%. That's the Wembanyama and Jaren Jackson Jr. inflation.

**What was learned:**
- **ESPN's per-game projection beats the board's own line** (last season per minute × ESPN minutes) in every season. The fitted blend peaked at w = 0.5–1.0 and was hurt by shrinking it toward the old line, so the parameter-free "use ESPN's line" is the one to keep. Caution: 6a and 6b are two versions of one idea, so its +0.024 (interval down to +0.003) is the least certain of the accepted changes.
- **Games barely affect the ranking.** With missed games filled at a 95 rating, neither the 9-game bias nor a shrink toward average moved it. ESPN's games stay as they are.
- **Keep TO rated.** Leaving it out costs 0.021. `settings.txt` leaves it out by default, while the saved Draft Room rates it.
- **The price formula overpaid stars.** Pricing by rank on the league's own price curve cut dollar error by about $1 and brought the top price from $97–168 down to about $78.

**Not yet tested:** player age and a minutes change on the ESPN line. These would need new parameters, and the list of candidates is closed until step 5 is done.

**Next, step 5:** score the final stack once on 2025-26, which hasn't been touched. If it holds (it beats the saved board in ranking and dollars), implement it in `library/valuation.py`, keeping today's defaults switchable:
- ESPN's per-game line, with the Exp MIN control rescaling it.
- Win-curve category weights.
- Price-curve dollars.

### Step 5: the held-back season, and the change (2026-09-24)

`python3.12 history/experiments.py lockbox` scored the frozen stack once on 2025-26. The weights and price curve were measured on 2020-21 to 2024-25, and ESPN's line has no parameters. The result is in `history/lockbox_result.json`.

| 2025-26 | Board as saved | With the changes | Prices paid |
|---|---|---|---|
| Ranking of drafted players (Spearman) | 0.640 | 0.654 (+0.014, 95% CI −0.030 to +0.055) | 0.622 |
| Board's top 200 | 0.695 | 0.728 | |
| Dollar error, picks $5+ | $14.27 | $12.16 | $11.50 |
| Most expensive player | $170 | $78 | |

**Passed** the rule set before running it: better than the saved board in both ranking and dollars. The ranking gain is smaller than in the tuning seasons (+0.056), and one season can't separate it from zero. The dollar gain held.

**Implemented**, with each part switchable in Settings → Rating model:

| Part | Code | Default | Old behavior |
|---|---|---|---|
| Per-game line | `DraftPlayer.line_source` | `"espn"` | `"last"` |
| Category weights | `valuation.CATEGORY_WEIGHTS`, `LeagueShape.weights`, `rate(..., weights)` | league weights | `{}` (equal) |
| Dollars | `valuation.PRICE_CURVE`, `LeagueShape.price_curve`, `Pricing.dollars` / `curve_dollars` | the price curve | `[]` (core formula) |

The Draft Room settings are `projLine` (`espn`/`last`), `catWeights` (`league`/`equal`) and `pricing` (`curve`/`formula`).

One difference from what was tested: the curve is scaled up 1.8% so that every roster spot adds up to the $2,400 budget (the league leaves about $42 unspent). The library reproduces the backtest: 0.722 ranking and $11.43 dollar error on the tuning seasons, 0.655 and $12.22 on 2025-26.

The harness pins `line_source = "last"` for its "board as saved" baseline, so the step 3 numbers still reproduce.

**Ideas for later**, each needing a new plan, since 2025-26 has now been used: player age, minutes changes on ESPN's line, and refreshing the weights and curve after each season (2025-26 can join them now).
