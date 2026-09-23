"""Fetch the draft player pool and league settings from ESPN.

espn_api's Player keeps only the current season's stats and drops ESPN's
draft data, so this module reads ESPN's JSON directly. League endpoints for
public leagues work without cookies; private leagues need espn_s2 and SWID.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from espn_api.basketball.constant import POSITION_MAP, PRO_TEAM_MAP, STATS_MAP

from library.valuation import PERCENT_STATS, VOLUME_STATS

BASE_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba"
BASE_POSITIONS = ["PG", "SG", "SF", "PF", "C"]
POOL_CACHE_VERSION = 1
MAX_GP = 82
MAX_MIN = 48
MIN_SAMPLE_GP = 20  # fewer games than this: last season's per-minute rates are too noisy
KEPT_STATS = set(VOLUME_STATS) | set(PERCENT_STATS) | {"GP"}
# Older espn_api releases use different names for some stats.
STAT_ALIASES = {"3PTM": "3PM", "3PTA": "3PA", "3PT%": "3P%"}


def stat_name(stat_id) -> str:
    name = STATS_MAP.get(str(stat_id), str(stat_id))
    return STAT_ALIASES.get(name, name)


class EspnError(Exception):
    pass


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------


def _cookie_header(espn_s2: Optional[str], swid: Optional[str]) -> Optional[str]:
    # settings.txt ships with placeholder values; only send real cookies.
    if not espn_s2 or not swid or swid in ("{123}", "123") or espn_s2 == "456":
        return None
    return f"espn_s2={espn_s2}; SWID={swid}"


def _get_json(url: str, headers: Optional[Dict[str, str]] = None, cookie: Optional[str] = None, timeout: int = 30) -> dict:
    request_headers = {"User-Agent": "espn-nba-fantasy-analyzer", "Accept": "application/json"}
    request_headers.update(headers or {})
    if cookie:
        request_headers["Cookie"] = cookie
    request = urllib.request.Request(url, headers=request_headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as ex:
        if ex.code in (401, 403):
            raise EspnError(
                "ESPN refused the request. If your league is private, set espn_s2 and SWID in settings.txt."
            ) from ex
        if ex.code == 404:
            raise EspnError("ESPN couldn't find that league or season. Check leagueId in settings.txt.") from ex
        raise EspnError(f"ESPN returned HTTP {ex.code}.") from ex
    except (urllib.error.URLError, TimeoutError) as ex:
        raise EspnError(f"Couldn't reach ESPN: {getattr(ex, 'reason', ex)}") from ex


def current_season() -> int:
    """The season ESPN is currently set up for (e.g. 2027 for 2026-27)."""
    return int(_get_json(BASE_URL)["currentSeasonId"])


# --------------------------------------------------------------------------
# League settings
# --------------------------------------------------------------------------


@dataclass
class LeagueInfo:
    league_id: Optional[int]
    season: int
    name: str = "ESPN default league"
    teams: int = 12
    budget: int = 200
    draft_type: str = "AUCTION"
    scoring_type: str = "H2H_CATEGORY"
    categories: List[str] = field(default_factory=lambda: ["PTS", "REB", "AST", "STL", "BLK", "3PM", "TO", "FG%", "FT%"])
    reverse: List[str] = field(default_factory=lambda: ["TO"])
    slot_counts: Dict[str, int] = field(default_factory=dict)
    team_names: Dict[int, str] = field(default_factory=dict)

    @property
    def rank_type(self) -> str:
        return "STANDARD" if "POINTS" in self.scoring_type else "ROTO"


def parse_league(data: dict, league_id: Optional[int], season: int) -> LeagueInfo:
    settings = data.get("settings", {})
    scoring = settings.get("scoringSettings", {})
    items = scoring.get("scoringItems", [])
    categories = [stat_name(i["statId"]) for i in items]
    reverse = [stat_name(i["statId"]) for i in items if i.get("isReverseItem")]
    counts = {
        POSITION_MAP.get(int(k), str(k)): int(v)
        for k, v in settings.get("rosterSettings", {}).get("lineupSlotCounts", {}).items()
        if int(v) > 0
    }
    draft = settings.get("draftSettings", {})
    info = LeagueInfo(
        league_id=league_id,
        season=season,
        name=settings.get("name") or f"League {league_id}",
        teams=int(settings.get("size") or len(data.get("teams", [])) or 12),
        budget=int(draft.get("auctionBudget") or 200),
        draft_type=draft.get("type") or "AUCTION",
        scoring_type=scoring.get("scoringType") or "H2H_CATEGORY",
        slot_counts=counts,
        team_names={int(t["id"]): t.get("name") or t.get("abbrev") or f"Team {t['id']}" for t in data.get("teams", [])},
    )
    if categories:
        info.categories = categories
        info.reverse = reverse
    return info


def fetch_league(league_id: int, season: int, espn_s2: Optional[str] = None, swid: Optional[str] = None) -> LeagueInfo:
    url = f"{BASE_URL}/seasons/{season}/segments/0/leagues/{league_id}?view=mSettings&view=mTeam"
    return parse_league(_get_json(url, cookie=_cookie_header(espn_s2, swid)), league_id, season)


# --------------------------------------------------------------------------
# Player pool
# --------------------------------------------------------------------------


@dataclass
class DraftPlayer:
    id: int
    name: str
    pro_team: str
    positions: List[str]  # base positions, e.g. ["SF", "PF"]
    eligible_slots: List[str]  # ESPN lineup slots, e.g. ["SF", "PF", "F", "UT", "BE"]
    injury: str
    last_pg: Dict[str, float]  # last season per game
    last_gp: int
    proj_pg: Dict[str, float]  # ESPN projection per game
    proj_gp: int
    espn_rank: Optional[int]
    espn_value: float  # ESPN suggested auction $ (league-specific when available)
    avg_paid: float  # average price in ESPN auction drafts
    adp: float
    owned: float
    on_team_id: int = 0

    @property
    def base_is_projection(self) -> bool:
        """No last-season games (e.g. rookies): fall back to ESPN's projection."""
        return self.last_gp <= 0 and bool(self.proj_pg)

    @property
    def base_pg(self) -> Dict[str, float]:
        return self.proj_pg if self.base_is_projection else self.last_pg

    @property
    def base_gp(self) -> int:
        return self.proj_gp if self.base_is_projection else self.last_gp

    @property
    def rate_line(self) -> Dict[str, float]:
        """Per-game line whose per-minute rates drive the projection.

        Last season when there's a real sample; otherwise ESPN's projection.
        """
        if self.last_gp >= MIN_SAMPLE_GP and self.last_pg.get("MIN"):
            return self.last_pg
        if self.proj_pg.get("MIN"):
            return self.proj_pg
        return self.base_pg

    @property
    def rate_source(self) -> str:
        return "last" if self.rate_line is self.last_pg else "espn"

    @property
    def rate_min(self) -> float:
        """Minutes per game behind rate_line."""
        return float(self.rate_line.get("MIN") or 0)

    @property
    def default_exp_min(self) -> float:
        """ESPN's projected minutes per game, else the rate line's minutes."""
        return round(float(self.proj_pg.get("MIN") or self.rate_min), 1)

    @property
    def default_exp_gp(self) -> int:
        """Two-thirds ESPN's projected games, one-third last season's."""
        if self.last_gp > 0 and self.proj_gp > 0:
            return min(MAX_GP, round((self.last_gp + 2 * self.proj_gp) / 3))
        return min(MAX_GP, self.last_gp or self.proj_gp)


def _stat_dict(raw: dict) -> Dict[str, float]:
    out = {}
    for key, value in raw.items():
        name = stat_name(key)
        if name in KEPT_STATS:
            out[name] = float(value)
    return out


def parse_player(entry: dict, season: int, rank_type: str = "ROTO") -> Optional[DraftPlayer]:
    player = entry.get("player", entry)
    splits = {s.get("id"): s for s in player.get("stats", [])}
    last = splits.get(f"00{season - 1}") or {}
    proj = splits.get(f"10{season}") or {}
    last_pg = _stat_dict(last.get("averageStats") or {})
    proj_pg = _stat_dict(proj.get("averageStats") or {})
    if not last_pg and not proj_pg:
        return None
    eligible_slots = [POSITION_MAP.get(s, str(s)) for s in player.get("eligibleSlots", [])]
    ranks = player.get("draftRanksByRankType", {}).get(rank_type, {})
    ownership = player.get("ownership", {})
    league_value = entry.get("draftAuctionValue")
    return DraftPlayer(
        id=int(player["id"]),
        name=player.get("fullName", "?"),
        pro_team=PRO_TEAM_MAP.get(player.get("proTeamId"), "FA"),
        positions=[s for s in eligible_slots if s in BASE_POSITIONS],
        eligible_slots=eligible_slots,
        injury=player.get("injuryStatus") or "ACTIVE",
        last_pg=last_pg,
        last_gp=int(last_pg.get("GP", 0)),
        proj_pg=proj_pg,
        proj_gp=int(round(proj_pg.get("GP", 0))),
        espn_rank=ranks.get("rank"),
        espn_value=float(league_value if league_value else ranks.get("auctionValue") or 0),
        avg_paid=float(ownership.get("auctionValueAverage") or 0),
        adp=float(ownership.get("averageDraftPosition") or 0),
        owned=float(ownership.get("percentOwned") or 0),
        on_team_id=int(entry.get("onTeamId") or 0),
    )


def fetch_pool(
    season: int,
    league_id: Optional[int] = None,
    espn_s2: Optional[str] = None,
    swid: Optional[str] = None,
    rank_type: str = "ROTO",
    limit: int = 600,
) -> List[DraftPlayer]:
    """Top `limit` players by ESPN draft rank, with last season's stats."""
    player_filter = {
        "players": {
            "filterStatus": {"value": ["FREEAGENT", "WAIVERS", "ONTEAM"]},
            "limit": limit,
            "sortDraftRanks": {"sortPriority": 1, "sortAsc": True, "value": rank_type},
        }
    }
    if league_id:
        url = f"{BASE_URL}/seasons/{season}/segments/0/leagues/{league_id}?view=kona_player_info"
    else:
        url = f"{BASE_URL}/seasons/{season}/segments/0/leaguedefaults/3?view=kona_player_info"
    data = _get_json(url, headers={"x-fantasy-filter": json.dumps(player_filter)}, cookie=_cookie_header(espn_s2, swid))
    players = [parse_player(p, season, rank_type) for p in data.get("players", [])]
    return [p for p in players if p is not None]


# --------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------


def save_pool(path: str, league: LeagueInfo, players: List[DraftPlayer]) -> None:
    payload = {
        "version": POOL_CACHE_VERSION,
        "fetchedAt": time.time(),
        "league": asdict(league),
        "players": [asdict(p) for p in players],
    }
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f)
    os.replace(tmp, path)


def load_pool(path: str):
    """Returns (league, players, fetched_at) or None if missing or outdated."""
    try:
        with open(path) as f:
            payload = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if payload.get("version") != POOL_CACHE_VERSION:
        return None
    league_data = payload["league"]
    league_data["team_names"] = {int(k): v for k, v in league_data.get("team_names", {}).items()}
    league = LeagueInfo(**league_data)
    players = [DraftPlayer(**p) for p in payload["players"]]
    return league, players, payload.get("fetchedAt", 0)
