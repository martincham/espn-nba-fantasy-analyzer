"""Draft board state and calculations behind the GUI's JSON API.

Holds the cached ESPN pool, your edits (Δ, expected games, notes, picks and
roster slots) and turns them into one JSON snapshot for the browser. All
math runs here, so the frontend only renders.
"""

from __future__ import annotations

import copy
import functools
import json
import os
import threading
import time
import uuid
from dataclasses import replace
from datetime import date
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

from library import availability, draft, planner, playoffs, roster, valuation
from library.valuation import Adjustment, LeagueShape

DEFAULT_SETTINGS = {
    "leagueId": None,
    "SWID": None,
    "espn_s2": None,
    "ignoredStats": ["FTM", "FTA", "FGA", "FGM", "GP", "MIN", "TO"],
    "rosterPositions": ["PG", "F", "F", "SG/SF", "SG/SF", "C", "UT"],
    "teamSize": 12,
}
MINE, TAKEN = "mine", "taken"
MAX_DELTA = 60  # rating points
MARKET_SCALE_RANGE = (0.5, 3.0)
DEFAULT_REPLACEMENT = 95  # per-game rating of a top free agent, who fills a hurt player's games
# Percent of a player's missed games that actually get filled, measured on this league's 2024-25 and
# 2025-26 box scores (history/games_model.py fill): 53% of short absences, 69% of whole weeks out.
DEFAULT_FILL_RATE = 60
MAX_REPLACEMENT = 150
DEFAULT_CORE = 7  # players per team worth paying for; the rest are $1 streamers
# Roster spots left out of team totals. The draft counts every player you roster;
# settings.txt's ignorePlayers is for the in-season spreadsheet, not the Draft Room.
DEFAULT_IGNORE = 0
# Draft Room settings saved in draftState.json. None means "use the default"
# (settings.txt, the league on ESPN, the computed price scale, or the constants above).
DEFAULT_FADE = (110, 140)  # team category rating where extra strength starts to stop helping, and stops
DEFAULT_ROOM_SETTINGS = {
    "marketScale": None, "rated": None, "ignorePlayers": None, "replacement": None, "fillRate": None, "core": None,
    "fadeStart": None, "fadeEnd": None, "punt": [], "fitModel": None,
    "projLine": None, "catWeights": None, "pricing": None, "planObjective": None, "planFocus": None,
}
FIT_MODELS = ("wins", "fade")  # weekly win chances (default), or the simple 110-140 fade
# Rating model choices; the first of each is the default, backtested in docs/BACKTEST_PLAN.md.
PROJ_LINES = ("espn", "last")  # ESPN's per-game projection, or last season's per-minute rates
CAT_WEIGHTS = ("league", "equal")  # valuation.CATEGORY_WEIGHTS, or every category equal
# How Ours turns value into dollars. Default (the user's call, 2026-09-27): worth, with no cap. The core
# players split the league's money in proportion to their value above the last of them. Past prices
# belong in Cost, the market side of Edge. The other option prices by rank on this league's price curve,
# which caps Ours at what the room has paid for its top player (about $80).
PRICING_MODELS = ("formula", "curve")
PLAN_OBJECTIVES = planner.OBJECTIVES  # what the Plan tab maximises: expected wins (default) or a bad season's wins
# The weeks a plan wins: the whole season (default), the season with the playoff weeks counting as much as
# the regular season, or only the fantasy playoffs.
PLAN_FOCUSES = ("season", "both", "playoffs")
MAX_SAVED = 10  # saved rosters (the Saved tab)
MAX_NAME = 40


# Environment variables that override settings.txt, so a hosted copy keeps the ESPN cookies in its secrets.
SETTINGS_ENV = {"ESPN_LEAGUE_ID": "leagueId", "ESPN_S2": "espn_s2", "ESPN_SWID": "SWID", "DRAFT_SEASON": "draftSeason"}


def load_settings(path: str) -> Dict[str, Any]:
    """Read settings.txt without creating or modifying it, then apply SETTINGS_ENV."""
    settings = dict(DEFAULT_SETTINGS)
    try:
        with open(path) as f:
            settings.update(json.load(f))
    except FileNotFoundError:
        pass
    settings.update({key: os.environ[env] for env, key in SETTINGS_ENV.items() if os.environ.get(env)})
    return settings


def season_label(season: int) -> str:
    return f"{season - 1}-{season % 100:02d}"


def _r(x: Optional[float], digits: int = 1) -> Optional[float]:
    return None if x is None else round(x, digits)


@functools.lru_cache(maxsize=8192)
def _ranges(espn_gp: int, gp_delta: int, hist: Optional[int], proj_pg: float, replacement: float) -> Tuple[Tuple[int, int, int], float, Tuple[float, float, float], float]:
    """Games (p10, p50, p90), P(under 41 games), season value (p10, p50, p90) and mean value.

    Cached: a player's inputs change only when you adjust him (see library/availability.py).
    """
    games = availability.games_range(espn_gp, shift=gp_delta, hist=hist)
    value = availability.value_range(proj_pg, games, replacement)
    return (tuple(availability.quantiles(games)), games.p_half, tuple(availability.quantiles(value)), value.mean)


class DraftBoard:
    def __init__(self, settings_path: str, pool_path: str, state_path: str):
        self.settings_path = settings_path
        self.pool_path = pool_path
        base, ext = os.path.splitext(pool_path)
        self.past_path = base + "History" + ext  # players' past seasons, for the games-played model
        self.state_path = state_path
        self.lock = threading.RLock()
        self.settings: Dict[str, Any] = {}
        self.league: Optional[draft.LeagueInfo] = None
        self.players: List[draft.DraftPlayer] = []
        self.team_days: Dict[str, List[int]] = {}  # NBA schedule: each team's game days
        self.schedule: Optional[valuation.Schedule] = None
        self.calendar: Optional[playoffs.Calendar] = None  # matchup weeks and playoff rounds
        self.focus_schedules: Dict[str, Optional[valuation.Schedule]] = {}  # the schedule each plan focus counts
        self.by_id: Dict[int, draft.DraftPlayer] = {}
        self.fetched_at = 0.0
        # Goes up on every change, so open pages can tell they're out of date. It starts
        # from the clock so it keeps going up across restarts.
        self.rev = time.time_ns() // 1_000_000
        self.shape = LeagueShape()
        self.slots: List[str] = []
        self.baseline: Optional[valuation.Baseline] = None
        self.warnings: List[str] = []
        self.market_scale = 1.0
        self.auto_market_scale = 1.0
        self.fade = valuation.Fade(*DEFAULT_FADE)
        self.punt: List[str] = []
        self.fit_model = FIT_MODELS[0]
        self.proj_line, self.cat_weights, self.pricing_model = PROJ_LINES[0], CAT_WEIGHTS[0], PRICING_MODELS[0]
        self.plan_objective = PLAN_OBJECTIVES[0]
        self.plan_focus = PLAN_FOCUSES[0]
        self.plan: Optional[Dict[str, Any]] = None  # the Plan tab's last result (not saved)
        # (inputs, recommended plan, plan shown) behind self.plan, so players can be switched in
        self._plan_work: Optional[Tuple[Dict[str, Any], planner.Plan, planner.Plan]] = None
        self._plan_seconds: Dict[str, float] = {}  # how long the last plan took, per objective (for the wait message)
        self._team_range: "tuple[str, Optional[Dict[str, Any]]]" = ("", None)  # (inputs, result) of the last team range
        self._playoffs: "tuple[str, Optional[Dict[str, Any]]]" = ("", None)  # (inputs, result) of the last Playoffs tab
        self.default_rated: List[str] = []
        self.state = self._empty_state()

    # ------------------------------------------------------------------ load

    @staticmethod
    def _empty_state() -> Dict[str, Any]:
        return {"adjustments": {}, "picks": {}, "filled": [], "settings": dict(DEFAULT_ROOM_SETTINGS), "avoid": [], "saved": []}

    def load(self, refresh: bool = False) -> None:
        with self.lock:
            warnings, self.warnings = self.warnings, []
            try:
                self._load(refresh)
            except Exception:  # a failed refresh leaves the board as it was
                self.warnings = warnings
                raise

    def _load(self, refresh: bool) -> None:
        self.settings = load_settings(self.settings_path)
        cached = None if refresh else draft.load_pool(self.pool_path)
        if cached:
            self.league, self.players, team_days, self.fetched_at, has_birth_dates = cached
            changed = False
            if team_days is None:  # cached before schedules were stored
                team_days, self.league.opening = self._fetch_schedule(self.league.season)
                changed = True
            self.team_days = team_days
            if self.league.matchup_weeks is None or self.league.opening is None:  # cached before the playoff calendar
                changed = self._add_calendar() or changed
            if not has_birth_dates:  # cached before birth dates were stored
                has_birth_dates = self._add_birth_dates(self.players)
                changed = changed or has_birth_dates
            if changed:
                draft.save_pool(self.pool_path, self.league, self.players, self.team_days, self.fetched_at, has_birth_dates)
        else:
            self._fetch()
        self._load_past(refresh)
        self._prepare()
        self._load_state()
        self._apply_settings()

    def _fetch(self) -> None:
        """Download a new pool. Nothing on the board changes unless every step succeeds."""
        season = int(self.settings.get("draftSeason") or draft.current_season())
        league_id = self.settings.get("leagueId")
        s2, swid = self.settings.get("espn_s2"), self.settings.get("SWID")
        league = None
        if league_id:
            try:
                league = draft.fetch_league(int(league_id), season, s2, swid)
            except draft.EspnError as ex:
                self.warnings.append(f"Using default league settings: {ex}")
        league = league or draft.LeagueInfo(league_id=None, season=season)
        players = draft.fetch_pool(season, league.league_id, s2, swid, rank_type=league.rank_type)
        team_days, league.opening = self._fetch_schedule(season)
        if league.matchup_weeks is None:  # the default league: no matchup settings to look up
            league.matchup_weeks = {}
        # Birth dates never change: keep the ones we have and look up only new players.
        known = {p.id: p.birth_date for p in self.players if p.birth_date}
        for p in players:
            p.birth_date = known.get(p.id)
        has_birth_dates = self._add_birth_dates(players)
        fetched_at = time.time()
        draft.save_pool(self.pool_path, league, players, team_days, fetched_at, has_birth_dates)
        self.league, self.players, self.team_days, self.fetched_at = league, players, team_days, fetched_at

    def _add_birth_dates(self, players: List[draft.DraftPlayer]) -> bool:
        """Fill in missing birth dates. False if ESPN couldn't be reached."""
        missing = [p for p in players if not p.birth_date]
        if not missing:
            return True
        try:
            dates = draft.fetch_birth_dates([p.id for p in missing])
        except draft.EspnError as ex:
            self.warnings.append(f"No ages: {ex}")
            return False
        for p in missing:
            p.birth_date = dates.get(p.id)
        return True

    def _load_past(self, refresh: bool = False) -> None:
        """Each player's past availability (library/availability.history_availability), cached next to the pool."""
        season = self.league.season
        past = None if refresh else draft.load_past(self.past_path, season)
        if past is None:
            try:
                past = draft.fetch_past(season, [p.id for p in self.players])
                draft.save_past(self.past_path, season, past)
            except draft.EspnError as ex:
                self.warnings.append(f"No past seasons for the games-played model: {ex}")
                past = {}
        for p in self.players:
            p.hist_avail = availability.history_availability(past.get(p.id, []), season)

    def _fetch_schedule(self, season: int) -> Tuple[Dict[str, List[int]], str]:
        """Each NBA team's game days, and the date of day 1 ("" if unknown)."""
        try:
            return draft.fetch_schedule(season)
        except draft.EspnError as ex:
            self.warnings.append(f"No NBA schedule, so Fit ignores it: {ex}")
            return {}, ""

    def _add_calendar(self) -> bool:
        """Look up the matchup settings and opening date for a pool cached before they were stored.

        False if ESPN couldn't be reached: the Playoffs tab then assumes the last four weeks.
        """
        league, s = self.league, self.settings
        try:
            if league.matchup_weeks is None:
                found = draft.fetch_league(int(league.league_id), league.season, s.get("espn_s2"), s.get("SWID")) if league.league_id else None
                league.matchup_count = found.matchup_count if found else 0
                league.matchup_weeks = found.matchup_weeks if found else {}
                league.playoff_teams = found.playoff_teams if found else 0
            if league.opening is None:
                team_days, league.opening = draft.fetch_schedule(league.season)
                self.team_days = team_days or self.team_days
        except draft.EspnError as ex:
            self.warnings.append(f"No playoff calendar from ESPN, so the Playoffs tab assumes the last four weeks: {ex}")
            return False
        return True

    def _prepare(self) -> None:
        league, s = self.league, self.settings
        self.by_id = {p.id: p for p in self.players}
        if league.slot_counts:
            self.slots = roster.slots_from_counts(league.slot_counts)
        else:
            self.slots = roster.slots_from_positions(s["rosterPositions"], int(s["teamSize"]))
        ignored = set(s.get("ignoredStats") or [])
        self.default_rated = [c for c in league.categories if c not in ignored]
        opening = date.fromisoformat(league.opening) if league.opening else None
        self.calendar = None
        if self.team_days:
            self.calendar = playoffs.calendar(self.team_days, opening, league.matchup_count, league.matchup_weeks or {},
                                              league.playoff_teams)
        # Real matchup weeks when the dates are known (streaming room is counted per week).
        week_of = self.calendar.week_of() if self.calendar and opening else None
        self.schedule = valuation.Schedule(self.team_days, week_of) if self.team_days else None
        self.focus_schedules = self._focus_schedules()
        self.shape = LeagueShape(
            teams=league.teams,
            budget=league.budget,
            roster_size=len(self.slots),
            ignore_players=DEFAULT_IGNORE,
            categories=list(league.categories),
            reverse=list(league.reverse),
            rated=list(self.default_rated),
            starters=sum(1 for slot in self.slots if slot != roster.BENCH),
        )
        if league.draft_type != "AUCTION":
            self.warnings.append(f"This league's draft type is {league.draft_type.lower()}; values are still shown in auction dollars.")
        # ESPN's average prices come from leagues of every size, so they add up
        # to less than this league spends. Scale them to this league's budget.
        top_market = sum(sorted((p.avg_paid for p in self.players), reverse=True)[: self.shape.pool_size])
        self.auto_market_scale = (self.shape.teams * self.shape.budget) / top_market if top_market > 0 else 1.0
        self.market_scale = self.auto_market_scale  # until saved settings are applied

    def _focus_schedules(self) -> Dict[str, Optional[valuation.Schedule]]:
        """The schedule behind each plan focus (PLAN_FOCUSES). Without playoff rounds, every focus is the season."""
        sched, cal = self.schedule, self.calendar
        out: Dict[str, Optional[valuation.Schedule]] = {f: sched for f in PLAN_FOCUSES}
        if sched is None or cal is None or not cal.rounds:
            return out
        days = set(cal.playoff_days)
        out["playoffs"] = sched.focus(days)
        # "both": the playoff weeks count as much as the regular season before them.
        start = min(days)
        regular = sum(1 for d in sched.day_ids if d < start)
        in_playoffs = sum(1 for d in sched.day_ids if d in days)
        out["both"] = sched.focus(days, repeat=max(1, round(regular / in_playoffs)) if in_playoffs else 1, rest=True)
        return out

    def _apply_settings(self) -> None:
        """Apply the Draft Room settings on top of the league's defaults."""
        room = self.state["settings"]
        self.shape.rated = list(room["rated"]) if room["rated"] is not None else list(self.default_rated)
        self.shape.ignore_players = room["ignorePlayers"] if room["ignorePlayers"] is not None else DEFAULT_IGNORE
        self.market_scale = room["marketScale"] if room["marketScale"] is not None else self.auto_market_scale
        self.shape.replacement = float(room["replacement"] if room["replacement"] is not None else DEFAULT_REPLACEMENT)
        self.shape.fill_rate = (room.get("fillRate") if room.get("fillRate") is not None else DEFAULT_FILL_RATE) / 100
        self.shape.core = room["core"] if room["core"] is not None else min(DEFAULT_CORE, len(self.slots))
        start = room["fadeStart"] if room["fadeStart"] is not None else DEFAULT_FADE[0]
        end = room["fadeEnd"] if room["fadeEnd"] is not None else DEFAULT_FADE[1]
        self.fade = valuation.Fade(start=start, end=max(end, start + 1))
        self.punt = list(room["punt"])
        self.fit_model = room["fitModel"] or FIT_MODELS[0]
        self.proj_line = room["projLine"] or PROJ_LINES[0]
        self.cat_weights = room["catWeights"] or CAT_WEIGHTS[0]
        self.pricing_model = room["pricing"] or PRICING_MODELS[0]
        self.plan_objective = room.get("planObjective") or PLAN_OBJECTIVES[0]
        self.plan_focus = room.get("planFocus") or PLAN_FOCUSES[0]
        for p in self.players:
            p.line_source = self.proj_line
        self.shape.weights = dict(valuation.CATEGORY_WEIGHTS) if self.cat_weights == "league" else {}
        self.shape.price_curve = list(valuation.PRICE_CURVE) if self.pricing_model == "curve" else []
        # The pool and its averages depend on which categories are rated.
        history = [p for p in self.players if not p.base_is_projection]
        self.baseline = valuation.compute_baseline(history, self.shape)

    # ----------------------------------------------------------------- state

    def _load_state(self) -> None:
        try:
            with open(self.state_path) as f:
                saved = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            saved = {}
        state = self._empty_state()
        state.update({k: saved[k] for k in state if k in saved})
        self.state = self._clean(state)
        self._save()

    def _clean(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Drop unknown players and fit the roster to the league's slots."""
        known = self.by_id
        state["adjustments"] = {k: v for k, v in state.get("adjustments", {}).items() if int(k) in known}
        for k, adj in state["adjustments"].items():
            # Older saves stored expected games as a total; keep it as games over ESPN's projection.
            if "expGp" in adj:
                gp = adj.pop("expGp")
                if gp is not None and not adj.get("gpDelta"):
                    adj["gpDelta"] = self._clamp_gp_delta(int(k), gp - known[int(k)].default_exp_gp)
        state["picks"] = {k: v for k, v in state.get("picks", {}).items() if int(k) in known}
        state["avoid"] = sorted({int(x) for x in state.get("avoid") or [] if int(x) in known})  # left out of the plan
        filled = [int(x) if x is not None and int(x) in known else None for x in state.get("filled", [])]
        if len(filled) != len(self.slots):
            mine = [x for x in filled if x is not None]
            filled = [None] * len(self.slots)
            for pid in mine:
                i = roster.auto_slot(self.slots, filled, self.by_id[pid].eligible_slots)
                if i >= 0:
                    filled[i] = pid
        state["filled"] = filled
        # Every rostered player is a "mine" pick, and every "mine" pick is rostered.
        for pid in filled:
            if pid is not None:
                state["picks"].setdefault(str(pid), {"status": MINE, "price": self._default_price(pid)})
                state["picks"][str(pid)]["status"] = MINE
        state["picks"] = {
            k: v for k, v in state["picks"].items() if v.get("status") != MINE or int(k) in filled
        }
        for pick in state["picks"].values():
            if pick.get("status") == TAKEN:
                pick.pop("price", None)  # only that they're gone matters, not what they cost
        state["settings"] = self._clean_settings(state.get("settings") or {})
        state["saved"] = self._clean_saved(state.get("saved") or [])
        return state

    def _clean_saved(self, saved: List[Any]) -> List[Dict[str, Any]]:
        """Saved rosters: known players only, at most MAX_SAVED. A bad entry is dropped."""
        out = []
        for entry in saved:
            try:
                players = [
                    {"id": int(p["id"]), "price": self._price(p.get("price"), None), "slot": None if p.get("slot") is None else int(p["slot"])}
                    for p in entry.get("players") or []
                    if int(p["id"]) in self.by_id
                ]
                out.append({"id": str(entry["id"]), "name": str(entry.get("name") or "Roster")[:MAX_NAME],
                            "savedAt": float(entry.get("savedAt") or 0), "players": players})
            except (KeyError, TypeError, ValueError, AttributeError):
                continue
        return out[:MAX_SAVED]

    def _clean_settings(self, saved: Dict[str, Any]) -> Dict[str, Any]:
        room = dict(DEFAULT_ROOM_SETTINGS)
        cats = self.league.categories if self.league else []
        try:
            if saved.get("marketScale") is not None:
                lo, hi = MARKET_SCALE_RANGE
                room["marketScale"] = round(min(hi, max(lo, float(saved["marketScale"]))), 3)
            if saved.get("rated") is not None:
                rated = [c for c in cats if c in set(saved["rated"])]
                room["rated"] = rated if rated else None  # at least one category must count
            if saved.get("ignorePlayers") is not None:
                room["ignorePlayers"] = max(0, min(len(self.slots) - 1, int(saved["ignorePlayers"])))
            if saved.get("replacement") is not None:
                room["replacement"] = max(0, min(MAX_REPLACEMENT, int(round(float(saved["replacement"])))))
            if saved.get("fillRate") is not None:
                room["fillRate"] = max(0, min(100, int(round(float(saved["fillRate"])))))
            if saved.get("core") is not None:
                room["core"] = max(1, min(len(self.slots), int(saved["core"])))
            if saved.get("fadeStart") is not None:
                room["fadeStart"] = max(80, min(200, int(round(float(saved["fadeStart"])))))
            if saved.get("fadeEnd") is not None:
                room["fadeEnd"] = max(80, min(300, int(round(float(saved["fadeEnd"])))))
            if saved.get("fitModel") in FIT_MODELS:
                room["fitModel"] = saved["fitModel"]
            if saved.get("projLine") in PROJ_LINES:
                room["projLine"] = saved["projLine"]
            if saved.get("catWeights") in CAT_WEIGHTS:
                room["catWeights"] = saved["catWeights"]
            if saved.get("pricing") in PRICING_MODELS:
                room["pricing"] = saved["pricing"]
            if saved.get("planObjective") in PLAN_OBJECTIVES:
                room["planObjective"] = saved["planObjective"]
            if saved.get("planFocus") in PLAN_FOCUSES:
                room["planFocus"] = saved["planFocus"]
            # Punting is always your choice: only categories you tick are punted.
            room["punt"] = [c for c in cats if c in set(saved.get("punt") or [])]
        except (TypeError, ValueError):
            pass  # a bad value keeps its default
        return room

    def _touch(self) -> None:
        self.rev = max(self.rev + 1, time.time_ns() // 1_000_000)

    def _save(self) -> None:
        self._touch()
        tmp = self.state_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.state, f, indent=1)
        os.replace(tmp, self.state_path)

    def _adjustments(self) -> Dict[int, Adjustment]:
        return {
            int(k): Adjustment(
                delta=float(v.get("delta") or 0), gp_delta=int(v.get("gpDelta") or 0), exp_min=v.get("expMin"), note=v.get("note") or ""
            )
            for k, v in self.state["adjustments"].items()
        }

    # ------------------------------------------------------------ operations

    def _clamp_gp_delta(self, player_id: int, gp_delta: float) -> int:
        """Keep expected games (ESPN's projection + Δ) between 0 and a full season."""
        base = self.by_id[player_id].default_exp_gp
        return max(-base, min(draft.MAX_GP - base, int(round(float(gp_delta)))))

    def adjust(self, player_id: int, **fields: Any) -> None:
        """Set delta, gpDelta (games over ESPN's projection), expMin, cost (None resets either) and/or note."""
        with self.lock:
            if player_id not in self.by_id:
                raise ValueError("Unknown player.")
            adj = dict(self.state["adjustments"].get(str(player_id), {}))
            if "delta" in fields:
                adj["delta"] = max(-MAX_DELTA, min(MAX_DELTA, round(float(fields["delta"] or 0))))
            if "gpDelta" in fields:
                adj["gpDelta"] = self._clamp_gp_delta(player_id, fields["gpDelta"] or 0)
            if "expMin" in fields:
                mins = fields["expMin"]
                adj["expMin"] = None if mins is None else max(0.0, min(float(draft.MAX_MIN), round(float(mins) * 2) / 2))
            if "cost" in fields:
                cost = fields["cost"]
                adj["cost"] = None if cost is None else max(0, min(self.shape.budget, int(round(float(cost)))))
            if "note" in fields:
                adj["note"] = str(fields["note"] or "")[:1000]
            if (not adj.get("delta") and not adj.get("gpDelta") and adj.get("expMin") is None
                    and adj.get("cost") is None and not adj.get("note")):
                self.state["adjustments"].pop(str(player_id), None)
            else:
                self.state["adjustments"][str(player_id)] = adj
            self._save()

    def update_settings(self, **fields: Any) -> None:
        """Change Draft Room settings. A None value goes back to the default."""
        with self.lock:
            merged = dict(self.state["settings"])
            merged.update({k: v for k, v in fields.items() if k in DEFAULT_ROOM_SETTINGS})
            self.state["settings"] = self._clean_settings(merged)
            self._apply_settings()
            self._save()

    def reset_draft(self) -> None:
        """Forget every pick: taken players come back and my roster empties."""
        with self.lock:
            self.state["picks"] = {}
            self.state["filled"] = [None] * len(self.slots)
            self._save()

    def reset_adjustments(self) -> None:
        with self.lock:
            # Notes and my own prices are kept; Δ, games and minutes are cleared.
            kept = {k: {f: v[f] for f in ("note", "cost") if v.get(f) not in (None, "")} for k, v in self.state["adjustments"].items()}
            self.state["adjustments"] = {k: v for k, v in kept.items() if v}
            self._save()

    def _names(self) -> Dict[int, str]:
        return {pid: p.name for pid, p in self.by_id.items()}

    def _eligibility(self) -> Dict[int, List[str]]:
        return {pid: p.eligible_slots for pid, p in self.by_id.items()}

    def pick(self, player_id: int, status: Optional[str], price: Optional[float] = None) -> Optional[str]:
        """Mark a player mine (auto-slotted), taken, or undrafted (status None).

        Mine: without a price, keeps the existing one or defaults to the average
        paid. Taken players have no price: only that they're gone matters.
        """
        with self.lock:
            if player_id not in self.by_id:
                return "Unknown player."
            key = str(player_id)
            filled = self.state["filled"]
            if status == MINE:
                if player_id not in filled:
                    i = roster.auto_slot(self.slots, filled, self.by_id[player_id].eligible_slots)
                    if i < 0:
                        return "Your roster is full. Remove someone on My Team first."
                    filled[i] = player_id
            else:
                self.state["filled"] = roster.remove(filled, player_id)
            if status == MINE:
                old = self.state["picks"].get(key, {})
                self.state["picks"][key] = {"status": MINE, "price": self._price(price, old.get("price") or self._default_price(player_id))}
            elif status == TAKEN:
                self.state["picks"][key] = {"status": TAKEN}
            else:
                self.state["picks"].pop(key, None)
            self._save()
            return None

    def set_avoid(self, player_id: int, avoid: bool = True) -> Optional[str]:
        """Leave a player out of the Plan tab's recommendations (or let him back in)."""
        with self.lock:
            if player_id not in self.by_id:
                return "Unknown player."
            avoided = set(self.state["avoid"])
            avoided.add(player_id) if avoid else avoided.discard(player_id)
            self.state["avoid"] = sorted(avoided)
            self._save()
            return None

    def _default_price(self, player_id: int) -> int:
        """A player's cost when no price is given: the average paid in ESPN auctions."""
        player = self.by_id.get(player_id)
        return max(1, int(round(self._market(player)))) if player else 1

    def _market(self, player: draft.DraftPlayer) -> float:
        """What a player should cost: my own price if I set one, else ESPN's scaled average."""
        own = (self.state["adjustments"].get(str(player.id)) or {}).get("cost")
        return float(own) if own is not None else self._espn_market(player)

    def _espn_market(self, player: draft.DraftPlayer) -> float:
        """ESPN's average price, scaled to this league's budget."""
        return player.avg_paid * self.market_scale

    @staticmethod
    def _price(price: Optional[float], fallback: Optional[float]) -> int:
        value = price if price is not None else fallback if fallback is not None else 1
        return max(1, int(round(float(value))))

    def set_price(self, player_id: int, price: float) -> None:
        with self.lock:
            pick = self.state["picks"].get(str(player_id))
            if pick and pick.get("status") == MINE:
                pick["price"] = self._price(price, pick.get("price"))
                self._save()

    def move(self, player_id: int, slot: int, price: Optional[float] = None) -> Optional[str]:
        """Drop a player into a roster slot (adding them to my team if needed)."""
        with self.lock:
            if player_id not in self.by_id:
                return "Unknown player."
            pick = self.state["picks"].get(str(player_id))
            if pick and pick.get("status") == TAKEN:
                return f"{self.by_id[player_id].name} is already taken."
            filled, error = roster.move(self.slots, self.state["filled"], player_id, int(slot), self._eligibility(), self._names())
            if error:
                return error
            self.state["filled"] = filled
            if not pick:
                self.state["picks"][str(player_id)] = {"status": MINE, "price": self._price(price, self._default_price(player_id))}
            self._save()
            return None

    def clear_roster(self) -> None:
        with self.lock:
            for pid in self.state["filled"]:
                if pid is not None:
                    self.state["picks"].pop(str(pid), None)
            self.state["filled"] = [None] * len(self.slots)
            self._save()

    # ---------------------------------------------------------- saved rosters

    def save_roster(self, name: Optional[str] = None) -> Optional[str]:
        """Keep a copy of my roster (players, slots and prices) on the Saved tab."""
        with self.lock:
            saved = self.state["saved"]
            if len(saved) >= MAX_SAVED:
                return f"You have {MAX_SAVED} saved rosters. Delete one first."
            players = [
                {"id": pid, "price": self._price(self.state["picks"].get(str(pid), {}).get("price"), self._default_price(pid)), "slot": i}
                for i, pid in enumerate(self.state["filled"]) if pid is not None
            ]
            if not players:
                return "Your roster is empty. Add players on the Board first."
            name = " ".join(str(name or "").split())[:MAX_NAME]
            if not name:
                used = {s["name"] for s in saved}
                name = next(f"Roster {n}" for n in range(1, MAX_SAVED + 2) if f"Roster {n}" not in used)
            saved.append({"id": uuid.uuid4().hex[:8], "name": name, "savedAt": time.time(), "players": players})
            self._save()
            return None

    def _saved(self, saved_id: str) -> Optional[Dict[str, Any]]:
        return next((s for s in self.state["saved"] if s["id"] == str(saved_id)), None)

    def load_roster(self, saved_id: str) -> Optional[str]:
        """Make a saved roster my team, in its slots at its prices. It replaces the players on my
        team now; saved players someone else has taken since are left out."""
        with self.lock:
            entry = self._saved(saved_id)
            if entry is None:
                return "That saved roster is gone. Someone may have deleted it."
            picks = self.state["picks"]
            for pid in self.state["filled"]:
                if pid is not None:
                    picks.pop(str(pid), None)
            filled: List[Optional[int]] = [None] * len(self.slots)
            wanted = [p for p in entry["players"] if picks.get(str(p["id"]), {}).get("status") != TAKEN]
            later = []
            for p in wanted:  # its own slot first, if that slot still exists and he still fits it
                i = p["slot"]
                if i is not None and 0 <= i < len(self.slots) and filled[i] is None and roster.eligible(self.slots[i], self.by_id[p["id"]].eligible_slots):
                    filled[i] = p["id"]
                else:
                    later.append(p)
            for p in later:
                i = roster.auto_slot(self.slots, filled, self.by_id[p["id"]].eligible_slots)
                if i >= 0:
                    filled[i] = p["id"]
            for p in wanted:
                if p["id"] in filled:
                    picks[str(p["id"])] = {"status": MINE, "price": p["price"]}
            self.state["filled"] = filled
            self._save()
            return None

    def delete_roster(self, saved_id: str) -> Optional[str]:
        with self.lock:
            entry = self._saved(saved_id)
            if entry is None:
                return "That saved roster is already gone."
            self.state["saved"].remove(entry)
            self._save()
            return None

    def rename_roster(self, saved_id: str, name: str) -> Optional[str]:
        with self.lock:
            entry, name = self._saved(saved_id), " ".join(str(name or "").split())[:MAX_NAME]
            if entry is None:
                return "That saved roster is gone. Someone may have deleted it."
            if name and name != entry["name"]:
                entry["name"] = name
                self._save()
            return None

    def _saved_for(self, rows, picks, taken: List[int]) -> List[Dict[str, Any]]:
        """Each saved roster scored like My Team: expected category wins a week against the average
        team, with the draft as it is now (empty spots count as replacement players)."""
        by_row = {r.id: r for r in rows}
        cats = self.shape.categories
        mine = {pid for pid in self.state["filled"] if pid is not None}
        out = []
        for entry in self.state["saved"]:
            ids = [p["id"] for p in entry["players"] if p["id"] in by_row]
            sim = valuation.simulate_league(rows, ids, [t for t in taken if t not in ids], self.shape, self.schedule)
            chances = {c: valuation.win_chance(sim.ratings.get(c, 100.0), c) for c in cats}
            out.append({
                **entry,
                "players": [{**p, "status": picks.get(p["id"], {}).get("status")} for p in entry["players"]],
                "cost": sum(p["price"] for p in entry["players"]),
                "worth": _r(sum(by_row[i].ours for i in ids), 0),
                "expectedWins": round(sum(chances.values()), 2),
                "chances": {c: round(x, 3) for c, x in chances.items()},
                "current": set(ids) == mine,
            })
        return out

    def replace_state(self, state: Dict[str, Any], rev: Optional[int] = None) -> Optional[str]:
        """Restore a previous state (used by Undo). `rev` is the board revision the
        undo belongs to: if anything changed since, restoring would lose that change."""
        with self.lock:
            if rev is not None and int(rev) != self.rev:
                return "The board changed since then, so it can't be undone. Fix it by hand."
            merged = self._empty_state()
            merged.update({k: state[k] for k in merged if k in state})
            self.state = self._clean(merged)
            self._apply_settings()
            self._save()

    # -------------------------------------------------------------- snapshot

    # ------------------------------------------------------------------ plan

    def _plan_stamp(self) -> str:
        """Everything a plan depends on; when it changes, the plan is out of date."""
        s = self.state
        return json.dumps([s["picks"], s["filled"], s["adjustments"], s["settings"], s["avoid"], self.fetched_at], sort_keys=True)

    def _plan_cost(self, p: draft.DraftPlayer, row: Optional[valuation.Valued]) -> int:
        """What a player should cost: my price, else ESPN's scaled average, else our value when ESPN has none."""
        market = self._market(p)
        if market < 0.5 and row is not None:
            market = row.ours
        return max(1, int(round(market)))

    def build_plan(self) -> Optional[str]:
        """Start searching for the recommended team in the background."""
        with self.lock:
            if self.plan and self.plan.get("status") == "building":
                return None
            rows = valuation.value_players(self.players, self.baseline, self.shape, self._adjustments())
            by_row = {r.id: r for r in rows}
            picks = {int(k): v for k, v in self.state["picks"].items()}
            mine = [pid for pid in self.state["filled"] if pid is not None]
            inputs = {
                "rows": rows,
                "shape": copy.deepcopy(self.shape),
                "schedule": self.focus_schedules.get(self.plan_focus, self.schedule),
                "costs": {p.id: self._plan_cost(p, by_row.get(p.id)) for p in self.players},
                "mine": mine,
                "taken": [pid for pid, v in picks.items() if v["status"] == TAKEN],
                "budget_left": self._me(picks, mine)["budgetLeft"],
                "punt": list(self.punt),
                "avoid": list(self.state["avoid"]),
                "objective": self.plan_objective,
                "averages": dict(self.baseline.per_game),
            }
            stamp = self._plan_stamp()
            focus = self.plan_focus
            self.plan = {"status": "building", "stamp": stamp, "started": time.time(), "focus": focus}
            self._plan_work = None
            self._touch()
        threading.Thread(target=self._run_plan, args=(inputs, stamp, focus), daemon=True).start()
        return None

    def _run_plan(self, inputs: Dict[str, Any], stamp: str, focus: str = PLAN_FOCUSES[0]) -> None:
        started = time.time()
        try:
            result = planner.plan_team(**inputs)
            payload = self._plan_payload(result, inputs["costs"]) if result else None
            done = {"status": "ready", "stamp": stamp, "seconds": round(time.time() - started, 1), "builtAt": time.time(),
                    "result": payload, "full": result is None, "focus": focus}
        except Exception as ex:  # keep the app alive; show the error on the tab
            done, result = {"status": "error", "stamp": stamp, "error": f"The plan failed: {ex}", "focus": focus}, None
        with self.lock:
            self.plan = done
            self._plan_work = (inputs, result, result) if result else None
            if done["status"] == "ready":
                self._plan_seconds[f"{inputs['objective']}/{focus}"] = done["seconds"]
            self._touch()

    def switch_plan(self, out_id: int, in_id: int) -> Optional[str]:
        """Put another player in a planned player's spot and rescore the plan."""
        with self.lock:
            if not self._plan_work or not self.plan or self.plan.get("status") != "ready":
                return "Build a plan first."
            inputs, recommended, shown = self._plan_work
            ids, costs = shown.best.ids, inputs["costs"]
            if out_id not in ids:
                return "That player isn't in the plan any more."
            if in_id not in self.by_id or in_id not in costs:
                return "Unknown player."
            if in_id in ids or in_id in inputs["mine"] or in_id in inputs["taken"]:
                return f"{self.by_id[in_id].name} can't be switched in: he's already on a team or in the plan."
            if shown.best.cost - costs[out_id] + costs[in_id] + shown.streamers > shown.budget_left:
                return f"{self.by_id[in_id].name} costs too much to fit the budget."
            plan = self.plan
        return self._rescore(plan, inputs, recommended, [in_id if i == out_id else i for i in ids])

    def use_plan(self, ids: List[int]) -> Optional[str]:
        """Show a plan with these players to buy instead (another build, or the one before an undo), rescored."""
        ids = list(dict.fromkeys(int(i) for i in ids))
        with self.lock:
            if not self._plan_work or not self.plan or self.plan.get("status") != "ready":
                return "Build a plan first."
            inputs, recommended, shown = self._plan_work
            costs = inputs["costs"]
            if not ids or any(i not in self.by_id or i not in costs for i in ids):
                return "Unknown player."
            gone = [self.by_id[i].name for i in ids if i in inputs["mine"] or i in inputs["taken"]]
            if gone:
                return f"{', '.join(gone)} can't be in the plan: already on a team."
            spots = len(shown.best.ids) + shown.streamers
            if len(ids) > spots:
                return "That's more players than you have open spots."
            if sum(costs[i] for i in ids) + spots - len(ids) > shown.budget_left:
                return "That team costs more than your budget."
            plan = self.plan
        return self._rescore(plan, inputs, recommended, ids)

    def _rescore(self, plan: Dict[str, Any], inputs: Dict[str, Any], recommended: planner.Plan, ids: List[int]) -> Optional[str]:
        if set(ids) == set(recommended.best.ids):
            result = recommended
        else:
            result = planner.score_team(**inputs, ids=ids)
            result.builds, result.searched = recommended.builds, recommended.searched  # the search behind it
        return self._show_plan(plan, inputs, recommended, result)

    def restore_plan(self) -> Optional[str]:
        """Undo every switch: back to the recommended team."""
        with self.lock:
            if not self._plan_work or not self.plan or self.plan.get("status") != "ready":
                return None
            inputs, recommended, _ = self._plan_work
            plan = self.plan
        return self._show_plan(plan, inputs, recommended, recommended)

    def _show_plan(self, plan: Dict[str, Any], inputs: Dict[str, Any], recommended: planner.Plan, result: planner.Plan) -> Optional[str]:
        payload = self._plan_payload(result, inputs["costs"], recommended)
        with self.lock:
            if self.plan is not plan:
                return "The plan was rebuilt in the meantime."
            self.plan = {**plan, "result": payload}
            self._plan_work = (inputs, recommended, result)
            self._touch()
        return None

    def save_plan(self) -> Optional[str]:
        """Add the plan's players to my team at their planned prices."""
        with self.lock:
            result = (self.plan or {}).get("result")
            if not result or self.plan.get("status") != "ready":
                return "Build a plan first."
            ids = result["best"]["ids"]
            if not ids:
                return "The plan has no players to add."
            gone = [self.by_id[i].name for i in ids if str(i) in self.state["picks"]]
            if gone:
                return f"Your draft changed since this plan was built ({', '.join(gone)} already drafted). Rebuild it first."
            if self.state["filled"].count(None) < len(ids):
                return "Your roster doesn't have room for the whole plan. Rebuild it first."
            for i in ids:
                self.pick(i, MINE, result["costs"][str(i)])
            return None

    @staticmethod
    def _plan_payload(plan: planner.Plan, costs: Dict[int, int], recommended: Optional[planner.Plan] = None) -> Dict[str, Any]:
        """The plan for the page. `recommended` is the search's own best when players were switched in."""
        def build(b: planner.Build) -> Dict[str, Any]:
            return {
                "ids": b.ids, "cost": b.cost, "wins": round(b.wins, 2),
                "winsSd": round(b.wins_sd, 3),
                "floor10": None if b.floor10 is None else round(b.floor10, 2),
                "floor20": None if b.floor20 is None else round(b.floor20, 2),
                "chances": {c: round(x, 3) for c, x in b.chances.items()},
                "ratings": {c: round(x, 1) for c, x in b.ratings.items()},
            }

        best = build(plan.best)
        others = []
        for n, b in enumerate(plan.builds):
            if set(b.ids) == set(plan.best.ids):
                continue
            out = build(b)
            out["n"] = n  # its place among the search's builds, so its name stays put when you use another
            out["adds"] = [i for i in b.ids if i not in plan.best.ids]
            out["drops"] = [i for i in plan.best.ids if i not in b.ids]
            others.append(out)
        ids = set(plan.best.ids) | {i for b in plan.builds for i in b.ids}
        swaps = {}
        for out_id, options in plan.swaps.items():
            swaps[str(out_id)] = [{"id": s.in_id, "costChange": s.cost_change, "winsChange": round(s.wins_change, 3)} for s in options]
            ids |= {s.in_id for s in options}
        switched = None
        if recommended is not None and set(recommended.best.ids) != set(plan.best.ids):
            rec = build(recommended.best)
            switched = {"in": [i for i in plan.best.ids if i not in rec["ids"]], "out": [i for i in rec["ids"] if i not in plan.best.ids],
                        "wins": rec["wins"], "floor10": rec["floor10"], "floor20": rec["floor20"], "cost": rec["cost"],
                        "build": next((n for n, b in enumerate(plan.builds) if set(b.ids) == set(plan.best.ids)), None)}
            ids |= set(rec["ids"])
        return {
            "best": best, "builds": others, "swaps": swaps, "mine": plan.mine, "switched": switched,
            "budgetLeft": plan.budget_left, "streamers": plan.streamers,
            "searched": plan.searched, "evaluated": plan.evaluated, "objective": plan.objective,
            "costs": {str(i): costs[i] for i in ids},
        }

    def _plan_snapshot(self) -> Optional[Dict[str, Any]]:
        if not self.plan:
            return None
        out = {k: x for k, x in self.plan.items() if k != "stamp"}
        out["stale"] = self.plan["stamp"] != self._plan_stamp()
        if self.plan["status"] == "building":
            out["elapsed"] = round(time.time() - self.plan["started"])
            out["lastSeconds"] = self._plan_seconds.get(f"{self.plan_objective}/{self.plan.get('focus')}")
        return out

    def snapshot(self) -> Dict[str, Any]:
        with self.lock:
            return self._snapshot()

    def _snapshot(self) -> Dict[str, Any]:
        shape, base, state = self.shape, self.baseline, self.state
        rows = valuation.value_players(self.players, base, shape, self._adjustments())
        picks = {int(k): v for k, v in state["picks"].items()}
        mine = [pid for pid in state["filled"] if pid is not None]
        taken = [pid for pid, v in picks.items() if v["status"] == TAKEN]
        sim = valuation.simulate_league(rows, mine, taken, shape, self.schedule)
        fit_cats = self.fit_categories()
        useful = valuation.fit_by_wins if self.fit_model == "wins" else valuation.fit_by_fade(self.fade)
        starts: Dict[int, float] = {}
        fits = valuation.team_fit(rows, mine, shape, sim, base, fit_cats, useful, starts)
        # Fit of a player who plays no games (all of them filled at replacement): Fit's ± runs from here.
        zero_games = replace(rows[0], id=-1, proj_stats={}, exp_gp=0, proj_pg=float(shape.replacement), team=None) if rows else None
        zero_fit = valuation.team_fit([zero_games], mine, shape, sim, base, fit_cats, useful).get(-1, 100.0) if rows else 100.0
        rate = valuation.pricing(rows, shape)
        # Fit $: the league's money split by Fit the way Ours splits it by Value. Fit sits higher than
        # Value (an empty roster's top 84 came to ~$3,400 at Ours' rate), so it gets its own rate.
        fit_rate = valuation.pricing([SimpleNamespace(value=f) for f in fits.values()], shape)
        # Ranges: games and season value when both games and the per-game rating are uncertain.
        # Their dollars are priced against every player's mean outcome, so the ranges share a scale.
        missed_value = shape.replacement * shape.fill_rate  # what a missed game is worth on average: filled or lost
        ranges = {r.id: _ranges(self.by_id[r.id].default_exp_gp, r.gp_delta, None if r.hist is None else round(r.hist),
                                round(r.proj_pg, 1), missed_value) for r in rows}
        range_rate = valuation.pricing([SimpleNamespace(value=x[3]) for x in ranges.values()], shape)
        # Fit rank among players I can still get (and my own).
        fit_order = sorted((pid for pid in fits if picks.get(pid, {}).get("status") != TAKEN), key=lambda pid: -fits[pid])
        fit_rank = {pid: i + 1 for i, pid in enumerate(fit_order)}

        out_rows = []
        age_day = date(self.league.season, 2, 1)  # season age, as Basketball Reference counts it
        adjustments = state["adjustments"]
        for r in rows:
            p = self.by_id[r.id]
            pick = picks.get(r.id)
            cat_last = valuation.category_ratings(p.base_pg, base.per_game, shape.rated)
            cat_proj = valuation.category_ratings(r.proj_stats, base.per_game, shape.rated)
            cat_all = valuation.category_ratings(r.proj_stats, base.per_game, shape.categories)
            gp_range, risk, value_range, _mean = ranges[r.id]
            out_rows.append({
                "id": r.id,
                "name": p.name,
                "team": p.pro_team,
                "pos": "/".join(p.positions) or "—",
                "age": draft.age_on(p.birth_date, age_day),
                "elig": p.eligible_slots,
                "inj": p.injury,
                "gp": p.last_gp,
                "projGp": p.proj_gp,
                "fromProj": p.base_is_projection,
                "line": [_r(p.base_pg.get(k)) for k in ("PTS", "REB", "AST")],
                "lastPg": _r(r.last_pg),
                "lastValue": _r(r.last_value),
                "expGp": r.exp_gp,
                "espnGp": p.default_exp_gp,
                "gpDelta": r.gp_delta,
                "gpRange": list(gp_range),  # games p10, p50, p90
                "gpLow": gp_range[0],
                "risk": round(risk, 3),  # chance of fewer than 41 games
                "valueRange": [_r(x) for x in value_range],
                "dollarRange": [_r(range_rate.dollars(x), 0) for x in value_range],
                "expMin": round(r.exp_min, 1),
                "minSet": r.min_set,
                "defMin": _r(p.default_exp_min),  # what Exp MIN resets to
                "lastMin": _r(p.last_pg.get("MIN")),
                "projMin": _r(p.proj_pg.get("MIN")),
                "rateSource": p.rate_source,
                "delta": r.delta,
                "projPg": _r(r.proj_pg),
                "value": _r(r.value, 2),
                "valuePm": _r(availability.plus_minus(r.value, missed_value, r), 1),  # ± 1 SD of games
                "rank": r.rank,
                "espnRank": p.espn_rank,
                "espn": _r(p.espn_value, 0),
                "avg": _r(self._market(p)),
                "avgRaw": _r(p.avg_paid),
                "avgEspn": _r(self._espn_market(p)),
                "costSet": (adjustments.get(str(r.id)) or {}).get("cost") is not None,
                "adp": _r(p.adp),
                "ours": _r(r.ours, 2),
                "edge": _r(r.ours - self._market(p), 2),
                "fit": _r(fits.get(r.id)),
                "fitPm": _r(availability.plus_minus(fits[r.id], zero_fit, r), 1) if r.id in fits else None,
                "fitDollars": _r(fit_rate.dollars(fits[r.id]), 2) if r.id in fits else None,
                "fitRank": fit_rank.get(r.id),
                "fitEdge": _r(fit_rate.dollars(fits[r.id]) - self._market(p), 2) if r.id in fits else None,
                "starts": _r(starts[r.id], 3) if r.id in starts else None,
                "teamGames": len(self.team_days.get(p.pro_team, [])) or None,
                "status": pick["status"] if pick else None,
                "price": pick.get("price") if pick else None,
                "note": (adjustments.get(str(r.id)) or {}).get("note", ""),
                "catLast": {k: _r(v * 100, 0) for k, v in cat_last.items()},
                "catProj": {k: _r(v * 100, 0) for k, v in cat_proj.items()},
                # Every league category, projected per game: rating (100 = average) and the stat itself.
                "cats": {k: _r(v * 100, 0) for k, v in cat_all.items()},
                "catStats": {
                    k: _r(r.proj_stats.get(k), 3 if k in valuation.PERCENT_STATS else 1)
                    for k in shape.categories
                    if r.proj_stats.get(k) is not None
                },
                "espnDelta": self._espn_delta(p),
            })

        return {
            "meta": self._meta(),
            "rev": self.rev,
            "state": state,
            "rows": out_rows,
            "pool": self._pool(rows, picks),
            "pricing": {"replacement": round(rate.replacement, 2), "perPoint": round(rate.per_point, 3)},
            "plan": self._plan_snapshot(),
            "me": self._me(picks, mine),
            "team": {**self._team(sim, rows, picks, mine), **self._team_range_for(rows, mine, taken)},
            "playoffs": self._playoffs_for(rows, mine, taken, sim),
            "saved": self._saved_for(rows, picks, taken),
            "maxSaved": MAX_SAVED,
        }

    def _meta(self) -> Dict[str, Any]:
        league, shape = self.league, self.shape
        return {
            "leagueName": league.name,
            "leagueId": league.league_id,
            "season": league.season,
            "seasonLabel": season_label(league.season),
            "statsLabel": season_label(league.season - 1),
            "teams": shape.teams,
            "budget": shape.budget,
            "rosterSize": shape.roster_size,
            "poolSize": shape.pool_size,
            "counted": shape.counted,
            "starters": shape.starters,
            "daily": self.schedule is not None,  # team totals from daily lineups on the NBA schedule
            "draftType": league.draft_type,
            "scoringType": league.scoring_type,
            "categories": shape.categories,
            "reverse": shape.reverse,
            "rated": shape.rated,
            "slots": self.slots,
            "fetchedAt": self.fetched_at,
            "marketScale": round(self.market_scale, 3),
            "autoMarketScale": round(self.auto_market_scale, 3),
            "pricedSize": shape.priced_size,
            "fade": [self.fade.start, self.fade.end],
            "fitModel": self.fit_model,
            "planObjective": self.plan_objective,
            "planFocus": self.plan_focus,
            "playoffWeeks": self.calendar.playoff_weeks if self.calendar and self.calendar.rounds else [],
            "projLine": self.proj_line,
            "catWeights": self.cat_weights,
            "pricingModel": self.pricing_model,
            "categoryWeights": {c: valuation.CATEGORY_WEIGHTS.get(c, 1.0) for c in shape.categories},
            "curveTop": round(valuation.league_curve(shape)[0]) if shape.price_curve else None,
            "spreads": {c: valuation.spread(c) for c in shape.categories},
            "punt": self.punt,
            "fitCategories": self.fit_categories(),
            "replacement": shape.replacement,
            "fillRate": round(shape.fill_rate * 100),
            "core": shape.core,
            "gamesInSeason": valuation.GAMES_IN_SEASON,
            "maxReplacement": MAX_REPLACEMENT,
            "defaults": {
                "rated": self.default_rated,
                "ignorePlayers": DEFAULT_IGNORE,
                "replacement": DEFAULT_REPLACEMENT,
                "fillRate": DEFAULT_FILL_RATE,
                "core": min(DEFAULT_CORE, len(self.slots)),
                "fade": list(DEFAULT_FADE),
            },
            "maxDelta": MAX_DELTA,
            "maxMin": draft.MAX_MIN,
            "warnings": self.warnings,
        }

    def fit_categories(self) -> List[str]:
        """Categories that count toward team fit: those in player value, minus punted ones."""
        return [c for c in self.shape.rated if c not in self.punt]

    def _pool(self, rows, picks) -> Dict[str, Any]:
        """How many of the players worth paying for (every team's core) are still available."""
        top = sorted(rows, key=lambda r: r.rank)[: self.shape.priced_size]
        return {
            "size": len(top),
            "left": sum(1 for r in top if r.id not in picks),
            "taken": sum(1 for v in picks.values() if v["status"] == TAKEN),
        }

    def _me(self, picks, mine: List[int]) -> Dict[str, Any]:
        spent = sum(int(picks[pid]["price"]) for pid in mine if pid in picks)
        left = self.shape.budget - spent
        spots = self.shape.roster_size - len(mine)
        return {
            "count": len(mine),
            "spent": spent,
            "budgetLeft": left,
            "maxBid": max(0, left - max(0, spots - 1)),
            "names": [self.by_id[pid].name for pid in mine],
        }

    def _espn_delta(self, p: draft.DraftPlayer) -> Optional[int]:
        """ESPN's skill change: its projected rating minus our line at ESPN's minutes.

        Minutes are handled by Exp MIN, so this is what ESPN projects beyond
        playing time. It's about 0 for most players, since ESPN mostly keeps
        per-minute rates.
        """
        if not p.proj_pg or not p.rate_min or not p.proj_pg.get("MIN"):
            return None
        avg, cats = self.baseline.per_game, self.shape.rated
        at_espn_minutes = valuation.scale(p.rate_line, p.proj_pg["MIN"] / p.rate_min)
        weights = self.shape.weights
        change = valuation.rate(p.proj_pg, avg, cats, weights) - valuation.rate(at_espn_minutes, avg, cats, weights)
        return max(-MAX_DELTA, min(MAX_DELTA, round(change)))

    def _team_range_for(self, rows, mine: List[int], taken: List[int]) -> Dict[str, Any]:
        """My roster's season range in weekly category wins (library/availability.team_range).

        Every player is set to the model's mean outcome to build the average
        team, then my roster's season is drawn 300 times. Recomputed only when
        the draft state or settings change.
        """
        key = json.dumps([self.state, sorted(mine), sorted(taken)], sort_keys=True, default=str)
        if key == self._team_range[0]:
            return self._team_range[1] or {}
        result: Dict[str, Any] = {}
        if mine:
            shape, averages = self.shape, self.baseline.per_game
            mean_rows = [availability.mean_row(r, averages, shape) for r in rows]
            mean_sim = valuation.simulate_league(mean_rows, mine, taken, shape, self.schedule)
            by_id = {r.id: r for r in rows}
            tr = availability.team_range([by_id[i] for i in mine if i in by_id], mean_sim, averages, shape)
            result = {"winsRange": [round(tr.quantile(q), 2) for q in (0.1, 0.5, 0.9)], "halfSeason": round(tr.half_season, 1)}
        self._team_range = (key, result)
        return result

    def _playoffs_for(self, rows, mine: List[int], taken: List[int], season: valuation.LeagueSim) -> Optional[Dict[str, Any]]:
        """The Playoffs tab: when the fantasy playoffs land, each NBA team's games in them, and my team
        and every available player counted over just those weeks. Recomputed only when the draft changes.

        Playoff Fit is Fit over the playoff weeks (the league simulated on those days alone), put back
        on the season's scale: 100 is an average player with an average playoff schedule, so a player
        whose team plays more then, on days my lineup has room, rates higher.
        """
        cal, sched = self.calendar, self.focus_schedules.get("playoffs")
        if cal is None or not cal.rounds or sched is None or sched is self.schedule:
            return None
        key = json.dumps([self.state, self.fetched_at], sort_keys=True, default=str)
        if key == self._playoffs[0]:
            return self._playoffs[1]
        shape = self.shape
        psim = valuation.simulate_league(rows, mine, taken, shape, sched)
        useful = valuation.fit_by_wins if self.fit_model == "wins" else valuation.fit_by_fade(self.fade)
        starts: Dict[int, float] = {}
        fits = valuation.team_fit(rows, mine, shape, psim, self.baseline, self.fit_categories(), useful, starts)
        window_games = sum(sched.share)  # an average team's games in the playoffs
        stretch = sched.average_games / window_games if window_games else 1.0
        teams = {t.team: t for t in playoffs.team_playoffs(self.team_days, cal)}

        def player(r: valuation.Valued) -> Dict[str, Any]:
            t = teams.get(r.team)
            games = t.games if t else None
            # team_fit's starts are a share of his season's games: turn them into playoff games started.
            started = starts.get(r.id, 0.0) * sched.games(r.team) if r.team in sched.team_days else None
            return {"id": r.id, "pfit": _r(100 + (fits[r.id] - 100) * stretch) if r.id in fits else None,
                    "games": games, "starts": _r(started, 1) if started is not None else None}

        skip = set(taken) | set(mine)
        cats = shape.categories
        chances = {c: valuation.win_chance(psim.ratings.get(c, 100.0), c) for c in cats}
        weights = psim.lineup.weights(psim.mine)
        streamer = psim.lineup.streamer
        streamed = next((w for m, w in weights if m is streamer), 0.0) * sched.average_games if streamer else 0.0
        by_id = {r.id: r for r in rows}
        date_of = lambda d: cal.date(d).isoformat() if cal.date(d) else None  # noqa: E731
        plays = {t: set(ds) for t, ds in self.team_days.items()}
        my_teams = [by_id[i].team for i in mine if i in by_id]
        # Each day's lineup: my players with a game, best per-game rating first, in the starting slots.
        # Each starts where he did the day before (at first, his slot on My Team) when he can.
        best_first = sorted((by_id[i] for i in mine if i in by_id), key=lambda r: -r.proj_pg)
        starting = [i for i, slot in enumerate(self.slots) if slot != roster.BENCH]
        elig = self._eligibility()
        prefer = {pid: i for i, pid in enumerate(self.state["filled"]) if pid is not None}
        weeks = []
        for w in playoffs.weekly_games(self.team_days, cal):
            days = range(w["first"], w["last"] + 1)
            lineups = []
            for d in days:
                playing = [r.id for r in best_first if d in plays.get(r.team, ())]
                filled, sits = roster.day_lineup(self.slots, playing, elig, prefer)
                prefer.update({pid: i for i, pid in enumerate(filled) if pid is not None})
                lineups.append({"date": date_of(d), "start": [filled[i] for i in starting], "sits": sits,
                                "off": [r.id for r in best_first if r.id not in playing]})
            weeks.append({**w, "first": date_of(w["first"]), "last": date_of(w["last"]),
                          "mine": [sum(1 for t in my_teams if d in plays.get(t, ())) for d in days],  # my players with a game
                          "lineups": lineups})
        result = {
            "known": cal.known,
            "playoffTeams": cal.playoff_teams,
            "teams": shape.teams,
            "regularWeeks": min(r.weeks[0] for r in cal.rounds) - 1,
            "rounds": [{"period": r.period, "weeks": r.weeks, "first": date_of(r.first), "last": date_of(r.last)} for r in cal.rounds],
            "weeks": weeks,
            "starters": shape.starters,
            "startSlots": [self.slots[i] for i in starting],
            "nba": [{"team": t.team, "weeks": t.weeks, "games": t.games, "light": t.light} for t in teams.values()],
            "avgGames": round(window_games, 1),
            "lightShare": playoffs.LIGHT_DAY,
            "team": {
                "ratings": {c: round(psim.ratings.get(c, 100.0), 1) for c in cats},
                "seasonRatings": {c: round(season.ratings.get(c, 100.0), 1) for c in cats},
                "chances": {c: round(x, 3) for c, x in chances.items()},
                "expectedWins": round(sum(chances.values()), 2),
                "seasonWins": round(sum(valuation.win_chance(season.ratings.get(c, 100.0), c) for c in cats), 2),
                "matchupWin": round(valuation.matchup_win(list(chances.values())), 3),
                "slots": shape.starters * sched.days,  # starting slots on playoff days with games
                "streamed": round(streamed, 1),
                "players": [player(by_id[i]) for i in mine if i in by_id],
            },
            "players": [player(r) for r in rows if r.id not in skip],
        }
        self._playoffs = (key, result)
        return result

    def _team(self, sim: valuation.LeagueSim, rows, picks, mine: List[int]) -> Dict[str, Any]:
        cats = self.shape.categories
        by_id = {r.id: r for r in rows}
        # ± from my players' games alone (1 SD), around these ratings and the expected record.
        spread = availability.team_spread([by_id[i] for i in mine if i in by_id], sim, self.shape) if mine else None
        pm = spread.categories if spread else {}
        n = len(sim.teams)
        averages = {c: sum(t[c] for t in sim.teams) / n for c in cats}
        # Chance of beating the average team in each category in a given week.
        chances = {c: valuation.win_chance(sim.ratings.get(c, 100.0), c) for c in cats}
        order = sorted(cats, key=lambda c: sim.ranks[c])
        strong = [c for c in order if sim.ranks[c] <= 4]
        weak = [c for c in reversed(order) if sim.ranks[c] >= n - 3 and c not in self.punt]
        targets = []
        rated = [c for c in weak if c in self.shape.rated]
        if rated:
            cat = rated[0]
            base = self.baseline.per_game
            candidates = [
                (valuation.category_rating(r.proj_stats, base, cat) or 0, r)
                for r in rows
                if r.id not in picks and r.ours - self._market(self.by_id[r.id]) > 0
            ]
            candidates.sort(key=lambda x: x[0], reverse=True)
            targets = [
                {"cat": cat, "id": r.id, "name": self.by_id[r.id].name, "rating": round(v * 100), "ours": round(r.ours)}
                for v, r in candidates[:2]
            ]
        return {
            "categories": [
                {
                    "cat": c,
                    "rank": sim.ranks[c],
                    "rating": round(sim.ratings.get(c, 100.0), 1),
                    "mine": sim.teams[0][c],
                    "avg": averages[c],
                    "teams": [t[c] for t in sim.teams],
                    "reverse": c in self.shape.reverse,
                    "punt": c in self.punt,
                    "win": round(chances[c], 3),
                    "pm": round(pm.get(c, 0.0), 1),
                    "inFit": c in self.fit_categories(),
                }
                for c in cats
            ],
            "roto": sim.roto,
            "rotoMax": len(cats) * n,
            "overall": sim.overall,
            "expectedWins": round(sum(chances.values()), 2),
            "winsPm": round(spread.wins, 2) if spread else 0.0,
            "winningPm": round(spread.winning, 1) if spread else 0.0,  # ± categories won
            "matchupWin": round(valuation.matchup_win(list(chances.values())), 3),
            "filled": sim.filled,
            "strong": strong,
            "weak": weak,
            "targets": targets,
        }
