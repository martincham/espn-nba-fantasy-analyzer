"""Rating and auction-value math shared by the CLI and the draft GUI.

Everything here is pure: no file or network access, and no imports of
library.config or library.globals, so importing it never loads a league
pickle or reads settings.txt.

Stats are plain dicts keyed by ESPN stat names ("PTS", "FGA", "FG%", ...).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

NEGATIVE_STATS = ["TO"]
PERCENT_MAP = {
    "FG%": ["FGM", "FGA"],
    "AFG%": ["FGM", "FGA"],
    "FT%": ["FTM", "FTA"],
    "3P%": ["3PM", "3PA"],
    "A/TO": ["AST", "TO"],
    "STR": ["STL", "TO"],
    "FTR": ["FTA", "FGA"],
}
PERCENT_STATS = ["FG%", "AFG%", "FT%", "3P%", "A/TO", "STR", "FTR"]

# Volume stats scale with Δ and games played; percentages are derived from them.
VOLUME_STATS = [
    "PTS", "REB", "OREB", "DREB", "AST", "STL", "BLK", "TO",
    "3PM", "3PA", "FGM", "FGA", "FTM", "FTA", "MIN", "DD", "TD",
]

Stats = Dict[str, float]


# --------------------------------------------------------------------------
# Rating (same formula as the original rating.ratePlayer / ratePercentStat)
# --------------------------------------------------------------------------


def rate_percent_stat(player_stats: Stats, averages: Stats, stat: str) -> float:
    """Percent-stat rating: (pct / avgPct) ** (attempts / avgAttempts * 2).

    League-average % on any attempts rates 1.0, and volume amplifies how good
    or bad the shooting is. Returns a neutral 1.0 when averages are missing.
    """
    raw = PERCENT_MAP.get(stat)
    if raw is None:
        return 0
    makes_key, attempts_key = raw
    attempts = player_stats.get(attempts_key) or 0
    avg_attempts = averages.get(attempts_key) or 0
    avg_makes = averages.get(makes_key) or 0
    if not avg_attempts or not avg_makes:
        return 1.0
    percent = player_stats.get(stat)
    if percent is None:
        makes = player_stats.get(makes_key) or 0
        percent = makes / attempts if attempts else 0
    avg_percent = avg_makes / avg_attempts
    percent_diff = percent / avg_percent
    attempt_diff = attempts / avg_attempts
    weighting_ratio = 2
    return pow(percent_diff, attempt_diff * weighting_ratio)


def category_rating(player_stats: Stats, averages: Stats, stat: str) -> Optional[float]:
    """One category's rating, where 1.0 is the pool average.

    Returns None when the category can't be rated (zero league average).
    """
    if stat in PERCENT_STATS:
        return rate_percent_stat(player_stats, averages, stat)
    average = averages.get(stat) or 0
    if not average:
        return None
    rating = (player_stats.get(stat) or 0) / average
    if rating != 0 and stat in NEGATIVE_STATS:
        rating = 2 - rating
    return rating


def category_ratings(player_stats: Stats, averages: Stats, categories: Iterable[str]) -> Dict[str, float]:
    result = {}
    for stat in categories:
        rating = category_rating(player_stats, averages, stat)
        if rating is not None:
            result[stat] = rating
    return result


def rate(player_stats: Optional[Stats], averages: Stats, categories: Iterable[str]) -> float:
    """Overall rating: mean of category ratings × 100 (100 = pool average)."""
    if player_stats is None:
        return 0
    ratings = category_ratings(player_stats, averages, categories)
    if not ratings:
        return 0
    return sum(ratings.values()) / len(ratings) * 100


def rate_player(player_stats: Optional[Stats], averages: Stats, ignore_stats: Sequence[str]) -> float:
    """CLI semantics: rate every stat in `averages` that isn't ignored."""
    return rate(player_stats, averages, [s for s in averages if s not in ignore_stats])


# --------------------------------------------------------------------------
# Stat vectors
# --------------------------------------------------------------------------


def with_percentages(stats: Stats) -> Stats:
    """Recompute percent stats from makes/attempts."""
    out = dict(stats)
    for stat, (makes, attempts) in PERCENT_MAP.items():
        if makes in out and attempts in out:
            out[stat] = out[makes] / out[attempts] if out[attempts] else 0.0
    return out


def scale(stats: Stats, factor: float) -> Stats:
    """Scale volume stats by `factor`; percentages stay the same."""
    out = {k: (v * factor if k in VOLUME_STATS else v) for k, v in stats.items()}
    return with_percentages(out)


def pool_averages(lines: Sequence["tuple[Stats, float]"]) -> "tuple[Stats, Stats]":
    """Averages over a pool of (per-game stats, games played).

    Per-game averages divide pooled totals by pooled games (like
    averages.py "avg"); season averages divide by player count (like "total").
    """
    totals: Stats = {}
    games = 0.0
    for per_game, gp in lines:
        games += gp
        for k in VOLUME_STATS:
            if k in per_game:
                totals[k] = totals.get(k, 0.0) + per_game[k] * gp
    count = len(lines) or 1
    per_game_avg = with_percentages({k: v / games for k, v in totals.items()} if games else {})
    season_avg = with_percentages({k: v / count for k, v in totals.items()})
    return per_game_avg, season_avg


# --------------------------------------------------------------------------
# Draft valuation
# --------------------------------------------------------------------------


@dataclass
class LeagueShape:
    teams: int = 12
    budget: int = 200
    roster_size: int = 12
    ignore_players: int = 3
    categories: List[str] = field(default_factory=list)  # league scoring categories
    reverse: List[str] = field(default_factory=lambda: ["TO"])  # lower is better
    rated: List[str] = field(default_factory=list)  # categories counted in ratings

    @property
    def pool_size(self) -> int:
        return self.teams * self.roster_size

    @property
    def counted(self) -> int:
        return max(1, self.roster_size - self.ignore_players)


@dataclass
class Adjustment:
    delta: float = 0.0  # percent
    exp_gp: Optional[int] = None
    note: str = ""


@dataclass
class Valued:
    id: int
    delta: float
    exp_gp: int
    gp_set: bool
    last_pg: float
    last_season: float
    proj_pg: float
    proj_season: float
    value: float
    proj_stats: Stats
    rank: int = 0
    ours: float = 1.0
    edge: float = 0.0
    bid: float = 1.0


@dataclass
class Baseline:
    """Pool averages, computed once per data load from last season."""

    per_game: Stats
    season: Stats
    pool_ids: List[int]


def compute_baseline(players: Sequence, shape: LeagueShape, weight: float = 0.5) -> Baseline:
    """Pick the draftable pool and compute its averages.

    `players` need .id, .base_pg (per-game stats), .base_gp and .espn_rank.
    Starts from ESPN's top N, then re-picks the top N by our own last-season
    value so the pool isn't defined by ESPN's ranking.
    """
    rated = [p for p in players if p.base_pg and p.base_gp > 0]
    n = min(shape.pool_size, len(rated))
    pool = sorted(rated, key=lambda p: p.espn_rank or 10**6)[:n]
    for _ in range(2):
        per_game, season = pool_averages([(p.base_pg, p.base_gp) for p in pool])

        def last_value(p):
            pg = rate(p.base_pg, per_game, shape.rated)
            ssn = rate(scale(p.base_pg, p.base_gp), season, shape.rated)
            return weight * pg + (1 - weight) * ssn

        pool = sorted(rated, key=last_value, reverse=True)[:n]
    per_game, season = pool_averages([(p.base_pg, p.base_gp) for p in pool])
    return Baseline(per_game=per_game, season=season, pool_ids=[p.id for p in pool])


def value_players(
    players: Sequence,
    baseline: Baseline,
    shape: LeagueShape,
    adjustments: Dict[int, Adjustment],
    weight: float,
) -> List[Valued]:
    """Rate every player, apply Δ and expected games, and price the pool.

    `players` need .id, .base_pg, .base_gp and .default_exp_gp.
    """
    rows: List[Valued] = []
    for p in players:
        if not p.base_pg:
            continue
        adj = adjustments.get(p.id) or Adjustment()
        exp_gp = adj.exp_gp if adj.exp_gp is not None else p.default_exp_gp
        proj = scale(p.base_pg, 1 + adj.delta / 100)
        last_pg = rate(p.base_pg, baseline.per_game, shape.rated)
        last_season = rate(scale(p.base_pg, p.base_gp), baseline.season, shape.rated) if p.base_gp else 0.0
        proj_pg = rate(proj, baseline.per_game, shape.rated)
        proj_season = rate(scale(proj, exp_gp), baseline.season, shape.rated)
        rows.append(
            Valued(
                id=p.id,
                delta=adj.delta,
                exp_gp=exp_gp,
                gp_set=adj.exp_gp is not None,
                last_pg=last_pg,
                last_season=last_season,
                proj_pg=proj_pg,
                proj_season=proj_season,
                value=weight * proj_pg + (1 - weight) * proj_season,
                proj_stats=proj,
            )
        )
    price(rows, shape)
    return rows


def price(rows: List[Valued], shape: LeagueShape) -> None:
    """Rank by value and convert surplus over replacement into dollars."""
    ordered = sorted(rows, key=lambda r: r.value, reverse=True)
    for i, r in enumerate(ordered):
        r.rank = i + 1
    if not ordered:
        return
    n = min(shape.pool_size, len(ordered))
    replacement = ordered[n - 1].value
    surplus = sum(max(0.0, r.value - replacement) for r in ordered[:n])
    per_point = (shape.teams * shape.budget - n) / surplus if surplus > 0 else 0.0
    for r in rows:
        r.ours = 1 + max(0.0, r.value - replacement) * per_point


@dataclass
class Market:
    inflation: float
    money_left: float
    spots_left: int
    drafted: int


def apply_inflation(rows: List[Valued], shape: LeagueShape, prices: Dict[int, float]) -> Market:
    """Money left vs value left among undrafted players; sets each row's bid.

    `prices` maps every drafted player (mine or taken) to the price paid.
    """
    money_left = shape.teams * shape.budget - sum(prices.values())
    spots_left = max(0, shape.pool_size - len(prices))
    value_left = sum(r.ours - 1 for r in rows if r.id not in prices)
    inflation = (money_left - spots_left) / value_left if value_left > 0 else 1.0
    for r in rows:
        r.bid = 1 + (r.ours - 1) * inflation
    return Market(inflation=inflation, money_left=money_left, spots_left=spots_left, drafted=len(prices))


# --------------------------------------------------------------------------
# Team category ranks
# --------------------------------------------------------------------------


def season_totals(row: Valued) -> Stats:
    return scale(row.proj_stats, row.exp_gp)


def team_categories(members: Sequence["tuple[Stats, float]"], categories: Sequence[str], counted: int) -> Stats:
    """Category totals from the best `counted` members by per-game rating.

    `members` are (season totals, per-game rating) pairs. Percent categories
    are pooled makes / attempts.
    """
    best = sorted(members, key=lambda m: m[1], reverse=True)[:counted]
    totals: Stats = {}
    for stats, _ in best:
        for k in VOLUME_STATS:
            if k in stats:
                totals[k] = totals.get(k, 0.0) + stats[k]
    totals = with_percentages(totals)
    return {c: totals.get(c, 0.0) for c in categories}


@dataclass
class LeagueSim:
    teams: List[Stats]  # index 0 is my team
    ranks: Dict[str, int]
    roto: int
    overall: int
    expected_wins: float
    filled: int


def simulate_league(
    rows: List[Valued],
    mine: Sequence[int],
    taken: Sequence[int],
    shape: LeagueShape,
) -> LeagueSim:
    """Rank my team against simulated opponents in every league category.

    Opponents are dealt taken players first, then the best remaining players
    by value, in snake order. Empty slots on my roster count as the average of
    the players ranked just above replacement.
    """
    by_id = {r.id: r for r in rows}
    ordered = sorted(rows, key=lambda r: r.value, reverse=True)
    n = min(shape.pool_size, len(ordered))
    reps = ordered[max(0, n - shape.roster_size):n] or ordered[-1:]
    rep_totals: Stats = {}
    for r in reps:
        for k, v in season_totals(r).items():
            if k in VOLUME_STATS:
                rep_totals[k] = rep_totals.get(k, 0.0) + v / len(reps)
    rep_member = (with_percentages(rep_totals), sum(r.proj_pg for r in reps) / len(reps))

    my_rows = [by_id[i] for i in mine if i in by_id]
    me = [(season_totals(r), r.proj_pg) for r in my_rows]
    me += [rep_member] * max(0, shape.roster_size - len(me))

    mine_set = set(mine)
    taken_set = set(taken)
    others = [r for r in ordered if r.id not in mine_set]
    deal = [r for r in others if r.id in taken_set] + [r for r in others if r.id not in taken_set]
    opponents = max(1, shape.teams - 1)
    deal = deal[: opponents * shape.roster_size]
    opp: List[list] = [[] for _ in range(opponents)]
    for k, r in enumerate(deal):
        rnd, pos = divmod(k, opponents)
        opp[opponents - 1 - pos if rnd % 2 else pos].append((season_totals(r), r.proj_pg))

    cats = shape.categories
    teams = [team_categories(me, cats, shape.counted)] + [team_categories(t, cats, shape.counted) for t in opp]

    def better(a: float, b: float, cat: str) -> bool:
        return a < b if cat in shape.reverse else a > b

    all_ranks = [
        {c: 1 + sum(1 for o in teams if better(o[c], t[c], c)) for c in cats} for t in teams
    ]
    roto = [sum(len(teams) + 1 - rk for rk in r.values()) for r in all_ranks]
    overall = 1 + sum(1 for x in roto if x > roto[0])
    expected = sum((len(teams) - rk) / (len(teams) - 1) for rk in all_ranks[0].values()) if len(teams) > 1 else 0.0
    return LeagueSim(
        teams=teams,
        ranks=all_ranks[0],
        roto=roto[0],
        overall=overall,
        expected_wins=expected,
        filled=len(my_rows),
    )
