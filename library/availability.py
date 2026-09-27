"""Games-played range and season-value range (docs/GAMES_RANGE_PLAN.md).

ESPN projects one number for games played; what actually happens is wide and
skewed. A season is either normal (rest days, short injuries) or includes a
major absence (40+ team games in a row missed). Each part is a beta-binomial
over 82 games, and the chance of a major absence falls as ESPN's projection
rises. Fitted by history/games_model.py on 1,403 player-seasons (2018-19 to
2025-26, leaving out 2022-23's mid-season projection); held out one season at
a time, 81% of actual games fell inside the 80% range.

Age, height, weight, BMI, experience, position, a new team and the team's
record the season before added nothing beyond ESPN's projection. Past
availability (games over his last three rotation seasons, weighted toward the
latest) helped a little in 5 of 7 held-out seasons; it's in by the user's
choice (2026-09-27), mainly for players ESPN projects above their record. The
board's GP delta shifts the result.

Season value also depends on the per-game rating, which misses by about 9
points either way, and misses low when games are missed:
rating error = bias + slope x (games - projected games) + noise, with the
noise larger over fewer games. value_range() combines both.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

FULL = 82
HALF = 41  # "loses half the season": fewer games than this


HIST_WEIGHTS = (1.0, 0.7, 0.5)  # last season counts most
ROTATION_MIN, ROTATION_PROJ_MIN = 20.0, 24.0  # a season counts as history at these minutes (played, or ESPN's projection)
SEASON_GAMES = {2020: 72, 2021: 72}  # shortened seasons (2019-20 varied by team)


def history_availability(past: Sequence[Sequence[float]], season: int) -> Optional[float]:
    """Weighted games (82-game basis) over his last three rotation seasons before `season`; None without any.

    `past` rows are [season, games played, minutes per game, ESPN's projected minutes].
    Matches history/games_model.py's hist_avail: a season counts when he averaged
    20+ minutes or ESPN projected 24+ (so a season lost to injury still counts).
    """
    by_season = {int(row[0]): row for row in past}
    pairs = []
    for k, w in zip((1, 2, 3), HIST_WEIGHTS):
        row = by_season.get(season - k)
        if not row:
            continue
        _, gp, minutes, proj_min = row
        if (minutes or 0) >= ROTATION_MIN or (proj_min or 0) >= ROTATION_PROJ_MIN:
            pairs.append((w, FULL * gp / SEASON_GAMES.get(season - k, FULL)))
    if not pairs:
        return None
    return sum(w * g for w, g in pairs) / sum(w for w, _ in pairs)


@dataclass(frozen=True)
class Params:
    proj_mean: float = 70.86  # ESPN projected games (82-game basis) of the players it was fitted on
    proj_sd: float = 8.125
    hist_mean: float = 65.90  # past availability of the players it was fitted on (a player without history gets this)
    hist_sd: float = 12.43
    major: tuple = (-2.7508, -0.6926, -0.1582)  # logit P(major absence) = a0 + a1 z_proj + a2 z_hist
    normal_mean: tuple = (1.2671, 0.3631, 0.0809)  # logit mean share of games in a normal season, same inputs
    normal_phi: float = 5.551  # its concentration (higher = tighter)
    major_mean: tuple = (-1.4728, 0.5472)  # logit mean share of games in a season with a major absence
    major_phi: float = 4.284
    rating_bias: float = -1.384  # per-game rating error when he plays his projected games
    rating_slope: float = 0.181  # rating points per game above (below) his projection
    rating_var: tuple = (57.05, 1532.1)  # noise variance = v0 + v1 / games


PARAMS = Params()


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def _betabinom(n: int, mean: float, phi: float) -> List[float]:
    """P(k) for k = 0..n of a beta-binomial with the given mean and concentration."""
    a, b = mean * phi, (1 - mean) * phi
    const = math.lgamma(n + 1) + math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) - math.lgamma(n + a + b)
    return [math.exp(const - math.lgamma(k + 1) - math.lgamma(n - k + 1) + math.lgamma(k + a) + math.lgamma(n - k + b))
            for k in range(n + 1)]


@dataclass
class GamesRange:
    pmf: List[float]  # P(games = k), k = 0..82
    projected: float  # the projection it was built from (82-game basis)

    def cdf(self, k: int) -> float:
        return sum(self.pmf[: max(0, min(FULL, k) + 1)])

    def quantile(self, q: float) -> int:
        total = 0.0
        for k, p in enumerate(self.pmf):
            total += p
            if total >= q - 1e-12:
                return k
        return FULL

    @property
    def mean(self) -> float:
        return sum(k * p for k, p in enumerate(self.pmf))

    @property
    def p_half(self) -> float:
        """Chance he plays fewer than 41 games."""
        return sum(self.pmf[:HALF])


def games_range(projected: float, out: int = 0, shift: int = 0, hist: Optional[float] = None,
                params: Params = PARAMS) -> GamesRange:
    """Distribution of games played for ESPN's projection, on 82 games.

    `hist`: past availability (history_availability); None counts as average.

    `out`: games he's known to miss at the start of the season. He can play at
    most the rest, with the same chance of playing each of them.
    `shift`: your own games adjustment (the board's GP delta). It moves the
    whole distribution, clipped to what he can play. It isn't fed into the
    model as a projection: a low ESPN projection usually means a known long
    injury, and your -10 doesn't.
    """
    projected = max(0.0, min(float(FULL), projected))
    out = max(0, min(FULL, int(out)))
    z = (projected - params.proj_mean) / params.proj_sd
    zh = (hist - params.hist_mean) / params.hist_sd if hist is not None else 0.0
    p_major = _sigmoid(params.major[0] + params.major[1] * z + params.major[2] * zh)
    n = FULL - out
    normal = _betabinom(n, _sigmoid(params.normal_mean[0] + params.normal_mean[1] * z + params.normal_mean[2] * zh),
                        params.normal_phi)
    major = _betabinom(n, _sigmoid(params.major_mean[0] + params.major_mean[1] * z), params.major_phi)
    base = [(1 - p_major) * a + p_major * b for a, b in zip(normal, major)]
    pmf = [0.0] * (FULL + 1)
    for k, p in enumerate(base):
        pmf[max(0, min(n, k + int(shift)))] += p
    return GamesRange(pmf=pmf, projected=max(0.0, min(float(FULL), projected + shift)))


# --------------------------------------------------------------------------
# Season value
# --------------------------------------------------------------------------

def _normal_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


@dataclass
class ValueRange:
    """Season value (per-game rating over 82 games, missed games at replacement) as a mixture over games."""

    parts: List["tuple[float, float, float]"]  # (probability, mean value, sd) for each games count

    def cdf(self, x: float) -> float:
        total = 0.0
        for p, mean, sd in self.parts:
            total += p * (_normal_cdf((x - mean) / sd) if sd > 0 else float(x >= mean))
        return total

    def quantile(self, q: float) -> float:
        lo = min(m - 6 * s for _, m, s in self.parts)
        hi = max(m + 6 * s for _, m, s in self.parts)
        for _ in range(60):
            mid = (lo + hi) / 2
            if self.cdf(mid) < q:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    @property
    def mean(self) -> float:
        return sum(p * m for p, m, _ in self.parts)


def value_range(rating: float, games: GamesRange, replacement: float, params: Params = PARAMS) -> ValueRange:
    """Season value when both games and the per-game rating are uncertain.

    For k games his rating is normal around `rating` + bias + slope x (k -
    projected), and his value is replacement + (rating - replacement) x k / 82.
    """
    parts = []
    for k, p in enumerate(games.pmf):
        if p < 1e-9:
            continue
        mean_rating = rating + params.rating_bias + params.rating_slope * (k - games.projected)
        sd_rating = math.sqrt(params.rating_var[0] + params.rating_var[1] / max(k, 1))
        share = k / FULL
        parts.append((p, replacement + (mean_rating - replacement) * share, sd_rating * share))
    return ValueRange(parts)


def quantiles(dist, qs: Sequence[float] = (0.1, 0.5, 0.9)) -> List[float]:
    return [dist.quantile(q) for q in qs]


def expected_value(rating: float, projected: float, replacement: float, out: int = 0, shift: int = 0,
                   hist: Optional[float] = None, params: Optional[Params] = None) -> float:
    """Mean season value: what the player is worth on average once both uncertainties are counted."""
    params = params or PARAMS
    return value_range(rating, games_range(projected, out, shift, hist, params), replacement, params).mean


# --------------------------------------------------------------------------
# Team level
# --------------------------------------------------------------------------
# A roster's season is its players' seasons drawn together: each player's
# games from his GamesRange and his per-game rating error given those games,
# independently of the others. Each draw goes through the board's lineup
# (daily starts, streamers) and is scored like the board scores a team:
# expected category wins a week against the average team. The average team
# is built with every player at the model's mean outcome, so the model's
# lower games and ratings apply to every team, not just mine.

import bisect  # noqa: E402
import random  # noqa: E402
from dataclasses import replace  # noqa: E402

from library import valuation as v  # noqa: E402


def center(row: "v.Valued") -> "tuple[int, int]":
    """(ESPN's projected games, your GP delta) behind a board row."""
    return row.exp_gp - row.gp_delta, row.gp_delta


def row_games(row: "v.Valued", params: Params = PARAMS) -> GamesRange:
    """A board row's games distribution: ESPN's projection, his past availability, moved by GP delta."""
    espn, delta = center(row)
    return games_range(espn, shift=delta, hist=row.hist, params=params)


def rating_slope(row: "v.Valued", averages: "v.Stats", shape: "v.LeagueShape") -> float:
    """Rating points per 1.0 of volume scale: turns a rating error into a stat line."""
    base = v.rate(row.proj_stats, averages, shape.rated, shape.weights or None)
    up = v.rate(v.scale(row.proj_stats, 1.1), averages, shape.rated, shape.weights or None)
    return max((up - base) / 0.1, 1.0)


def mean_row(row: "v.Valued", averages: "v.Stats", shape: "v.LeagueShape", params: Params = PARAMS) -> "v.Valued":
    """The row at the model's mean outcome: mean games, and the rating error expected at them."""
    games = row_games(row, params)
    mean_games = games.mean
    error = params.rating_bias + params.rating_slope * (mean_games - games.projected)
    factor = max(0.0, 1 + error / rating_slope(row, averages, shape))
    return replace(row, exp_gp=mean_games, proj_stats=v.scale(row.proj_stats, factor), proj_pg=row.proj_pg + error)


@dataclass
class TeamRange:
    wins: List[float]  # expected category wins a week in each draw, sorted
    half_season: float  # expected number of my players who play fewer than 41 games

    def quantile(self, q: float) -> float:
        if not self.wins:
            return 0.0
        return self.wins[min(len(self.wins) - 1, int(q * len(self.wins)))]

    @property
    def mean(self) -> float:
        return sum(self.wins) / len(self.wins) if self.wins else 0.0


def team_range(my_rows: Sequence["v.Valued"], sim: "v.LeagueSim", averages: "v.Stats", shape: "v.LeagueShape",
               draws: int = 300, seed: int = 7, params: Params = PARAMS) -> TeamRange:
    """Weekly category wins across draws of my roster's season.

    `sim` is simulate_league run on mean_row() rows: it supplies the average
    team to beat, the lineup, the fill for missed games and my open slots
    (sim.mine after my players).
    """
    rng = random.Random(seed)
    players = []
    for r in my_rows:
        games = row_games(r, params)
        cdf, total = [], 0.0
        for p in games.pmf:
            total += p
            cdf.append(total)
        players.append((r, games, cdf, rating_slope(r, averages, shape)))
    open_slots = list(sim.mine[len(my_rows):])
    cats = shape.categories
    wins = []
    for _ in range(draws):
        members = []
        for r, games, cdf, slope in players:
            g = min(FULL, bisect.bisect_left(cdf, rng.random() * cdf[-1]))
            error = rng.gauss(params.rating_bias + params.rating_slope * (g - games.projected),
                              math.sqrt(params.rating_var[0] + params.rating_var[1] / max(g, 1)))
            line = v.scale(r.proj_stats, max(0.0, 1 + error / slope))
            members.append(v.Member(v.with_fill(v.scale(line, g), g, sim.fill), r.proj_pg, r.team))
        totals = sim.lineup.totals(members + open_slots)
        ratings = v.team_ratings(totals, sim.average_team, cats, shape.reverse)
        wins.append(sum(v.win_chance(ratings.get(c, 100.0), c) for c in cats))
    wins.sort()
    half = sum(games.p_half for _, games, _, _ in players)
    return TeamRange(wins=wins, half_season=half)


# --------------------------------------------------------------------------
# ± from games played alone
# --------------------------------------------------------------------------
# One standard deviation of games (GamesRange around ESPN + GP delta) carried
# through to the board's numbers, around the board's own estimates. Value and
# a player's share of a team total are straight lines in games (his games at
# his line, the rest filled at replacement), so their ± follows directly.
# Players' games are independent, so team spreads add in quadrature.

import functools  # noqa: E402


@functools.lru_cache(maxsize=8192)
def games_sd(projected: int, shift: int = 0, hist: Optional[int] = None) -> float:
    """Standard deviation of games played for ESPN's projection (and past availability) moved by `shift`."""
    g = games_range(projected, shift=shift, hist=hist)
    mean = g.mean
    return math.sqrt(sum(p * (k - mean) ** 2 for k, p in enumerate(g.pmf)))


def row_games_sd(row: "v.Valued") -> float:
    espn, delta = center(row)
    return games_sd(int(round(espn)), int(delta), None if row.hist is None else int(round(row.hist)))


def plus_minus(value: float, zero_games: float, row: "v.Valued") -> float:
    """± of a number that runs in a straight line from `zero_games` (0 games) to `value` (his expected games)."""
    if row.exp_gp <= 0:
        return 0.0
    return abs(value - zero_games) * row_games_sd(row) / row.exp_gp


WINNING = 100.5  # a category rating the board counts as winning (within half a point is even)


@dataclass
class TeamSpread:
    categories: Dict[str, float]  # ± of each category rating
    wins: float  # ± of expected weekly category wins
    winning: float  # ± of how many categories I'm winning (better than the average team)


def team_spread(my_rows: Sequence["v.Valued"], sim: "v.LeagueSim", shape: "v.LeagueShape",
                draws: int = 2000, seed: int = 11) -> TeamSpread:
    """± of my team's category ratings, expected weekly category wins and categories won, from games alone.

    For each of my players, move his games up one standard deviation and see
    how every category rating changes (through the daily lineup, missed games
    filled at replacement). Rating and expected-wins spreads add in quadrature
    over players. Categories won is a count, so it's drawn: each player's
    games move all his categories together by a standard normal times his
    changes, and the count is taken per draw.
    """
    cats = shape.categories
    base_members = list(sim.mine)
    base = v.team_ratings(sim.lineup.totals(base_members), sim.average_team, cats, shape.reverse)
    base_wins = {c: v.win_chance(base.get(c, 100.0), c) for c in cats}
    var = {c: 0.0 for c in cats}
    wins_var = 0.0
    deltas = []  # per player: each category's rating change for +1 SD of games
    for k, r in enumerate(my_rows):
        sd = row_games_sd(r)
        # Move one SD up, or down when he's already near 82; the change is scaled back to one SD.
        games = r.exp_gp + sd if r.exp_gp + sd <= FULL else max(0.0, r.exp_gp - sd)
        step = abs(games - r.exp_gp)
        if step <= 0:
            continue
        members = list(base_members)
        members[k] = base_members[k]._replace(stats=v.member_totals(replace(r, exp_gp=games), sim.fill))
        ratings = v.team_ratings(sim.lineup.totals(members), sim.average_team, cats, shape.reverse)
        scale_ = sd / step
        d = {c: (ratings.get(c, 100.0) - base.get(c, 100.0)) * scale_ for c in cats}
        deltas.append(d)
        for c in cats:
            var[c] += d[c] ** 2
        wins_var += sum(v.win_chance(base.get(c, 100.0) + d[c], c) - base_wins[c] for c in cats) ** 2
    winning = 0.0
    if deltas:
        rng = random.Random(seed)
        counts = []
        for _ in range(draws):
            z = [rng.gauss(0, 1) for _ in deltas]
            counts.append(sum(1 for c in cats
                              if base.get(c, 100.0) + sum(zi * d[c] for zi, d in zip(z, deltas)) >= WINNING))
        mean = sum(counts) / len(counts)
        winning = math.sqrt(sum((x - mean) ** 2 for x in counts) / len(counts))
    return TeamSpread({c: math.sqrt(x) for c, x in var.items()}, math.sqrt(wins_var), winning)
