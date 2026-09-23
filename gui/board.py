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
        self.by_id: Dict[int, draft.DraftPlayer] = {}
        self.fetched_at = 0.0
        self.shape = LeagueShape()
        self.slots: List[str] = []
        self.baseline: Optional[valuation.Baseline] = None
        self.warnings: List[str] = []
        self.state = self._empty_state()

    # ------------------------------------------------------------------ load

    @staticmethod
    def _empty_state() -> Dict[str, Any]:
        return {"weight": 0.5, "adjustments": {}, "picks": {}, "filled": []}

    def load(self, refresh: bool = False) -> None:
        with self.lock:
            self.settings = load_settings(self.settings_path)
            cached = None if refresh else draft.load_pool(self.pool_path)
            if cached:
                self.league, self.players, self.fetched_at = cached
            else:
                self._fetch()
            self._prepare()
            self._load_state()

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
        self.league, self.players, self.fetched_at = league, players, time.time()
        draft.save_pool(self.pool_path, league, players)

    def _prepare(self) -> None:
        league, s = self.league, self.settings
        self.by_id = {p.id: p for p in self.players}
        if league.slot_counts:
            self.slots = roster.slots_from_counts(league.slot_counts)
        else:
            self.slots = roster.slots_from_positions(s["rosterPositions"], int(s["teamSize"]))
        ignored = set(s.get("ignoredStats") or [])
        self.shape = LeagueShape(
            teams=league.teams,
            budget=league.budget,
            roster_size=len(self.slots),
            ignore_players=int(s.get("ignorePlayers") or 0),
            categories=list(league.categories),
            reverse=list(league.reverse),
            rated=[c for c in league.categories if c not in ignored],
        )
        self.warnings = [w for w in self.warnings if w.startswith("Using default")]
        if league.draft_type != "AUCTION":
            self.warnings.append(f"This league's draft type is {league.draft_type.lower()}; values are still shown in auction dollars.")
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
        state["weight"] = min(1.0, max(0.0, float(state.get("weight", 0.5))))
        return state

    def _save(self) -> None:
        tmp = self.state_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.state, f, indent=1)
        os.replace(tmp, self.state_path)

    def _adjustments(self) -> Dict[int, Adjustment]:
        return {
            int(k): Adjustment(delta=float(v.get("delta") or 0), exp_gp=v.get("expGp"), note=v.get("note") or "")
            for k, v in self.state["adjustments"].items()
        }

    # ------------------------------------------------------------ operations

    def set_weight(self, weight: float) -> None:
        with self.lock:
            self.state["weight"] = min(1.0, max(0.0, float(weight)))
            self._save()

    def adjust(self, player_id: int, **fields: Any) -> None:
        """Set delta, expGp (None resets to the default) and/or note."""
        with self.lock:
            if player_id not in self.by_id:
                raise ValueError("Unknown player.")
            adj = dict(self.state["adjustments"].get(str(player_id), {}))
            if "delta" in fields:
                adj["delta"] = max(-50.0, min(50.0, round(float(fields["delta"] or 0))))
            if "expGp" in fields:
                gp = fields["expGp"]
                adj["expGp"] = None if gp is None else max(0, min(draft.MAX_GP, int(round(float(gp)))))
            if "note" in fields:
                adj["note"] = str(fields["note"] or "")[:1000]
            if not adj.get("delta") and adj.get("expGp") is None and not adj.get("note"):
                self.state["adjustments"].pop(str(player_id), None)
            else:
                self.state["adjustments"][str(player_id)] = adj
            self._save()

    def reset_adjustments(self) -> None:
        with self.lock:
            # Notes are kept; only Δ and expected games are cleared.
            self.state["adjustments"] = {
                k: {"note": v["note"]} for k, v in self.state["adjustments"].items() if v.get("note")
            }
            self._save()

    def _names(self) -> Dict[int, str]:
        return {pid: p.name for pid, p in self.by_id.items()}

    def _eligibility(self) -> Dict[int, List[str]]:
        return {pid: p.eligible_slots for pid, p in self.by_id.items()}

    def pick(self, player_id: int, status: Optional[str], price: Optional[float] = None) -> Optional[str]:
        """Mark a player mine (auto-slotted), taken, or undrafted (status None).

        Without a price, keeps the existing one or defaults to the average paid.
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
            if status in (MINE, TAKEN):
                old = self.state["picks"].get(key, {})
                self.state["picks"][key] = {"status": status, "price": self._price(price, old.get("price") or self._default_price(player_id))}
            else:
                self.state["picks"].pop(key, None)
            self._save()
            return None

    def _default_price(self, player_id: int) -> int:
        """A player's cost when no price is given: the average paid in ESPN auctions."""
        player = self.by_id.get(player_id)
        return max(1, int(round(player.avg_paid))) if player else 1

    @staticmethod
    def _price(price: Optional[float], fallback: Optional[float]) -> int:
        value = price if price is not None else fallback if fallback is not None else 1
        return max(1, int(round(float(value))))

    def set_price(self, player_id: int, price: float) -> None:
        with self.lock:
            pick = self.state["picks"].get(str(player_id))
            if pick:
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
            self._save()

    # -------------------------------------------------------------- snapshot

    def snapshot(self) -> Dict[str, Any]:
        with self.lock:
            return self._snapshot()

    def _snapshot(self) -> Dict[str, Any]:
        shape, base, state = self.shape, self.baseline, self.state
        weight = state["weight"]
        rows = valuation.value_players(self.players, base, shape, self._adjustments(), weight)
        picks = {int(k): v for k, v in state["picks"].items()}
        market = valuation.apply_inflation(rows, shape, {pid: float(v["price"]) for pid, v in picks.items()})
        mine = [pid for pid in state["filled"] if pid is not None]
        taken = [pid for pid, v in picks.items() if v["status"] == TAKEN]
        sim = valuation.simulate_league(rows, mine, taken, shape)

        out_rows = []
        adjustments = state["adjustments"]
        for r in rows:
            p = self.by_id[r.id]
            pick = picks.get(r.id)
            cat_last = valuation.category_ratings(p.base_pg, base.per_game, shape.rated)
            cat_proj = valuation.category_ratings(r.proj_stats, base.per_game, shape.rated)
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
                "lastSeason": _r(r.last_season),
                "expGp": r.exp_gp,
                "gpSet": r.gp_set,
                "delta": r.delta,
                "projPg": _r(r.proj_pg),
                "projSeason": _r(r.proj_season),
                "value": _r(r.value, 2),
                "rank": r.rank,
                "espnRank": p.espn_rank,
                "espn": _r(p.espn_value, 0),
                "avg": _r(p.avg_paid),
                "adp": _r(p.adp),
                "ours": _r(r.ours, 2),
                "edge": _r(r.ours - p.avg_paid, 2),
                "bid": _r(r.bid, 2),
                "status": pick["status"] if pick else None,
                "price": pick["price"] if pick else None,
                "note": (adjustments.get(str(r.id)) or {}).get("note", ""),
                "catLast": {k: _r(v * 100, 0) for k, v in cat_last.items()},
                "catProj": {k: _r(v * 100, 0) for k, v in cat_proj.items()},
                "espnDelta": self._espn_delta(p),
            })

        return {
            "meta": self._meta(),
            "state": state,
            "rows": out_rows,
            "market": {
                "inflation": round(market.inflation, 3),
                "moneyLeft": round(market.money_left),
                "drafted": market.drafted,
            },
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
            "draftType": league.draft_type,
            "scoringType": league.scoring_type,
            "categories": shape.categories,
            "reverse": shape.reverse,
            "rated": shape.rated,
            "slots": self.slots,
            "fetchedAt": self.fetched_at,
            "warnings": self.warnings,
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
        """ESPN's projection as a volume change vs last season, in %."""
        if p.base_is_projection or not p.proj_pg or not p.last_pg:
            return None
        avg = self.baseline.per_game
        keys = [k for k in ("PTS", "REB", "AST", "STL", "BLK", "3PM", "FGA", "FTA") if avg.get(k)]
        before = sum(p.last_pg.get(k, 0) / avg[k] for k in keys)
        after = sum(p.proj_pg.get(k, 0) / avg[k] for k in keys)
        return round((after / before - 1) * 100) if before else None

    def _team(self, sim: valuation.LeagueSim, rows, picks) -> Dict[str, Any]:
        cats = self.shape.categories
        n = len(sim.teams)
        averages = {c: sum(t[c] for t in sim.teams) / n for c in cats}
        order = sorted(cats, key=lambda c: sim.ranks[c])
        strong = [c for c in order if sim.ranks[c] <= 4]
        weak = [c for c in reversed(order) if sim.ranks[c] >= n - 3]
        targets = []
        rated = [c for c in weak if c in self.shape.rated]
        if rated:
            cat = rated[0]
            base = self.baseline.per_game
            candidates = [
                (valuation.category_rating(r.proj_stats, base, cat) or 0, r)
                for r in rows
                if r.id not in picks and r.ours - self.by_id[r.id].avg_paid > 0
            ]
            candidates.sort(key=lambda x: x[0], reverse=True)
            targets = [
                {"cat": cat, "id": r.id, "name": self.by_id[r.id].name, "rating": round(v * 100), "bid": round(r.bid)}
                for v, r in candidates[:2]
            ]
        return {
            "categories": [
                {
                    "cat": c,
                    "rank": sim.ranks[c],
                    "mine": sim.teams[0][c],
                    "avg": averages[c],
                    "teams": [t[c] for t in sim.teams],
                    "reverse": c in self.shape.reverse,
                }
                for c in cats
            ],
            "roto": sim.roto,
            "rotoMax": len(cats) * n,
            "overall": sim.overall,
            "expectedWins": round(sim.expected_wins, 1),
            "filled": sim.filled,
            "strong": strong,
            "weak": weak,
            "targets": targets,
        }
