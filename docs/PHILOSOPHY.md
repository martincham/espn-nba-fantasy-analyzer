# Draft Room philosophy

The ideas behind how Draft Room values players, and the draft strategy it's built to support. For how the math is implemented, see [`GUI_PLAN.md`](GUI_PLAN.md). For how to run the app, see [`gui/README.md`](../gui/README.md).

## The league

- **Draft:** a 12-team auction, $200 per team.
- **Roster:** 12 players. Seven start each night (PG, C, F, F, SG/SF, SG/SF, UT) and five sit on the bench.
- **Scoring:** head-to-head **each category**, 9 categories (PTS, REB, AST, STL, BLK, 3PM, FG%, FT%, TO). Every category is its own win or loss each week, and your record is the sum: an 8–1 week counts 8 wins, a 5–4 week counts 5. Lineups are set daily.
- **Transactions:** 3 adds per week.
- **IR:** 2 slots. An injured player on IR doesn't use a roster spot.

Every choice below comes from these rules.

## 1. Rate players the way the league scores them

A player's rating is how much they add to each category, compared with the average draftable player.

- **100 is the average player** in the pool: the top 144 players (12 teams × 12 roster spots).
- **Counting stats** (PTS, REB, …) compare the player's output with the pool average. Twice the average scores 200.
- **Percentages** are weighted by attempts. A 60% shooter on 15 shots moves a team's FG% far more than one on 4 shots.
- **Categories can be left out** of the rating. TO is left out by default, since it's usually punted. The Settings tab controls this.

One number per player is a simplification: it adds all categories together, so a shot-blocker and a point guard can have the same rating. That's fine for pricing players against the market. For your own team, the **Fit** column corrects it (section 6).

## 2. Separate what changes a player

A player's outlook changes for three different reasons. Each has its own control, and each defaults to ESPN's projection.

| Reason | Control | Default |
|---|---|---|
| **Role:** more or fewer minutes | Exp MIN | ESPN's projected minutes |
| **Skill:** better or worse per minute | Δ, in rating points | 0 |
| **Health:** more or fewer games | GP Δ, in games | 0, so ESPN's projected games |

Keeping them separate prevents double counting. If you expect a young player to jump from 20 to 28 minutes, change Exp MIN. His production scales with the minutes automatically, so don't also add a big Δ for the same jump. Use Δ only when you think he'll get better per minute.

## 3. Value is quality × availability, with missed games filled

A player's value is his per-game rating across a full 82-game season. **He plays his expected games at his own rating, and a replacement free agent plays the games he misses:**

`Value = (per-game rating × Exp GP + replacement rating × (82 − Exp GP)) ÷ 82`

**Why missed games aren't lost.** When a player is hurt, he goes on IR (2 slots) or sits, and you pick up a free agent to play in his place.

- **The average free agent rates about 86.** With this tool you can usually find one rated 90 to 100, so the replacement rating defaults to **95**.
- **So a missed game only costs the gap between the player and that pickup.**
- **This assumption carries a lot of weight.** It holds only if you actually make the pickups, and make good ones.

Examples at a replacement rating of 95:

| Player | Value |
|---|---|
| 140-rated star, 50 games | 122: each missed game costs about 0.55 |
| 140-rated star, all 82 games | 140 |
| 100-rated player, 82 games | 100 |
| 95-rated player, any number of games | 95: no better than a free agent |

**Health still matters, but less than a simple rating × games.** At a replacement rating of 0, the formula becomes plain rating × games ÷ 82, and the 50-game star drops to 85. The replacement rating is on the Settings tab. Health is set per player with GP Δ.

## 4. Dollars go to the core

A player's value in dollars (**Ours**) comes from how far he is above the best player you can get for $1.

- Every roster spot costs at least $1.
- The rest of the league's money ($2,400 − $144) is split among each team's **core players**: 7 per team by default, so the top 84.
- Each of them gets a share in proportion to how far his value is above the 84th player's.
- Everyone else is a $1 player: the streamers and holds.

Why 7? See [the strategy section](#7-roster-strategy-a-core-seven-and-a-rotating-five). The number is on the Settings tab.

## 5. The market is information, not truth

**Avg paid** is what players cost in real ESPN auction drafts, scaled to fit this league's budget. **Edge = Ours − Avg paid**.

- A positive Edge means the room tends to pay less than the player is worth to us: a target.
- A negative Edge means the room pays more. Stars lean this way: the 12 most expensive players average about −$4.
- The scale is on the Settings tab. Auto makes ESPN's top-144 prices add up to $2,400.

## 6. Win categories, not points

In head-to-head you don't win on total rating. You win **categories**: each week, whoever has more in a category takes it, and in this league each category counts in the standings. The goal is the most category wins per week, not just taking the matchup. So a point of rating isn't worth the same everywhere.

- **Taking a category from 80 to 100 turns losses into toss-ups.** A weak category is where extra strength wins the most.
- **Taking a category from 130 to 150 wins nothing.** You were already winning it every week, so the extra is wasted.

A player's rating adds up all his categories, so it can't see this. A player who's great in blocks is worth a lot to a team that needs blocks and very little to a team that already has them.

### How often a category wins

The league's own 2025-26 results say how often a team category rating wins its category in a given week. They cover 22 weeks and 12 teams, about 2,300 category results.

| Team rating in a category | Wins that category |
|---|---|
| 80 | about 21% of weeks |
| 90 | 34% |
| 100 | 50% |
| 110 | 66% |
| 120 | 79% |
| 130 | 88% |

**The curve is a smooth fit to the data, not the raw counts,** so one season doesn't overfit. It's a normal curve: chance = Φ((rating − 100) ÷ spread), with a spread of about 25 rating points.

**Categories differ in how reliable an edge is.** The spread is how much a category swings from week to week:

| Category | Spread | Character |
|---|---|---|
| PTS, FG%, FT% | 20 | Steady: a small edge wins most weeks |
| REB | 21 | |
| AST | 24.5 | |
| 3PM | 26 | |
| TO | 27.5 | |
| BLK | 28 | Swingy: one big game flips the week |
| STL | 29 | |

These are last season's fitted spreads pulled halfway toward the overall 25, again so one season doesn't overfit.

**What this means:**
- A rating point is worth more in steady categories than in swingy ones.
- The player rating counts every category the same, so it overrates swingy ones. That's part of why an extreme shot-blocker rates so high.

**In the app:**
- **Team row:** each category shows your win chance. The first box shows your expected weekly record, the sum of the nine win chances, e.g. 5.8–3.2.
- **All of these are against the average team.** Real draft-day projections are less certain than last season's final numbers, so true win rates sit a bit closer to 50%.

### Fit: value to the team you have

The **Fit** column rates each player by how much he'd help *your current team*. It's on the same scale as Value.

- **Your team:** your players, plus average players in the open slots. Early in the draft your team sits near 100 everywhere, and Fit is close to Value.
- **Win chances (the default):** a player's Fit is how much he raises your weekly win chances across the categories, compared with an average player in his place.
  - Strength fades on its own as a category nears a sure win.
  - It fades faster in steady categories (PTS, FG%, FT%) than in swingy ones (BLK, STL).
  - Fit is converted back to rating points, so it stays on the Value scale.
- **Simple fade (the alternative on the Settings tab):**
  - Each of your team's category ratings counts in full up to **110**.
  - Above that, each point counts less, falling in a straight line to nothing at **140**.
- **It works in both directions.** After drafting Wembanyama, Kessler and Sarr, your blocks are well past enough:
  - More big men like Mobley or Holmgren drop to about 99 Fit, no better than an average player.
  - Guards who fill your weak categories rise above their Value.
- **Weak categories are never faded down on their own.** Only strength is faded.
  - Below 100, a category keeps the value per point it has at 100.
  - The raw win-chance curve would flatten for very weak categories, which amounts to punting them automatically. Punting is your choice.

**Ours and Edge don't change with your team.** They price players against the market, and the room doesn't care what you've drafted. Fit is for choosing between players during the draft. **Fit $** converts Fit to dollars at the league's rate: roughly what that player is worth *to you*. **Fit edge = Fit $ − Avg paid**, the bargain for your team, where Edge is the bargain for anyone. Fit edge usually runs below Edge, because fading only ever takes value away.

### Punting is always your choice

**Punting** means giving up a category on purpose: you expect to lose it most weeks, and you spend nothing on it. In an each-category league a punt has a clear price: you give up that category's weekly win chance (about 0.4–0.5 wins a week for a middling category), every week. It's worth it only if the money and roster spots add more than that across the other eight.

Checked against your roster in September 2026, a hard punt of TO and FG% didn't pay:
- **Hard punt:** tanking them to 82 and 88 made the other seven stronger, but the record fell to about 5.6 wins a week.
- **Soft punt:** letting them sit near 97–99 while strengthening the rest reached about 5.8.

- **Draft Room never punts for you.** A category you're losing is a category to fix, until you decide otherwise.
- **To punt a category,** tick **Punt** on it in the team row under the scoreline. Fit then ignores it completely. It still shows in your team ratings, dimmed.
- **Common punts:**
  - **FT%**, with a team of big men, who help REB, BLK and FG% but shoot free throws poorly.
  - **TO**, with high-usage stars, who turn the ball over because they have it so much.

## 7. Roster strategy: a core seven and a rotating five

**The plan:**
- Spend almost all of the $200 on a core of about 7 players.
- The other 5 roster spots are $1 players that get dropped and added all season, based on health, schedule and hot streaks.

**Is it sound?** Mostly yes. The core idea is right, but one step in the reasoning is off and a few details matter.

### What holds up

- **The bottom of the pool is flat.** In the current data (September 2026, default settings):

  | Value rank | Value |
  |---|---|
  | #1 | 177 |
  | #12 | 129 |
  | #84 (the last core player in a 12-team league) | 104 |
  | #144 (the last rostered player) | 93 |
  | #180 (a typical free agent) | 89 |

  The gap between the #144 player and a free agent is about 4 points. The gap between a star and the #84 player is 25 to 70 points. Money spent on the bench buys almost nothing that the waiver wire doesn't give you for free.

- **The market already agrees.** About 97% of Avg paid goes to the top 84 players.
- **There's enough roster churn.** 3 adds a week over about 20 weeks is around 60 moves, which is enough to keep turning over the bench.

### The flaw: "only 7 play a night" doesn't mean only 7 matter

- Seven lineup spots over seven nights is **49 player-games a week**.
- An NBA player plays about 3.5 games a week, so **your core seven fill only about 25 of those 49**.
- The bench fills most of the other 24. **The bottom five produce roughly 40% of your counting stats.**

This doesn't break the plan, because those stats come from *games*, not from *which* player. A $1 streamer with four games that week gives you more than a $6 bench player with two. But it changes how to treat the bench:

- The bench is a **games engine**, not dead weight.
  - Pick streamers for their schedule: four-game weeks, and nights when your core is idle.
  - Pick them for the categories you're chasing that week.
- Don't judge a team's strength by its top 7 alone. Its weekly totals include the streamers.

### Details that matter

- **3 adds a week covers 3 spots, not 5.** The other two bench spots are closer to holds.
  - Use them for an injured player worth stashing, a young player who could break out, or a steady player who plays every night.
  - So the roster is really **7 core + 2 holds + 3 streamers**.
- **Concentration risk.** With about $28 per core player, one injury costs a seventh of your spend. That's the price of this strategy. Two things soften it:
  - Streamers fill a hurt star's games, so you lose the gap between him and a streamer, not his whole line.
  - Durable players are worth a little more in the core.
- **Stars are expensive.** When all 144 players share the money, the room looks like it overpays stars by about $33 each. In a core-seven world most of that premium is rational (see below), but stars are still where overpaying happens. Check Edge before chasing one.

### What it means for the model

Two changes bring the model in line with this strategy. Both are built, with a Settings control for each.

1. **Core players (default 7).**
   - *Before:* the model priced all 144 rostered players above the #144 player. That put about $390 of value on players #85 to #144, who the room buys for $68 in total.
   - *Now:* only the top 84 share the money, above the #84 player, and the rest are $1.
   - *Result:* Ours now lines up with the market. With all 144 priced and no replacement fill, the 12 most expensive players averaged an Edge of −$33. Now they average about −$4, and players #13 to #84 about $0.
2. **Replacement player (default 95).**
   - A missed game costs only the gap between the player and the free agent who fills it (section 3).
   - Kristaps Porzingis, for example: 117 per game over an expected 59 games. As plain rating × games he'd be worth 84; now he's worth 111.

**Watch the top of the board.** Pricing only the core stretches the gap between stars and everyone else. Our model's biggest outlier is Victor Wembanyama:
- He rates about 180 per game, largely because his blocks rate almost 6 times the average (578).
- The rating adds categories together, so one extreme category can carry a player.
- He comes out at about $155, which is more than anyone would pay in a $200 budget.
- Treat extreme values as "top target" rather than a literal price. For your own team, Fit handles this: once your blocks are past enough, his extra blocks stop counting (section 6).

## 8. On draft day, only who's gone matters

Other teams' picks are marked **Taken** with one click and no price. Draft Room doesn't track inflation or what the room has spent. Only two things matter:

- who's still available
- your own budget: Budget left and max bid assume $1 for each open roster spot, so the core-seven plan fits.

## 9. Defaults from ESPN, judgment from you

ESPN's projections are the starting point for minutes, games and prices. Your edits are the reason to use this tool: expected minutes, Δ, GP Δ and notes are saved per player and shown highlighted. **Use ESPN's** undoes them in one click.

## 10. Other ways to win

The draft sets your team up. Most weeks are won by how you manage it.

1. **Play more games than your opponent.**
   - Counting stats come from games. Fill every lineup spot every night.
   - Use the bench spots for players whose NBA teams play four games that week, or play on nights your core is idle.
2. **Play the week's matchup, not the season.**
   - By midweek most categories are settled either way. Spend your adds on the two or three you can still swing, using the same idea as Fit for that one week.
3. **Protect a percentage lead late in the week.**
   - FG% and FT% are averages over attempts, so one bad shooting night from a high-volume player can flip a narrow lead.
   - On the last days of a week you're narrowly ahead, bench poor shooters and start low-volume players.
4. **Build around categories that go together.**
   - Big men bring REB, BLK and FG% together. Guards bring AST, 3PM, STL and FT% together.
   - A team that reliably wins one bundle, plus one or two more categories, starts every week well above .500.
   - Draft Room shows the bundles as they form in the team row.
5. **Draft for the fantasy playoffs.**
   - The regular season only gets you in; the playoff weeks decide the season.
   - An injured star who'll be back by then is worth an IR slot and a lower price.
   - Near the playoffs, favor players whose NBA teams play the most games in those weeks and aren't likely to rest their starters.
6. **Use the auction.**
   - Early on, nominate players you *don't* want but others overpay for (a negative Edge), to drain their budgets.
   - Save your targets for when budgets are thin.
   - Know your top price for each target before the draft: Ours, or Fit $ once your team takes shape.
7. **Move first on role changes.**
   - When an NBA starter is hurt, his backup's minutes jump.
   - Picking that player up in the first day is how you find the 95-rated free agents this model assumes.
   - The spreadsheet's 7-, 15- and 30-day ratings show who's rising.
8. **Trade from surplus.**
   - A category past "enough" is strength you can't use.
   - Trade it for help where you're weak: Fit works for trades just as it does in the draft.
