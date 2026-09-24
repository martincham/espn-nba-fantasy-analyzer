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
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from library import valuation as v


@dataclass
class Build:
    ids: List[int]  # players to buy (not the ones already mine)
    cost: int  # what they should cost together
    utility: float  # the search's score: summed win utility over unpunted categories
    wins: float  # expected category wins per week vs the average team, every category
    ratings: Dict[str, float]  # team category ratings, 100 = the average team
    chances: Dict[str, float]  # weekly win chance per category


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


class _Env:
    """The simulated league, fixed for one plan, and a fast scorer for my roster."""

    def __init__(self, rows: Sequence[v.Valued], shape: v.LeagueShape, schedule: Optional[v.Schedule],
                 mine: Sequence[int], taken: Sequence[int], punt: Iterable[str]):
        self.by_id = {r.id: r for r in rows}
        self.shape = shape
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
        self.mine = [self.member(i) for i in mine if i in self.by_id]
        self._members: Dict[int, v.Member] = {}
        self.evaluated = 0

    def member(self, pid: int) -> v.Member:
        r = self.by_id[pid]
        return v.Member(v.member_totals(r, self.fill), r.proj_pg, r.team)

    def cached(self, pid: int) -> v.Member:
        m = self._members.get(pid)
        if m is None:
            m = self._members[pid] = self.member(pid)
        return m

    def score(self, ids: Sequence[int]) -> Tuple[float, float, Dict[str, float], Dict[str, float]]:
        self.evaluated += 1
        members = self.mine + [self.cached(i) for i in ids]
        if len(members) < self.shape.roster_size:
            members.append(v.Member(self.rep_stats, self.rep_rating, None, self.shape.roster_size - len(members)))
        totals = self.lineup.totals(members)
        ratings = v.team_ratings(totals, self.average, self.cats, self.shape.reverse)
        chances = {c: v.win_chance(ratings[c], c) for c in self.cats}
        utility = sum(v.win_utility(ratings[c], c) for c in self.scored)
        return utility, sum(chances.values()), ratings, chances


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
    utility, wins, ratings, chances = env.score(ids)
    order = sorted(ids, key=lambda i: -costs[i])
    return Build(order, sum(costs[i] for i in ids), utility, wins, ratings, chances)


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
    pool: int = 140,
    starts: int = 6,
    alternatives: int = 3,
    builds: int = 2,
    distinct: int = 3,
    seed: int = 7,
) -> Optional[Plan]:
    """The best players to buy for the rest of the draft; None when there's nothing to plan.

    `avoid` are players I won't buy: never recommended, but still in the
    simulated league, where other teams draft them.
    """
    mine = [i for i in mine]
    open_spots = shape.roster_size - len(mine)
    if open_spots <= 0:
        return None
    picks = min(open_spots, max(0, shape.counted - len(mine)))
    streamers = open_spots - picks
    budget = budget_left - streamers  # $1 for every streaming spot
    taken_set: Set[int] = set(taken) | set(mine)
    env = _Env(rows, shape, schedule, mine, list(set(taken)), punt)
    if picks == 0 or budget < picks:
        empty = _build(env, [], costs)
        return Plan(empty, [], {}, mine, budget_left, streamers, 0, env.evaluated)

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
        return Plan(_build(env, [], costs), [], {}, mine, budget_left, streamers, 0, env.evaluated)
    ids = [r.id for r in cands]

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
    best = _build(env, ends[0][1], costs)

    others: List[Build] = []
    for _, team in ends[1:]:
        if len(others) >= builds:
            break
        if all(len(set(team) - set(b.ids)) >= distinct for b in [best] + others):
            others.append(_build(env, team, costs))

    swaps: Dict[int, List[Swap]] = {}
    spent = best.cost
    chosen = set(best.ids)
    for pos, out in enumerate(best.ids):
        room = budget - spent + costs[out]
        options = []
        for j in ids:
            if j in chosen or costs[j] > room:
                continue
            trial = best.ids[:pos] + [j] + best.ids[pos + 1:]
            u, w, _, _ = env.score(trial)
            options.append((u, w, j))
        options.sort(key=lambda x: -x[0])
        swaps[out] = [Swap(out, j, costs[j] - costs[out], w - best.wins) for _, w, j in options[:alternatives]]

    # The search holds the league fixed; the full simulation also takes the players
    # I'd buy out of the opponents' pool. Report each build the way My Team would.
    for b in [best] + others:
        _exact(b, rows, shape, schedule, mine, taken_set - set(mine))
    return Plan(best, others, swaps, mine, budget_left, streamers, len(starts_list), env.evaluated)


def _exact(build: Build, rows, shape, schedule, mine, taken) -> None:
    sim = v.simulate_league(list(rows), list(mine) + build.ids, list(taken), shape, schedule)
    build.ratings = dict(sim.ratings)
    build.chances = {c: v.win_chance(sim.ratings[c], c) for c in shape.categories}
    build.wins = sum(build.chances.values())
