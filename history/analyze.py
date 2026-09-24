"""Why did the top teams win? Standings, drafts and where each team's production came from.

Run with python3.12 (it needs espn_api for the stat names): python3.12 history/analyze.py
Reads history/<season>/*.json from fetch_history.py and writes standings.csv,
draft.csv and analysis.json into each season's folder.

Player value uses the draft board's model (library/valuation.py) on all 9
league categories: a per-game rating where 100 is the average of the top 144,
over 82 games with missed games filled at a 95 replacement, priced so the
league's $2,400 goes to each team's top 7. "Projected" runs it on ESPN's
preseason projection, "Earned" on the player's actual season.
"""

import csv
import json
import math
import os
import sys
from collections import defaultdict
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from library import valuation as v  # noqa: E402
from library.draft import PRO_TEAM_MAP, _stat_dict  # noqa: E402

SEASONS = (2024, 2025, 2026)
CATS = ["PTS", "REB", "AST", "STL", "BLK", "3PM", "TO", "FG%", "FT%"]
CAT_IDS = {"PTS": "0", "REB": "6", "AST": "3", "STL": "2", "BLK": "1", "3PM": "17", "TO": "11", "FG%": "19", "FT%": "20"}
SHAPE = v.LeagueShape(teams=12, budget=200, roster_size=12, categories=CATS, rated=CATS, core=7, replacement=95)


def load(season, name):
    with open(os.path.join(HERE, str(season), name)) as f:
        return json.load(f)


def split(player, split_id):
    for s in player.get("stats", []):
        if s.get("id") == split_id:
            return _stat_dict(s.get("averageStats") or {})
    return {}


def season_data(season):
    league, draft = load(season, "league.json"), load(season, "draft.json")
    matchups, box, pool = load(season, "matchups.json"), load(season, "boxscores.json"), load(season, "players.json")
    regular = league["settings"]["scheduleSettings"]["matchupPeriodCount"]

    # ---- players: projected and actual per-game lines
    players = {}
    for entry in pool["players"]:
        pl = entry["player"]
        actual, proj = split(pl, f"00{season}"), split(pl, f"10{season}")
        players[pl["id"]] = SimpleNamespace(
            id=pl["id"], name=pl["fullName"], nba=PRO_TEAM_MAP.get(pl.get("proTeamId"), "FA"),
            actual=actual, gp=int(actual.get("GP", 0)), proj=proj, proj_gp=int(round(proj.get("GP", 0))),
            base_pg=actual, base_gp=int(actual.get("GP", 0)),
            espn_rank=(pl.get("draftRanksByRankType", {}).get("STANDARD", {}) or {}).get("rank"),
        )
    baseline = v.compute_baseline(list(players.values()), SHAPE)
    avg = baseline.per_game

    for p in players.values():
        p.rating = v.rate(p.actual, avg, CATS) if p.gp else None
        p.proj_rating = v.rate(p.proj, avg, CATS) if p.proj_gp else None
        p.value = v.season_value(p.rating, p.gp, SHAPE.replacement) if p.rating is not None else None
        p.proj_value = v.season_value(p.proj_rating, p.proj_gp, SHAPE.replacement) if p.proj_rating is not None else None
    # Dollars by rank on this league's own price curve: the Nth most valuable
    # player is worth what the league paid for its Nth most expensive pick.
    prices = sorted((pick["bidAmount"] for pick in draft["draftDetail"]["picks"]), reverse=True)
    for attr, dollars in (("value", "earned"), ("proj_value", "projected")):
        ranked = sorted((p for p in players.values() if getattr(p, attr) is not None), key=lambda p: -getattr(p, attr))
        for p in players.values():
            setattr(p, dollars, 0.0 if attr == "value" else None)
        for i, p in enumerate(ranked):
            setattr(p, dollars, float(prices[i]) if i < len(prices) else 0.0)
            setattr(p, "rank" if attr == "value" else "proj_rank", i + 1)

    # ---- teams, standings
    members = {m["id"]: m for m in league["members"]}
    teams = {}
    for t in league["teams"]:
        owner = members.get(t.get("primaryOwner"), {})
        rec = t["record"]["overall"]
        teams[t["id"]] = SimpleNamespace(
            id=t["id"], name=" ".join(t["name"].split()), manager=owner.get("displayName", "?"), owner=t.get("primaryOwner"),
            wins=rec["wins"], losses=rec["losses"], ties=rec["ties"],
            pct=(rec["wins"] + rec["ties"] / 2) / max(1, rec["wins"] + rec["losses"] + rec["ties"]),
            seed=t.get("playoffSeed"), final=t.get("rankCalculatedFinal"),
            adds=t["transactionCounter"]["acquisitions"], moves=t["transactionCounter"]["moveToActive"],
            ir_moves=t["transactionCounter"]["moveToIR"],
            picks=[], stints={}, cat_record={c: [0, 0, 0] for c in CATS}, week_totals=defaultdict(float),
        )

    # ---- draft
    for pick in draft["draftDetail"]["picks"]:
        teams[pick["teamId"]].picks.append(pick)
    drafted_by = {pick["playerId"]: pick["teamId"] for pick in draft["draftDetail"]["picks"]}

    # ---- category records (regular season)
    for m in matchups["schedule"]:
        if m["matchupPeriodId"] > regular:
            continue
        for side in ("home", "away"):
            s = m.get(side)
            if not s or not s.get("cumulativeScore"):
                continue
            by_stat = s["cumulativeScore"].get("scoreByStat") or {}
            for c in CATS:
                result = (by_stat.get(CAT_IDS[c]) or {}).get("result")
                if result:
                    teams[s["teamId"]].cat_record[c][{"WIN": 0, "LOSS": 1, "TIE": 2}[result]] += 1

    # ---- what each player produced for each team (regular season, counted stats only)
    for side in box:
        if side["matchupPeriodId"] > regular:
            continue
        team = teams[side["teamId"]]
        for e in (side.get("rosterForMatchupPeriod") or {}).get("entries", []):
            pl = e["playerPoolEntry"]["player"]
            line = next((s["stats"] for s in pl.get("stats", []) if s.get("statSourceId") == 0), None)
            if not line:
                continue
            stint = team.stints.setdefault(pl["id"], {"totals": defaultdict(float), "weeks": 0, "name": pl["fullName"]})
            stint["weeks"] += 1
            for k, val in _stat_dict(line).items():
                if k in v.VOLUME_STATS or k == "GP":
                    stint["totals"][k] += val
    return SimpleNamespace(season=season, league=league, players=players, teams=teams, avg=avg,
                           drafted_by=drafted_by, regular=regular, prices=prices)


def score_stints(d):
    """Rate what each player produced for each team, against a typical pickup.

    A stint's value is (rating - R) x games / 100: extra games of an average
    (100) player, where R is the games-weighted rating of every pickup stint
    that season, i.e. what a free agent actually gave these teams.
    """
    pickups = []
    for t in d.teams.values():
        for pid, s in t.stints.items():
            tot = v.with_percentages(dict(s["totals"]))
            s["gp"] = gp = tot.get("GP", 0)
            s["rating"] = v.rate(v.scale(tot, 1 / gp), d.avg, CATS) if gp else 0.0
            s["source"] = "Draft" if d.drafted_by.get(pid) == t.id else "Pickup"
            if s["source"] == "Pickup" and gp:
                pickups.append((s["rating"], gp))
    d.replacement = sum(r * g for r, g in pickups) / sum(g for _, g in pickups)
    for t in d.teams.values():
        for s in t.stints.values():
            s["var"] = (s["rating"] - d.replacement) * s["gp"] / 100
        t.var_draft = sum(s["var"] for s in t.stints.values() if s["source"] == "Draft")
        t.var_pickup = sum(s["var"] for s in t.stints.values() if s["source"] == "Pickup")
        t.var = t.var_draft + t.var_pickup
        t.gp = sum(s["gp"] for s in t.stints.values())
        t.gp_pickup = sum(s["gp"] for s in t.stints.values() if s["source"] == "Pickup")
        t.spent = sum(p["bidAmount"] for p in t.picks)
        t.proj = sum(d.players[p["playerId"]].projected or 0 for p in t.picks if p["playerId"] in d.players)
        t.earned = sum(d.players[p["playerId"]].earned for p in t.picks if p["playerId"] in d.players)
        t.cat_wins = t.wins + t.ties / 2


def fit(xs, ys):
    """Least squares y = a + b x; returns (a, b, r)."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    syy = sum((y - my) ** 2 for y in ys)
    b = sxy / sxx
    return my - b * mx, b, sxy / math.sqrt(sxx * syy)


def share_of_spread(parts, total):
    """Each part's share of the variance of total = sum(parts): cov(part, total) / var(total)."""
    n = len(total)
    mt = sum(total) / n
    var = sum((x - mt) ** 2 for x in total)
    out = {}
    for name, xs in parts.items():
        mx = sum(xs) / n
        out[name] = sum((x - mx) * (y - mt) for x, y in zip(xs, total)) / var
    return out


def team_production(d):
    """Production = rating x games / 100 over everything that counted: games of an average player."""
    for t in d.teams.values():
        t.prod = sum(s["rating"] * s["gp"] / 100 for s in t.stints.values())
        t.prod_draft = sum(s["rating"] * s["gp"] / 100 for s in t.stints.values() if s["source"] == "Draft")
        t.prod_pickup = t.prod - t.prod_draft


def all_play(d):
    """Category wins a team would expect against a random opponent each week.

    Compares each week's category totals with all 11 other teams; the gap
    between actual and all-play category wins is schedule luck.
    """
    weekly = defaultdict(dict)
    for m in load(d.season, "matchups.json")["schedule"]:
        if m["matchupPeriodId"] > d.regular:
            continue
        for side in ("home", "away"):
            s = m.get(side)
            if s and s.get("cumulativeScore"):
                by_stat = s["cumulativeScore"].get("scoreByStat") or {}
                weekly[m["matchupPeriodId"]][s["teamId"]] = {c: (by_stat.get(CAT_IDS[c]) or {}).get("score") for c in CATS}
    wins = defaultdict(float)
    for teams in weekly.values():
        for a, sa in teams.items():
            for b, sb in teams.items():
                for c in CATS:
                    x, y = sa[c], sb[c]
                    if a == b or x is None or y is None:
                        continue
                    wins[a] += 0.5 if x == y else float((x < y) if c == "TO" else (x > y))
    for t in d.teams.values():
        t.allplay = wins[t.id] / (len(d.teams) - 1)
        t.luck = t.cat_wins - t.allplay


def pickup_dates(d, season):
    """First date each player was added by each team."""
    added = {}
    for tx in load(season, "transactions.json"):
        if tx.get("status") != "EXECUTED" or tx.get("type") not in ("FREEAGENT", "WAIVER"):
            continue
        for item in tx.get("items", []):
            if item.get("type") == "ADD":
                key = (item["toTeamId"], item["playerId"])
                added[key] = min(added.get(key, tx["proposedDate"]), tx["proposedDate"])
    return added


def rank_of(teams, attr, reverse=True):
    ordered = sorted(teams, key=lambda t: getattr(t, attr), reverse=reverse)
    return {t.id: i + 1 for i, t in enumerate(ordered)}


def r1(x, digits=1):
    return None if x is None else (int(round(x)) if digits == 0 else round(x, digits))


def season_report(d):
    import datetime
    teams = list(d.teams.values())
    added = pickup_dates(d, d.season)
    ranks = {a: rank_of(teams, a) for a in ("cat_wins", "allplay", "prod", "prod_draft", "prod_pickup", "gp", "gp_pickup", "adds", "moves", "proj", "earned", "var")}
    avg = {a: sum(getattr(t, a) for t in teams) / len(teams) for a in ("cat_wins", "allplay", "prod", "prod_draft", "prod_pickup", "gp", "gp_pickup", "adds", "moves", "proj", "earned")}

    draft_rows = []
    for pick in sorted(load(d.season, "draft.json")["draftDetail"]["picks"], key=lambda p: p["overallPickNumber"]):
        p, t = d.players.get(pick["playerId"]), d.teams[pick["teamId"]]
        stint = t.stints.get(pick["playerId"], {})
        draft_rows.append({
            "pick": pick["overallPickNumber"], "team": t.name, "teamId": t.id, "player": p.name if p else str(pick["playerId"]),
            "nba": p.nba if p else "", "paid": pick["bidAmount"],
            "projected": r1(p.projected, 0) if p else None, "earned": r1(p.earned, 0) if p else 0,
            "projRating": r1(p.proj_rating) if p else None, "rating": r1(p.rating) if p else None,
            "projGp": p.proj_gp if p else None, "gp": p.gp if p else 0,
            "gpForTeam": int(stint.get("gp", 0)),
        })

    team_rows = []
    for t in sorted(teams, key=lambda t: -t.cat_wins):
        stints = []
        for pid, s in t.stints.items():
            p = d.players.get(pid)
            pick = next((k for k in t.picks if k["playerId"] == pid), None)
            when = added.get((t.id, pid))
            stints.append({
                "player": s["name"], "source": s["source"], "gp": int(s["gp"]), "weeks": s["weeks"],
                "rating": r1(s["rating"]), "var": r1(s["var"]), "prod": r1(s["rating"] * s["gp"] / 100),
                "paid": pick["bidAmount"] if pick else None,
                "projected": r1(p.projected, 0) if p and p.projected is not None else None,
                "earned": r1(p.earned, 0) if p else None,
                "projRating": r1(p.proj_rating) if p else None, "seasonRating": r1(p.rating) if p else None,
                "projGp": p.proj_gp if p else None, "seasonGp": p.gp if p else None,
                "added": datetime.date.fromtimestamp(when / 1000).isoformat() if when else None,
            })
        stints.sort(key=lambda s: -s["var"])
        team_rows.append({
            "id": t.id, "name": t.name, "manager": t.manager, "owner": t.owner, "wins": t.wins, "losses": t.losses, "ties": t.ties,
            "pct": round(t.pct, 3), "seed": t.seed, "final": t.final, "catWins": t.cat_wins,
            "allPlay": round(t.allplay, 1), "luck": round(t.luck, 1),
            "catRecord": t.cat_record, "spent": t.spent,
            "proj": round(t.proj), "earned": round(t.earned), "prod": round(t.prod), "prodDraft": round(t.prod_draft),
            "prodPickup": round(t.prod_pickup), "gp": int(t.gp), "gpPickup": int(t.gp_pickup),
            "adds": t.adds, "moves": t.moves, "irMoves": t.ir_moves,
            "ranks": {a: r[t.id] for a, r in ranks.items()}, "stints": stints,
        })
    names = {t.id: t.name for t in teams}
    playoffs = []
    for m in load(d.season, "matchups.json")["schedule"]:
        if m.get("playoffTierType") == "WINNERS_BRACKET" and m.get("away"):
            h, a = m["home"], m["away"]
            hs = h.get("cumulativeScore") or {}
            playoffs.append({"round": "Final" if m["matchupPeriodId"] == max(x["matchupPeriodId"] for x in load(d.season, "matchups.json")["schedule"]) else "Semifinal",
                             "home": names[h["teamId"]], "away": names[a["teamId"]],
                             "score": f'{hs.get("wins", 0)}-{hs.get("losses", 0)}-{hs.get("ties", 0)}',
                             "winner": names[h["teamId"]] if m["winner"] == "HOME" else names[a["teamId"]]})
    return {"season": d.season, "playoffs": playoffs, "label": f"{d.season - 1}-{d.season % 100:02d}", "replacement": round(d.replacement, 1),
            "averages": {k: round(x, 1) for k, x in avg.items()}, "teams": team_rows, "draft": draft_rows}


def write_csvs(report):
    folder = os.path.join(HERE, str(report["season"]))
    with open(os.path.join(folder, "standings.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Rank", "Team", "Manager", "Cat W", "Cat L", "Cat T", "Win %", "All-play cat W", "Schedule luck",
                    "Drafted $ spent", "Draft projected $", "Draft earned $", "Production", "From draft", "From pickups",
                    "Games counted", "Adds", "Lineup moves"] + [f"{c} W-L-T" for c in CATS])
        for t in report["teams"]:
            w.writerow([t["ranks"]["cat_wins"], t["name"], t["manager"], t["wins"], t["losses"], t["ties"], t["pct"],
                        t["allPlay"], t["luck"], t["spent"], t["proj"], t["earned"], t["prod"], t["prodDraft"],
                        t["prodPickup"], t["gp"], t["adds"], t["moves"]]
                       + ["-".join(map(str, t["catRecord"][c])) for c in CATS])
    with open(os.path.join(folder, "draft.csv"), "w", newline="") as f:
        cols = ["pick", "team", "player", "nba", "paid", "projected", "earned", "projRating", "rating", "projGp", "gp", "gpForTeam"]
        w = csv.writer(f)
        w.writerow(["Pick", "Team", "Player", "NBA", "Paid $", "Projected $", "Earned $", "Proj rating", "Rating",
                    "Proj GP", "GP", "GP counted for team"])
        for row in report["draft"]:
            w.writerow([row[c] for c in cols])


def league_summary(data):
    rows = [t for d in data for t in d.teams.values()]
    wins = [t.cat_wins for t in rows]
    corr = {}
    for name in ("prod", "gp", "moves", "adds", "earned", "proj", "prod_draft", "prod_pickup", "allplay"):
        xs, ys = [], []
        for d in data:  # compare teams within a season
            ts = list(d.teams.values())
            mx, my = sum(getattr(t, name) for t in ts) / len(ts), sum(t.cat_wins for t in ts) / len(ts)
            xs += [getattr(t, name) - mx for t in ts]
            ys += [t.cat_wins - my for t in ts]
        corr[name] = round(fit(xs, ys)[2], 2)
    a, b, r = fit([t.prod for t in rows], wins)
    split_prod = share_of_spread({"draft": [t.prod_draft for t in rows], "pickup": [t.prod_pickup for t in rows]}, [t.prod for t in rows])
    # Within the draft: what was expected on draft day vs how it turned out.
    luck = [t.earned - t.proj for t in rows]
    # Did the model's projected $ beat the room's prices at predicting earned $?
    picks = [(pk["bidAmount"], d.players[pk["playerId"]].projected, d.players[pk["playerId"]].earned)
             for d in data for t in d.teams.values() for pk in t.picks
             if pk["playerId"] in d.players and d.players[pk["playerId"]].projected is not None]
    edge_groups = []
    for lo, hi, label in ((10, 999, "Model said $10+ more than paid"), (3, 10, "$3 to $10 more"), (-3, 3, "Within $3"),
                          (-10, -3, "$3 to $10 less"), (-999, -10, "Model said $10+ less than paid")):
        g = [(pd, pj, e) for pd, pj, e in picks if lo <= pj - pd < hi]
        edge_groups.append({"label": label, "n": len(g), "paid": round(sum(x[0] for x in g) / len(g), 1),
                            "gain": round(sum(e - pd for pd, _, e in g) / len(g), 1)})
    tiers = []
    for lo, hi, label in ((40, 999, "$40+"), (20, 40, "$20-39"), (10, 20, "$10-19"), (4, 10, "$4-9"), (1, 4, "$1-3")):
        g = [(pd, pj, e) for pd, pj, e in picks if lo <= pd < hi]
        tiers.append({"label": label, "n": len(g), "gain": round(sum(e - pd for pd, _, e in g) / len(g), 1),
                      "hit": round(sum(e >= pd for pd, _, e in g) / len(g), 2)})
    draft_model = {"n": len(picks), "rPaid": round(fit([x[0] for x in picks], [x[2] for x in picks])[2], 2),
                   "rProjected": round(fit([x[1] for x in picks], [x[2] for x in picks])[2], 2),
                   "edgeGroups": edge_groups, "tiers": tiers}
    return {"draftModel": draft_model, "corr": corr, "winsPerProd": round(b, 3), "prodR": round(r, 2),
            "prodSpread": {k: round(x, 2) for k, x in split_prod.items()},
            "projVsLuckR": {"proj": round(fit([t.proj for t in rows], wins)[2], 2), "luck": round(fit(luck, wins)[2], 2)}}


if __name__ == "__main__":
    data = [season_data(s) for s in SEASONS]
    reports = []
    for d in data:
        score_stints(d)
        team_production(d)
        all_play(d)
        report = season_report(d)
        write_csvs(report)
        reports.append(report)
    summary = league_summary(data)
    with open(os.path.join(HERE, "analysis.json"), "w") as f:
        json.dump({"summary": summary, "seasons": reports}, f, indent=1)
    print(json.dumps(summary, indent=1))
