# Games Played Range Plan

Branch: `gui` · Data: `history/` (fetched by `history/fetch_history.py` and `history/fetch_games.py`, untracked) · Written 2026-09-26 · Results added 2026-09-27

## Status and results (2026-09-27)

Steps 1–5 and the board part of step 6 are built. The Plan tab doesn't use the ranges, and by the step 5 test it shouldn't get a risk setting.

**Data** (`history/fetch_games.py`):
- **Game logs:** ESPN's per-game logs for 2017-18 to 2025-26 list every team game, including the ones a player missed (2017-18 lists only games played). That gives each player's team games, games played and longest run of missed games.
- **Bios:** birth date, height and weight from ESPN's athlete API, for 1,526 players.
- **Standings:** NBA standings for every season.

**Sample:** 1,403 player-seasons of rotation players, over 7 held-out seasons (2018-19 to 2021-22 and 2023-24 to 2025-26). 2019-20's stored projection has games but no minutes, so there last season's minutes pick the rotation.

**Games model** (`python3.12 history/games_model.py evaluate`), each season held out in turn:

| Model | CRPS | In 80% range | In 50% range | 80% width |
|---|---|---|---|---|
| B0: ESPN + one pooled error | 9.29 | 81% | 52% | 41 games |
| B1: errors by projection group | 9.25 | 81% | 51% | 41 |
| **Two-part, major absence = 40+ games in a row** | **9.18** | **81%** | **53%** | **42** |

- The two-part model beats B1 in 6 of 7 seasons, gain +0.067 (95% CI +0.016 to +0.121).
- How long a "major absence" is was scored from 12 to 50 games in a row. CRPS improved up to about 40 and barely after. That's one tuned setting.
- The predicted chance of fewer than 41 games is calibrated (for example 24% predicted, 21% observed).

**Inputs added one at a time on top of ESPN's projection:**

| Input | Gain | Seasons won | Kept |
|---|---|---|---|
| Past availability (weighted last 3 seasons) | +0.018 (CI −0.024 to +0.063) | 5/7 | No: CI includes 0. Revisit after the 2026-27 lockbox |
| Team record the season before | +0.004 | 4/7 | No |
| Weight | +0.001 | 4/7 | No |
| Height | −0.001 | 3/7 | No |
| BMI | −0.000 | 3/7 | No |
| Age | −0.014 | 1/7 | No |
| Major absences in the last 4 seasons, experience, new team, position, minutes | ≤ 0 | ≤ 3/7 | No |

- **Height, weight and BMI aren't predictive.** Neither is age once ESPN's projection is known: ESPN already builds in what they'd add.
- **Team context matters for timing, not totals.** Players on teams that finished below .350 missed 50% of their team's last 15 games, against 36% over the season. But the team's record the season before (the only team-strength number known before the draft) raises late-season misses by just 5–9 points for every team. That isn't enough to split teams apart. A preseason win projection (for example, betting win totals) would be needed to test it properly.

**Per-game rating** (`python3.12 history/games_model.py value`):
- The rating error (actual − projected, on the board's weighted rating) is −1.4 + 0.18 × (games − projected games), with noise variance 57 + 1,532 ÷ games. That's a spread of about 9 points at 70 games and 12 at 20 games.
- Seasons with a major absence averaged 9 points worse per game.
- Held out by season, **82% of actual season values fell inside the 80% value range, and 53% inside the 50% range.** A games-only range would have covered 29%, which is why per-game uncertainty is included.

**On the board:**
- **Table:** "GP 80%" (10th–90th percentile of games) and "Risk" (chance of fewer than 41 games), both sortable.
- **Detail panel:** a Range table with games, value and worth (low / median / high) and the under-41-games chance.
- **GP Δ** shifts the whole range. It isn't treated as a projection, because a low ESPN projection means a known long injury and your −10 doesn't.
- **Worth** prices each value on the league's curve against every player's mean outcome.
- **Value and Ours:** unchanged by the ranges, but see the fill rate below (2026-09-27).
- Code: `library/availability.py` (fitted constants from `python3.12 history/games_model.py fit`), `tests/availability_test.py`.

**Team level** (`library/availability.team_range`, `python3.12 history/games_model.py team`):

How it works:
- Every player's games and per-game rating are drawn together, independently between players, 300 times.
- Each draw goes through the board's daily lineup and is scored as expected category wins a week against the average team.
- The average team is built with every player at the model's mean outcome (`mean_row`), so the model's lower games and ratings apply to every team, not just mine.
- It takes about 0.1 s and is recomputed only when the draft state changes.

On the board:
- The team header shows the 80% range next to the expected record.
- The My Team tab has a Season range card: the range, its median, and how many of my players are expected to miss half the season.

**Does fragility predict results?** 60 drafted rosters from the league's history (2020-21, 2021-22 and 2023-24 to 2025-26). The model was fitted without the tested season each time, and all-play category wins are compared within each season:

| Draft-day measure | r with all-play category wins |
|---|---|
| Board value (ESPN games) | +0.30 |
| Model mean value | +0.29 |
| Downside (mean − p10 of summed value) | −0.01 |
| Expected half-season losses | +0.36 |
| Downside, once board value is known | −0.18 (95% CI −0.41 to +0.06) |
| Expected half-season losses, once board value is known | +0.27 (95% CI −0.04 to +0.53) |

- Neither fragility measure predicts worse results once value is known.
- If anything, rosters with more expected half-season losses did better. Plausibly that's because injured players come at a discount, but it isn't significant.
- By the plan's rule, **the planner gets no risk setting**, and Value/Ours stay on ESPN's games. The range is shown for information.
- Caveat: rosters change a lot after the draft (pickups are about 25% of production), so draft-day fragility is a weak lever on results.

**± from games played alone** (`availability.games_sd`, `plus_minus`, `team_spread`):
- Every ± is one standard deviation of games (ESPN's projection moved by GP Δ), carried through to the board's own estimates.
- **Value and Fit** are straight lines in games. His games count at his line and the rest are filled at replacement. So ± = |number − its value at 0 games| × SD of games ÷ Exp GP. Value is replacement (95) at 0 games. Fit at 0 games comes from one extra team-fit run on a player with no games.
- **Team categories:** each of my players' games moves up one SD, through the daily lineup. The rating changes add in quadrature across players, since players' games are independent.
- **Expected record:** the same per-player changes are turned into win-chance changes, summed across categories for each player, then added in quadrature. The header shows the record ± as a range of wins.
- These cover games only. The My Team "Season range" card also counts per-game misses, so it's wider.

**Changes made at the user's request (2026-09-27)**, after they pointed out that a Wembanyama/Davis/Embiid roster can't have a safe floor, and neither can LaMelo:

*1. Missed games are only partly filled* (`python3.12 history/games_model.py fill`, `fillcheck`):
- **How it's measured:** for each regular on a roster in 2024-25 and 2025-26, his team's counted games in weeks he missed games are compared with weeks he played them all, against the league average each week. The box scores only list players who counted, so a week fully out shows up as a gap between his first and last weeks on the team, with no games in his log.

| Absence | Lost games the team covered | 95% CI | Share of missed games |
|---|---|---|---|
| Short (part of a week) | 53% | 32–71% | 57% |
| Whole week out | 69% | 53–87% | 43% |

- **The board's default is now 60%** (`LeagueShape.fill_rate`, Settings → Replacement player → Missed games filled). Before, every missed game was filled at 95.
- **What it changes:** in `season_value`, only 60% of missed games count at the replacement rating. The league simulation's fill for missed games is scaled the same way. Streaming spots stay at the full replacement line, because those are real pickups.
- **Backtest:** the target is CWA minus what each unfilled missed game would have added at replacement level (`League.volume_cwa`). Against it, a 60% board ranks drafted players better than a 100% board in all 5 seasons: +0.038, +0.025, +0.010, +0.010, and +0.033 on the opened lockbox. Dollar error is mixed: better in 3 seasons, worse in 2.
- **Effect:** Anthony Davis (with the user's −15 games) goes from $43 to $14, Embiid from $31 to $15, Kawhi from $30 to $22. Derrick White goes from $33 to $45 and Mikal Bridges from $11 to $21.

*2. Past availability is in the games model.*
- **The test:** it didn't pass the significance rule (+0.018 CRPS, 5 of 7 seasons, CI includes 0). The user chose to keep it. It matters most for players ESPN projects above their record.
- **Fitted coefficients:** P(major absence) −0.16 per SD of history, normal-season mean +0.08.
- **Runtime:** each pool player's last three seasons (games, minutes, ESPN's preseason minutes) come from ESPN's league-independent pool (`draft.fetch_past`). They're cached in `draftPoolHistory.json` next to the pool. 326 of 440 players have history; the rest get the average, which is the ESPN-only answer.
- **Chance of losing half the season, before → after:** Embiid 41% → 54%, Davis 26% → 33%, LaMelo 15% → 18%, Markkanen 14% → 18%, Derrick White 7% → 6%.

*3. Floors come from simulated seasons.*
- The Plan tab has **Most wins**, **Floor · 1 in 10** and **Floor · 1 in 20**.
- The search uses the quick games-only stand-in: score − z·SD, with z = 1.28 or 1.64. In floor modes it starts from twice as many rosters.
- The distinct end points are then drawn 600 times each with `team_range` (games and per-game rating, same seed for every roster). The best 10th or 5th percentile of weekly category wins decides.
- Every build shows its simulated floors.
- With the user's 3 players, $107 left and nobody left out, the three modes chose:

| Mode | Buys | Expected | 1 in 10 | 1 in 20 |
|---|---|---|---|---|
| Most wins | Towns, Curry, White, Murphy, Clingan, Miller | 5.34 | 4.62 | 4.39 |
| Floor · 1 in 10 | Towns, Curry, White, Markkanen, Clingan, Buzelis | 5.30 | 4.63 | 4.38 |
| Floor · 1 in 20 | Towns, White, Knueppel, Porter Jr., Holmgren, Clingan | 5.27 | 4.65 | 4.43 |

- None of them buys Wembanyama, Davis, Embiid or LaMelo any more. The biggest change came from the fill rate, not the floor objective.

**Not built yet:** the "out until" control in the UI (`games_range(out=...)` supports it), a settings switch, and the frozen 2026-27 forecast (step 7, to do right before the draft).

## Goal

Give every player a **range** for games played, not just ESPN's single number, and carry it through to a range for **season value** (rating × games, missed games filled at replacement). Some players' outcomes are tight (Jokic: 63–79 games in each of the last seven seasons, two of them shortened). Others swing between a full season and almost nothing (Zion: 19, 61, 0, 29, 70, 30, 62). The board should show that, and the Plan tab should be able to see when a roster is stacked with fragile players (a league team's four losing seasons came down to exactly that).

## What the data shows

Diagnostic on rotation players (ESPN projected 26+ minutes), 2023-24 to 2025-26, 537 player-seasons:

| | |
|---|---|
| ESPN projected games (avg) | 70.1 |
| Actual games (avg) | 61.8 |
| Error: bias / SD / mean absolute | −8.3 / 16.2 / 12.7 games |
| r, ESPN projected vs actual games | 0.32 |
| r, last season's availability vs actual games | 0.08 |
| r, last 3 seasons' availability vs actual games | 0.05 |
| r, last 3 seasons' availability vs **ESPN's error** | −0.02 |
| Year-to-year availability, players at 25+ min both years | 0.15 |

**The outcome is skewed with a long left tail.** Share of the season missed:

| Missed | 0–5% | 5–15% | 15–30% | 30–50% | 50%+ |
|---|---|---|---|---|---|
| Player-seasons | 14% | 28% | 25% | 20% | 13% |

**History moves the tail more than the middle.** Veterans grouped by availability over the last 3 seasons:

| 3-season availability | n | ESPN proj | Actual avg | p10 | p25 | p50 | p90 | Under 40 games |
|---|---|---|---|---|---|---|---|---|
| Under 60% | 22 | 65 | 58 | 24 | 47 | 62 | 77 | 18% |
| 60–80% | 147 | 67 | 58 | 34 | 50 | 62 | 77 | 15% |
| 80–90% | 139 | 70 | 63 | 41 | 55 | 69 | 79 | 9% |
| 90%+ | 111 | 75 | 66 | 46 | 56 | 70 | 82 | 7% |

**The bias changes by season.** ESPN overshot by 12 games in 2020-21, 15 in 2021-22 (COVID absences), 4 in 2023-24, 12 in 2024-25 and 12 in 2025-26. Part of each season's error hits every team at once.

What this means for the design:

1. **Games are mostly noise.** No input predicts them well. A range is the honest output, and it will be wide for everyone (the 80% range is about 35 games even for durable players).
2. **Differences between players are real but modest.** They show mostly in the chance of a big absence (7% vs 18% under 40 games), less in the median. ESPN's projection already captures some of it, because it projects fewer games for players with a history of missing time.
3. **A player's own history is thin.** Three or four seasons with r = 0.15 from year to year means his history has to be pulled strongly toward his group. It can't be used raw.
4. **The prediction should be centered below ESPN.** The backtest (candidates 4 and 4b) left ESPN's games alone because correcting them didn't change the **ranking**. A range is a different use: an 80% range centered 8 games too high would be miscalibrated.

## Model

### Target

Availability = games played ÷ the team's games that season, scaled to 82. That handles 2019-20 (63–75 games by team) and 2020-21 (72).

A **rotation filter** separates injury from role. Only seasons where the player averaged 20+ minutes count as history. Games lost to losing a role (DNP-coach's decision, being traded into a smaller role) are a different risk, and ESPN's minutes projection covers them.

### Structure: two parts

A season is either **normal** (rest days and short injuries) or includes a **major absence** (one injury or shutdown costing 25%+ of the season):

```
games = 82 × availability
availability ~ (1 − p_major) × Normal-season  +  p_major × Major-absence
```

- **Normal season:** a Beta distribution for availability. Its mean comes from the player's inputs, and its spread is shared by everyone.
- **Major absence:** a single Beta distribution fitted to all seasons where a player missed 25%+ of the season. How long a big injury lasts is largely random, so every player shares it.
- **p_major:** logistic regression on a few inputs.

Why two parts: the data's long left tail and the "tight vs wide" players the user describes are both mainly a difference in **p_major**. A single bell curve would miss the tail or make everyone wide.

### Inputs (at most 4, matching the backtest rules)

| Input | Available historically | Notes |
|---|---|---|
| ESPN projected games | 2020-21, 2021-22, 2023-24 to 2026-27 | Already reflects known injuries. 2022-23 is a mid-season projection and can't be used (see BACKTEST_PLAN) |
| Availability over the last 3 seasons, weighted toward recent seasons and shrunk toward the pool | All seasons (2019-20 onward) | Empirical Bayes: the fewer counted seasons, the closer to the pool average |
| Major absences in the last 4 seasons | All seasons | Direct evidence for p_major |
| Age | Needs a fetch | ESPN's athlete API (`site.api.espn.com/.../athletes/{id}`) has date of birth. Add only if it earns its place in testing |

**Not in the model, but a manual override on the board:** preseason injury status (for example, OUT for the start of the season). ESPN's history only stores it as of the fetch date, so it can't be tested. The board already has GP Δ. Add an **"out until"** option that removes games from the top of the range without changing its shape.

**Rookies and players with no counted seasons:** use p_major and the normal-season mean from the pool, centered by ESPN's projection.

### Outputs per player

- Games: p10, p25, p50, p75, p90 and the mean. Because of the tail, the mean is below the median.
- P(under 41 games), the "loses half the season" risk, as a single number to sort by.
- The same numbers for season value (below).

## From games to season value

`season_value(rating, games, R) = R + (rating − R) × games / 82`, with R = 95 (replacement). For a known per-game rating, value is linear in games, so games quantiles map directly to value quantiles. A player rated below R gains value from missing games, and the formula already handles that.

**The per-game rating is uncertain too, and the backtest found it is the bigger source of error** (projected vs actual per-game rating r = 0.73–0.81, compared with only 0.03–0.04 added by knowing games exactly). A value range that only varies games would look much tighter than it really is. So the value range should include both:

1. Measure the per-game rating error (actual − projected) on the same seasons, with its spread by group. Likely groups: rookies and second-year players, players changing teams or roles, and everyone else.
2. Measure the correlation between the games error and the rating error. Players coming back from injury often play worse, and if so the two should move together.
3. Monte Carlo: draw games and per-game rating together (about 2,000 draws per player), compute season value for each draw, and report p10/p50/p90.
4. Dollars: price each value quantile on `PRICE_CURVE` against the pool's median values. For example: "$31 expected, $12–$44 (80%)".

**Build games first.** Per-game uncertainty is phase 2, but the value range shouldn't appear on the board until phase 2 is done, or it will understate the risk.

## Team level

- Plan tab: simulate a roster's season by drawing every player together. That gives a range for team production and for expected category wins, using the existing `Lineup` daily-schedule logic on each draw.
- The season-wide shock (4–15 games, see above) affects every team at once. Draw it for absolute totals, but it barely changes standings between teams.
- Fragility metric: expected production lost to major absences, and the team's p10.
- A risk setting for the planner (maximize expected value vs protect the downside) is **optional**. It's the user's choice, like punting, and never automatic.

**Test it:** does a roster's simulated p10, or its expected loss to major absences, predict all-play category wins beyond expected production? Use the 48 team-seasons in `history/`. If it doesn't, show the range but keep the planner on expected value.

## Evaluation

Same rules as `BACKTEST_PLAN.md`: few parameters, leave one season out, and a change must win in most seasons.

**Seasons:**
- Tuning: 2020-21, 2021-22, 2023-24 and 2024-25.
- 2022-23 is used only for history inputs and for fitting the major-absence length, never with its leaked projection.
- 2025-26 was the backtest's lockbox and has already been opened. Use it as a fifth fold, and don't call it held out.
- **The real lockbox is 2026-27:** freeze and save every player's predicted quantiles before the draft (`history/games_forecast_2027.json`) and score them after the season.

**Metrics** (for a range, "r against actual" is the wrong test):

| Metric | Checks |
|---|---|
| Coverage: share of actuals inside the 50% and 80% ranges | Calibration: they should land near 50% and 80% |
| Predicted vs observed rate of under 41 games, by risk group | Is the tail calibrated? |
| CRPS (continuous ranked probability score) | One overall score for accuracy plus sharpness. Lower is better |
| Average width of the 80% range | Sharpness at equal calibration |

**Baselines to beat:**

1. **B0:** ESPN's projection minus the pooled bias, plus one pooled error distribution. The same width for everyone.
2. **B1:** B0 with width by ESPN projected games group.
3. **Model:** the two-part model.

Player-specific ranges are kept only if the model beats B1 on CRPS in at least 3 of 4 tuning folds, with a bootstrap confidence interval excluding zero, and stays calibrated. **Expect a modest result:** the diagnostic suggests the gain is mostly in the tail (who is likely to miss half the season), not in a sharper middle. If the model doesn't beat B1, ship B1. It still gives honest ranges.

## Board and planner

- **Pool table:** a "GP" column showing the p10–p90 range as a small bar with a p50 tick. A "Risk" column: P(under 41 games), sortable. A tooltip with the counted seasons' games.
- **Value/Ours unchanged at first.** They keep using ESPN's games (the backtest's accepted default). Show the value range next to them. Switching Value to the distribution's mean is a separate backtest candidate, judged on ranking and dollar error like the others.
- **GP Δ** shifts the whole distribution. **"Out until"** removes games from the top.
- **Plan tab:** team production and category-win ranges, and the fragility metric.
- **Settings → Rating model:** a switch for the games model (B1 / two-part), like `projLine`, `catWeights` and `pricing`.

## Code layout

- `library/availability.py`: pure functions. Build inputs from `DraftPlayer` history, compute quantiles, `sample(n)`, and the value range. Fitted parameters live as constants, like `valuation.CATEGORY_WEIGHTS`.
- `history/games_model.py`: builds the player-season table from `history/<season>/players.json`, fits with leave-one-season-out, scores the baselines and the model, and logs to `history/experiments_log.json`.
- `library/draft.py`: `DraftPlayer` needs past seasons' games and minutes. Today it keeps only last season (`last_gp`). Pull 3–4 seasons into `draftPool.json` on fetch.
- Tests: `tests/availability_test.py` covers quantile order, 82-game scaling, the value mapping for players rated below replacement, and that the override removes games from the top only.

## Steps

1. **Player-season table:** games, team games, minutes, ESPN projection, age (if fetched), for 2019-20 to 2025-26. Check rotation-filter counts and the per-season team-games scaling.
2. **Baselines B0 and B1**, scored with coverage, tail rate, CRPS and width. This sets the bar.
3. **Two-part model**, adding inputs one at a time. Each must improve CRPS in 3 of 4 folds.
4. **Per-game rating error and its correlation with games error**, then value quantiles by Monte Carlo.
5. **Team-level test** on the 48 team-seasons. Decide whether the planner gets a risk setting.
6. **Board UI and Plan tab**, behind the settings switch.
7. **Freeze 2026-27 predictions** before the draft.

## Decisions for the user

1. **Age:** fetch date of birth from ESPN's athlete API (one extra call per player, cached)? It's the most likely useful input not already in the data.
2. **Value range with both sources of uncertainty (recommended), or games only?** Games only is quicker but understates the risk.
3. **Planner risk setting:** only if step 5 shows fragility predicts results, or regardless as a user choice?
4. **Draft timing:** steps 1–3 plus a GP-range column is the smallest useful piece if the draft is soon. Value ranges and team simulation can follow.
