"""Recommend a team: the roster that wins the most categories per week at expected prices.

Pure, like valuation.py. Given valued players, what each one should cost,
the players already mine and those already taken, it finds the players to
buy that maximise my team's weekly category win chances against the average
simulated team, within the budget I have left.

- Only the best `counted` players count; the rest of the roster are
  streaming spots, so the plan buys up to `counted` players and keeps $1 for
  each remaining spot.
- The score is the Fit objective (valuation.win_utility summed over the
  categories I haven't punted), so the plan never gives up a category on its
  own. The expected record shown is plain win chances over every category.
- The simulated league is built once per plan. Each candidate roster only
  needs its own daily-lineup totals, which keeps a search to seconds.
- Search: a knapsack start (most value above replacement for the money), plus
  seeded random starts, each improved by the best single swap until none
  helps. Distinct end points are the alternative builds.
- Objectives "floor" and "floor20" (your choice, never the default)
  maximise a bad season instead: the 1-in-10 or 1-in-20 season.
  - The search uses a quick stand-in: the score minus z standard deviations
    from games played. Each player's effect on the category ratings for one
    SD of games is worked out once against the average team, scaled by the
    share of his games that start, and added in quadrature.
  - The distinct end points are then scored on the real thing:
    library/availability.team_range draws the roster's seasons (games and
    per-game rating), and the best simulated bad season wins.
  - Every build reports its simulated floors either way.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, replace
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from library import availability, valuation as v

OBJECTIVES = ("wins", "floor", "floor20")  # most expected wins (default), the best 1-in-10 or 1-in-20 bad season
FLOOR_Q = {"floor": 0.10, "floor20": 0.05}  # the bad season each floor objective maximises
FLOOR_Z = {"floor": 1.2816, "floor20": 1.6449}  # the search's stand-in: standard deviations below the mean
FLOOR_DRAWS = 600  # simulated seasons per finalist (same seed for every roster, so they compare fairly)


@dataclass
class Build:
    ids: List[int]  # players to buy (not the ones already mine)
    cost: int  # what they should cost together
    utility: float  # the search's score: summed win utility over unpunted categories
    wins: float  # expected category wins per week vs the average team, every category
    ratings: Dict[str, float]  # team category ratings, 100 = the average team
    chances: Dict[str, float]  # weekly win chance per category
    wins_sd: float = 0.0  # ± of wins from the players' games played (1 SD)
    floor10: Optional[float] = None  # simulated weekly category wins in a 1-in-10 bad season (games and per-game)
    floor20: Optional[float] = None  # ... and a 1-in-20 one

    def floor(self, objective: str = "floor") -> Optional[float]:
        return self.floor20 if objective == "floor20" else self.floor10


@dataclass
class Swap:
    out_id: int
    in_id: int
    cost_change: int
    wins_change: float


@dataclass
class Plan:
    best: Build
    builds: List[Build]  # other good rosters, each at least `distinct` players different
    swaps: Dict[int, List[Swap]]  # per player to buy: the best alternatives for his spot
    mine: List[int]
    budget_left: int
    streamers: int  # open spots left for $1 streaming players
    searched: int  # starting points
    evaluated: int  # rosters scored
    objective: str = "wins"


class _Env:
    """The simulated league, fixed for one plan, and a fast scorer for my roster."""

    def __init__(self, rows: Sequence[v.Valued], shape: v.LeagueShape, schedule: Optional[v.Schedule],
                 mine: Sequence[int], taken: Sequence[int], punt: Iterable[str], objective: str = "wins"):
        self.by_id = {r.id: r for r in rows}
        self.shape = shape
        self.objective = objective if objective in OBJECTIVES else OBJECTIVES[0]
        sim = v.simulate_league(list(rows), list(mine), list(taken), shape, schedule)
        self.lineup, self.fill, self.average = sim.lineup, sim.fill, sim.average_team
        self.cats = list(shape.categories)
        punted = set(punt)
        self.scored = [c for c in self.cats if c not in punted]
        ordered = sorted(rows, key=lambda r: r.value, reverse=True)
        n = min(shape.pool_size, len(ordered))
        reps = ordered[max(0, n - shape.roster_size):n] or ordered[-1:]
        totals: v.Stats = {}
        for r in reps:
            for k, x in v.season_totals(r).items():
                if k in v.VOLUME_STATS:
                    totals[k] = totals.get(k, 0.0) + x / len(reps)
        self.rep_stats = v.with_percentages(totals)
        self.rep_rating = sum(r.proj_pg for r in reps) / len(reps)
        self.mine_ids = [i for i in mine if i in self.by_id]
        self.mine = [self.member(i) for i in self.mine_ids]
        self._members: Dict[int, v.Member] = {}
        self._deltas: Dict[int, Dict[str, float]] = {}
        self.evaluated = 0

    def member(self, pid: int) -> v.Member:
        r = self.by_id[pid]
        return v.Member(v.member_totals(r, self.fill), r.proj_pg, r.team)

    def cached(self, pid: int) -> v.Member:
        m = self._members.get(pid)
        if m is None:
            m = self._members[pid] = self.member(pid)
        return m

    def delta(self, pid: int) -> Dict[str, float]:
        """Category rating change, against the average team, when he plays one SD more games (all started)."""
        d = self._deltas.get(pid)
        if d is None:
            r = self.by_id[pid]
            sd = availability.row_games_sd(r)
            moved = v.member_totals(replace(r, exp_gp=r.exp_gp + sd), self.fill)
            base = v.member_totals(r, self.fill)
            team = v.with_percentages({k: self.average.get(k, 0.0) + moved.get(k, 0.0) - base.get(k, 0.0)
                                       for k in v.VOLUME_STATS if k in self.average})
            before = v.team_ratings(self.average, self.average, self.cats, self.shape.reverse)
            after = v.team_ratings(team, self.average, self.cats, self.shape.reverse)
            d = self._deltas[pid] = {c: after.get(c, 100.0) - before.get(c, 100.0) for c in self.cats}
        return d

    def score(self, ids: Sequence[int]) -> Tuple[float, float, Dict[str, float], Dict[str, float], float]:
        """(search score, expected wins, ratings, win chances, ± of wins from games played)."""
        self.evaluated += 1
        members = self.mine + [self.cached(i) for i in ids]
        pids = self.mine_ids + list(ids)
        if len(members) < self.shape.roster_size:
            members.append(v.Member(self.rep_stats, self.rep_rating, None, self.shape.roster_size - len(members)))
        weights = self.lineup.weights(members)
        totals = v.add_totals((m.stats, w) for m, w in weights)
        ratings = v.team_ratings(totals, self.average, self.cats, self.shape.reverse)
        chances = {c: v.win_chance(ratings[c], c) for c in self.cats}
        utility = sum(v.win_utility(ratings[c], c) for c in self.scored)
        # Spread from games played: slopes of win chance and win utility at these ratings.
        share = {id(m): w for m, w in weights}
        slope_w = {c: _win_slope(ratings[c], c) for c in self.cats}
        slope_u = {c: _utility_slope(ratings[c], c) for c in self.scored}
        var_w = var_u = 0.0
        for pid, m in zip(pids, members):
            w = share.get(id(m), 0.0)
            if w <= 0:
                continue
            d = self.delta(pid)
            var_w += (w * sum(slope_w[c] * d[c] for c in self.cats)) ** 2
            var_u += (w * sum(slope_u[c] * d[c] for c in self.scored)) ** 2
        score = utility - FLOOR_Z[self.objective] * math.sqrt(var_u) if self.objective in FLOOR_Z else utility
        return score, sum(chances.values()), ratings, chances, math.sqrt(var_w)


def _win_slope(rating: float, cat: str) -> float:
    """d win_chance / d rating."""
    s = v.spread(cat)
    z = (rating - 100) / s
    return math.exp(-z * z / 2) / (s * math.sqrt(2 * math.pi))


def _utility_slope(rating: float, cat: str) -> float:
    """d win_utility / d rating: the win-chance slope above 100, constant below (see valuation.win_utility)."""
    return _win_slope(rating, cat) if rating >= 100 else 1 / (v.spread(cat) * math.sqrt(2 * math.pi))


def _knapsack(cands: Sequence[v.Valued], costs: Dict[int, int], picks: int, budget: int, replacement: float) -> List[int]:
    """Exactly `picks` players with the most value above replacement for at most `budget`."""
    neg = float("-inf")
    best = [[neg] * (budget + 1) for _ in range(picks + 1)]
    best[0][0] = 0.0
    keep: List[List[List[bool]]] = []
    for r in cands:
        w, gain = costs[r.id], max(0.0, r.value - replacement)
        took = [[False] * (budget + 1) for _ in range(picks + 1)]
        for k in range(picks, 0, -1):
            row, prev = best[k], best[k - 1]
            for b in range(budget, w - 1, -1):
                if prev[b - w] > neg and prev[b - w] + gain > row[b]:
                    row[b] = prev[b - w] + gain
                    took[k][b] = True
        keep.append(took)
    k, b = picks, max(range(budget + 1), key=lambda x: best[picks][x])
    if best[picks][b] == neg:
        return []
    chosen = []
    for idx in range(len(cands) - 1, -1, -1):
        if k > 0 and keep[idx][k][b]:
            chosen.append(cands[idx].id)
            b -= costs[cands[idx].id]
            k -= 1
    return chosen


def _improve(env: _Env, ids: List[int], cands: Sequence[int], costs: Dict[int, int], budget: int) -> Tuple[float, List[int]]:
    """Best single swap, repeated until no affordable swap raises the score."""
    ids = list(ids)
    best = env.score(ids)[0]
    while True:
        spent = sum(costs[i] for i in ids)
        taken = set(ids)
        move = None
        for pos, out in enumerate(ids):
            room = budget - spent + costs[out]
            for j in cands:
                if j in taken or costs[j] > room:
                    continue
                trial = ids[:pos] + [j] + ids[pos + 1:]
                s = env.score(trial)[0]
                if s > best + 1e-9 and (move is None or s > move[0]):
                    move = (s, trial)
        if move is None:
            return best, ids
        best, ids = move


def _build(env: _Env, ids: List[int], costs: Dict[int, int]) -> Build:
    score, wins, ratings, chances, wins_sd = env.score(ids)
    order = sorted(ids, key=lambda i: -costs[i])
    return Build(order, sum(costs[i] for i in ids), score, wins, ratings, chances, wins_sd)


def plan_team(
    rows: Sequence[v.Valued],
    shape: v.LeagueShape,
    schedule: Optional[v.Schedule],
    costs: Dict[int, int],
    mine: Sequence[int],
    taken: Iterable[int],
    budget_left: int,
    punt: Iterable[str] = (),
    avoid: Iterable[int] = (),
    objective: str = "wins",
    averages: Optional[v.Stats] = None,
    pool: int = 140,
    starts: int = 6,
    alternatives: int = 3,
    builds: int = 2,
    distinct: int = 3,
    seed: int = 7,
) -> Optional[Plan]:
    """The best players to buy for the rest of the draft; None when there's nothing to plan.

    `avoid` are players I won't buy: never recommended, but still in the
    simulated league, where other teams draft them. `objective` is "wins"
    (most expected wins), "floor" or "floor20" (the best 1-in-10 or 1-in-20
    season). `averages` (the pool's per-game averages) turns a per-game
    rating miss into stats for the simulated floors; without it builds get
    no floor and floor objectives rank by the stand-in.
    """
    mine = [i for i in mine]
    open_spots = shape.roster_size - len(mine)
    if open_spots <= 0:
        return None
    picks = min(open_spots, max(0, shape.counted - len(mine)))
    streamers = open_spots - picks
    budget = budget_left - streamers  # $1 for every streaming spot
    taken_set: Set[int] = set(taken) | set(mine)
    env = _Env(rows, shape, schedule, mine, list(set(taken)), punt, objective)
    if picks == 0 or budget < picks:
        empty = _build(env, [], costs)
        return Plan(empty, [], {}, mine, budget_left, streamers, 0, env.evaluated, env.objective)

    skip = taken_set | set(avoid)
    ranked = [r for r in sorted(rows, key=lambda r: -r.value) if r.id not in skip]
    # Buy as many counted players as the budget allows; any spot left over streams at $1.
    first: List[int] = []
    while picks > 0:
        budget = budget_left - (open_spots - picks)
        cands = [r for r in ranked if costs.get(r.id, 1) <= budget - (picks - 1)][:pool]
        first = _knapsack(cands, costs, picks, budget, shape.replacement) if budget >= picks else []
        if first:
            break
        picks -= 1
    streamers = open_spots - picks
    if not first:
        return Plan(_build(env, [], costs), [], {}, mine, budget_left, streamers, 0, env.evaluated, env.objective)
    ids = [r.id for r in cands]

    if env.objective in FLOOR_Z:
        starts *= 2  # more distinct end points for the simulation to choose from
    starts_list: List[List[int]] = [first]
    rng = random.Random(seed)
    spread = ids[: max(picks * 8, 60)]
    tries = 0
    while len(starts_list) < starts and tries < 500:
        tries += 1
        team = rng.sample(spread, min(picks, len(spread)))
        if sum(costs[i] for i in team) <= budget:
            starts_list.append(team)

    ends: List[Tuple[float, List[int]]] = []
    for team in starts_list:
        ends.append(_improve(env, team, ids, costs, budget))
    ends.sort(key=lambda x: -x[0])
    finalists: List[Build] = []
    for _, team in ends:
        if not any(set(team) == set(b.ids) for b in finalists):
            finalists.append(_build(env, team, costs))
    # The search holds the league fixed; the full simulation also takes the players
    # I'd buy out of the opponents' pool. Report each build the way My Team would.
    for b in finalists:
        _exact(b, rows, shape, schedule, mine, taken_set - set(mine))
    floors = _Floors(rows, shape, schedule, taken_set - set(mine), averages) if averages else None
    if env.objective in FLOOR_Z and floors:
        for b in finalists:
            floors.score(b, mine)
        finalists.sort(key=lambda b: -b.floor(env.objective))  # the simulated bad season decides
    best = finalists[0]

    others: List[Build] = []
    for b in finalists[1:]:
        if len(others) >= builds:
            break
        if all(len(set(b.ids) - set(o.ids)) >= distinct for o in [best] + others):
            others.append(b)

    swaps: Dict[int, List[Swap]] = {}
    spent = best.cost
    chosen = set(best.ids)
    base_wins = env.score(best.ids)[1]  # swaps compare on the search's fixed league, like for like
    for pos, out in enumerate(best.ids):
        room = budget - spent + costs[out]
        options = []
        for j in ids:
            if j in chosen or costs[j] > room:
                continue
            trial = best.ids[:pos] + [j] + best.ids[pos + 1:]
            u, w, _, _, _ = env.score(trial)
            options.append((u, w, j))
        options.sort(key=lambda x: -x[0])
        swaps[out] = [Swap(out, j, costs[j] - costs[out], w - base_wins) for _, w, j in options[:alternatives]]

    if floors and env.objective not in FLOOR_Z:
        for b in [best] + others:
            floors.score(b, mine)
    return Plan(best, others, swaps, mine, budget_left, streamers, len(starts_list), env.evaluated, env.objective)


class _Floors:
    """Simulated bad seasons for rosters, against the league with every player at his mean outcome."""

    def __init__(self, rows, shape, schedule, taken, averages):
        self.rows, self.shape, self.schedule, self.taken, self.averages = rows, shape, schedule, list(taken), averages
        self.mean_rows = [availability.mean_row(r, averages, shape) for r in rows]
        self.by_id = {r.id: r for r in rows}

    def score(self, build: Build, mine: Sequence[int]) -> None:
        roster = list(mine) + build.ids
        sim = v.simulate_league(self.mean_rows, roster, self.taken, self.shape, self.schedule)
        tr = availability.team_range([self.by_id[i] for i in roster if i in self.by_id], sim, self.averages,
                                     self.shape, draws=FLOOR_DRAWS)
        build.floor10, build.floor20 = tr.quantile(FLOOR_Q["floor"]), tr.quantile(FLOOR_Q["floor20"])


def _exact(build: Build, rows, shape, schedule, mine, taken) -> None:
    roster = list(mine) + build.ids
    sim = v.simulate_league(list(rows), roster, list(taken), shape, schedule)
    build.ratings = dict(sim.ratings)
    build.chances = {c: v.win_chance(sim.ratings[c], c) for c in shape.categories}
    build.wins = sum(build.chances.values())
    by_id = {r.id: r for r in rows}
    build.wins_sd = availability.team_spread([by_id[i] for i in roster if i in by_id], sim, shape).wins
