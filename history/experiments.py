"""Step 4 of docs/BACKTEST_PLAN.md: test candidate changes one at a time.

Every change is scored on the projection tuning seasons (2020-21, 2021-22,
2023-24, 2024-25) against category wins added, with the guards from the plan:

- Anything measured or fitted is measured on the other seasons only
  (leave one season out), never on the season being scored.
- At most one fitted parameter per change, pulled halfway toward today's value.
- A paired bootstrap (players resampled within each season) gives a 95%
  interval on the change.
- Accept on ranking: wins in >= 3 of 4 seasons, mean gain >= 0.02 Spearman,
  interval above 0. Or on dollars, if ranking doesn't get worse: lower dollar
  error in >= 3 of 4 seasons, mean gain >= $0.50, interval above 0.
- Accepted changes stack; later candidates are tested on top of them.
- Every variant tried is logged to history/experiments_log.json.

Nothing here changes library/; variants swap the board's inputs or patch
valuation functions only while they run.

Run: python3.12 history/experiments.py
"""

import contextlib
import json
import random
from types import SimpleNamespace

from backtest import (HERE, LOCKBOX, NEEDED, PERCENT, PROJECTION_TUNING, SEASON_GAMES, TUNING, League, board_shape,
                      load, os, preseason_players, price_curve, score, spearman, truth)
from library import valuation as v
from library.draft import _stat_dict

CATS9 = ["PTS", "BLK", "STL", "AST", "REB", "3PM", "TO", "FT%", "FG%"]
DEFAULT = {"w_espn": 0.0, "gp_scale": None, "gp_shrink": 1.0, "replacement": 95.0, "weights": None, "linear_pct": False,
           "rated": CATS9, "pricing": "board"}
RHO_GAIN, DOLLAR_GAIN, BOOT = 0.02, 0.5, 1000
LOG_PATH = os.path.join(HERE, "experiments_log.json")

_players, _leagues, _actual = {}, {}, {}


def players_for(season):
    if season not in _players:
        _players[season] = preseason_players(season)
    return _players[season]


def league_for(season):
    if season not in _leagues:
        _leagues[season] = League(season)
    return _leagues[season]


def actual_lines(season):
    """Actual per-game line and games for everyone who played that season."""
    if season not in _actual:
        out = {}
        for e in load(season, "players.json")["players"]:
            pl = e["player"]
            sp = next((x for x in pl.get("stats", []) if x.get("id") == f"00{season}"), None)
            if sp:
                pg = _stat_dict(sp.get("averageStats") or {})
                if pg.get("GP"):
                    out[pl["id"]] = pg
        _actual[season] = out
    return _actual[season]


# --------------------------------------------------------------------------
# Rating patches
# --------------------------------------------------------------------------


def linear_percent(player_stats, averages, stat):
    """First-order version of rate_percent_stat: makes above an average shooter on the same attempts."""
    makes_key, attempts_key = v.PERCENT_MAP[stat]
    avg_att, avg_makes = averages.get(attempts_key) or 0, averages.get(makes_key) or 0
    if not avg_att or not avg_makes:
        return 1.0
    attempts = player_stats.get(attempts_key) or 0
    makes = player_stats.get(makes_key)
    if makes is None:
        makes = (player_stats.get(stat) or 0) * attempts
    avg_pct = avg_makes / avg_att
    return 1 + 2 * (makes - avg_pct * attempts) / (avg_pct * avg_att)


@contextlib.contextmanager
def rating_patch(cfg):
    orig_rate, orig_pct = v.rate, v.rate_percent_stat
    if cfg["linear_pct"]:
        v.rate_percent_stat = linear_percent
    if cfg["weights"]:
        weights = cfg["weights"]

        def weighted(player_stats, averages, categories):
            if player_stats is None:
                return 0
            ratings = v.category_ratings(player_stats, averages, categories)
            if not ratings:
                return 0
            den = sum(weights.get(c, 1.0) for c in ratings)
            return sum(weights.get(c, 1.0) * r for c, r in ratings.items()) / den * 100

        v.rate = weighted
    try:
        yield
    finally:
        v.rate, v.rate_percent_stat = orig_rate, orig_pct


# --------------------------------------------------------------------------
# Quantities measured on training seasons
# --------------------------------------------------------------------------


def measured_gp_scale(train):
    """Actual games / ESPN's projected games, over drafted players (82-game basis)."""
    proj = act = 0.0
    for t in train:
        by = {p.id: p for p in players_for(t)}
        lines = actual_lines(t)
        for pk in load(t, "draft.json")["draftDetail"]["picks"]:
            p = by.get(pk["playerId"])
            if p is None or not p.proj_gp:
                continue
            proj += p.proj_gp
            act += lines.get(p.id, {}).get("GP", 0) * 82 / SEASON_GAMES.get(t, 82)
    return act / proj


def actual_baseline(season, cfg):
    shape = board_shape(rated=list(cfg["rated"]))
    pool = [SimpleNamespace(id=pid, base_pg=pg, base_gp=int(pg["GP"]), espn_rank=None)
            for pid, pg in actual_lines(season).items()]
    with rating_patch(cfg):
        return v.compute_baseline(pool, shape), shape


def measured_replacement(train, cfg):
    """Games-weighted rating of every pickup stint: what a free agent actually gave teams."""
    total = games = 0.0
    for t in train:
        lg = league_for(t)
        baseline, shape = actual_baseline(t, cfg)
        with rating_patch(cfg):
            for (team, pid), tot in lg.stints.items():
                gp = tot["GP"]
                if gp <= 0 or lg.drafted_by.get(pid) == team:
                    continue
                line = v.with_percentages({k: tot[k] / gp for k in NEEDED})
                total += v.rate(line, baseline.per_game, shape.rated) * gp
                games += gp
    return total / games


def measured_weights(train, rated):
    """Category weights from the league's win curves: weekly category wins per rating point.

    Counting stat: a rating point is avg/100 of the stat per game, worth
    avg x games_per_week / sigma. Percentages: linearising the rating gives
    (avg% x avg attempts / 2) x games_per_week / (team attempts x sigma).
    Normalised to mean 1 per season, then averaged over seasons.
    """
    acc = {c: 0.0 for c in rated}
    for t in train:
        lg = league_for(t)
        baseline, _ = actual_baseline(t, {**DEFAULT, "rated": rated})
        avg = baseline.per_game
        w = {}
        for c in rated:
            if c in PERCENT:
                m, a = PERCENT[c]
                pct = avg[m] / avg[a]
                w[c] = (pct * avg[a] / 2) * lg.games_per_week / (lg.mean[a] * lg.sigma[c])
            else:
                w[c] = avg[c] * lg.games_per_week / lg.sigma[c]
        mean = sum(w.values()) / len(w)
        for c in rated:
            acc[c] += w[c] / mean / len(train)
    return acc


def training_seasons(season, projection=True):
    pool = PROJECTION_TUNING if projection else TUNING
    return [t for t in pool if t != season]


# --------------------------------------------------------------------------
# Running the board with a configuration
# --------------------------------------------------------------------------


def board_line(p):
    line, lmin, emin = p.rate_line, p.rate_min, p.default_exp_min
    return v.scale(line, emin / lmin) if lmin and emin else dict(line)


def proxies(season, cfg):
    out = []
    w = cfg["w_espn"]
    for p in players_for(season):
        line, lmin, emin = p.rate_line, p.rate_min, p.default_exp_min
        if w and p.proj_pg:
            ours = board_line(p)
            espn = p.proj_pg
            blended = {k: w * espn.get(k, 0.0) + (1 - w) * ours.get(k, 0.0) for k in v.VOLUME_STATS
                       if k in espn or k in ours}
            line, lmin, emin = v.with_percentages(blended), 0, 0
        gp = p.default_exp_gp
        if cfg["gp_shrink"] != 1.0 and p.proj_gp:
            gp = max(0, min(82, round(cfg["gp_mean"] + cfg["gp_shrink"] * (gp - cfg["gp_mean"]))))
        if cfg["gp_scale"]:
            gp = max(0, min(82, round(gp * cfg["gp_scale"])))
        out.append(SimpleNamespace(id=p.id, base_pg=p.base_pg, base_gp=p.base_gp, espn_rank=p.espn_rank,
                                   base_is_projection=p.base_is_projection, default_exp_gp=gp, rate_line=line,
                                   rate_min=lmin, default_exp_min=emin, pro_team=p.pro_team))
    return out


def run(season, cfg):
    players = proxies(season, cfg)
    shape = board_shape(rated=list(cfg["rated"]), replacement=float(cfg["replacement"]))
    with rating_patch(cfg):
        history = [p for p in players if not p.base_is_projection]
        baseline = v.compute_baseline(history, shape)
        rows = v.value_players(players, baseline, shape, {})
    if cfg["pricing"] == "curve":
        curve = cfg["curve"]
        for i, r in enumerate(sorted(rows, key=lambda r: -r.value)):
            r.ours = curve[i] if i < len(curve) else 0.0
    return {r.id: r for r in rows}


# --------------------------------------------------------------------------
# Comparing two configurations
# --------------------------------------------------------------------------


def drafted_arrays(season, values):
    cwa = truth(season)
    picks = [pk for pk in load(season, "draft.json")["draftDetail"]["picks"] if pk["playerId"] in values]
    return [values[pk["playerId"]].value for pk in picks], [cwa.get(pk["playerId"], 0.0) for pk in picks]


def bootstrap(ref_runs, var_runs, seed=7):
    """95% interval of the mean (over seasons) change in drafted Spearman, resampling players."""
    rng = random.Random(seed)
    arrays = []
    for s in ref_runs:
        xr, y = drafted_arrays(s, ref_runs[s])
        xv, _ = drafted_arrays(s, var_runs[s])
        arrays.append((xr, xv, y))
    deltas = []
    for _ in range(BOOT):
        d = 0.0
        for xr, xv, y in arrays:
            idx = [rng.randrange(len(y)) for _ in y]
            yy = [y[i] for i in idx]
            d += spearman([xv[i] for i in idx], yy) - spearman([xr[i] for i in idx], yy)
        deltas.append(d / len(arrays))
    deltas.sort()
    return deltas[int(0.025 * BOOT)], deltas[int(0.975 * BOOT)]


def dollar_bootstrap(ref_scores, var_runs_scores, seed=11):
    """Interval on the mean dollar-error improvement, resampling seasons' pick sets is too coarse;
    use the per-season differences' spread instead (t-style, 4 seasons)."""
    diffs = [ref_scores[s]["dollarError"] - var_runs_scores[s]["dollarError"] for s in ref_scores]
    n = len(diffs)
    mean = sum(diffs) / n
    sd = (sum((d - mean) ** 2 for d in diffs) / (n - 1)) ** 0.5
    half = 3.18 * sd / n ** 0.5  # t(0.975, 3)
    return mean - half, mean + half


def compare(name, ref_cfgs, var_cfgs, note=""):
    """Score a variant against the reference on every projection tuning season."""
    ref_runs = {s: run(s, ref_cfgs[s]) for s in PROJECTION_TUNING}
    var_runs = {s: run(s, var_cfgs[s]) for s in PROJECTION_TUNING}
    ref_sc = {s: score(s, ref_runs[s]) for s in PROJECTION_TUNING}
    var_sc = {s: score(s, var_runs[s]) for s in PROJECTION_TUNING}
    d_rho = {s: var_sc[s]["drafted"] - ref_sc[s]["drafted"] for s in PROJECTION_TUNING}
    d_usd = {s: ref_sc[s]["dollarError"] - var_sc[s]["dollarError"] for s in PROJECTION_TUNING}
    mean_rho = sum(d_rho.values()) / len(d_rho)
    mean_usd = sum(d_usd.values()) / len(d_usd)
    lo, hi = bootstrap(ref_runs, var_runs)
    ulo, uhi = dollar_bootstrap(ref_sc, var_sc)
    rho_wins = sum(d > 0 for d in d_rho.values())
    usd_wins = sum(d > 0 for d in d_usd.values())
    by_rank = rho_wins >= 3 and mean_rho >= RHO_GAIN and lo > 0
    by_dollars = (mean_rho > -0.005 and lo > -RHO_GAIN) and usd_wins >= 3 and mean_usd >= DOLLAR_GAIN and ulo > 0
    accepted = by_rank or by_dollars
    top_price = {s: round(max(r.ours for r in var_runs[s].values())) for s in PROJECTION_TUNING}
    entry = {
        "name": name, "note": note, "accepted": accepted, "acceptedOn": "ranking" if by_rank else "dollars" if by_dollars else None,
        "meanRho": round(sum(x["drafted"] for x in var_sc.values()) / 4, 3),
        "dRho": round(mean_rho, 3), "dRhoCI": [round(lo, 3), round(hi, 3)], "rhoWins": rho_wins,
        "meanDollarError": round(sum(x["dollarError"] for x in var_sc.values()) / 4, 2),
        "dDollar": round(mean_usd, 2), "dDollarCI": [round(ulo, 2), round(uhi, 2)], "dollarWins": usd_wins,
        "bySeason": {s: {"rho": round(var_sc[s]["drafted"], 3), "dRho": round(d_rho[s], 3),
                         "dollarError": round(var_sc[s]["dollarError"], 2), "top200": round(var_sc[s]["top200"], 3),
                         "topPrice": top_price[s]} for s in PROJECTION_TUNING},
        "configs": {s: {k: x for k, x in var_cfgs[s].items() if k != "curve"} for s in PROJECTION_TUNING},
    }
    print(f"{name:44} ρ {entry['meanRho']:.3f} ({mean_rho:+.3f} [{lo:+.3f},{hi:+.3f}], wins {rho_wins}/4) | "
          f"$err {entry['meanDollarError']:5.2f} ({mean_usd:+.2f} [{ulo:+.2f},{uhi:+.2f}], wins {usd_wins}/4) | "
          f"top $ {list(top_price.values())} -> {'ACCEPT (' + entry['acceptedOn'] + ')' if accepted else 'reject'}")
    return entry


# --------------------------------------------------------------------------
# The sequence
# --------------------------------------------------------------------------


def per_season(base, **changes):
    """A config per held-out season; callables get the held-out season."""
    out = {}
    for s in PROJECTION_TUNING:
        cfg = dict(base[s])
        for k, x in changes.items():
            cfg[k] = x(s) if callable(x) else x
        out[s] = cfg
    return out


def fit_blend(current, grid=(0.0, 0.25, 0.5, 0.75, 1.0)):
    """Leave-one-season-out choice of the ESPN weight, shrunk halfway toward 0 (today)."""
    table = {s: {w: score(s, run(s, {**current[s], "w_espn": w}))["drafted"] for w in grid} for s in PROJECTION_TUNING}
    chosen = {}
    for s in PROJECTION_TUNING:
        train = training_seasons(s)
        best = max(grid, key=lambda w: sum(table[t][w] for t in train))
        chosen[s] = (best + DEFAULT["w_espn"]) / 2
    print("  blend grid (drafted ρ by season):")
    for s in PROJECTION_TUNING:
        print(f"    {s}: " + "  ".join(f"w={w:.2f} {table[s][w]:.3f}" for w in grid) + f"  -> uses {chosen[s]:.3f}")
    return chosen, table


def draft_check(before, after):
    """Does the model's edge (Ours - paid) line up with what players earned (CWA $ - paid)?"""
    print("\nDraft check: average (CWA $ - paid) by model edge, all 4 seasons pooled")
    buckets = [(10, 999, "model $10+ above paid"), (3, 10, "$3 to $10 above"), (-3, 3, "within $3"),
               (-10, -3, "$3 to $10 below"), (-999, -10, "model $10+ below paid")]
    for label, cfgs in (("before", before), ("after", after)):
        rows, top84 = [], []
        for s in PROJECTION_TUNING:
            vals = run(s, cfgs[s])
            cwa = truth(s)
            prices = price_curve(s)
            ranked = sorted(cwa, key=lambda pid: -cwa[pid])
            cwa_usd = {pid: (prices[i] if i < len(prices) else 0) for i, pid in enumerate(ranked)}
            for pk in load(s, "draft.json")["draftDetail"]["picks"]:
                r = vals.get(pk["playerId"])
                if r:
                    rows.append((r.ours - pk["bidAmount"], cwa_usd.get(pk["playerId"], 0) - pk["bidAmount"]))
            top = sorted(vals.values(), key=lambda r: -r.value)[:84]
            top84.append(spearman([r.value for r in top], [cwa.get(r.id, 0.0) for r in top]))
        parts = []
        for lo, hi, name in buckets:
            g = [gain for edge, gain in rows if lo <= edge < hi]
            parts.append(f"{name}: {sum(g) / len(g):+.1f} (n {len(g)})" if g else f"{name}: -")
        print(f"  {label:6} top-84 ρ {sum(top84) / len(top84):.3f} | " + " | ".join(parts))


def main():
    log = []
    current = per_season({s: dict(DEFAULT) for s in PROJECTION_TUNING})
    print(f"Reference: the board as saved. Projection tuning seasons {PROJECTION_TUNING}; {LOCKBOX} untouched.\n")

    def step(name, variant, note=""):
        nonlocal current
        entry = compare(name, current, variant, note)
        log.append(entry)
        if entry["accepted"]:
            current = variant
        return entry

    # Candidate 6: the per-game line. ESPN's projection directly (no parameter), then a fitted blend.
    step("6a  ESPN per-game projection (w=1)", per_season(current, w_espn=1.0))
    chosen, table = fit_blend(current)
    entry = step("6b  blend ESPN + board line (LOSO, shrunk)", per_season(current, w_espn=lambda s: chosen[s]),
                 note="grid " + json.dumps({str(s): {str(w): round(r, 3) for w, r in t.items()} for s, t in table.items()}))
    entry["blendChosen"] = chosen

    # Candidate 4: correct ESPN's games by the ratio measured on the other seasons.
    scales = {s: measured_gp_scale(training_seasons(s)) for s in PROJECTION_TUNING}
    print("  games scale by held-out season:", {s: round(x, 3) for s, x in scales.items()})
    step("4   games x measured actual/projected", per_season(current, gp_scale=lambda s: scales[s]))

    # Candidate 4b: pull ESPN's games toward this season's average projection (one parameter).
    def gp_mean(season):
        top = sorted((p for p in players_for(season) if p.proj_gp), key=lambda p: -(p.proj_pg.get("PTS", 0)))[:200]
        return sum(p.proj_gp for p in top) / len(top)
    means = {s: gp_mean(s) for s in PROJECTION_TUNING}
    grid = (1.0, 0.75, 0.5, 0.25, 0.0)
    table = {s: {a: score(s, run(s, {**current[s], "gp_shrink": a, "gp_mean": means[s]}))["drafted"] for a in grid}
             for s in PROJECTION_TUNING}
    shrink = {}
    for s in PROJECTION_TUNING:
        best = max(grid, key=lambda a: sum(table[t][a] for t in training_seasons(s)))
        shrink[s] = (best + 1.0) / 2
    print("  games shrink grid (drafted ρ):")
    for s in PROJECTION_TUNING:
        print(f"    {s}: " + "  ".join(f"a={a:.2f} {table[s][a]:.3f}" for a in grid) + f"  -> uses {shrink[s]:.3f}")
    step("4b  games pulled toward the average (LOSO, shrunk)",
         per_season(current, gp_shrink=lambda s: shrink[s], gp_mean=lambda s: means[s]))

    # Candidate 5: replacement rating measured from pickups on the other seasons.
    repl = {s: measured_replacement(training_seasons(s, projection=False), current[s]) for s in PROJECTION_TUNING}
    print("  replacement by held-out season:", {s: round(x, 1) for s, x in repl.items()})
    step("5   replacement = measured pickup rating", per_season(current, replacement=lambda s: repl[s]))

    # Candidates 1-3: the rating formula.
    weights = {s: measured_weights(training_seasons(s, projection=False), current[s]["rated"]) for s in PROJECTION_TUNING}
    print("  win-curve weights (held out 2025):", {c: round(x, 2) for c, x in weights[PROJECTION_TUNING[-1]].items()})
    step("1   category weights from win curves", per_season(current, weights=lambda s: weights[s]))
    step("2   linear FG%/FT% impact", per_season(current, linear_pct=True))
    no_to = [c for c in CATS9 if c != "TO"]
    step("3   leave TO out of the rating", per_season(current, rated=no_to,
                                                           weights=lambda s: ({c: x for c, x in current[s]["weights"].items() if c != "TO"}
                                                                              if current[s]["weights"] else None)))

    # Pricing: dollars by value rank on the league's average price curve (other seasons).
    curves = {}
    for s in PROJECTION_TUNING:
        lists = [price_curve(t) for t in training_seasons(s, projection=False)]
        curves[s] = [sum(x[i] for x in lists) / len(lists) for i in range(min(len(x) for x in lists))]
    step("7   dollars from the league's price curve", per_season(current, pricing="curve", curve=lambda s: curves[s]))

    # The whole accepted stack against the board as saved.
    baseline = per_season({s: dict(DEFAULT) for s in PROJECTION_TUNING})
    total = compare("ALL accepted changes vs the board as saved", baseline, current)
    total["accepted"] = None
    log.append(total)
    draft_check(baseline, current)

    with open(LOG_PATH, "w") as f:
        json.dump(log, f, indent=1)
    print(f"\nFinal stack: " + ", ".join(e["name"].split()[0] for e in log if e["accepted"]) if any(e["accepted"] for e in log) else "\nNothing accepted.")
    print(f"Logged {len(log)} variants to {LOG_PATH}")




# --------------------------------------------------------------------------
# Step 5: the one check on the held-back season
# --------------------------------------------------------------------------


def final_config(train=TUNING):
    """The accepted stack, with everything measured on the tuning seasons."""
    lists = [price_curve(t) for t in train]
    curve = [sum(x[i] for x in lists) / len(lists) for i in range(min(len(x) for x in lists))]
    return {**DEFAULT, "w_espn": 1.0, "weights": measured_weights(list(train), CATS9), "pricing": "curve", "curve": curve}


def lockbox():
    s = LOCKBOX
    before, after = run(s, dict(DEFAULT)), run(s, final_config())
    b, a = score(s, before), score(s, after)
    arrays = []
    xr, y = drafted_arrays(s, before)
    xv, _ = drafted_arrays(s, after)
    rng = random.Random(7)
    deltas = []
    for _ in range(BOOT):
        idx = [rng.randrange(len(y)) for _ in y]
        yy = [y[i] for i in idx]
        deltas.append(spearman([xv[i] for i in idx], yy) - spearman([xr[i] for i in idx], yy))
    deltas.sort()
    passed = a["drafted"] > b["drafted"] and a["dollarError"] < b["dollarError"]
    result = {"season": s, "before": b, "after": a, "dRhoCI": [deltas[int(.025 * BOOT)], deltas[int(.975 * BOOT)]],
              "topPrice": {"before": max(r.ours for r in before.values()), "after": max(r.ours for r in after.values())},
              "passed": passed}
    with open(os.path.join(HERE, "lockbox_result.json"), "w") as f:
        json.dump(result, f, indent=1)
    print(f"{s} (held back): ranking {b['drafted']:.3f} -> {a['drafted']:.3f} "
          f"({a['drafted'] - b['drafted']:+.3f}, 95% CI [{result['dRhoCI'][0]:+.3f}, {result['dRhoCI'][1]:+.3f}]) | room {b['room']:.3f}")
    print(f"  pearson {b['draftedPearson']:.3f} -> {a['draftedPearson']:.3f} | top-200 {b['top200']:.3f} -> {a['top200']:.3f}")
    print(f"  dollar error ${b['dollarError']:.2f} -> ${a['dollarError']:.2f} | room ${b['roomDollarError']:.2f} | "
          f"top price ${result['topPrice']['before']:.0f} -> ${result['topPrice']['after']:.0f}")
    print("  PASSED" if passed else "  FAILED")
    return result


if __name__ == "__main__":
    import sys
    lockbox() if sys.argv[1:] == ["lockbox"] else main()
