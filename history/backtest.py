"""Backtest harness for the rating (docs/BACKTEST_PLAN.md).

Step 2: the target. Category wins added (CWA) measures what a player's actual
season adds to an average team in this league, using no rating formula:

- Each week, every team's counted category totals come from the box scores
  (history/<season>/boxscores.json, regular season). Totals are put on a
  common week length by league-wide games played, since some matchups run two
  weeks and some weeks have fewer NBA games.
- A category's weekly spread (sigma) is how much team totals differ within the
  same week. Beating a random opponent after adding delta to an average team
  has chance Phi(delta / (sigma * sqrt 2)).
- A player plays GAMES_PER_WEEK games in each week he's active, so a season of
  GP games is GP / GAMES_PER_WEEK active weeks. Each active week he replaces a
  replacement player: the games-weighted average line of every pickup stint
  that season, i.e. what a free agent actually gave these teams.
- FG% and FT% are recomputed from makes and attempts on the average team's
  volume; TO counts against.

CWA = active weeks x sum over categories of (P(win with him) - 1/2), in
category wins over a season.

Run: python3.12 history/backtest.py targets    (step 2: build and check CWA)
     python3.12 history/backtest.py baseline   (step 3: score the draft board)
     python3.12 history/backtest.py ceiling    (how much of a season's per-game CWA is signal)
"""

import json
import math
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from library.draft import _stat_dict  # noqa: E402

ALL_SEASONS = (2021, 2022, 2023, 2024, 2025, 2026)
LOCKBOX = 2026  # scored once, at the very end
COUNTING = ["PTS", "REB", "AST", "STL", "BLK", "3PM", "TO"]
PERCENT = {"FG%": ("FGM", "FGA"), "FT%": ("FTM", "FTA")}
CATS = COUNTING + list(PERCENT)
NEEDED = COUNTING + ["FGM", "FGA", "FTM", "FTA"]
REVERSE = {"TO"}


def load(season, name):
    with open(os.path.join(HERE, str(season), name)) as f:
        return json.load(f)


def phi(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def counted_line(entry):
    pl = entry["playerPoolEntry"]["player"]
    line = next((s["stats"] for s in pl.get("stats", []) if s.get("statSourceId") == 0), None)
    return pl["id"], (_stat_dict(line) if line else {})


class League:
    """One season's weekly category environment, built from the box scores."""

    def __init__(self, season):
        self.season = season
        league = load(season, "league.json")
        regular = league["settings"]["scheduleSettings"]["matchupPeriodCount"]
        draft = load(season, "draft.json")["draftDetail"]["picks"]
        drafted_by = {p["playerId"]: p["teamId"] for p in draft}

        weeks = defaultdict(dict)  # period -> team -> totals
        self.stints = defaultdict(lambda: defaultdict(float))  # (team, player) -> counted totals
        pickup = defaultdict(float)
        for side in load(season, "boxscores.json"):
            period = side["matchupPeriodId"]
            if period > regular:
                continue
            totals = defaultdict(float)
            for e in (side.get("rosterForMatchupPeriod") or {}).get("entries", []):
                pid, line = counted_line(e)
                for k in NEEDED + ["GP"]:
                    totals[k] += line.get(k, 0.0)
                    self.stints[(side["teamId"], pid)][k] += line.get(k, 0.0)
                if drafted_by.get(pid) != side["teamId"]:
                    for k in NEEDED + ["GP"]:
                        pickup[k] += line.get(k, 0.0)
            weeks[period][side["teamId"]] = totals
        self.weeks = weeks
        self.regular = regular
        self.drafted_by = drafted_by

        # Week length by league-wide games; scale every week to the average.
        games = {p: sum(t["GP"] for t in teams.values()) for p, teams in weeks.items()}
        avg_games = sum(games.values()) / len(games)
        self.scale = {p: avg_games / g for p, g in games.items()}
        # Games per player-week: average games a counted player plays in a scaled week.
        players_per_team = self._players_per_team()
        self.team_games = avg_games / len(next(iter(weeks.values())))  # counted games per team-week
        self.games_per_week = self.team_games / players_per_team

        # The average team (per scaled week) and each category's within-week spread.
        self.mean = {k: 0.0 for k in NEEDED}
        n = 0
        for p, teams in weeks.items():
            for totals in teams.values():
                n += 1
                for k in NEEDED:
                    self.mean[k] += totals[k] * self.scale[p]
        self.mean = {k: x / n for k, x in self.mean.items()}
        self.sigma = {}
        for c in CATS:
            devs = []
            for p, teams in weeks.items():
                vals = [self._cat(totals, c, self.scale[p]) for totals in teams.values()]
                mu = sum(vals) / len(vals)
                devs += [(x - mu) ** 2 for x in vals]
            self.sigma[c] = math.sqrt(sum(devs) / len(devs))

        self.replacement = {k: pickup[k] / pickup["GP"] for k in NEEDED}

    def _players_per_team(self):
        """Average counted players per team-week with at least one game: about 10-12."""
        counts = []
        for side in load(self.season, "boxscores.json"):
            if side["matchupPeriodId"] <= self.regular:
                entries = (side.get("rosterForMatchupPeriod") or {}).get("entries", [])
                counts.append(sum(1 for e in entries if counted_line(e)[1].get("GP", 0) > 0))
        return sum(counts) / len(counts)

    @staticmethod
    def _cat(totals, c, scale=1.0):
        if c in PERCENT:
            m, a = PERCENT[c]
            return totals[m] / totals[a] if totals[a] else 0.0
        return totals[c] * scale

    def gain(self, delta):
        """Expected category wins added in one week by `delta` (stat -> change vs the average team)."""
        out = {}
        for c in COUNTING:
            d = -delta.get(c, 0.0) if c in REVERSE else delta.get(c, 0.0)
            out[c] = phi(d / (self.sigma[c] * math.sqrt(2))) - 0.5
        for c, (m, a) in PERCENT.items():
            base = self.mean[m] / self.mean[a]
            attempts = self.mean[a] + delta.get(a, 0.0)
            d = (self.mean[m] + delta.get(m, 0.0)) / attempts - base if attempts > 0 else 0.0
            out[c] = phi(d / (self.sigma[c] * math.sqrt(2))) - 0.5
        return out

    def cwa(self, per_game, gp):
        """Category wins added over a season: active weeks x weekly gain over a replacement."""
        delta = {k: (per_game.get(k, 0.0) - self.replacement[k]) * self.games_per_week for k in NEEDED}
        gain = self.gain(delta)
        weeks = gp / self.games_per_week
        return weeks * sum(gain.values()), {c: weeks * g for c, g in gain.items()}

    def volume_cwa(self, extra_games):
        """Category wins from playing extra_games more games than average at the replacement level."""
        if not extra_games:
            return 0.0
        weeks = len(self.weeks)
        delta = {k: self.replacement[k] * extra_games / weeks for k in NEEDED}
        return weeks * sum(self.gain(delta).values())


def player_targets(lg):
    """CWA for every player in the pool from his actual season line."""
    out = {}
    for entry in load(lg.season, "players.json")["players"]:
        pl = entry["player"]
        split = next((s for s in pl.get("stats", []) if s.get("id") == f"00{lg.season}"), None)
        if not split:
            continue
        per_game = _stat_dict(split.get("averageStats") or {})
        gp = per_game.get("GP", 0)
        if gp <= 0:
            continue
        total, by_cat = lg.cwa(per_game, gp)
        out[pl["id"]] = {"name": pl["fullName"], "gp": gp, "cwa": total, "byCat": by_cat}
    return out


def all_play(lg):
    """Each team's all-play category wins against the other teams, regular season."""
    wins = defaultdict(float)
    for teams in lg.weeks.values():
        for a, ta in teams.items():
            for b, tb in teams.items():
                if a == b:
                    continue
                for c in CATS:
                    x, y = lg._cat(ta, c), lg._cat(tb, c)
                    better = x < y if c in REVERSE else x > y
                    wins[a] += 0.5 if x == y else float(better)
    return {t: w / (len(lg.weeks[next(iter(lg.weeks))]) - 1) for t, w in wins.items()}


def pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    return sxy / math.sqrt(sxx * syy)


def validate(lg):
    """Summed CWA of what each team counted, plus its games volume, vs all-play category wins."""
    team_cwa, team_gp = defaultdict(float), defaultdict(float)
    for (team, _pid), totals in lg.stints.items():
        gp = totals["GP"]
        if gp > 0:
            team_cwa[team] += lg.cwa({k: totals[k] / gp for k in NEEDED}, gp)[0]
            team_gp[team] += gp
    avg_gp = sum(team_gp.values()) / len(team_gp)
    players_only = dict(team_cwa)
    for t in team_cwa:
        team_cwa[t] += lg.volume_cwa(team_gp[t] - avg_gp)
    ap = all_play(lg)
    teams = sorted(ap)
    r_players = pearson([players_only[t] for t in teams], [ap[t] for t in teams])
    return pearson([team_cwa[t] for t in teams], [ap[t] for t in teams]), r_players, team_cwa, ap


def seasons_available():
    return [s for s in ALL_SEASONS if os.path.exists(os.path.join(HERE, str(s), "boxscores.json"))]


# --------------------------------------------------------------------------
# Step 3: replay the draft board before each season
# --------------------------------------------------------------------------

TUNING = tuple(x for x in ALL_SEASONS if x != LOCKBOX)
# ESPN's stored 2022-23 projection (102023) is a mid-season rest-of-season
# projection (e.g. Markkanen 21.5 pts over 39 games), not preseason. It leaks
# the answer, so tests that use ESPN's projection skip that season. It stays
# usable for tests that don't (rating formula, last-season-only boards).
NO_PRESEASON_PROJECTION = {2023}
PROJECTION_TUNING = tuple(x for x in TUNING if x not in NO_PRESEASON_PROJECTION)
SEASON_GAMES = {2021: 72}  # everything else is 82
BOARD_CATS = ["PTS", "BLK", "STL", "AST", "REB", "3PM", "TO", "FT%", "FG%"]  # league order


def board_shape(**overrides):
    """The Draft Room as saved: all 9 categories rated, 95 replacement, 7-player core."""
    from library.valuation import LeagueShape
    shape = LeagueShape(teams=12, budget=200, roster_size=12, ignore_players=3, categories=list(BOARD_CATS),
                        reverse=["TO"], rated=list(BOARD_CATS), core=7, replacement=95.0, starters=7)
    for k, x in overrides.items():
        setattr(shape, k, x)
    return shape


def preseason_players(season):
    """DraftPlayers as the board would have built them before `season`.

    Each player gets last season's actual line (00{season-1}, from last
    season's file) and ESPN's preseason projection (10{season}, from this
    season's file), then goes through draft.parse_player like a live fetch.
    """
    from library import draft
    last = {}
    for entry in load(season - 1, "players.json")["players"]:
        pl = entry["player"]
        split = next((st for st in pl.get("stats", []) if st.get("id") == f"00{season - 1}"), None)
        if split:
            last[pl["id"]] = split
    players = []
    for entry in load(season, "players.json")["players"]:
        pl = dict(entry["player"])
        proj = [st for st in pl.get("stats", []) if st.get("id") == f"10{season}"]
        pl["stats"] = proj + ([last[pl["id"]]] if pl["id"] in last else [])
        p = draft.parse_player({**entry, "player": pl}, season)
        if p is not None:
            # The board assumes 82 games; put a short season's projection on that basis.
            p.proj_gp = min(draft.MAX_GP, round(p.proj_gp * 82 / SEASON_GAMES.get(season, 82)))
            p.line_source = "last"  # the board as it was before step 4; variants switch it
            players.append(p)
    return players


def board_values(season, players=None, shape=None, adjustments=None):
    """Run the board's own valuation: id -> Valued."""
    from library import valuation
    players = players if players is not None else preseason_players(season)
    shape = shape or board_shape()
    history = [p for p in players if not p.base_is_projection]
    baseline = valuation.compute_baseline(history, shape)
    rows = valuation.value_players(players, baseline, shape, adjustments or {})
    return {r.id: r for r in rows}


def spearman(xs, ys):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):  # average ranks for ties
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r
    return pearson(ranks(xs), ranks(ys))


def truth(season):
    """CWA by player id; a drafted player who never played added nothing."""
    return {int(k): x["cwa"] for k, x in load(season, "cwa.json")["players"].items()}


def price_curve(season):
    return sorted((p["bidAmount"] for p in load(season, "draft.json")["draftDetail"]["picks"]), reverse=True)


def score(season, values):
    """How well preseason values predict CWA, on the league's real decisions.

    - drafted: the 144 players this league drafted (what money was spent on)
    - top200: the board's own top 200 by preseason value
    - dollar error: Ours $ vs CWA $ (CWA rank on the league's price curve) for picks that cost $5+
    """
    cwa = truth(season)
    picks = load(season, "draft.json")["draftDetail"]["picks"]
    drafted = [pk for pk in picks if pk["playerId"] in values]
    xs = [values[pk["playerId"]].value for pk in drafted]
    ys = [cwa.get(pk["playerId"], 0.0) for pk in drafted]
    paid = [pk["bidAmount"] for pk in drafted]
    top = sorted(values.values(), key=lambda r: -r.value)[:200]

    prices = price_curve(season)
    ranked = sorted(cwa, key=lambda pid: -cwa[pid])
    cwa_dollars = {pid: (prices[i] if i < len(prices) else 0) for i, pid in enumerate(ranked)}
    big = [pk for pk in drafted if pk["bidAmount"] >= 5]
    return {
        "season": season,
        "n": len(drafted),
        "drafted": spearman(xs, ys),
        "draftedPearson": pearson(xs, ys),
        "room": spearman(paid, ys),
        "top200": spearman([r.value for r in top], [cwa.get(r.id, 0.0) for r in top]),
        "dollarError": sum(abs(values[pk["playerId"]].ours - cwa_dollars.get(pk["playerId"], 0)) for pk in big) / len(big),
        "roomDollarError": sum(abs(pk["bidAmount"] - cwa_dollars.get(pk["playerId"], 0)) for pk in big) / len(big),
    }


def summarize(results):
    keys = ("drafted", "draftedPearson", "room", "top200", "dollarError", "roomDollarError")
    return {k: sum(r[k] for r in results) / len(results) for k in keys}


def print_scores(label, results):
    print(f"\n{label}")
    print(f"{'season':>7} {'n':>4} {'drafted ρ':>10} {'(pearson)':>10} {'room ρ':>7} {'top200 ρ':>9} {'$ err':>6} {'room $ err':>10}")
    for r in results:
        print(f"{r['season']:>7} {r['n']:>4} {r['drafted']:>10.3f} {r['draftedPearson']:>10.3f} {r['room']:>7.3f} "
              f"{r['top200']:>9.3f} {r['dollarError']:>6.1f} {r['roomDollarError']:>10.1f}")
    m = summarize(results)
    print(f"{'mean':>7} {'':>4} {m['drafted']:>10.3f} {m['draftedPearson']:>10.3f} {m['room']:>7.3f} "
          f"{m['top200']:>9.3f} {m['dollarError']:>6.1f} {m['roomDollarError']:>10.1f}")
    return m


def split_half(season, min_games=15):
    """Reliability of CWA per game: odd weeks vs even weeks, from counted box scores.

    Players need min_games counted games in each half. Returns the half-to-half
    correlation and its Spearman-Brown full-season reliability. The square
    root of the reliability bounds how well anything could correlate with a
    season's per-game CWA.
    """
    lg = League(season)
    halves = defaultdict(lambda: [defaultdict(float), defaultdict(float)])
    for side in load(season, "boxscores.json"):
        period = side["matchupPeriodId"]
        if period > lg.regular:
            continue
        for e in (side.get("rosterForMatchupPeriod") or {}).get("entries", []):
            pid, line = counted_line(e)
            half = halves[pid][period % 2]
            for k in NEEDED + ["GP"]:
                half[k] += line.get(k, 0.0)
    xs, ys = [], []
    for a, b in halves.values():
        if a["GP"] >= min_games and b["GP"] >= min_games:
            xs.append(lg.cwa({k: a[k] / a["GP"] for k in NEEDED}, 1)[0])
            ys.append(lg.cwa({k: b[k] / b["GP"] for k in NEEDED}, 1)[0])
    r = pearson(xs, ys)
    return r, 2 * r / (1 + r), len(xs)


def build_targets():
    pooled_x, pooled_y = [], []
    for season in seasons_available():
        lg = League(season)
        r, r_players, team_cwa, ap = validate(lg)
        mean_ap = sum(ap.values()) / len(ap)
        mean_cwa = sum(team_cwa.values()) / len(team_cwa)
        pooled_x += [team_cwa[t] - mean_cwa for t in ap]
        pooled_y += [ap[t] - mean_ap for t in ap]
        targets = player_targets(lg)
        with open(os.path.join(HERE, str(season), "cwa.json"), "w") as f:
            json.dump({"sigma": lg.sigma, "replacement": lg.replacement, "gamesPerWeek": lg.games_per_week,
                       "players": targets}, f)
        top = sorted(targets.values(), key=lambda p: -p["cwa"])[:5]
        print(f"{season}: team CWA vs all-play r = {r:.3f} (players only {r_players:.3f}) | games/player-week {lg.games_per_week:.2f} | "
              f"top: " + ", ".join(f"{p['name']} {p['cwa']:.1f}" for p in top))
    print(f"pooled (within season): r = {pearson(pooled_x, pooled_y):.3f}")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    if command == "targets":
        build_targets()
    elif command == "baseline":
        print_scores("Baseline: the draft board as saved (tuning seasons with a preseason projection)",
                     [score(s, board_values(s)) for s in PROJECTION_TUNING])
    elif command == "ceiling":
        for season in TUNING:
            r, rel, n = split_half(season)
            print(f"{season}: odd vs even weeks r = {r:.3f}, full-season reliability {rel:.3f}, "
                  f"ceiling on r ~ {math.sqrt(rel):.3f} (n = {n})")
