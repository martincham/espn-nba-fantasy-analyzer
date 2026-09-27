"""Download what the games-played model needs (docs/GAMES_RANGE_PLAN.md).

Usage: python3 history/fetch_games.py logs [season ...]   (default: 2018-2026)
       python3 history/fetch_games.py bios                 (players in history/games/)
       python3 history/fetch_games.py standings [season ...]
Seasons are ESPN seasonIds, so 2026 is the 2025-26 season.

- logs: ESPN's league-independent player pool (leaguedefaults), top 1000 by
  ownership, with each player's season line, preseason projection and game
  log. Saved compact to history/games/<season>.json. From 2018-19 on the log
  lists every team game, with the ones he missed empty; 2017-18 lists only
  games played, so team games come from teammates' logs (see games_model.py).
- bios: birth date, height, weight and debut year from ESPN's athlete API,
  cached in history/bios.json (only missing players are fetched).
- standings: each NBA team's wins and losses, in history/standings.json.
"""

import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from library.draft import _stat_dict  # noqa: E402

GAMES_DIR = os.path.join(HERE, "games")
BIOS = os.path.join(HERE, "bios.json")
STANDINGS = os.path.join(HERE, "standings.json")
POOL_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/{season}/segments/0/leaguedefaults/3?view=kona_player_info"
ATHLETE_URL = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/athletes/{id}"
STANDINGS_URL = "https://site.api.espn.com/apis/v2/sports/basketball/nba/standings?season={season}"
PAGE, POOL_SIZE = 250, 1000


def get(url, fantasy_filter=None):
    # The site APIs refuse a browser user agent that sends no other browser headers; the fantasy API wants one.
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"} if "fantasy.espn.com" in url else {})
    if fantasy_filter:
        req.add_header("x-fantasy-filter", json.dumps(fantasy_filter))
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))


def split(pl, split_id):
    s = next((s for s in pl.get("stats", []) if s.get("id") == split_id), None)
    if not s:
        return None
    line = _stat_dict(s.get("averageStats") or {})
    line["GP"] = (s.get("stats") or {}).get("42", line.get("GP", 0))
    return line


def compact(pl, season):
    """A player's season line, projection and game log: [[day, proTeamId, minutes], ...]."""
    games = sorted(
        [s["scoringPeriodId"], s.get("proTeamId"), round((s.get("stats") or {}).get("40", 0.0), 1)]
        for s in pl.get("stats", []) if str(s.get("id", "")).startswith("05") and s.get("seasonId") == season
    )
    return {
        "id": pl["id"], "name": pl["fullName"], "team": pl.get("proTeamId"), "pos": pl.get("defaultPositionId"),
        "actual": split(pl, f"00{season}"), "proj": split(pl, f"10{season}"), "games": games,
    }


def fetch_logs(season):
    players = []
    for offset in range(0, POOL_SIZE, PAGE):
        data = get(POOL_URL.format(season=season), {"players": {
            "filterStatus": {"value": ["FREEAGENT", "WAIVERS", "ONTEAM"]}, "limit": PAGE, "offset": offset,
            "sortPercOwned": {"sortPriority": 1, "sortAsc": False}}})
        players += [compact(e["player"], season) for e in data.get("players", [])]
    unique = list({p["id"]: p for p in players}.values())
    os.makedirs(GAMES_DIR, exist_ok=True)
    path = os.path.join(GAMES_DIR, f"{season}.json")
    with open(path, "w") as f:
        json.dump({"season": season, "players": unique}, f)
    logged = sum(1 for p in unique if p["games"])
    print(f"Season {season}: {len(unique)} players, {logged} with game logs, {os.path.getsize(path) / 1e6:.1f} MB")


def inches(text):
    """6' 11" -> 83."""
    try:
        feet, rest = text.split("'")
        return int(feet) * 12 + int(rest.strip().strip('"') or 0)
    except (AttributeError, ValueError):
        return None


def bio(player_id):
    try:
        a = get(ATHLETE_URL.format(id=player_id)).get("athlete", {})
    except Exception as ex:
        return player_id, {"error": str(ex)}
    dob = a.get("displayDOB")  # day/month/year
    if dob:
        d, m, y = dob.split("/")
        dob = f"{y}-{int(m):02d}-{int(d):02d}"
    weight = (a.get("displayWeight") or "").split(" ")[0]
    return player_id, {"name": a.get("displayName"), "dob": dob, "height": inches(a.get("displayHeight")),
                       "weight": int(weight) if weight.isdigit() else None, "debut": a.get("debutYear")}


def fetch_bios():
    bios = json.load(open(BIOS)) if os.path.exists(BIOS) else {}
    ids = set()
    for name in os.listdir(GAMES_DIR):
        for p in json.load(open(os.path.join(GAMES_DIR, name)))["players"]:
            if (p["actual"] or {}).get("GP") or p["proj"]:
                ids.add(p["id"])
    pool = os.path.join(os.path.dirname(HERE), "draftPool.json")
    if os.path.exists(pool):
        ids |= {p["id"] for p in json.load(open(pool))["players"]}
    todo = sorted(i for i in ids if str(i) not in bios or "error" in bios[str(i)])
    print(f"{len(ids)} players, fetching {len(todo)}")
    with ThreadPoolExecutor(max_workers=6) as pool_:
        for n, (pid, b) in enumerate(pool_.map(bio, todo), 1):
            bios[str(pid)] = b
            if n % 200 == 0:
                print(f"  {n}/{len(todo)}")
                json.dump(bios, open(BIOS, "w"))
    json.dump(bios, open(BIOS, "w"))
    missing = sum(1 for i in ids if not bios.get(str(i), {}).get("dob"))
    print(f"Saved {len(bios)} bios; {missing} without a birth date")


def fetch_standings(seasons):
    out = json.load(open(STANDINGS)) if os.path.exists(STANDINGS) else {}
    for season in seasons:
        data = get(STANDINGS_URL.format(season=season))
        teams = {}
        for conf in data.get("children", []):
            for e in conf["standings"]["entries"]:
                st = {s["name"]: s.get("value") for s in e["stats"]}
                teams[e["team"]["id"]] = {"abbrev": e["team"]["abbreviation"], "wins": int(st["wins"]), "losses": int(st["losses"])}
        out[str(season)] = teams
        print(f"Season {season}: {len(teams)} teams")
    json.dump(out, open(STANDINGS, "w"), indent=1)


if __name__ == "__main__":
    cmd, args = (sys.argv[1:2] or ["logs"])[0], [int(a) for a in sys.argv[2:]]
    if cmd == "logs":
        for s in args or range(2018, 2027):
            fetch_logs(s)
    elif cmd == "bios":
        fetch_bios()
    elif cmd == "standings":
        fetch_standings(args or range(2017, 2027))
    else:
        sys.exit(__doc__)
