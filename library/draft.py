"""Fetch the draft player pool and league settings from ESPN.

espn_api's Player keeps only the current season's stats and drops ESPN's
draft data, so this module reads ESPN's JSON directly. League endpoints for
public leagues work without cookies; private leagues need espn_s2 and SWID.
"""

from __future__ import annotations

import http.client
import json
import os
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from espn_api.basketball.constant import POSITION_MAP, PRO_TEAM_MAP, STATS_MAP

from library.valuation import PERCENT_STATS, VOLUME_STATS

BASE_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba"
ATHLETES_URL = "https://sports.core.api.espn.com/v3/sports/basketball/nba/athletes"
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
    except (OSError, http.client.HTTPException) as ex:  # URLError, timeouts, dropped connections
        raise EspnError(f"Couldn't reach ESPN: {getattr(ex, 'reason', ex)}") from ex
    except ValueError as ex:  # not JSON, or not UTF-8
        raise EspnError("ESPN sent a response that isn't JSON.") from ex


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
    # The matchup schedule (library/playoffs.py). None: not looked up yet (a pool cached before it was).
    matchup_count: int = 0  # matchup periods in the regular season
    matchup_weeks: Optional[Dict[int, List[int]]] = None  # matchup period -> its matchup weeks, numbered from 1
    playoff_teams: int = 0
    opening: Optional[str] = None  # the date of day 1 (ISO); "" when ESPN's schedule has no dates

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
    schedule = settings.get("scheduleSettings", {})
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
        matchup_count=int(schedule.get("matchupPeriodCount") or 0),
        matchup_weeks={int(k): [int(w) for w in v] for k, v in (schedule.get("matchupPeriods") or {}).items()},
        playoff_teams=int(schedule.get("playoffTeamCount") or 0),
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
    # Which per-game line drives the projection: "espn" (ESPN's projection,
    # which backtested better) or "last" (last season's per-minute rates).
    line_source: str = "espn"
    birth_date: Optional[str] = None  # YYYY-MM-DD

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

        With line_source "espn": ESPN's projection when it has minutes. With
        "last" (or no ESPN minutes): last season when there's a real sample,
        otherwise ESPN's projection.
        """
        if self.line_source == "espn" and self.proj_pg.get("MIN"):
            return self.proj_pg
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
        """ESPN's projected games, or last season's when ESPN has no projection."""
        return min(MAX_GP, self.proj_gp or self.last_gp)


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
# NBA schedule
# --------------------------------------------------------------------------


def parse_schedule(data: dict) -> Dict[str, List[int]]:
    """Each NBA team's game days, as ESPN scoring periods (one per fantasy day).

    Teams are keyed like DraftPlayer.pro_team. Games not yet scheduled (e.g.
    NBA Cup knockouts) aren't included.
    """
    days: Dict[str, List[int]] = {}
    for team in data.get("settings", {}).get("proTeams", []):
        abbrev = PRO_TEAM_MAP.get(team.get("id"))
        games = [g for period in (team.get("proGamesByScoringPeriod") or {}).values() for g in period]
        if abbrev and abbrev != "FA" and games:
            days[abbrev] = sorted({int(g["scoringPeriodId"]) for g in games})
    return days


def parse_opening(data: dict) -> str:
    """The date of day 1 (scoring period 1), ISO. "" when the games have no dates.

    Each game's date in US Eastern time, minus its day number: the most common answer.
    """
    eastern = timezone(timedelta(hours=-5))  # every game starts after noon, so standard time is close enough
    votes: Counter = Counter()
    for team in data.get("settings", {}).get("proTeams", []):
        for period in (team.get("proGamesByScoringPeriod") or {}).values():
            for g in period:
                if g.get("date") and g.get("scoringPeriodId"):
                    day = datetime.fromtimestamp(g["date"] / 1000, eastern).date()
                    votes[day - timedelta(days=int(g["scoringPeriodId"]) - 1)] += 1
    return votes.most_common(1)[0][0].isoformat() if votes else ""


def fetch_schedule(season: int) -> Tuple[Dict[str, List[int]], str]:
    """The season's NBA schedule and the date of day 1 (see parse_opening). Empty when ESPN hasn't published it yet."""
    data = _get_json(f"{BASE_URL}/seasons/{season}?view=proTeamSchedules_wl")
    return parse_schedule(data), parse_opening(data)


# --------------------------------------------------------------------------
# Past seasons (for the games-played model)
# --------------------------------------------------------------------------

PAST_SEASONS = 3


def parse_past(data: dict, season: int) -> Dict[int, List[float]]:
    """id -> [season, games played, minutes per game, ESPN's preseason minutes] from a season's player pool."""
    out: Dict[int, List[float]] = {}
    for entry in data.get("players", []):
        pl = entry.get("player") or {}
        splits = {s.get("id"): s for s in pl.get("stats", [])}
        actual, proj = splits.get(f"00{season}") or {}, splits.get(f"10{season}") or {}
        if not actual and not proj:
            continue
        gp = (actual.get("stats") or {}).get("42", 0.0)
        minutes = (actual.get("averageStats") or {}).get("40", 0.0)
        proj_min = (proj.get("averageStats") or {}).get("40", 0.0)
        out[pl["id"]] = [season, float(gp), float(minutes), float(proj_min)]
    return out


def fetch_past(season: int, ids: List[int]) -> Dict[int, List[List[float]]]:
    """Each player's last PAST_SEASONS seasons: id -> [[season, games, minutes, ESPN's preseason minutes], ...]."""
    out: Dict[int, List[List[float]]] = {}
    for past in range(season - 1, season - 1 - PAST_SEASONS, -1):
        player_filter = {"players": {"filterIds": {"value": list(ids)}}}  # ESPN rejects a limit with filterIds
        url = f"{BASE_URL}/seasons/{past}/segments/0/leaguedefaults/3?view=kona_player_info"
        data = _get_json(url, headers={"x-fantasy-filter": json.dumps(player_filter)}, timeout=120)
        for pid, row in parse_past(data, past).items():
            out.setdefault(pid, []).append(row)
    return out


def save_past(path: str, season: int, past: Dict[int, List[List[float]]]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"season": season, "players": {str(k): v for k, v in past.items()}}, f)
    os.replace(tmp, path)


def load_past(path: str, season: int) -> Optional[Dict[int, List[List[float]]]]:
    """The cached past seasons, or None when missing or for another season."""
    try:
        with open(path) as f:
            payload = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if payload.get("season") != season:
        return None
    return {int(k): v for k, v in payload.get("players", {}).items()}


# --------------------------------------------------------------------------
# Birth dates
# --------------------------------------------------------------------------


def _birth_date(athlete: dict) -> Optional[str]:
    dob = athlete.get("dateOfBirth")  # e.g. "1999-09-19T07:00Z": midnight US time, so the date part is right
    try:
        return date.fromisoformat(dob[:10]).isoformat()
    except (TypeError, ValueError):
        return None


def parse_birth_dates(data: dict) -> Dict[int, str]:
    """id -> birth date (YYYY-MM-DD) from ESPN's list of NBA athletes."""
    out: Dict[int, str] = {}
    for a in data.get("items", []):
        dob = _birth_date(a)
        if a.get("id") and dob:
            out[int(a["id"])] = dob
    return out


def fetch_birth_dates(ids: List[int]) -> Dict[int, str]:
    """Birth dates for these players. ESPN's athlete list leaves out some (often
    injured) players, so those are looked up one at a time."""
    out = parse_birth_dates(_get_json(f"{ATHLETES_URL}?limit=5000", timeout=60))

    def one(pid: int) -> Optional[str]:
        try:
            return _birth_date(_get_json(f"{ATHLETES_URL}/{pid}"))
        except EspnError:
            return None

    missing = [pid for pid in ids if pid not in out]
    with ThreadPoolExecutor(max_workers=6) as pool:
        for pid, dob in zip(missing, pool.map(one, missing)):
            if dob:
                out[pid] = dob
    return out


def age_on(birth_date: Optional[str], day: date) -> Optional[int]:
    """Age in whole years on `day`."""
    try:
        born = date.fromisoformat(birth_date or "")
    except ValueError:
        return None
    return day.year - born.year - ((day.month, day.day) < (born.month, born.day))


# --------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------


def save_pool(
    path: str,
    league: LeagueInfo,
    players: List[DraftPlayer],
    schedule: Optional[Dict[str, List[int]]] = None,
    fetched_at: Optional[float] = None,
    birth_dates: bool = False,
) -> None:
    """`fetched_at` is when the pool came from ESPN (default: now). `birth_dates`
    records that they were looked up, even if ESPN had none for some players."""
    payload = {
        "version": POOL_CACHE_VERSION,
        "fetchedAt": time.time() if fetched_at is None else fetched_at,
        "birthDates": birth_dates,
        "league": asdict(league),
        "players": [asdict(p) for p in players],
        "schedule": schedule or {},
    }
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f)
    os.replace(tmp, path)


def load_pool(path: str):
    """Returns (league, players, schedule, fetched_at, birth_dates) or None if missing or outdated.

    The schedule is None in caches saved before it was stored, and birth_dates
    is False until birth dates have been looked up.
    """
    try:
        with open(path) as f:
            payload = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    if payload.get("version") != POOL_CACHE_VERSION:
        return None
    league_data = payload["league"]
    league_data["team_names"] = {int(k): v for k, v in league_data.get("team_names", {}).items()}
    if league_data.get("matchup_weeks") is not None:
        league_data["matchup_weeks"] = {int(k): v for k, v in league_data["matchup_weeks"].items()}
    league = LeagueInfo(**league_data)
    players = [DraftPlayer(**p) for p in payload["players"]]
    return league, players, payload.get("schedule"), payload.get("fetchedAt", 0), bool(payload.get("birthDates"))
