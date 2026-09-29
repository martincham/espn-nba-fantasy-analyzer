"""The fantasy playoffs: when they land, and the NBA schedule over just those weeks.

Pure, like valuation.py. ESPN numbers fantasy days (scoring periods) from
opening night. Its matchup weeks run Monday to Sunday, except the first, which
runs from opening night to the first Sunday, and the week of the All-Star break,
which is merged with the next into one two-week matchup. (Checked against
2025-26: every matchup's days matched.) The league's settings then say which
matchup periods are the playoffs and which weeks each one covers.

Before the season, ESPN leaves NBA Cup knockout games off the schedule, so a
week in December can look empty; the All-Star break is found in February.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

DEFAULT_ROUNDS = ((1, 2), (3, 4))  # without the league's settings: the last 4 weeks, as two 2-week rounds
LIGHT_DAY = 0.5  # a light day: fewer than this share of NBA teams play, so a game there fits a lineup easily


@dataclass
class Round:
    period: int  # ESPN matchup period
    weeks: List[int]  # its matchup weeks, numbered from 1
    first: int  # its first and last day (scoring periods)
    last: int


@dataclass
class Calendar:
    weeks: List[Tuple[int, int]]  # each matchup week's (first day, last day); week 1 first
    rounds: List[Round]  # the playoff rounds, in order
    playoff_teams: int
    opening: Optional[date]  # the date of day 1
    known: bool  # False: the league's playoff settings are unknown, so the rounds are DEFAULT_ROUNDS

    def date(self, day: int) -> Optional[date]:
        return self.opening + timedelta(days=day - 1) if self.opening else None

    def week_of(self) -> Dict[int, int]:
        """Each day's matchup week, numbered from 0 (for valuation.Schedule)."""
        return {d: w for w, (a, b) in enumerate(self.weeks) for d in range(a, b + 1)}

    @property
    def playoff_weeks(self) -> List[int]:
        return [w for r in self.rounds for w in r.weeks]

    @property
    def playoff_days(self) -> List[int]:
        return [d for r in self.rounds for d in range(r.first, r.last + 1)]


def matchup_weeks(game_days: Iterable[int], opening: Optional[date], count: Optional[int] = None) -> List[Tuple[int, int]]:
    """ESPN's matchup weeks as (first day, last day), from the days with games.

    Without an opening date, weeks are 7-day blocks from the first day. With
    `count` (the league's number of matchup weeks) and more weeks than that, the
    longest stretch without games (the All-Star break: in February, when the
    dates are known) joins its week to the next.
    """
    days = sorted(set(game_days))
    if not days:
        return []
    first, last = days[0], days[-1]
    if opening is None:
        end = first + 6
    else:
        end = first + 6 - (opening + timedelta(days=first - 1)).weekday()  # the first Sunday
    weeks = [(first, min(end, last))]
    while weeks[-1][1] < last:
        start = weeks[-1][1] + 1
        weeks.append((start, min(start + 6, last)))
    if count:
        playing = set(days)
        gaps: List[Tuple[int, int]] = []  # (length, first day) of each stretch without games
        d = first
        while d <= last:
            if d in playing:
                d += 1
                continue
            start = d
            while d <= last and d not in playing:
                d += 1
            gaps.append((d - start, start))
        if opening is not None:
            gaps = [g for g in gaps if (opening + timedelta(days=g[1] - 1)).month == 2] or gaps
        for _, start in sorted(gaps, key=lambda g: (-g[0], g[1])):
            if len(weeks) <= count:
                break
            i = next(k for k, (a, b) in enumerate(weeks) if a <= start <= b)
            if i + 1 < len(weeks):
                weeks[i:i + 2] = [(weeks[i][0], weeks[i + 1][1])]
    return weeks


def calendar(
    team_days: Dict[str, Sequence[int]],
    opening: Optional[date],
    matchup_count: int = 0,
    periods: Optional[Dict[int, List[int]]] = None,
    playoff_teams: int = 0,
) -> Calendar:
    """The season's matchup weeks and playoff rounds.

    `matchup_count` and `periods` are the league's settings: regular-season
    matchup periods, and each period's matchup weeks. Periods after the
    regular season are the playoff rounds.
    """
    periods = periods or {}
    count = max((w for ws in periods.values() for w in ws), default=0)
    weeks = matchup_weeks((d for ds in team_days.values() for d in ds), opening, count or None)
    rounds: List[Round] = []
    if matchup_count and weeks:
        for p in sorted(periods):
            ws = periods[p]
            if p > matchup_count and ws and all(1 <= w <= len(weeks) for w in ws):
                rounds.append(Round(p, list(ws), weeks[ws[0] - 1][0], weeks[ws[-1] - 1][1]))
    known = bool(rounds)
    if not known and len(weeks) >= 4:
        n = len(weeks)
        for k, ws in enumerate(DEFAULT_ROUNDS):
            ws = [n - 4 + w for w in ws]
            rounds.append(Round(n - 4 + k + 1, ws, weeks[ws[0] - 1][0], weeks[ws[-1] - 1][1]))
    return Calendar(weeks, rounds, playoff_teams or 4, opening, known)


@dataclass
class TeamPlayoffs:
    """One NBA team's playoff schedule."""

    team: str
    weeks: List[int]  # games in each playoff week
    light: int  # games on light days (see LIGHT_DAY)

    @property
    def games(self) -> int:
        return sum(self.weeks)


def day_counts(team_days: Dict[str, Sequence[int]]) -> Dict[int, int]:
    """NBA teams playing on each day."""
    counts: Dict[int, int] = {}
    for ds in team_days.values():
        for d in ds:
            counts[d] = counts.get(d, 0) + 1
    return counts


def team_playoffs(team_days: Dict[str, Sequence[int]], cal: Calendar) -> List[TeamPlayoffs]:
    """Every NBA team's games in each playoff week, most games first."""
    counts = day_counts(team_days)
    teams = len(team_days) or 1
    spans = [cal.weeks[w - 1] for w in cal.playoff_weeks]
    out = []
    for team, ds in team_days.items():
        weeks = [sum(1 for d in ds if a <= d <= b) for a, b in spans]
        light = sum(1 for d in ds if any(a <= d <= b for a, b in spans) and counts[d] < LIGHT_DAY * teams)
        out.append(TeamPlayoffs(team, weeks, light))
    out.sort(key=lambda t: (-t.games, -t.light, t.team))
    return out


def weekly_games(team_days: Dict[str, Sequence[int]], cal: Calendar) -> List[Dict[str, float]]:
    """Per playoff week: its first and last day, NBA games, and the teams playing each day."""
    counts = day_counts(team_days)
    out = []
    for w in cal.playoff_weeks:
        a, b = cal.weeks[w - 1]
        per_day = [counts.get(d, 0) for d in range(a, b + 1)]
        out.append({"week": w, "first": a, "last": b, "games": sum(per_day) / 2, "days": per_day})
    return out
