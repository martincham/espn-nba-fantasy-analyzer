"""Download past seasons of the ESPN league into history/<season>/.

Usage: python3 history/fetch_history.py [season ...]   (default: 2024 2025 2026)
       python3 history/fetch_history.py --players-only 2020   (player pool only, for seasons before the league)
Seasons are ESPN seasonIds, so 2026 is the 2025-26 season.
"""

import json
import os
import sys
import time
import urllib.request

LEAGUE_ID = 1640258594
BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/{season}/segments/0/leagues/{league}"
HERE = os.path.dirname(os.path.abspath(__file__))


def get(season, query, fantasy_filter=None):
    url = BASE.format(season=season, league=LEAGUE_ID) + query
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    if fantasy_filter:
        req.add_header("x-fantasy-filter", json.dumps(fantasy_filter))
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2)


def save(season, name, data):
    path = os.path.join(HERE, str(season), name)
    with open(path, "w") as f:
        json.dump(data, f)
    print(f"  {name}: {os.path.getsize(path) / 1e6:.1f} MB")


def fetch(season):
    print(f"Season {season} ({season - 1}-{season % 100:02d})")
    os.makedirs(os.path.join(HERE, str(season)), exist_ok=True)
    league = get(season, "?view=mSettings&view=mTeam&view=mRoster&view=mStandings&view=mNav&view=mStatus")
    save(season, "league.json", league)
    save(season, "draft.json", get(season, "?view=mDraftDetail"))
    save(season, "matchups.json", get(season, "?view=mMatchup&view=mMatchupScore&view=mScoreboard"))

    # Transactions are only served per scoring period (one per fantasy day).
    last = league["status"].get("finalScoringPeriod") or league["scoringPeriodId"]
    transactions = []
    for period in range(1, last + 1):
        transactions += get(season, f"?view=mTransactions2&scoringPeriodId={period}").get("transactions", [])
    unique = {t["id"]: t for t in transactions}
    save(season, "transactions.json", sorted(unique.values(), key=lambda t: t.get("proposedDate", 0)))

    player_filter = {"players": {
        "filterStatus": {"value": ["FREEAGENT", "WAIVERS", "ONTEAM"]},
        "limit": 1500,
        "sortPercOwned": {"sortPriority": 1, "sortAsc": False},
    }}
    save(season, "players.json", get(season, "?view=kona_player_info", player_filter))
    fetch_boxscores(season)


def fetch_pool(season):
    """Players only, from ESPN's league-independent endpoint: for seasons before the league existed."""
    url = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/{season}/segments/0/leaguedefaults/3?view=kona_player_info"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "x-fantasy-filter": json.dumps({"players": {
        "filterStatus": {"value": ["FREEAGENT", "WAIVERS", "ONTEAM"]}, "limit": 1500,
        "sortPercOwned": {"sortPriority": 1, "sortAsc": False}}})})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    for entry in data.get("players", []):  # drop per-game logs (ids starting 05), keep season splits
        pl = entry["player"]
        pl["stats"] = [st for st in pl.get("stats", []) if not str(st.get("id", "")).startswith("05")]
    os.makedirs(os.path.join(HERE, str(season)), exist_ok=True)
    save(season, "players.json", data)


def box_week(season, period, day):
    """The teams' sides of one matchup period, as seen from a day inside it."""
    data = get(season, f"?view=mBoxscore&view=mMatchupScore&scoringPeriodId={day}",
               {"schedule": {"filterMatchupPeriodIds": {"value": [period]}}})
    sides = [m[side] for m in data.get("schedule", []) for side in ("home", "away") if m.get(side)]
    return sides if any((s.get("rosterForMatchupPeriod") or {}).get("entries") for s in sides) else None


def week_ends(season, matchups, final_day):
    """Last scoring day of each matchup period.

    Recent seasons list each side's days in pointsByScoringPeriod. Older ones
    don't, so probe: a period ends on day d when d is in it and d + 1 is in the next.
    """
    ends = {}
    for m in matchups["schedule"]:
        for side in ("home", "away"):
            for d in (m.get(side) or {}).get("pointsByScoringPeriod") or {}:
                ends[m["matchupPeriodId"]] = max(ends.get(m["matchupPeriodId"], 0), int(d))
    if ends:
        return ends
    periods = sorted({m["matchupPeriodId"] for m in matchups["schedule"]})
    prev = 0
    for p in periods[:-1]:
        for length in (7, 6, 14, 8, 13, 15):
            d = prev + length
            if box_week(season, p, d) and box_week(season, p + 1, d + 1):
                ends[p] = prev = d
                break
        else:
            raise RuntimeError(f"Couldn't find the days of matchup period {p}")
    ends[periods[-1]] = final_day
    return ends


def fetch_boxscores(season):
    """Each week's counted stats per player per team (rosterForMatchupPeriod), saved to boxscores.json."""
    matchups = json.load(open(os.path.join(HERE, str(season), "matchups.json")))
    league = json.load(open(os.path.join(HERE, str(season), "league.json")))
    final_day = league["status"].get("finalScoringPeriod") or league["scoringPeriodId"]
    weeks = []
    for period, end in sorted(week_ends(season, matchups, final_day).items()):
        for side in box_week(season, period, end) or []:
            side.pop("rosterForCurrentScoringPeriod", None)
            side["matchupPeriodId"] = period
            weeks.append(side)
    save(season, "boxscores.json", weeks)


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["--players-only"]:
        for s in args[1:]:
            fetch_pool(int(s))
    else:
        for s in [int(a) for a in args] or [2024, 2025, 2026]:
            fetch(s)
