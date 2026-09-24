"""Rating and auction-value math shared by the CLI and the draft GUI.

Everything here is pure: no file or network access, and no imports of
library.config or library.globals, so importing it never loads a league
pickle or reads settings.txt.

Stats are plain dicts keyed by ESPN stat names ("PTS", "FGA", "FG%", ...).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, NamedTuple, Optional, Sequence, Tuple

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
GAMES_IN_SEASON = 82

# How much a rating point in each category is worth in this league: weekly
# category wins per point, from 2020-21 to 2024-25 matchups (normalised to
# mean 1). An equal-weight rating counts a block like 1.7 blocks are worth and
# undercounts FG% and FT% by about 40%. Measured, not fitted: every single
# season lands within about 0.1 of these. Backtest: docs/BACKTEST_PLAN.md.
CATEGORY_WEIGHTS = {
    "PTS": 1.15, "REB": 1.10, "AST": 0.94, "STL": 0.81, "BLK": 0.58,
    "3PM": 0.71, "TO": 0.85, "FG%": 1.44, "FT%": 1.42,
}

# What this league pays for its Nth most expensive player: the average price
# by rank over its 2020-21 to 2024-25 auctions (12 teams, $200). Ours is
# priced on this curve by value rank, which cut dollar error by about $1 and
# stopped the formula from pricing stars at $100+. Backtest: docs/BACKTEST_PLAN.md.
PRICE_CURVE = [
    78.4, 77.0, 73.8, 71.4, 66.6, 64.0, 62.6, 60.4, 56.2, 52.8, 51.2, 49.4, 47.4, 44.4, 42.4, 41.2,
    39.6, 38.8, 37.8, 36.6, 35.2, 34.8, 33.4, 32.6, 31.4, 30.4, 29.8, 29.2, 29.0, 28.6, 27.8, 27.6,
    27.0, 26.0, 25.6, 24.0, 22.8, 22.0, 21.6, 21.0, 20.4, 19.2, 19.0, 18.4, 17.8, 17.4, 17.2, 16.6,
    16.2, 15.8, 15.8, 15.8, 15.4, 15.2, 14.6, 14.2, 14.0, 13.8, 13.4, 12.8, 12.4, 12.4, 11.8, 11.4,
    11.2, 11.2, 11.0, 10.6, 10.4, 10.0, 9.8, 9.2, 9.0, 8.8, 8.8, 8.6, 8.4, 8.2, 7.6, 7.4,
    7.4, 7.4, 7.0, 6.8, 6.6, 6.2, 5.8, 5.8, 5.8, 5.6, 5.4, 5.2, 5.0, 4.6, 4.6, 4.6,
    4.4, 4.0, 4.0, 3.6, 3.6, 3.6, 3.4, 3.4, 3.2, 2.6, 2.6, 2.6, 2.6, 2.6, 2.4, 2.4,
    2.4, 2.0, 2.0, 2.0, 2.0, 1.6, 1.6, 1.6, 1.6, 1.2, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0,
    1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0,
]
PRICE_CURVE_LEAGUE = (12, 200)  # teams, budget the curve was measured on


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


def rate(
    player_stats: Optional[Stats],
    averages: Stats,
    categories: Iterable[str],
    weights: Optional[Dict[str, float]] = None,
) -> float:
    """Overall rating: mean of category ratings × 100 (100 = pool average).

    With `weights`, a weighted mean (categories missing from it weigh 1), so
    an average player still rates 100.
    """
    if player_stats is None:
        return 0
    ratings = category_ratings(player_stats, averages, categories)
    if not ratings:
        return 0
    if weights:
        total = sum(weights.get(c, 1.0) for c in ratings)
        return sum(weights.get(c, 1.0) * r for c, r in ratings.items()) / total * 100
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


def scale_for_rating(
    stats: Stats,
    averages: Stats,
    categories: Sequence[str],
    target: float,
    weights: Optional[Dict[str, float]] = None,
) -> float:
    """Volume multiplier that moves a player's rating to `target`.

    Δ is entered in rating points; this finds the single factor applied to
    every counting stat and attempt (percentages unchanged) that produces
    the target rating, so the change spreads across categories in
    proportion to what the player already produces. Solved by bisection.
    """
    def rating_at(s: float) -> float:
        return rate(scale(stats, s), averages, categories, weights)

    lo, hi = 0.0, 2.0
    if target <= rating_at(lo):
        return lo
    while rating_at(hi) < target and hi < 64:
        hi *= 2
    for _ in range(40):
        mid = (lo + hi) / 2
        if rating_at(mid) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


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
    core: Optional[int] = None  # players per team worth paying for; the rest cost $1 (None = whole roster)
    replacement: float = 0.0  # per-game rating of the free agent who fills a missed game
    starters: int = 0  # daily starting slots (bench and IR excluded); 0 = no daily lineups
    weights: Dict[str, float] = field(default_factory=dict)  # category weights in ratings; empty = equal
    price_curve: List[float] = field(default_factory=list)  # $ by value rank (PRICE_CURVE); empty = the formula

    @property
    def pool_size(self) -> int:
        return self.teams * self.roster_size

    @property
    def priced_size(self) -> int:
        """How many players share the money above $1: every team's core."""
        core = min(self.core or self.roster_size, self.roster_size)
        return self.teams * core

    @property
    def counted(self) -> int:
        return max(1, self.roster_size - self.ignore_players)


@dataclass
class Adjustment:
    delta: float = 0.0  # change in per-game rating points (100 = average player)
    gp_delta: int = 0  # games added to (or taken from) the default expected games
    exp_min: Optional[float] = None  # minutes per game
    note: str = ""


@dataclass
class Valued:
    id: int
    delta: float
    gp_delta: int
    exp_gp: int
    exp_min: float
    min_set: bool
    last_pg: float
    last_value: float
    proj_pg: float
    value: float
    proj_stats: Stats
    team: Optional[str] = None  # NBA team, for its schedule
    rank: int = 0
    ours: float = 1.0
    edge: float = 0.0


@dataclass
class Baseline:
    """Pool averages, computed once per data load from last season."""

    per_game: Stats
    season: Stats
    pool_ids: List[int]
    avg_gp: float = 1.0  # average games played in the pool


def season_value(rating: float, games: float, replacement: float = 0.0) -> float:
    """A roster spot's average per-game rating over a full season.

    The player's games count at his rating, and the games he misses at the
    replacement rating (the free agent picked up while he's out or on IR).
    With replacement 0 this is simply rating × games / 82.
    """
    games = max(0.0, min(float(GAMES_IN_SEASON), games))
    return (rating * games + replacement * (GAMES_IN_SEASON - games)) / GAMES_IN_SEASON


def compute_baseline(players: Sequence, shape: LeagueShape) -> Baseline:
    """Pick the draftable pool and compute its averages.

    `players` need .id, .base_pg (per-game stats), .base_gp and .espn_rank.
    Starts from ESPN's top N, then re-picks the top N by our own last-season
    value (per-game rating × games) so the pool isn't defined by ESPN's ranking.
    """
    rated = [p for p in players if p.base_pg and p.base_gp > 0]
    n = min(shape.pool_size, len(rated))
    pool = sorted(rated, key=lambda p: p.espn_rank or 10**6)[:n]
    for _ in range(2):
        per_game, _season = pool_averages([(p.base_pg, p.base_gp) for p in pool])
        avg_gp = sum(p.base_gp for p in pool) / len(pool) if pool else 1.0
        pool = sorted(rated, key=lambda p: rate(p.base_pg, per_game, shape.rated, shape.weights) * p.base_gp / avg_gp,
                      reverse=True)[:n]
    per_game, season = pool_averages([(p.base_pg, p.base_gp) for p in pool])
    avg_gp = sum(p.base_gp for p in pool) / len(pool) if pool else 1.0
    return Baseline(per_game=per_game, season=season, pool_ids=[p.id for p in pool], avg_gp=avg_gp)


def value_players(
    players: Sequence,
    baseline: Baseline,
    shape: LeagueShape,
    adjustments: Dict[int, Adjustment],
) -> List[Valued]:
    """Rate every player, apply minutes, Δ and games, and price the pool.

    Value = projected per-game rating × expected games, with missed games
    filled at shape.replacement (see season_value). Expected games = the
    player's .default_exp_gp (ESPN's projection) + the games Δ.

    `players` need .id, .base_pg, .base_gp and .default_exp_gp. Optionally
    .rate_line / .rate_min / .default_exp_min: the projection keeps rate_line's
    per-minute production and scales it to the expected minutes, then Δ
    (rating points) is applied on top as a skill change.
    """
    rows: List[Valued] = []
    for p in players:
        if not p.base_pg:
            continue
        adj = adjustments.get(p.id) or Adjustment()
        exp_gp = max(0, min(GAMES_IN_SEASON, p.default_exp_gp + adj.gp_delta))
        line = getattr(p, "rate_line", None) or p.base_pg
        line_min = getattr(p, "rate_min", 0) or 0
        default_min = getattr(p, "default_exp_min", None) or line_min
        exp_min = adj.exp_min if adj.exp_min is not None else default_min
        last_pg = rate(p.base_pg, baseline.per_game, shape.rated, shape.weights)
        # Role: same per-minute production, expected minutes.
        proj = scale(line, exp_min / line_min) if line_min and exp_min else dict(line)
        # Skill: Δ rating points on top of the minutes-adjusted line.
        if adj.delta:
            role_rating = rate(proj, baseline.per_game, shape.rated, shape.weights)
            proj = scale(proj, scale_for_rating(proj, baseline.per_game, shape.rated, role_rating + adj.delta, shape.weights))
        proj_pg = rate(proj, baseline.per_game, shape.rated, shape.weights)
        rows.append(
            Valued(
                id=p.id,
                delta=adj.delta,
                gp_delta=adj.gp_delta,
                exp_gp=exp_gp,
                exp_min=exp_min,
                min_set=adj.exp_min is not None,
                last_pg=last_pg,
                last_value=season_value(last_pg, p.base_gp, shape.replacement),
                proj_pg=proj_pg,
                value=season_value(proj_pg, exp_gp, shape.replacement),
                proj_stats=proj,
                team=getattr(p, "pro_team", None),
            )
        )
    price(rows, shape)
    return rows


def price(rows: List[Valued], shape: LeagueShape) -> None:
    """Rank by value and convert it into dollars (see pricing)."""
    ordered = sorted(rows, key=lambda r: r.value, reverse=True)
    for i, r in enumerate(ordered):
        r.rank = i + 1
    rate = pricing(rows, shape)
    for r in rows:
        r.ours = rate.dollars(r.value)


@dataclass
class Pricing:
    replacement: float  # value of the last core player: what $1 gets you
    per_point: float  # dollars per point of value above replacement (the curve's average, when there is one)
    values: List[float] = field(default_factory=list)  # with a price curve: the pool's values, best first
    curve: List[float] = field(default_factory=list)  # ... and the dollars at each of those ranks

    def dollars(self, value: float) -> float:
        if not self.curve:
            return 1 + max(0.0, value - self.replacement) * self.per_point
        return curve_dollars(value, self.values, self.curve)


def curve_dollars(value: float, values: Sequence[float], curve: Sequence[float]) -> float:
    """Dollars for a value on a price curve: interpolated between the ranks it falls between.

    Above the best player it's the top price; past the end of the curve, $1.
    """
    n = min(len(values), len(curve))
    if n == 0:
        return 1.0
    if value >= values[0]:
        return curve[0]
    for i in range(1, n):
        if value >= values[i]:
            hi, lo = values[i - 1], values[i]
            t = (hi - value) / (hi - lo) if hi > lo else 0.0
            return max(1.0, curve[i - 1] + t * (curve[i] - curve[i - 1]))
    return 1.0


def league_curve(shape: LeagueShape) -> List[float]:
    """shape.price_curve resampled to this league's roster spots and scaled to its budget."""
    base = shape.price_curve
    spots = shape.pool_size
    if not base or spots <= 0:
        return []
    curve = [base[min(len(base) - 1, int(i * len(base) / spots))] for i in range(spots)]
    extra = shape.teams * shape.budget - spots  # money above $1 a spot
    above = sum(c - 1 for c in curve)
    k = extra / above if above > 0 else 1.0
    return [1 + (c - 1) * k for c in curve]


def pricing(rows: Sequence[Valued], shape: LeagueShape) -> Pricing:
    """The league's exchange rate between value points and dollars.

    With a price curve (shape.price_curve), the Nth most valuable player is
    worth what this league pays for its Nth most expensive player, scaled so
    every spot adds up to the budget. Without one, every roster spot costs $1
    and the rest of the money goes to the top `priced_size` players in
    proportion to their value above the last of them.
    """
    ordered = sorted((r.value for r in rows), reverse=True)
    if not ordered:
        return Pricing(0.0, 0.0)
    n = min(shape.priced_size, len(ordered))
    replacement = ordered[n - 1]
    curve = league_curve(shape)
    if curve:
        top = ordered[: len(curve)]
        spread_ = top[0] - replacement
        per_point = (curve[0] - 1) / spread_ if spread_ > 0 else 0.0
        return Pricing(replacement, per_point, top, curve[: len(top)])
    surplus = sum(max(0.0, v - replacement) for v in ordered[:n])
    spots = min(shape.pool_size, len(ordered))
    per_point = (shape.teams * shape.budget - spots) / surplus if surplus > 0 else 0.0
    return Pricing(replacement, per_point)


# --------------------------------------------------------------------------
# Team category ranks
# --------------------------------------------------------------------------


def season_totals(row: Valued) -> Stats:
    return scale(row.proj_stats, row.exp_gp)


def replacement_fill(rows: Sequence[Valued], shape: LeagueShape) -> Stats:
    """The per-game line of the free agent who fills a player's missed games.

    The average line of the players ranked just above replacement, scaled to
    shape.replacement. Empty when missed games aren't filled (replacement 0).
    """
    ordered = sorted(rows, key=lambda r: r.value, reverse=True)
    n = min(shape.pool_size, len(ordered))
    reps = ordered[max(0, n - shape.roster_size):n] or ordered[-1:]
    rep_rating = sum(r.proj_pg for r in reps) / len(reps) if reps else 0.0
    if shape.replacement <= 0 or rep_rating <= 0:
        return {}
    line: Stats = {}
    for r in reps:
        for k, v in r.proj_stats.items():
            if k in VOLUME_STATS:
                line[k] = line.get(k, 0.0) + v / len(reps)
    return scale(line, shape.replacement / rep_rating)


def with_fill(totals: Stats, games: float, fill: Stats) -> Stats:
    """Season totals plus `fill` for the games missed out of a full season."""
    missed = GAMES_IN_SEASON - games
    if not fill or missed <= 0:
        return totals
    out = dict(totals)
    for k, v in fill.items():
        out[k] = out.get(k, 0.0) + v * missed
    return with_percentages(out)


def member_totals(row: Valued, fill: Stats) -> Stats:
    """A player's season totals, with his missed games filled by a free agent."""
    return with_fill(season_totals(row), row.exp_gp, fill)


class Member(NamedTuple):
    """A roster spot in a team simulation."""

    stats: Stats  # season totals over a full season, missed games filled
    rating: float  # per-game rating: who plays when there's no room for everyone
    team: Optional[str] = None  # NBA team whose schedule he plays; None = an average schedule
    count: int = 1  # identical spots this stands for (open slots, streaming spots)


def best_members(members: Sequence[Member], counted: int) -> List[Member]:
    """The best `counted` spots by per-game rating."""
    best: List[Member] = []
    left = counted
    for m in sorted(members, key=lambda m: m.rating, reverse=True):
        if left <= 0:
            break
        take = min(m.count, left)
        best.append(m if take == m.count else m._replace(count=take))
        left -= take
    return best


def add_totals(weighted: Iterable["tuple[Stats, float]"]) -> Stats:
    """Sum (season totals × weight) over volume stats; percentages are pooled makes / attempts."""
    totals: Stats = {}
    for stats, weight in weighted:
        for k in VOLUME_STATS:
            if k in stats:
                totals[k] = totals.get(k, 0.0) + stats[k] * weight
    return with_percentages(totals)


def team_totals(members: Sequence[Member], counted: int) -> Stats:
    """Season totals from the best `counted` members by per-game rating."""
    return add_totals((m.stats, m.count) for m in best_members(members, counted))


def team_categories(members: Sequence[Member], categories: Sequence[str], counted: int) -> Stats:
    totals = team_totals(members, counted)
    return {c: totals.get(c, 0.0) for c in categories}


# --------------------------------------------------------------------------
# Daily lineups
# --------------------------------------------------------------------------


class Schedule:
    """The NBA schedule as fantasy days (ESPN scoring periods).

    `team_days` maps each NBA team to the days it plays. A player without a
    known team plays an average schedule: on each day, the share of NBA teams
    that play that day. Weeks are 7-day blocks from opening night.
    """

    def __init__(self, team_days: Dict[str, Sequence[int]]):
        days = sorted({d for ds in team_days.values() for d in ds})
        index = {d: i for i, d in enumerate(days)}
        self.days = len(days)
        first = days[0] if days else 0
        self.week = [(d - first) // 7 for d in days]
        self.weeks = self.week[-1] + 1 if days else 0
        self.team_days = {t: [index[d] for d in sorted(set(ds))] for t, ds in team_days.items()}
        playing = [0] * self.days
        for ds in self.team_days.values():
            for i in ds:
                playing[i] += 1
        teams = len(self.team_days) or 1
        self.share = [n / teams for n in playing]
        self.average_games = sum(self.share)

    def presence(self, team: Optional[str]) -> List["tuple[int, float]"]:
        """(day, chance he has a game) for every day his team might play."""
        days = self.team_days.get(team) if team else None
        if days is None:
            return [(i, p) for i, p in enumerate(self.share) if p > 0]
        return [(i, 1.0) for i in days]

    def games(self, team: Optional[str]) -> float:
        days = self.team_days.get(team) if team else None
        return float(len(days)) if days is not None else self.average_games


@dataclass
class Lineup:
    """How a roster's games become team totals.

    Without a schedule: the best `counted` members' full seasons.

    With a schedule, day by day: the best `counted` members fill
    `starters` slots each day. Whoever has a game plays, best per-game rating
    first; games past the open slots are lost on the bench. A member's season
    totals are scaled by the share of his team's games he starts. Positions
    are ignored: any player fills any slot.

    Then the `streamer` spots (the rest of the roster, cycled through free
    agents at the replacement line) fill open slots. Adds let you pick
    streamers who play on the days you need, so each week they fill open
    slots anywhere in the week, up to the games that many average players
    would play that week.
    """

    counted: int
    schedule: Optional[Schedule] = None
    starters: int = 0
    streamer: Optional[Member] = None

    @property
    def daily(self) -> bool:
        return self.schedule is not None and self.starters > 0

    def weights(self, members: Sequence[Member]) -> List["tuple[Member, float]"]:
        """Each counted member with the share of a full season's games he counts for.

        Without a schedule a member counts his whole season (times his
        count). With one, it's his starts divided by his team's game days.
        """
        best = best_members(members, self.counted)
        if not self.daily:
            return [(m, float(m.count)) for m in best]
        sched = self.schedule
        open_slots = [float(self.starters)] * sched.days
        out = []
        for m in sorted(best, key=lambda m: m.rating, reverse=True):
            starts = 0.0
            for day, chance in sched.presence(m.team):
                room = open_slots[day]
                if room <= 0:
                    continue
                take = min(chance * m.count, room)
                open_slots[day] = room - take
                starts += take
            games = sched.games(m.team)
            out.append((m, starts / games if games else 0.0))
        if self.streamer is not None and sched.average_games:
            room = [0.0] * sched.weeks
            cap = [0.0] * sched.weeks
            for day in range(sched.days):
                week = sched.week[day]
                room[week] += open_slots[day]
                cap[week] += sched.share[day] * self.streamer.count
            streamed = sum(min(r, c) for r, c in zip(room, cap))
            out.append((self.streamer, streamed / sched.average_games))
        return out

    def totals(self, members: Sequence[Member]) -> Stats:
        return add_totals((m.stats, w) for m, w in self.weights(members))

    def size(self, members: Sequence[Member]) -> float:
        """How many full seasons the team's counted games add up to."""
        return sum(w for _, w in self.weights(members))


def team_ratings(team: Stats, average_team: Stats, categories: Sequence[str], reverse: Sequence[str]) -> Dict[str, float]:
    """Team category ratings vs the average team, on the player scale (100 = average).

    Percentages use the same volume-weighted formula as players; `reverse`
    categories (e.g. TO) are inverted so higher is always better.
    """
    ratings = {}
    for cat in categories:
        if cat in PERCENT_STATS:
            ratings[cat] = rate_percent_stat(team, average_team, cat) * 100
            continue
        average = average_team.get(cat) or 0
        if not average:
            continue
        ratio = (team.get(cat) or 0) / average
        ratings[cat] = (2 - ratio if cat in reverse else ratio) * 100
    return ratings


def make_lineup(shape: LeagueShape, schedule: Optional[Schedule], fill: Stats) -> Lineup:
    """Daily lineups when there's a schedule; the roster spots past `counted` stream free agents."""
    streams = shape.roster_size - shape.counted
    streamer = None
    if fill and streams > 0:
        streamer = Member(scale(fill, GAMES_IN_SEASON), shape.replacement, None, streams)
    return Lineup(counted=shape.counted, schedule=schedule, starters=shape.starters, streamer=streamer)


@dataclass
class LeagueSim:
    average_team: Stats  # the average simulated team's season totals
    fill: Stats  # per-game line that fills a player's missed games (empty: not filled)
    lineup: Lineup  # how rosters become team totals
    teams: List[Stats]  # category values per team; index 0 is my team
    ranks: Dict[str, int]
    ratings: Dict[str, float]  # my team vs the average team, 100 = average
    roto: int
    overall: int
    expected_wins: float
    filled: int


def simulate_league(
    rows: List[Valued],
    mine: Sequence[int],
    taken: Sequence[int],
    shape: LeagueShape,
    schedule: Optional[Schedule] = None,
) -> LeagueSim:
    """Rank my team against simulated opponents in every league category.

    Opponents are dealt taken players first, then the best remaining players
    by value, in snake order. Empty slots on my roster count as the average of
    the players ranked just above replacement. With a schedule, team totals
    come from daily lineups (see Lineup).
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
    rep_stats, rep_rating = with_percentages(rep_totals), sum(r.proj_pg for r in reps) / len(reps)

    fill = replacement_fill(rows, shape)
    lineup = make_lineup(shape, schedule, fill)

    def member(r: Valued) -> Member:
        return Member(member_totals(r, fill), r.proj_pg, r.team)

    my_rows = [by_id[i] for i in mine if i in by_id]
    me = [member(r) for r in my_rows]
    if len(me) < shape.roster_size:
        me.append(Member(rep_stats, rep_rating, None, shape.roster_size - len(me)))

    mine_set = set(mine)
    taken_set = set(taken)
    others = [r for r in ordered if r.id not in mine_set]
    deal = [r for r in others if r.id in taken_set] + [r for r in others if r.id not in taken_set]
    opponents = max(1, shape.teams - 1)
    deal = deal[: opponents * shape.roster_size]
    opp: List[List[Member]] = [[] for _ in range(opponents)]
    for k, r in enumerate(deal):
        rnd, pos = divmod(k, opponents)
        opp[opponents - 1 - pos if rnd % 2 else pos].append(member(r))

    cats = shape.categories
    totals = [lineup.totals(me)] + [lineup.totals(t) for t in opp]
    teams = [{c: t.get(c, 0.0) for c in cats} for t in totals]
    average_team = with_percentages(
        {k: sum(t.get(k, 0.0) for t in totals) / len(totals) for k in VOLUME_STATS}
    )

    def better(a: float, b: float, cat: str) -> bool:
        return a < b if cat in shape.reverse else a > b

    all_ranks = [
        {c: 1 + sum(1 for o in teams if better(o[c], t[c], c)) for c in cats} for t in teams
    ]
    roto = [sum(len(teams) + 1 - rk for rk in r.values()) for r in all_ranks]
    overall = 1 + sum(1 for x in roto if x > roto[0])
    expected = sum((len(teams) - rk) / (len(teams) - 1) for rk in all_ranks[0].values()) if len(teams) > 1 else 0.0
    return LeagueSim(
        average_team=average_team,
        fill=fill,
        lineup=lineup,
        teams=teams,
        ranks=all_ranks[0],
        ratings=team_ratings(totals[0], average_team, cats, shape.reverse),
        roto=roto[0],
        overall=overall,
        expected_wins=expected,
        filled=len(my_rows),
    )


# --------------------------------------------------------------------------
# Team fit: how much a player helps the team I have
# --------------------------------------------------------------------------


@dataclass
class Fade:
    """Where extra category strength stops helping.

    A team category rating counts in full up to `start`, each point above it
    counts less (linearly down to nothing at `end`), and points past `end`
    don't count. In H2H, a category you already win can't be won twice.
    """

    start: float = 110.0
    end: float = 140.0

    def useful(self, rating: float) -> float:
        """The part of a team category rating that still wins matchups."""
        a, b = self.start, max(self.end, self.start + 1e-9)
        if rating <= a:
            return rating
        x = min(rating, b) - a
        return a + x - x * x / (2 * (b - a))


# --------------------------------------------------------------------------
# Weekly win chances
# --------------------------------------------------------------------------

# How much a team's category rating swings from week to week, as the spread
# (in rating points) of a normal curve: P(win a category) = Φ((rating − 100) / spread).
# Fitted on one season of this league's head-to-head results (2025-26: 22 weeks,
# 12 teams), then pulled halfway toward the overall fit of 25 so a single
# season doesn't overfit. Steady categories (PTS, FG%, FT%) have small spreads:
# a small edge wins most weeks. Swingy ones (STL, BLK, TO) have large spreads.
OVERALL_SPREAD = 25.0
CATEGORY_SPREAD = {
    "PTS": 20.0, "REB": 21.0, "AST": 24.5, "STL": 29.0, "BLK": 28.0,
    "3PM": 26.0, "TO": 27.5, "FG%": 20.0, "FT%": 20.0,
}


def spread(cat: str) -> float:
    return CATEGORY_SPREAD.get(cat, OVERALL_SPREAD)


def normal_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def win_chance(rating: float, cat: str) -> float:
    """Chance of beating the average team in a category in a given week."""
    return normal_cdf((rating - 100) / spread(cat))


def win_utility(rating: float, cat: str) -> float:
    """Win chance, except below 100 it keeps the slope it has at 100.

    Above 100 extra strength fades as the category becomes a sure win. Below
    100 it doesn't fade: a losing category is one to fix, and giving up on it
    (punting) is always the user's choice, never automatic.
    """
    if rating >= 100:
        return win_chance(rating, cat)
    return 0.5 + (rating - 100) / (spread(cat) * math.sqrt(2 * math.pi))


def matchup_win(chances: Sequence[float]) -> float:
    """Chance of winning a week: more categories than the opponent.

    Categories are treated as independent. With an even count, a split
    counts as half a win.
    """
    dist = [1.0]
    for p in chances:
        nxt = [0.0] * (len(dist) + 1)
        for k, q in enumerate(dist):
            nxt[k] += q * (1 - p)
            nxt[k + 1] += q * p
        dist = nxt
    n = len(chances)
    return sum(q for k, q in enumerate(dist) if 2 * k > n) + sum(0.5 * q for k, q in enumerate(dist) if 2 * k == n)


# A category's win utility is scaled back to rating points at the overall
# spread, so Fit stays on the player scale (≈ Value on an unsaturated team).
WIN_UTILITY_SCALE = OVERALL_SPREAD * math.sqrt(2 * math.pi)


def team_fit(
    rows: Sequence[Valued],
    mine: Sequence[int],
    shape: LeagueShape,
    sim: LeagueSim,
    baseline: Baseline,
    categories: Sequence[str],
    useful: Callable[[float, str], float],
    starts: Optional[Dict[int, float]] = None,
) -> Dict[int, float]:
    """Each player's value to my current team, on the player rating scale.

    My team is my players plus average players (rating 100) in the open slots.
    A player's fit compares my team with him against my team with an average
    player in his place, category by category, counting only the `useful`
    part of each team category rating: a Fade, or weekly win chances (see
    fit_by_wins). Players already on my team are compared with an average
    player in their place.

    With daily lineups (sim.lineup), a player only adds on days he'd start,
    so the same player fits better on a roster whose games fall on other
    days. If `starts` is given, it's filled with the share of each player's
    games he'd start on my team.
    """
    cats = [c for c in categories if c in shape.categories]
    if not cats or not rows:
        return {}
    by_id = {r.id: r for r in rows}
    fill, lineup = sim.fill, sim.lineup
    avg_gp = baseline.avg_gp or GAMES_IN_SEASON
    average_stats = with_fill(scale(baseline.per_game, avg_gp), avg_gp, fill)

    def average(n: int) -> List[Member]:
        return [Member(average_stats, 100.0, None, n)] if n > 0 else []

    def member(r: Valued) -> Member:
        return Member(member_totals(r, fill), r.proj_pg, r.team)

    my_rows = [by_id[i] for i in mine if i in by_id][: shape.roster_size]
    my = [member(r) for r in my_rows]
    open_slots = shape.roster_size - len(my)

    def useful_total(members: List[Member], him: Optional[int] = None) -> float:
        """Useful rating summed over categories; records the share of `him`'s games he starts."""
        weights = lineup.weights(members)
        if starts is not None and him is not None:
            starts[him] = next((w for m, w in weights if m is members[0]), 0.0)
        totals = add_totals((m.stats, w) for m, w in weights)
        ratings = team_ratings(totals, sim.average_team, cats, shape.reverse)
        return sum(useful(ratings.get(c, 100.0), c) for c in cats)

    # One player's share of the team totals: a season's worth of games out of the team's.
    size = lineup.size(my + average(open_slots)) if lineup.daily else shape.counted
    scale_to_player = size / len(cats)
    fits: Dict[int, float] = {}
    mine_set = set(mine)
    if open_slots > 0:
        base = useful_total(my + average(open_slots))
        for r in rows:
            if r.id in mine_set:
                continue
            fits[r.id] = 100 + (useful_total([member(r)] + my + average(open_slots - 1), r.id) - base) * scale_to_player
    else:
        # A full roster: a new player would take the place of my weakest one.
        weakest = min(range(len(my)), key=lambda k: my[k].rating)
        rest = my[:weakest] + my[weakest + 1:]
        base = useful_total(rest + average(1))
        for r in rows:
            if r.id in mine_set:
                continue
            fits[r.id] = 100 + (useful_total([member(r)] + rest, r.id) - base) * scale_to_player
    pad = average(shape.roster_size - len(my))
    for k, r in enumerate(my_rows):
        others = my[:k] + my[k + 1:]
        fits[r.id] = 100 + (useful_total([my[k]] + others + pad, r.id) - useful_total(others + average(1) + pad)) * scale_to_player
    return fits


def fit_by_fade(fade: Fade) -> Callable[[float, str], float]:
    return lambda rating, cat: fade.useful(rating)


def fit_by_wins(rating: float, cat: str) -> float:
    """Useful rating = weekly win utility, in rating points at the overall spread."""
    return win_utility(rating, cat) * WIN_UTILITY_SCALE
