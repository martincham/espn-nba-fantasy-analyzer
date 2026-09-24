"""Draft board state and calculations behind the GUI's JSON API.

Holds the cached ESPN pool, your edits (Δ, expected games, notes, picks and
roster slots) and turns them into one JSON snapshot for the browser. All
math runs here, so the frontend only renders.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

from library import draft, roster, valuation
from library.valuation import Adjustment, LeagueShape

DEFAULT_SETTINGS = {
    "leagueId": None,
    "SWID": None,
    "espn_s2": None,
    "ignoredStats": ["FTM", "FTA", "FGA", "FGM", "GP", "MIN", "TO"],
    "rosterPositions": ["PG", "F", "F", "SG/SF", "SG/SF", "C", "UT"],
    "teamSize": 12,
    "ignorePlayers": 3,
}
MINE, TAKEN = "mine", "taken"
MAX_DELTA = 60  # rating points
MARKET_SCALE_RANGE = (0.5, 3.0)
DEFAULT_REPLACEMENT = 95  # per-game rating of a top free agent, who fills a hurt player's games
MAX_REPLACEMENT = 150
DEFAULT_CORE = 7  # players per team worth paying for; the rest are $1 streamers
# Draft Room settings saved in draftState.json. None means "use the default"
# (settings.txt, the league on ESPN, the computed price scale, or the constants above).
DEFAULT_FADE = (110, 140)  # team category rating where extra strength starts to stop helping, and stops
DEFAULT_ROOM_SETTINGS = {
    "marketScale": None, "rated": None, "ignorePlayers": None, "replacement": None, "core": None,
    "fadeStart": None, "fadeEnd": None, "punt": [], "fitModel": None,
    "projLine": None, "catWeights": None, "pricing": None,
}
FIT_MODELS = ("wins", "fade")  # weekly win chances (default), or the simple 110-140 fade
# Rating model choices; the first of each is the default, backtested in docs/BACKTEST_PLAN.md.
PROJ_LINES = ("espn", "last")  # ESPN's per-game projection, or last season's per-minute rates
CAT_WEIGHTS = ("league", "equal")  # valuation.CATEGORY_WEIGHTS, or every category equal
PRICING_MODELS = ("curve", "formula")  # this league's price curve, or the core-share formula


def load_settings(path: str) -> Dict[str, Any]:
    """Read settings.txt without creating or modifying it."""
    settings = dict(DEFAULT_SETTINGS)
    try:
        with open(path) as f:
            settings.update(json.load(f))
    except FileNotFoundError:
        pass
    return settings


def season_label(season: int) -> str:
    return f"{season - 1}-{season % 100:02d}"


def _r(x: Optional[float], digits: int = 1) -> Optional[float]:
    return None if x is None else round(x, digits)


class DraftBoard:
    def __init__(self, settings_path: str, pool_path: str, state_path: str):
        self.settings_path = settings_path
        self.pool_path = pool_path
        self.state_path = state_path
        self.lock = threading.RLock()
        self.settings: Dict[str, Any] = {}
        self.league: Optional[draft.LeagueInfo] = None
        self.players: List[draft.DraftPlayer] = []
        self.team_days: Dict[str, List[int]] = {}  # NBA schedule: each team's game days
        self.schedule: Optional[valuation.Schedule] = None
        self.by_id: Dict[int, draft.DraftPlayer] = {}
        self.fetched_at = 0.0
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
        self.default_rated: List[str] = []
        self.default_ignore = 0
        self.state = self._empty_state()

    # ------------------------------------------------------------------ load

    @staticmethod
    def _empty_state() -> Dict[str, Any]:
        return {"adjustments": {}, "picks": {}, "filled": [], "settings": dict(DEFAULT_ROOM_SETTINGS)}

    def load(self, refresh: bool = False) -> None:
        with self.lock:
            self.settings = load_settings(self.settings_path)
            cached = None if refresh else draft.load_pool(self.pool_path)
            if cached:
                self.league, self.players, team_days, self.fetched_at = cached
                if team_days is None:  # cached before schedules were stored
                    self.team_days = self._fetch_schedule(self.league.season)
                    draft.save_pool(self.pool_path, self.league, self.players, self.team_days)
                else:
                    self.team_days = team_days
            else:
                self._fetch()
            self._prepare()
            self._load_state()
            self._apply_settings()

    def _fetch(self) -> None:
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
        self.team_days = self._fetch_schedule(season)
        self.league, self.players, self.fetched_at = league, players, time.time()
        draft.save_pool(self.pool_path, league, players, self.team_days)

    def _fetch_schedule(self, season: int) -> Dict[str, List[int]]:
        try:
            days = draft.fetch_schedule(season)
        except draft.EspnError as ex:
            days = {}
            self.warnings.append(f"No NBA schedule, so Fit ignores it: {ex}")
        return days

    def _prepare(self) -> None:
        league, s = self.league, self.settings
        self.by_id = {p.id: p for p in self.players}
        if league.slot_counts:
            self.slots = roster.slots_from_counts(league.slot_counts)
        else:
            self.slots = roster.slots_from_positions(s["rosterPositions"], int(s["teamSize"]))
        ignored = set(s.get("ignoredStats") or [])
        self.default_rated = [c for c in league.categories if c not in ignored]
        self.default_ignore = int(s.get("ignorePlayers") or 0)
        self.schedule = valuation.Schedule(self.team_days) if self.team_days else None
        self.shape = LeagueShape(
            teams=league.teams,
            budget=league.budget,
            roster_size=len(self.slots),
            ignore_players=self.default_ignore,
            categories=list(league.categories),
            reverse=list(league.reverse),
            rated=list(self.default_rated),
            starters=sum(1 for slot in self.slots if slot != roster.BENCH),
        )
        self.warnings = [w for w in self.warnings if w.startswith(("Using default", "No NBA schedule"))]
        if league.draft_type != "AUCTION":
            self.warnings.append(f"This league's draft type is {league.draft_type.lower()}; values are still shown in auction dollars.")
        # ESPN's average prices come from leagues of every size, so they add up
        # to less than this league spends. Scale them to this league's budget.
        top_market = sum(sorted((p.avg_paid for p in self.players), reverse=True)[: self.shape.pool_size])
        self.auto_market_scale = (self.shape.teams * self.shape.budget) / top_market if top_market > 0 else 1.0
        self.market_scale = self.auto_market_scale  # until saved settings are applied

    def _apply_settings(self) -> None:
        """Apply the Draft Room settings on top of the league's defaults."""
        room = self.state["settings"]
        self.shape.rated = list(room["rated"]) if room["rated"] is not None else list(self.default_rated)
        self.shape.ignore_players = room["ignorePlayers"] if room["ignorePlayers"] is not None else self.default_ignore
        self.market_scale = room["marketScale"] if room["marketScale"] is not None else self.auto_market_scale
        self.shape.replacement = float(room["replacement"] if room["replacement"] is not None else DEFAULT_REPLACEMENT)
        self.shape.core = room["core"] if room["core"] is not None else min(DEFAULT_CORE, len(self.slots))
        start = room["fadeStart"] if room["fadeStart"] is not None else DEFAULT_FADE[0]
        end = room["fadeEnd"] if room["fadeEnd"] is not None else DEFAULT_FADE[1]
        self.fade = valuation.Fade(start=start, end=max(end, start + 1))
        self.punt = list(room["punt"])
        self.fit_model = room["fitModel"] or FIT_MODELS[0]
        self.proj_line = room["projLine"] or PROJ_LINES[0]
        self.cat_weights = room["catWeights"] or CAT_WEIGHTS[0]
        self.pricing_model = room["pricing"] or PRICING_MODELS[0]
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
        return state

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
            # Punting is always your choice: only categories you tick are punted.
            room["punt"] = [c for c in cats if c in set(saved.get("punt") or [])]
        except (TypeError, ValueError):
            pass  # a bad value keeps its default
        return room

    def _save(self) -> None:
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

    def replace_state(self, state: Dict[str, Any]) -> None:
        """Restore a previous state (used by Undo)."""
        with self.lock:
            merged = self._empty_state()
            merged.update({k: state[k] for k in merged if k in state})
            self.state = self._clean(merged)
            self._apply_settings()
            self._save()

    # -------------------------------------------------------------- snapshot

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
        rate = valuation.pricing(rows, shape)
        # Fit rank among players I can still get (and my own).
        fit_order = sorted((pid for pid in fits if picks.get(pid, {}).get("status") != TAKEN), key=lambda pid: -fits[pid])
        fit_rank = {pid: i + 1 for i, pid in enumerate(fit_order)}

        out_rows = []
        adjustments = state["adjustments"]
        for r in rows:
            p = self.by_id[r.id]
            pick = picks.get(r.id)
            cat_last = valuation.category_ratings(p.base_pg, base.per_game, shape.rated)
            cat_proj = valuation.category_ratings(r.proj_stats, base.per_game, shape.rated)
            cat_all = valuation.category_ratings(r.proj_stats, base.per_game, shape.categories)
            out_rows.append({
                "id": r.id,
                "name": p.name,
                "team": p.pro_team,
                "pos": "/".join(p.positions) or "—",
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
                "expMin": round(r.exp_min, 1),
                "minSet": r.min_set,
                "lastMin": _r(p.last_pg.get("MIN")),
                "projMin": _r(p.proj_pg.get("MIN")),
                "rateSource": p.rate_source,
                "delta": r.delta,
                "projPg": _r(r.proj_pg),
                "value": _r(r.value, 2),
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
                "fitDollars": _r(rate.dollars(fits[r.id]), 2) if r.id in fits else None,
                "fitRank": fit_rank.get(r.id),
                "fitEdge": _r(rate.dollars(fits[r.id]) - self._market(p), 2) if r.id in fits else None,
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
            "state": state,
            "rows": out_rows,
            "pool": self._pool(rows, picks),
            "pricing": {"replacement": round(rate.replacement, 2), "perPoint": round(rate.per_point, 3)},
            "me": self._me(picks, mine),
            "team": self._team(sim, rows, picks),
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
            "projLine": self.proj_line,
            "catWeights": self.cat_weights,
            "pricingModel": self.pricing_model,
            "categoryWeights": {c: valuation.CATEGORY_WEIGHTS.get(c, 1.0) for c in shape.categories},
            "curveTop": round(valuation.league_curve(shape)[0]) if shape.price_curve else None,
            "spreads": {c: valuation.spread(c) for c in shape.categories},
            "punt": self.punt,
            "fitCategories": self.fit_categories(),
            "replacement": shape.replacement,
            "core": shape.core,
            "gamesInSeason": valuation.GAMES_IN_SEASON,
            "maxReplacement": MAX_REPLACEMENT,
            "defaults": {
                "rated": self.default_rated,
                "ignorePlayers": self.default_ignore,
                "replacement": DEFAULT_REPLACEMENT,
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

    def _team(self, sim: valuation.LeagueSim, rows, picks) -> Dict[str, Any]:
        cats = self.shape.categories
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
                    "inFit": c in self.fit_categories(),
                }
                for c in cats
            ],
            "roto": sim.roto,
            "rotoMax": len(cats) * n,
            "overall": sim.overall,
            "expectedWins": round(sum(chances.values()), 2),
            "matchupWin": round(valuation.matchup_win(list(chances.values())), 3),
            "filled": sim.filled,
            "strong": strong,
            "weak": weak,
            "targets": targets,
        }
