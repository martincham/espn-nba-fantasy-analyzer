"""Games-played model: player-season table, baselines and the two-part model (docs/GAMES_RANGE_PLAN.md).

Run with python3.12 (needs numpy):
    python3.12 history/games_model.py table       build and summarize the player-season table
    python3.12 history/games_model.py diagnose    which inputs relate to games played
    python3.12 history/games_model.py evaluate    leave-one-season-out: baselines vs the model
    python3.12 history/games_model.py fit         fit on every season; prints library/availability.py's Params
    python3.12 history/games_model.py value       leave-one-season-out: does the season-value range cover the actual value?
    python3.12 history/games_model.py team        do fragile drafted rosters do worse than their value says?

Data: history/games/<season>.json, history/bios.json and history/standings.json,
all from history/fetch_games.py. Seasons are ESPN seasonIds (2026 = 2025-26).

Games are put on an 82-game basis: games played / team games x 82, where team
games are the days his team actually played while he was on it. That handles
2019-20 (63-75 games by team) and 2020-21 (72).
"""

import json
import math
import os
import sys
from collections import defaultdict
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

GAMES_DIR = os.path.join(HERE, "games")
SEASONS = tuple(range(2018, 2027))
# Seasons with a usable preseason projection. 2022-23's is a mid-season one
# (see BACKTEST_PLAN), and 2017-18 has no season before it for history.
FOLDS = (2019, 2020, 2021, 2022, 2024, 2025, 2026)
FULL = 82
ROTATION_MIN = 20.0  # a season counts as history when he averaged this many minutes...
ROTATION_PROJ_MIN = 24.0  # ...or ESPN expected him to (so a season lost to injury still counts)
# A major absence: this many team games in a row missed (on an 82-game basis). Scored at 12-50
# (evaluate): CRPS improved steadily up to about 40 and barely after; 40 is "half a season".
MAJOR = 40
SAMPLE_PROJ_MIN = 24.0  # players the model is scored on: ESPN projected at least these minutes


def load_json(path):
    with open(path) as f:
        return json.load(f)


def team_days(players):
    """(team -> set of days) on which the team played, from every player's log."""
    days = defaultdict(set)
    for p in players:
        for day, team, minutes in p["games"]:
            if minutes > 0:
                days[team].add(day)
    return days


def schedule_for(p, days, full_log):
    """The team games while he was on the team, in order, as [(day, played)].

    From 2018-19 ESPN's log lists every team game (missed ones empty), so the
    log is the schedule, minus games the team never played (postponed). For
    2017-18 the log lists only games played: each team he played for counts
    from the day after he left the previous team (or the season start) until
    his last game for it (or the season end, for his last team).
    """
    if full_log:
        return [(d, m > 0) for d, t, m in p["games"] if d in days.get(t, ())]
    played = [(d, t) for d, t, m in p["games"] if m > 0]
    if not played:
        return []
    stints = []  # [team, first day, last day]
    for d, t in played:
        if stints and stints[-1][0] == t:
            stints[-1][2] = d
        else:
            stints.append([t, d, d])
    played_days = {d for d, _ in played}
    out = []
    for i, (t, first, last) in enumerate(stints):
        lo = stints[i - 1][2] + 1 if i else 0
        hi = last if i < len(stints) - 1 else 10 ** 6
        out += [(d, d in played_days) for d in sorted(days.get(t, ())) if lo <= d <= hi]
    return out


def longest_miss(sched):
    best = run = 0
    for _, played in sched:
        run = 0 if played else run + 1
        best = max(best, run)
    return best


def in_rotation(season_row):
    """Whether a season says something about his health rather than his role."""
    return season_row["min"] >= ROTATION_MIN or ((season_row["proj"] or {}).get("MIN") or 0) >= ROTATION_PROJ_MIN


def age_on(dob, season):
    """Age on Oct 15 before the season (float years)."""
    if not dob:
        return None
    y, m, d = map(int, dob.split("-"))
    return (date(season - 1, 10, 15) - date(y, m, d)).days / 365.25


def build_table():
    """One row per player-season with a game log: what happened and what was known before it."""
    bios = load_json(os.path.join(HERE, "bios.json")) if os.path.exists(os.path.join(HERE, "bios.json")) else {}
    standings = load_json(os.path.join(HERE, "standings.json"))
    by_season = {}
    for s in SEASONS:
        path = os.path.join(GAMES_DIR, f"{s}.json")
        if os.path.exists(path):
            by_season[s] = load_json(path)["players"]

    seasons = {}  # (id, season) -> facts about that season
    for s, players in by_season.items():
        days = team_days(players)
        for p in players:
            sched = schedule_for(p, days, full_log=s >= 2019)
            if not sched:
                continue
            gp = sum(1 for _, played in sched if played)
            team_games = len(sched)
            actual = p["actual"] or {}
            played_teams = [t for d, t, m in p["games"] if m > 0]
            seasons[(p["id"], s)] = {
                "id": p["id"], "name": p["name"], "season": s, "gp": gp, "teamGames": team_games,
                "g82": FULL * gp / team_games if team_games else 0.0,
                "min": actual.get("MIN", 0.0), "longest": longest_miss(sched) * FULL / max(team_games, 1),
                "lateMissed": sum(1 for _, played in sched[-15:] if not played),
                "firstTeam": played_teams[0] if played_teams else p["team"],
                "lastTeam": played_teams[-1] if played_teams else p["team"],
                "proj": p["proj"], "pos": p["pos"], "actual": actual,
            }

    rows = []
    for (pid, s), row in seasons.items():
        proj = row["proj"] or {}
        if not proj.get("GP"):
            continue
        # A 72-game season's projection is on a 72-game basis.
        scheduled = 72 if s == 2021 else FULL
        hist = [seasons.get((pid, s - k)) for k in (1, 2, 3, 4)]
        prev = hist[0]
        bio = bios.get(str(pid), {})
        team = row["firstTeam"]
        # The team he started the season with, and its record the season before.
        prior = standings.get(str(s - 1), {}).get(str(team))
        now = standings.get(str(s), {}).get(str(team))
        height, weight = bio.get("height"), bio.get("weight")
        rows.append({
            "id": pid, "name": row["name"], "season": s, "g82": row["g82"], "gp": row["gp"], "teamGames": row["teamGames"],
            "min": row["min"], "longest": row["longest"], "major": row["longest"] >= MAJOR, "lateMissed": row["lateMissed"],
            "proj82": min(FULL, proj["GP"] * FULL / scheduled), "projMin": proj.get("MIN"), "pos": row["pos"],
            "projLine": proj, "actualLine": row["actual"],
            # history: earlier seasons where he was in the rotation
            "hist": [(h["g82"], h["longest"] >= MAJOR) if h and in_rotation(h) else None for h in hist],
            "prevMin": prev["min"] if prev else None,
            "age": age_on(bio.get("dob"), s), "height": height, "weight": weight,
            "bmi": 703 * weight / height ** 2 if height and weight else None,
            "debut": bio.get("debut"),
            "teamPrior": prior["wins"] / (prior["wins"] + prior["losses"]) if prior else None,
            "teamNow": now["wins"] / (now["wins"] + now["losses"]) if now else None,
            "newTeam": bool(prev) and prev["lastTeam"] != team,
            "traded": row["firstTeam"] != row["lastTeam"],
        })
    return rows


def sample(rows):
    """Rows the model is scored on: rotation players ESPN projected before a usable season.

    2019-20's stored projection has games but no minutes, so there last season's minutes pick the rotation.
    """
    return [r for r in rows if r["season"] in FOLDS and (r["projMin"] or r["prevMin"] or 0) >= SAMPLE_PROJ_MIN]


def cmd_table():
    rows = build_table()
    s = sample(rows)
    print(f"{len(rows)} player-seasons with a projection; {len(s)} in the scored sample")
    print("season  n   proj82  g82   bias   major%  missing age  missing height")
    for season in FOLDS:
        g = [r for r in s if r["season"] == season]
        if not g:
            continue
        mean = lambda xs: sum(xs) / len(xs)
        print(f"{season}  {len(g):3d}  {mean([r['proj82'] for r in g]):5.1f}  {mean([r['g82'] for r in g]):5.1f}"
              f"  {mean([r['g82'] - r['proj82'] for r in g]):+5.1f}  {100 * mean([r['major'] for r in g]):5.0f}%"
              f"  {sum(r['age'] is None for r in g):11d}  {sum(r['height'] is None for r in g):14d}")


COMMANDS = {"table": cmd_table}


# ---------------------------------------------------------------- inputs

HIST_WEIGHTS = (1.0, 0.7, 0.5)  # last season counts most


def hist_avail(r):
    """Recency-weighted availability over the last 3 rotation seasons, and how many there were."""
    pairs = [(w, h[0]) for w, h in zip(HIST_WEIGHTS, r["hist"][:3]) if h]
    if not pairs:
        return None, 0
    return sum(w * g for w, g in pairs) / sum(w for w, _ in pairs), len(pairs)


def hist_majors(r):
    """Major absences in the last 4 seasons."""
    return sum(1 for h in r["hist"] if h and h[1])


def experience(r):
    return r["season"] - 1 - r["debut"] if r["debut"] else None


def features(r):
    """Every candidate input, None when unknown."""
    avail, n = hist_avail(r)
    return {
        "proj82": r["proj82"], "histAvail": avail, "histN": n, "histMajors": hist_majors(r),
        "age": r["age"], "height": r["height"], "weight": r["weight"], "bmi": r["bmi"],
        "experience": experience(r), "teamPrior": r["teamPrior"], "newTeam": float(r["newTeam"]),
        "center": float(r["pos"] == 5), "guard": float(r["pos"] in (1, 2)),
        "projMin": r["projMin"] or r["prevMin"],
    }


def corr(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(sxx * syy) if sxx and syy else 0.0


def cmd_diagnose():
    rows = sample(build_table())
    # Compare within a season: each season's bias differs (COVID, lockout-like schedules).
    by_season = defaultdict(list)
    for r in rows:
        by_season[r["season"]].append(r)
    for g in by_season.values():
        mean_res = sum(r["g82"] - r["proj82"] for r in g) / len(g)
        mean_major = sum(r["major"] for r in g) / len(g)
        for r in g:
            r["res"] = r["g82"] - r["proj82"] - mean_res
            r["majorDev"] = r["major"] - mean_major
    feats = [features(r) for r in rows]
    print(f"{len(rows)} player-seasons. r with: ESPN's miss (actual - projected, within season) | major absence | actual games")
    for name in feats[0]:
        pairs = [(f[name], r) for f, r in zip(feats, rows) if f[name] is not None]
        xs = [x for x, _ in pairs]
        print(f"  {name:11s} n={len(pairs):4d}  miss {corr(xs, [r['res'] for _, r in pairs]):+.2f}"
              f"  major {corr(xs, [r['majorDev'] for _, r in pairs]):+.2f}  games {corr(xs, [r['g82'] for _, r in pairs]):+.2f}")

    def table(name, cuts, fmt="{:.0f}"):
        print(f"\n{name}: n, ESPN proj, actual, miss vs season, major%, p10/p50/p90")
        for lo, hi in zip(cuts, cuts[1:]):
            g = [r for f, r in zip(feats, rows) if f[name] is not None and lo <= f[name] < hi]
            if len(g) < 10:
                continue
            a = sorted(r["g82"] for r in g)
            q = lambda p: a[min(len(a) - 1, int(p * len(a)))]
            print(f"  {fmt.format(lo):>5}-{fmt.format(hi):<5} n={len(g):4d}  {sum(r['proj82'] for r in g) / len(g):5.1f}"
                  f"  {sum(a) / len(a):5.1f}  {sum(r['res'] for r in g) / len(g):+5.1f}  {100 * sum(r['major'] for r in g) / len(g):4.0f}%"
                  f"  {q(.1):3.0f}/{q(.5):3.0f}/{q(.9):3.0f}")

    table("proj82", [0, 50, 60, 66, 72, 76, 83])
    table("histAvail", [0, 45, 55, 65, 72, 77, 83])
    table("histMajors", [0, 1, 2, 3, 5])
    table("age", [18, 22, 25, 28, 31, 34, 42])
    table("height", [60, 76, 79, 81, 83, 90])
    table("weight", [150, 200, 215, 230, 245, 260, 330])
    table("bmi", [18, 23, 24.5, 26, 27.5, 35], "{:.1f}")
    table("teamPrior", [0, .35, .45, .55, .65, 1], "{:.2f}")
    table("experience", [0, 1, 3, 6, 10, 25])

    # Team context and timing: missed games in each team's last 15 games, by the team's record that season.
    print("\nLast 15 team games missed, by team record that season (shutdowns)")
    all_rows = [r for r in rows if r["teamNow"] is not None]
    for lo, hi in ((0, .35), (.35, .5), (.5, .6), (.6, 1)):
        g = [r for r in all_rows if lo <= r["teamNow"] < hi]
        print(f"  win% {lo:.2f}-{hi:.2f} n={len(g):4d}  late missed {sum(r['lateMissed'] for r in g) / len(g):4.1f} of 15"
              f"  ({100 * sum(r['lateMissed'] for r in g) / len(g) / 15:.0f}% vs {100 * (1 - sum(r['g82'] for r in g) / len(g) / FULL):.0f}% all season)")


COMMANDS["diagnose"] = cmd_diagnose


# ---------------------------------------------------------------- models
# Every model returns, per row, a probability for each game count 0..82.

import numpy as np  # noqa: E402  (only the fitting needs numpy; library/availability.py doesn't)

GAMES = np.arange(FULL + 1)


def outcome(r):
    return int(round(min(FULL, max(0.0, r["g82"]))))


def empirical_pmf(centers, residuals):
    """Each row's games = its center + a residual drawn from `residuals` (clipped to 0..82)."""
    out = np.zeros((len(centers), FULL + 1))
    res = np.asarray(residuals)
    for i, c in enumerate(centers):
        g = np.clip(np.round(c + res), 0, FULL).astype(int)
        out[i] = np.bincount(g, minlength=FULL + 1) / len(g)
    return out


PROJ_BUCKETS = (0, 60, 66, 72, 76, 83)


def bucket(proj):
    return next(i for i, hi in enumerate(PROJ_BUCKETS[1:]) if proj < hi)


def b0(train, test):
    """ESPN's projection plus one pooled residual distribution: the same shape for everyone."""
    return empirical_pmf([r["proj82"] for r in test], [outcome(r) - r["proj82"] for r in train])


def b1(train, test):
    """Like B0, with residuals from players with a similar projection."""
    out = np.zeros((len(test), FULL + 1))
    for b in range(len(PROJ_BUCKETS) - 1):
        idx = [i for i, r in enumerate(test) if bucket(r["proj82"]) == b]
        if not idx:
            continue
        res = [outcome(r) - r["proj82"] for r in train if bucket(r["proj82"]) == b]
        out[idx] = empirical_pmf([test[i]["proj82"] for i in idx], res)
    return out


def gammaln(x):
    """Vectorized log-gamma (Lanczos), good to ~1e-10 for x > 0."""
    g = 7
    coef = np.array([0.99999999999980993, 676.5203681218851, -1259.1392167224028, 771.32342877765313,
                     -176.61502916214059, 12.507343278686905, -0.13857109526572012,
                     9.9843695780195716e-6, 1.5056327351493116e-7])
    x = np.asarray(x, dtype=float) - 1
    a = coef[0] + sum(coef[i] / (x + i) for i in range(1, g + 2))
    t = x + g + 0.5
    return 0.5 * np.log(2 * np.pi) + (x + 0.5) * np.log(t) - t + np.log(a)


def bb_logpmf(k, a, b, n=FULL):
    """log P(k | n, a, b) for the beta-binomial; k, a, b broadcast."""
    return (gammaln(n + 1) - gammaln(k + 1) - gammaln(n - k + 1)
            + gammaln(k + a) + gammaln(n - k + b) - gammaln(n + a + b)
            + gammaln(a + b) - gammaln(a) - gammaln(b))


def minimize(f, x0, iters=4000, step=0.5, tol=1e-7):
    """Nelder-Mead, enough for a handful of parameters."""
    n = len(x0)
    simplex = [np.array(x0, dtype=float)] + [np.array(x0, dtype=float) + step * np.eye(n)[i] for i in range(n)]
    values = [f(x) for x in simplex]
    for _ in range(iters):
        order = np.argsort(values)
        simplex, values = [simplex[i] for i in order], [values[i] for i in order]
        if abs(values[-1] - values[0]) < tol * (abs(values[0]) + tol):
            break
        centroid = np.mean(simplex[:-1], axis=0)
        reflected = centroid + (centroid - simplex[-1])
        fr = f(reflected)
        if fr < values[0]:
            expanded = centroid + 2 * (centroid - simplex[-1])
            fe = f(expanded)
            simplex[-1], values[-1] = (expanded, fe) if fe < fr else (reflected, fr)
        elif fr < values[-2]:
            simplex[-1], values[-1] = reflected, fr
        else:
            contracted = centroid + 0.5 * (simplex[-1] - centroid)
            fc = f(contracted)
            if fc < values[-1]:
                simplex[-1], values[-1] = contracted, fc
            else:
                simplex = [simplex[0]] + [simplex[0] + 0.5 * (x - simplex[0]) for x in simplex[1:]]
                values = [values[0]] + [f(x) for x in simplex[1:]]
    return simplex[int(np.argmin(values))]


def sigmoid(z):
    return 1 / (1 + np.exp(-z))


class TwoPart:
    """games = mixture of a normal season and a season with a major absence.

    P(major) = sigmoid(x . a). Normal season: beta-binomial with mean
    sigmoid(x . b) and a shared concentration. Major absence: beta-binomial
    with mean sigmoid(c0 + c1 * proj) and its own concentration. x is an
    intercept, ESPN's projection and the chosen inputs, standardized on the
    training rows (a missing input is set to its training mean).
    """

    def __init__(self, inputs=()):
        self.inputs = ["proj82"] + list(inputs)

    def design(self, rows):
        cols = []
        for name in self.inputs:
            col = np.array([features(r)[name] if features(r)[name] is not None else np.nan for r in rows], dtype=float)
            cols.append(col)
        x = np.column_stack(cols)
        if not hasattr(self, "mean"):
            self.mean, self.sd = np.nanmean(x, axis=0), np.nanstd(x, axis=0) + 1e-9
        x = np.where(np.isnan(x), self.mean, x)
        return np.column_stack([np.ones(len(rows)), (x - self.mean) / self.sd])

    def fit(self, rows):
        x = self.design(rows)
        k = np.array([outcome(r) for r in rows], dtype=float)
        major = np.array([r["major"] for r in rows], dtype=float)
        d = x.shape[1]
        # P(major): logistic regression (lightly penalized so a useless input stays near 0)
        nll_p = lambda a: -np.sum(major * (x @ a) - np.logaddexp(0, x @ a)) + 0.5 * np.sum(a[1:] ** 2)
        self.a = minimize(nll_p, np.zeros(d))
        # normal seasons
        xn, kn = x[major == 0], k[major == 0]

        def nll_n(theta):
            mu, phi = sigmoid(xn @ theta[:d]), np.exp(theta[d])
            return -np.sum(bb_logpmf(kn, mu * phi, (1 - mu) * phi)) + 0.5 * np.sum(theta[1:d] ** 2)
        theta = minimize(nll_n, np.r_[1.5, np.zeros(d - 1), np.log(20.0)])
        self.b, self.phi_n = theta[:d], np.exp(theta[d])
        # seasons with a major absence
        xm, km = x[major == 1][:, :2], k[major == 1]

        def nll_m(theta):
            mu, phi = sigmoid(xm @ theta[:2]), np.exp(theta[2])
            return -np.sum(bb_logpmf(km, mu * phi, (1 - mu) * phi))
        theta = minimize(nll_m, np.r_[0.0, 0.0, np.log(3.0)])
        self.c, self.phi_m = theta[:2], np.exp(theta[2])
        return self

    def pmf(self, rows):
        x = self.design(rows)
        p = sigmoid(x @ self.a)[:, None]
        mu_n = sigmoid(x @ self.b)[:, None]
        mu_m = sigmoid(x[:, :2] @ self.c)[:, None]
        normal = np.exp(bb_logpmf(GAMES[None, :], mu_n * self.phi_n, (1 - mu_n) * self.phi_n))
        major = np.exp(bb_logpmf(GAMES[None, :], mu_m * self.phi_m, (1 - mu_m) * self.phi_m))
        return (1 - p) * normal + p * major


def two_part(inputs=()):
    return lambda train, test: TwoPart(inputs).fit(train).pmf(test)


# ---------------------------------------------------------------- scoring

def crps(pmf, k):
    """Continuous ranked probability score on 0..82, per row (lower is better)."""
    cdf = np.cumsum(pmf, axis=1)
    step = (GAMES[None, :] >= np.asarray(k)[:, None]).astype(float)
    return np.sum((cdf - step) ** 2, axis=1)


def quantile(pmf, q):
    cdf = np.cumsum(pmf, axis=1)
    return np.argmax(cdf >= q - 1e-12, axis=1)


def scores(pmf, rows):
    k = np.array([outcome(r) for r in rows])
    lo10, hi90, lo25, hi75 = (quantile(pmf, q) for q in (0.1, 0.9, 0.25, 0.75))
    p_half = pmf[:, :41].sum(axis=1)
    return {
        "crps": crps(pmf, k), "in80": (k >= lo10) & (k <= hi90), "in50": (k >= lo25) & (k <= hi75),
        "width80": hi90 - lo10, "pHalf": p_half, "half": k < 41,
    }


def loso(model, rows):
    """Leave one season out: fit on the other folds, score the held-out one."""
    out = {}
    for season in FOLDS:
        train = [r for r in rows if r["season"] != season]
        test = [r for r in rows if r["season"] == season]
        out[season] = scores(model(train, test), test)
    return out


def summarize(name, result, base=None):
    crps_all = np.concatenate([result[s]["crps"] for s in FOLDS])
    line = (f"{name:28s} CRPS {crps_all.mean():6.3f}"
            f"  in 80% {100 * np.concatenate([result[s]['in80'] for s in FOLDS]).mean():4.1f}%"
            f"  in 50% {100 * np.concatenate([result[s]['in50'] for s in FOLDS]).mean():4.1f}%"
            f"  80% width {np.concatenate([result[s]['width80'] for s in FOLDS]).mean():4.1f}")
    if base is not None:
        diff = np.concatenate([base[s]["crps"] - result[s]["crps"] for s in FOLDS])  # > 0: better than base
        wins = sum((base[s]["crps"] - result[s]["crps"]).mean() > 0 for s in FOLDS)
        rng = np.random.default_rng(0)
        boot = [rng.choice(diff, len(diff)).mean() for _ in range(2000)]
        line += f"  gain {diff.mean():+.3f} [{np.percentile(boot, 2.5):+.3f}, {np.percentile(boot, 97.5):+.3f}] wins {wins}/{len(FOLDS)}"
    print(line)


def tail_table(result):
    p = np.concatenate([result[s]["pHalf"] for s in FOLDS])
    y = np.concatenate([result[s]["half"] for s in FOLDS])
    print("    P(under 41 games): predicted vs observed")
    for lo, hi in ((0, .1), (.1, .2), (.2, .35), (.35, 1.01)):
        m = (p >= lo) & (p < hi)
        if m.sum():
            print(f"      {lo:.2f}-{hi:.2f}: n={m.sum():4d}  predicted {100 * p[m].mean():4.1f}%  observed {100 * y[m].mean():4.1f}%")


CANDIDATES = ("histAvail", "histMajors", "teamPrior", "age", "height", "weight", "bmi", "experience", "newTeam",
              "projMin", "center", "guard")


def cmd_evaluate():
    global MAJOR
    rows = sample(build_table())
    print(f"{len(rows)} player-seasons, folds {FOLDS}\n")
    chosen, base = MAJOR, loso(b1, rows)
    print("Major-absence length (two-part, ESPN only, gain vs B1):")
    for MAJOR in (12, 20, 30, 40, 50):
        summarize(f"  {MAJOR}+ games in a row", loso(two_part(), sample(build_table())), base)
    MAJOR = chosen
    rows = sample(build_table())
    print()
    base0 = loso(b0, rows)
    summarize("B0 pooled residuals", base0)
    base1 = loso(b1, rows)
    summarize("B1 residuals by projection", base1, base0)
    m0 = loso(two_part(), rows)
    summarize("Two-part, ESPN only", m0, base1)
    tail_table(m0)
    print("\nEach input added alone to the two-part model (gain vs two-part ESPN only):")
    for name in CANDIDATES:
        summarize(f"  + {name}", loso(two_part([name]), rows), m0)


COMMANDS["evaluate"] = cmd_evaluate

# ---------------------------------------------------------------- per-game rating and season value

from library import availability as av  # noqa: E402
from library import valuation as v  # noqa: E402

RATED = ["PTS", "REB", "AST", "STL", "BLK", "3PM", "TO", "FG%", "FT%"]
REPLACEMENT = 95.0


def _line(stats):
    stats = dict(stats)
    return v.with_percentages(stats) if "FGA" in stats else stats


def add_ratings(rows, all_rows):
    """Projected and actual per-game ratings on the board's weighted rating, against each season's top 156."""
    averages = {}
    for season in {r["season"] for r in rows}:
        pool = sorted((r for r in all_rows if r["season"] == season and (r["actualLine"] or {}).get("MIN")),
                      key=lambda r: -r["actualLine"]["MIN"] * r["gp"])[:156]
        averages[season] = v.pool_averages([(_line(r["actualLine"]), r["gp"]) for r in pool])[0]
    for r in rows:
        proj, actual = r["projLine"] or {}, r["actualLine"] or {}
        ok = "PTS" in proj and r["gp"] > 0 and actual.get("MIN")  # 2019-20's projection has no stat line
        r["projRating"] = v.rate(_line(proj), averages[r["season"]], RATED, v.CATEGORY_WEIGHTS) if ok else None
        r["actualRating"] = v.rate(_line(actual), averages[r["season"]], RATED, v.CATEGORY_WEIGHTS) if ok else None
    return rows


def fit_rating_error(rows):
    """rating error = bias + slope x (games - projected), noise variance = v0 + v1 / games."""
    use = [r for r in rows if r["projRating"] is not None and r["gp"] >= 5]
    x = np.array([r["g82"] - r["proj82"] for r in use])
    y = np.array([r["actualRating"] - r["projRating"] for r in use])
    g = np.array([r["g82"] for r in use])
    bias, slope = np.linalg.lstsq(np.column_stack([np.ones_like(x), x]), y, rcond=None)[0]
    res = y - bias - slope * x
    v0, v1 = np.linalg.lstsq(np.column_stack([np.ones_like(g), 1 / np.maximum(g, 1)]), res ** 2, rcond=None)[0]
    return float(bias), float(slope), (float(max(v0, 1.0)), float(max(v1, 0.0)))


def params_for(rows):
    """library.availability.Params fitted on these rows (ESPN projection only)."""
    m = TwoPart().fit(rows)
    bias, slope, var = fit_rating_error(rows)
    return av.Params(
        proj_mean=float(m.mean[0]), proj_sd=float(m.sd[0]), major=tuple(float(x) for x in m.a),
        normal_mean=tuple(float(x) for x in m.b), normal_phi=float(m.phi_n),
        major_mean=tuple(float(x) for x in m.c), major_phi=float(m.phi_m),
        rating_bias=bias, rating_slope=slope, rating_var=var)


def cmd_fit():
    all_rows = build_table()
    rows = add_ratings(sample(all_rows), all_rows)
    params = params_for(rows)
    print(f"Fitted on {len(rows)} player-seasons, major absence = {MAJOR}+ games in a row. For library/availability.py:\n")
    for name, value in params.__dict__.items():
        shown = tuple(round(x, 4) for x in value) if isinstance(value, tuple) else round(value, 4)
        print(f"    {name} = {shown}")
    # the library must reproduce the fitted model
    m = TwoPart().fit(rows)
    diff = max(abs(a - b) for r, row in zip(m.pmf(rows[:50]), rows[:50])
               for a, b in zip(r, av.games_range(row["proj82"], params=params).pmf))
    print(f"\nlargest difference, library vs fitted model: {diff:.2e}")


def cmd_value():
    """Held out one season at a time: does the season-value range cover what happened?"""
    all_rows = build_table()
    rows = add_ratings(sample(all_rows), all_rows)
    hits = defaultdict(list)
    print("season   n   in 80%   in 50%   games-only in 80%   80% width (value pts)")
    for season in FOLDS:
        train = [r for r in rows if r["season"] != season]
        test = [r for r in rows if r["season"] == season and r["projRating"] is not None]
        if not test:
            continue
        params = params_for(train)
        still = av.Params(**{**params.__dict__, "rating_var": (1e-6, 0.0), "rating_slope": 0.0, "rating_bias": 0.0})
        row_hits = defaultdict(list)
        for r in test:
            actual = v.season_value(r["actualRating"], r["g82"], REPLACEMENT)
            games = av.games_range(r["proj82"], params=params)
            for label, p in (("full", params), ("games", still)):
                lo10, lo25, hi75, hi90 = av.quantiles(av.value_range(r["projRating"], games, REPLACEMENT, p), (.1, .25, .75, .9))
                row_hits[label + "80"].append(lo10 <= actual <= hi90)
                row_hits[label + "50"].append(lo25 <= actual <= hi75)
                row_hits[label + "w"].append(hi90 - lo10)
        for k, xs in row_hits.items():
            hits[k] += xs
        print(f"{season}  {len(test):4d}   {100 * np.mean(row_hits['full80']):4.0f}%    {100 * np.mean(row_hits['full50']):4.0f}%"
              f"   {100 * np.mean(row_hits['games80']):4.0f}%                 {np.mean(row_hits['fullw']):4.1f}")
    print(f"all    {len(hits['full80']):5d}   {100 * np.mean(hits['full80']):4.0f}%    {100 * np.mean(hits['full50']):4.0f}%"
          f"   {100 * np.mean(hits['games80']):4.0f}%  (games-only width {np.mean(hits['gamesw']):.1f})"
          f"       {np.mean(hits['fullw']):4.1f}")


COMMANDS["fit"] = cmd_fit
COMMANDS["value"] = cmd_value

# ---------------------------------------------------------------- team level

LEAGUE_SEASONS = (2021, 2022, 2024, 2025, 2026)  # league drafts with a usable preseason projection


def team_draws(players, params, draws=2000, seed=3):
    """Draws of a roster's summed season value: each player's games and rating error, independently."""
    rng = np.random.default_rng(seed)
    total = np.zeros(draws)
    for proj82, rating in players:
        games = av.games_range(proj82, params=params)
        g = rng.choice(FULL + 1, size=draws, p=np.array(games.pmf) / sum(games.pmf))
        sd = np.sqrt(params.rating_var[0] + params.rating_var[1] / np.maximum(g, 1))
        error = params.rating_bias + params.rating_slope * (g - games.projected) + rng.normal(0, 1, draws) * sd
        total += REPLACEMENT + (rating + error - REPLACEMENT) * g / FULL
    return total


def cmd_team():
    """Does a fragile drafted roster do worse than its expected value says? (all-play category wins)"""
    import analyze
    all_rows = build_table()
    by_key = {(r["id"], r["season"]): r for r in add_ratings([r for r in all_rows if r["season"] in LEAGUE_SEASONS], all_rows)}
    scored = sample(all_rows)
    out = []
    for season in LEAGUE_SEASONS:
        params = params_for(add_ratings([r for r in scored if r["season"] != season], all_rows))  # held out
        d = analyze.season_data(season)
        analyze.score_stints(d)
        analyze.all_play(d)
        teams = []
        for t in d.teams.values():
            players = []
            for pick in t.picks:
                r = by_key.get((pick["playerId"], season))
                if r and r["projRating"] is not None:
                    players.append((r["proj82"], r["projRating"]))
            point = sum(v.season_value(rt, g, REPLACEMENT) for g, rt in players)
            draws = team_draws(players, params)
            teams.append({"season": season, "allplay": t.allplay, "point": point, "mean": draws.mean(),
                          "gap": draws.mean() - np.percentile(draws, 10),
                          "half": sum(av.games_range(g, params=params).p_half for g, _ in players), "n": len(players)})
        for key in ("allplay", "point", "mean", "gap", "half"):  # compare within a season
            m = np.mean([x[key] for x in teams])
            for x in teams:
                x[key + "C"] = x[key] - m
        out += teams
    y = np.array([x["allplayC"] for x in out])
    print(f"{len(out)} team-seasons ({', '.join(map(str, LEAGUE_SEASONS))}); drafted players matched: "
          f"{np.mean([x['n'] for x in out]):.1f} per team")
    for key, label in (("point", "board value (ESPN games)"), ("mean", "model mean value"), ("gap", "downside (mean - p10)"),
                       ("half", "expected half-season losses")):
        print(f"  r(all-play wins, {label:28s}) = {np.corrcoef([x[key + 'C'] for x in out], y)[0, 1]:+.2f}")
    # beyond draft-day value: residual after the board's value
    point = np.array([x["pointC"] for x in out])
    slope = np.polyfit(point, y, 1)
    resid = y - np.polyval(slope, point)
    rng = np.random.default_rng(5)
    for key, label in (("gap", "downside"), ("half", "half-season losses")):
        f = np.array([x[key + "C"] for x in out])
        f = f - np.polyval(np.polyfit(point, f, 1), point)  # the part not explained by value
        r = np.corrcoef(f, resid)[0, 1]
        boot = []
        for _ in range(2000):
            i = rng.integers(0, len(out), len(out))
            boot.append(np.corrcoef(f[i], resid[i])[0, 1])
        print(f"  partial r({label}, all-play | board value) = {r:+.2f}  [95% CI {np.percentile(boot, 2.5):+.2f}, {np.percentile(boot, 97.5):+.2f}]")


COMMANDS["team"] = cmd_team

if __name__ == "__main__":
    COMMANDS[(sys.argv[1:2] or ["table"])[0]]()
