"""Games-played range and season-value range (docs/GAMES_RANGE_PLAN.md).

ESPN projects one number for games played; what actually happens is wide and
skewed. A season is either normal (rest days, short injuries) or includes a
major absence (40+ team games in a row missed). Each part is a beta-binomial
over 82 games, and the chance of a major absence falls as ESPN's projection
rises. Fitted by history/games_model.py on 1,403 player-seasons (2018-19 to
2025-26, leaving out 2022-23's mid-season projection); held out one season at
a time, 81% of actual games fell inside the 80% range.

Age, height, weight, BMI, experience, position, a new team and the team's
record the season before added nothing beyond ESPN's projection, and past
availability only a little (not enough to pass), so the only input is the
projection; the board's GP delta shifts the result.

Season value also depends on the per-game rating, which misses by about 9
points either way, and misses low when games are missed:
rating error = bias + slope x (games - projected games) + noise, with the
noise larger over fewer games. value_range() combines both.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence

FULL = 82
HALF = 41  # "loses half the season": fewer games than this


@dataclass(frozen=True)
class Params:
    proj_mean: float = 70.86  # ESPN projected games (82-game basis) of the players it was fitted on
    proj_sd: float = 8.125
    major: tuple = (-2.7226, -0.7570)  # logit P(major absence) = a0 + a1 z, z = standardized projection
    normal_mean: tuple = (1.2618, 0.4399)  # logit mean share of games in a normal season
    normal_phi: float = 5.532  # its concentration (higher = tighter)
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


def games_range(projected: float, out: int = 0, shift: int = 0, params: Params = PARAMS) -> GamesRange:
    """Distribution of games played for ESPN's projection, on 82 games.

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
    p_major = _sigmoid(params.major[0] + params.major[1] * z)
    n = FULL - out
    normal = _betabinom(n, _sigmoid(params.normal_mean[0] + params.normal_mean[1] * z), params.normal_phi)
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
                   params: Optional[Params] = None) -> float:
    """Mean season value: what the player is worth on average once both uncertainties are counted."""
    params = params or PARAMS
    return value_range(rating, games_range(projected, out, shift, params), replacement, params).mean
