"use strict";
// Draft Room frontend. The server owns all state and math (gui/board.py);
// this file renders the snapshot it returns and sends edits back.

const $ = (id) => document.getElementById(id);
let B = null; // latest board snapshot
let byId = new Map();
const UI = { q: "", pos: "ALL", team: "ALL", hideGone: false, onlyAdj: false, sort: { key: "rank", dir: 1 },
  sel: null, view: "board", pickSlot: null, dragging: false };

// ------------------------------------------------------------------ format

const fmt = (n, d = 1) => (n == null ? "—" : Number(n).toFixed(d));
const money = (n) => (n == null ? "—" : "$" + Math.round(n));
const signed = (n, d = 0) => {
  const r = +Number(n).toFixed(d);
  return (r > 0 ? "+" : r < 0 ? "−" : "±") + Math.abs(r).toFixed(d);
};
const ord = (n) => n + (n % 10 === 1 && n !== 11 ? "st" : n % 10 === 2 && n !== 12 ? "nd" : n % 10 === 3 && n !== 13 ? "rd" : "th");
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const norm = (s) => s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
// Forgiving number parser for typed values: "+5", "5%", "−5", "$34", " 12 ".
// Returns null for an empty box and NaN for anything unreadable.
function parseNum(s) {
  const clean = String(s).trim().replace(/[−–]/g, "-").replace(/[%$\s]/g, "").replace(/^\+/, "");
  if (clean === "") return null;
  return /^-?\d+(\.\d+)?$/.test(clean) ? Number(clean) : NaN;
}
const signedInput = (n) => (n > 0 ? "+" + n : n ? String(n) : "");
const lastName = (n) => { const w = n.split(" "); return /^(Jr\.|Sr\.|II|III|IV)$/.test(w[w.length - 1]) ? w[w.length - 2] : w[w.length - 1]; };

// ------------------------------------------------------------------ api

async function api(path, body) {
  try {
    const res = await fetch(path, body === undefined ? {} : {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({ error: `The server returned ${res.status}.` }));
    if (!res.ok) { toast(data.error || `The server returned ${res.status}.`); return null; }
    return data;
  } catch (e) {
    toast("Can't reach the Draft Room server. Is python3 -m gui still running?");
    return null;
  }
}

async function act(action, body = {}, { live = false } = {}) {
  const data = await api("/api/" + action, body);
  if (!data) return false;
  B = data.board;
  live ? renderLive() : renderKeepFocus();
  if (data.error) { toast(data.error); return false; }
  return true;
}

// Coalesce rapid slider input: at most one request in flight, latest value wins.
function liveSender(action) {
  let inflight = false, pending = null;
  return async (body) => {
    pending = body;
    if (inflight) return;
    while (pending) {
      const b = pending; pending = null; inflight = true;
      await act(action, b, { live: true });
      inflight = false;
    }
  };
}
const sendAdjust = liveSender("adjust");
const sendSettings = liveSender("settings");

// Snapshot state so destructive actions can be undone.
const snapshotState = () => JSON.parse(JSON.stringify(B.state));
const undoTo = (state) => () => act("state", { state });

// ------------------------------------------------------------------ toast

let toastTimer, toastUndo = null;
function toast(msg, undo) {
  const t = $("toast");
  toastUndo = undo || null;
  t.textContent = msg;
  if (undo) {
    const b = document.createElement("button");
    b.type = "button"; b.className = "undo"; b.textContent = "Undo";
    t.append(b);
  }
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; toastUndo = null; }, undo ? 6000 : 3000);
}
$("toast").addEventListener("click", (e) => {
  if (!e.target.closest(".undo") || !toastUndo) return;
  const fn = toastUndo; toastUndo = null; $("toast").hidden = true; fn();
});
function shake(els) {
  els.forEach((el) => { el.classList.remove("shake"); void el.offsetWidth; el.classList.add("shake"); });
}

// ------------------------------------------------------------------ render

function render() {
  if (!B) return;
  byId = new Map(B.rows.map((r) => [r.id, r]));
  if (UI.sel == null || !byId.has(UI.sel)) {
    const first = [...B.rows].sort((a, b) => a.rank - b.rank).find((r) => !r.status);
    UI.sel = first ? first.id : null;
  }
  if (!$("teams").childElementCount) renderTeams();
  renderMeta(); renderScore(); renderCatRow(); renderHead(); renderBody(); renderStrip(); renderDetail(); renderTeam(); renderSettings();
}
function renderLive() { // while dragging a slider: leave the panel being dragged alone
  byId = new Map(B.rows.map((r) => [r.id, r]));
  renderScore(); renderCatRow(); renderBody(); renderStrip(); renderTeam();
}
function renderKeepFocus() {
  const a = document.activeElement, id = a && a.id;
  const pos = a && typeof a.selectionStart === "number" ? a.selectionStart : null;
  render();
  if (!id) return;
  const n = $(id);
  if (!n || n === document.activeElement) return;
  n.focus({ preventScroll: true });
  try { if (pos != null) n.setSelectionRange(pos, pos); } catch (e) { /* number inputs */ }
}

function renderMeta() {
  const m = B.meta;
  const when = m.fetchedAt ? new Date(m.fetchedAt * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "—";
  $("meta").innerHTML = `
    <span><b>${esc(m.leagueName)}</b></span>
    <span>${m.teams} teams · $${m.budget} · ${m.rosterSize} roster</span>
    <span>Season <b>${m.seasonLabel}</b></span>
    <span>Stats <b>${m.statsLabel}</b></span>
    <span>Pool fetched <b>${when}</b></span>`;
  const w = $("warnings");
  w.hidden = !m.warnings.length;
  w.innerHTML = m.warnings.map((x) => `<div class="warn">${esc(x)}</div>`).join("");
}


function renderScore() {
  const me = B.me, pool = B.pool;
  $("sBudget").textContent = money(me.budgetLeft);
  $("sMax").textContent = `max bid ${money(me.maxBid)}`;
  $("sRoster").textContent = `${me.count} / ${B.meta.rosterSize}`;
  $("sRosterSub").textContent = me.count ? me.names.map(lastName).join(", ") : "No picks yet";
  $("sPool").textContent = `${pool.left} / ${pool.size}`;
  $("sPoolSub").textContent = `core players left (${B.meta.core} per team) · ${pool.taken} taken by others`;
  const best = B.rows.filter((r) => !r.status).sort((a, b) => b.edge - a.edge)[0];
  $("sEdge").textContent = best ? signed(best.edge) : "—";
  $("sEdge").className = "val" + (best && best.edge >= 3 ? " up" : "");
  $("sEdgeSub").textContent = best ? `${best.name} · ${money(best.ours)} vs ${money(best.avg)}` : "—";
  $("teamCount").textContent = `${me.count}/${B.meta.rosterSize}`;
}

// ------------------------------------------------------------------ team category row

// Built once per category list, then updated in place so bars animate between values.
let catRowKey = "", prevRatings = null;
const chipTimers = {};
function renderCatRow() {
  const el = $("catrow"), t = B.team, n = B.meta.teams;
  el.hidden = !t.categories.length || t.categories[0].rating == null; // older server: no ratings yet
  if (el.hidden) return;
  const key = t.categories.map((c) => c.cat).join("|");
  if (key !== catRowKey) {
    catRowKey = key; prevRatings = null;
    el.style.setProperty("--cats", t.categories.length);
    el.innerHTML = `<div class="cr-head"><span class="lbl" id="crLbl">My team</span><span class="v" id="crOverall"></span>
        <span class="wl" id="crDots" aria-hidden="true">${t.categories.map((c, i) => `<i id="wl-${i}" title="${esc(c.cat)}"></i>`).join("")}</span>
        <span class="s" id="crSub"></span>
        <button class="linkbtn" type="button" id="crOpen">Open My Team</button></div>` +
      t.categories.map((c, i) => `<div class="cc" id="cc-${i}">
        <span class="ctop"><span class="lbl">${esc(c.cat)}</span>
          <label class="punt" for="punt-${i}" title="Punt ${esc(c.cat)}: stop valuing it in Fit"><input type="checkbox" id="punt-${i}" data-punt="${esc(c.cat)}">Punt</label></span>
        <span class="col"><i></i></span>
        <span class="nums"><span class="rv"></span><span class="meta"><span class="rt"></span><span class="rk"></span></span></span>
        <span class="dchip"></span></div>`).join("");
  }
  // Winning a category = better than the average team in it (within half a point is even).
  const outcome = (r) => (r >= 100.5 ? "w" : r <= 99.5 ? "l" : "e");
  const wins = t.categories.filter((c) => outcome(c.rating) === "w").length;
  const losses = t.categories.filter((c) => outcome(c.rating) === "l").length;
  const even = t.categories.length - wins - losses;
  $("crLbl").textContent = `My team · ${ord(t.overall)} of ${n}`;
  $("crOverall").textContent = `Winning ${wins} of ${t.categories.length}`;
  $("crOverall").title = `Better than the average team in ${wins} categories, worse in ${losses}${even ? `, even in ${even}` : ""}`;
  t.categories.forEach((c, i) => { $(`wl-${i}`).className = outcome(c.rating); $(`wl-${i}`).title = `${c.cat}: ${signed(c.rating - 100)}`; });
  $("crSub").textContent = `vs the average team${t.filled < B.meta.rosterSize ? ` · ${B.meta.rosterSize - t.filled} empty slots at replacement` : ""}`;
  const next = {};
  t.categories.forEach((c, i) => {
    const cell = $(`cc-${i}`), r = c.rating;
    next[c.cat] = r;
    cell.classList.toggle("punted", !!c.punt);
    const box = cell.querySelector("[data-punt]");
    if (box) box.checked = !!c.punt;
    const bar = cell.querySelector(".col i");
    // Diverging from the 100 midline: up = better than the average team, down = worse. ±40 fills a half.
    bar.classList.toggle("below", r < 100);
    // Color strength: neutral at 100, full green by 120, full red by 80.
    cell.style.setProperty("--up", Math.min(Math.max((r - 100) / 20, 0), 1).toFixed(3));
    cell.style.setProperty("--down", Math.min(Math.max((100 - r) / 20, 0), 1).toFixed(3));
    bar.style.height = `${Math.min(Math.abs(r - 100), 40) / 40 * 50}%`;
    // The margin over the average team is the headline; the rating and rank sit under it.
    cell.querySelector(".rv").textContent = signed(r - 100);
    cell.querySelector(".rt").textContent = Math.round(r);
    const rk = cell.querySelector(".rk");
    rk.textContent = ord(c.rank);
    rk.className = "rk " + (c.rank <= 3 ? "top" : c.rank >= n - 2 ? "low" : "mid");
    cell.title = `${c.cat}: ${outcome(r) === "w" ? "winning" : outcome(r) === "l" ? "losing" : "even"} by ${Math.abs(Math.round(r - 100))} vs the average team (rating ${Math.round(r)}), ${ord(c.rank)} of ${n}${c.reverse ? " (lower totals are better)" : ""}${c.punt ? ". Punted: Fit ignores it" : ""}`;
    const prev = prevRatings && prevRatings[c.cat];
    const d = prev == null ? 0 : Math.round(r) - Math.round(prev);
    if (d) {
      const chip = cell.querySelector(".dchip");
      chip.textContent = signed(d);
      chip.className = "dchip show " + (d > 0 ? "up" : "down");
      clearTimeout(chipTimers[i]);
      chipTimers[i] = setTimeout(() => chip.classList.remove("show"), 3500);
    }
  });
  prevRatings = next;
}
$("catrow").addEventListener("click", (e) => {
  if (e.target.id === "crOpen") { setView("team"); render(); }
});
$("catrow").addEventListener("change", (e) => {
  const box = e.target.closest("[data-punt]");
  if (!box) return;
  const punt = [...$("catrow").querySelectorAll("[data-punt]")].filter((b) => b.checked).map((b) => b.dataset.punt);
  act("settings", { punt });
});

// ------------------------------------------------------------------ board table

const GROUPS = () => [
  { label: "", span: 3 },
  { label: B.meta.statsLabel, span: 3 },
  { label: `${B.meta.seasonLabel} outlook`, span: 7, cls: "g-out" },
  { label: "Auction $", span: 4, cls: "g-ours" },
];
const COLS = [
  { key: "taken", label: "", sr: "Taken", nosort: true, cls: "tk-h", title: "Drafted by another team" },
  { key: "rank", label: "Rk", title: "Rank by value" },
  { key: "name", label: "Player", cls: "l" },
  { key: "gp", label: "GP", title: "Games played last season" },
  { key: "lastPg", label: "Per gm", title: "Per-game rating (100 = pool average)" },
  { key: "lastValue", label: "Value", title: "Per-game rating over the season, with missed games filled by a replacement free agent" },
  { key: "gpDelta", label: "GP Δ", title: "Games more or fewer than ESPN projects, e.g. -10. Drag or type; clear to reset." },
  { key: "expGp", label: "Exp GP", title: "Expected games: ESPN's projection + GP Δ" },
  { key: "expMin", label: "Exp MIN", title: "Expected minutes per game. Default: ESPN's projection. Production scales with minutes. Drag or type; clear to reset." },
  { key: "delta", label: "Δ", title: "Change in per-game rating points (100 = average player), e.g. +10. Spread across categories by scaling every counting stat and shot attempt." },
  { key: "projPg", label: "Per gm", title: "Projected per-game rating" },
  { key: "value", label: "Value", title: "Projected per-game rating over 82 games: Exp GP at his rating, the games he misses at the replacement rating (Settings)" },
  { key: "fit", label: "Fit", title: "Value to your current team: categories you're already winning count less (fading from the Settings range), punted ones not at all. 100 = an average player." },
  { key: "avg", label: "Avg paid", title: "Average price in ESPN auction drafts, scaled to this league's budget" },
  { key: "ours", label: "Ours", cls: "ours-h", title: "Our value before the draft" },
  { key: "edge", label: "Edge", cls: "ours-h", title: "Ours − Avg paid" },
  { key: "fitEdge", label: "Fit edge", cls: "ours-h", title: "Fit $ − Avg paid: the bargain for your current team. Fit $ converts Fit to dollars at the league's rate." },
];

function renderHead() {
  const g = `<tr class="grp">${GROUPS().map((g) => `<th colspan="${g.span}" class="${g.cls || ""}">${g.label ? `<span>${esc(g.label)}</span>` : ""}</th>`).join("")}</tr>`;
  const c = `<tr>${COLS.map((c) => {
    if (c.nosort) return `<th class="${c.cls || ""}" scope="col" title="${esc(c.title)}"><span class="sr">${c.sr}</span></th>`;
    const s = UI.sort.key === c.key ? ` aria-sort="${UI.sort.dir < 0 ? "descending" : "ascending"}"` : "";
    const title = c.key === "avg" ? `${c.title} (ESPN average × ${B.meta.marketScale.toFixed(2)})` : c.title || "";
    return `<th class="${c.cls || ""}"${s} scope="col"><button type="button" data-sort="${c.key}" title="${esc(title)}">${c.label}</button></th>`;
  }).join("")}</tr>`;
  $("thead").innerHTML = g + c;
}

function visibleRows() {
  const q = norm(UI.q.trim());
  const rows = B.rows.filter((r) =>
    (!q || norm(r.name).includes(q) || norm(r.team).includes(q)) &&
    (UI.pos === "ALL" || r.elig.includes(UI.pos)) &&
    (UI.team === "ALL" || r.team === UI.team) &&
    (!UI.hideGone || !r.status) &&
    (!UI.onlyAdj || r.delta || r.gpDelta || r.minSet || r.note));
  const { key, dir } = UI.sort;
  rows.sort((a, b) => {
    const x = a[key], y = b[key];
    if (typeof x === "string") return dir * x.localeCompare(y);
    return dir * ((x ?? -1e9) - (y ?? -1e9));
  });
  return rows;
}

function injuryPill(inj, long = false) {
  if (!inj || inj === "ACTIVE") return "";
  if (inj === "DAY_TO_DAY") return `<span class="pill inj">${long ? "Day-to-day" : "DTD"}</span>`;
  if (inj === "OUT" || inj === "INJURY_RESERVE") return `<span class="pill out">Out</span>`;
  return `<span class="pill inj">${esc(inj.replace(/_/g, " ").toLowerCase())}</span>`;
}
function statusPill(r) {
  if (!r.status) return "";
  return `<span class="pill ${r.status}">${r.status === "mine" ? `Mine $${r.price}` : "Taken"}</span>`;
}
function badges(r) {
  let s = injuryPill(r.inj);
  if (r.fromProj) s += `<span class="pill proj" title="No ${B.meta.statsLabel} games. Based on ESPN's projection.">ESPN proj</span>`;
  else if (r.gp < 25) s += `<span class="pill low" title="Only ${r.gp} games last season">${r.gp} GP</span>`;
  return s;
}

function takenToggle(r) {
  if (r.status === "mine") return `<span class="mine-dot" title="On your team"></span>`;
  const on = r.status === "taken";
  return `<button class="tswitch" type="button" role="switch" aria-checked="${on}" data-taken="${r.id}"` +
    ` aria-label="${esc(r.name)} drafted by another team" title="${on ? "Taken by another team. Click to undo." : "Mark drafted by another team"}"></button>`;
}

const edgeCls = (e) => (e >= 3 ? "pos" : e <= -3 ? "neg" : "");

function rowHTML(r) {
  const e = r.edge, ecls = edgeCls(e);
  const drag = r.status === "taken" ? "" : ` draggable="true" data-drag="${r.id}" title="Drag onto a roster slot"`;
  return `<tr data-id="${r.id}" class="${UI.sel === r.id ? "sel" : ""} ${r.status ? "gone" : ""}">
    <td class="tk">${takenToggle(r)}</td>
    <td class="rk">${r.rank}</td>
    <td class="l"><div class="pcell"${drag}><span class="pname">${esc(r.name)}${statusPill(r)}</span><span class="psub">${esc(r.team)} · ${esc(r.pos)}${badges(r)}</span></div></td>
    <td>${r.fromProj ? "—" : r.gp}</td>
    <td>${fmt(r.lastPg)}</td>
    <td>${r.fromProj ? "—" : fmt(r.lastValue)}</td>
    <td><input class="cell ${r.gpDelta ? "edited" : ""}" type="text" inputmode="text" autocomplete="off" value="${signedInput(r.gpDelta)}" placeholder="0" title="ESPN projects ${r.espnGp} games" aria-label="Games more or fewer than ESPN projects for ${esc(r.name)}" data-gp="${r.id}" id="g-${r.id}"></td>
    <td class="${r.gpDelta ? "edited-v" : ""}">${r.expGp}</td>
    <td><input class="cell ${r.minSet ? "edited" : ""}" type="text" inputmode="decimal" autocomplete="off" value="${fmt(r.expMin)}" title="Last season ${r.lastMin ?? "—"} min · ESPN projects ${r.projMin ?? "—"}" aria-label="Expected minutes for ${esc(r.name)}" data-min="${r.id}" id="m-${r.id}"></td>
    <td><input class="cell ${r.delta ? "edited" : ""}" type="text" inputmode="text" autocomplete="off" value="${signedInput(r.delta)}" placeholder="0" aria-label="Δ rating points for ${esc(r.name)}" data-delta="${r.id}" id="d-${r.id}"></td>
    <td>${fmt(r.projPg)}</td>
    <td class="val">${fmt(r.value)}</td>
    <td class="fit">${r.status === "taken" ? "—" : fmt(r.fit)}</td>
    <td>${money(r.avg)}</td>
    <td class="ours">${money(r.ours)}</td>
    <td class="ours"><span class="edge ${ecls}">${signed(e)}</span></td>
    <td class="ours">${r.status === "taken" || r.fitEdge == null ? "—" : `<span class="edge ${edgeCls(r.fitEdge)}">${signed(r.fitEdge)}</span>`}</td>
  </tr>`;
}

function renderBody() {
  const rows = visibleRows();
  $("tbody").innerHTML = rows.length ? rows.map(rowHTML).join("")
    : `<tr><td colspan="${COLS.length}" class="empty-row">No players match${UI.q ? ` “${esc(UI.q)}”` : ""}. Clear the search or turn off a filter.</td></tr>`;
}

// ------------------------------------------------------------------ detail panel

function bars(before, after, cats) {
  const MAX = 250, x0 = 44, w = 172, rh = 24; // leaves room for labels like "281+ (+53)"
  const x = (v) => x0 + Math.min(Math.max(v, 0), MAX) / MAX * w;
  const h = cats.length * rh + 22;
  let s = `<svg viewBox="0 0 300 ${h}" role="img" aria-label="Per-game category ratings, last season and projected">`;
  s += `<line x1="${x(100)}" x2="${x(100)}" y1="0" y2="${cats.length * rh}" stroke="var(--line-strong)" stroke-dasharray="3 3"></line>`;
  cats.forEach((k, i) => {
    const b = before[k] ?? 0, a = after[k] ?? 0, y = i * rh + 5, d = a - b;
    s += `<text class="cl" x="0" y="${y + 11}">${esc(k)}</text>`;
    s += `<rect x="${x0}" y="${y}" width="${w}" height="14" rx="2" fill="var(--sunk)"></rect>`;
    s += `<rect x="${x0}" y="${y}" width="${Math.max(2, x(b) - x0)}" height="14" rx="2" fill="var(--line-strong)"></rect>`;
    s += `<rect x="${x0}" y="${y + 4}" width="${Math.max(2, x(a) - x0)}" height="6" rx="1" fill="${a >= 100 ? "var(--accent)" : "var(--bad)"}"></rect>`;
    s += `<text x="${x0 + w + 6}" y="${y + 11}">${Math.round(a)}${a > MAX ? "+" : ""}${d ? ` (${d > 0 ? "+" : "−"}${Math.abs(Math.round(d))})` : ""}</text>`;
  });
  const ty = cats.length * rh + 14;
  [0, 100, 200].forEach((t) => (s += `<text x="${x(t)}" y="${ty}" text-anchor="middle">${t}</text>`));
  return s + "</svg>";
}

const gpOut = (r, d) => `${signed(d)} → ${r.espnGp + d} GP`;

function renderDetail() {
  const el = $("detail"), r = byId.get(UI.sel);
  if (!r) { el.innerHTML = `<p class="muted">Select a player to see their category breakdown.</p>`; return; }
  const slotName = r.status === "mine" ? B.meta.slots[B.state.filled.indexOf(r.id)] : null;
  const espnHint = r.fromProj
    ? `No ${B.meta.statsLabel} games, so this uses ESPN's projection (${r.projGp} GP).`
    : `Last season ${r.gp} GP, ${r.lastMin ?? "—"} min · ESPN projects ${r.projGp || "—"} GP, ${r.projMin ?? "—"} min${r.espnDelta ? `, ${signed(r.espnDelta)} rating beyond minutes` : ""}.${r.rateSource === "espn" ? " Small sample, so production uses ESPN's line." : ""}`;
  el.innerHTML = `
    <div><h2>${esc(r.name)}</h2>
      <div class="dsub"><span>${esc(r.team)} · ${esc(r.pos)}</span><span class="num">${r.line.map((v) => fmt(v)).join(" / ")} pts/reb/ast</span>${injuryPill(r.inj, true)}</div></div>
    <div class="kv">
      <div><span class="lbl">Value rank</span><span class="v">#${r.rank}</span></div>
      <div><span class="lbl">Ours</span><span class="v">${money(r.ours)}</span></div>
      <div title="Ours − Avg paid"><span class="lbl">Edge</span><span class="v ${r.edge >= 3 ? "up" : r.edge <= -3 ? "down" : ""}">${signed(r.edge)}</span></div>
      <div title="Rank by Fit among players still available"><span class="lbl">Fit rank</span><span class="v">${r.fitRank ? "#" + r.fitRank : "—"}</span></div>
      <div title="Fit ${fmt(r.fit)} converted at the league's $/point"><span class="lbl">Fit $</span><span class="v">${r.fitDollars == null ? "—" : money(r.fitDollars)}</span></div>
      <div title="Fit $ − Avg paid"><span class="lbl">Fit edge</span><span class="v ${r.fitEdge >= 3 ? "up" : r.fitEdge <= -3 ? "down" : ""}">${r.fitEdge == null ? "—" : signed(r.fitEdge)}</span></div>
      <div><span class="lbl">ESPN rank</span><span class="v">#${r.espnRank ?? "—"}</span></div>
      <div><span class="lbl">ESPN $</span><span class="v">${money(r.espn)}</span></div>
      <div title="ESPN average $${fmt(r.avgRaw)} × ${B.meta.marketScale.toFixed(2)} to fit this league's budget"><span class="lbl">Avg paid</span><span class="v">${money(r.avg)}</span></div>
    </div>
    <table class="rtab" aria-label="Ratings">
      <thead><tr><th scope="col">Rating</th><th scope="col">${B.meta.statsLabel}</th><th scope="col">${B.meta.seasonLabel}</th></tr></thead>
      <tbody>
        <tr><th scope="row">Per game</th><td>${fmt(r.lastPg)}</td><td>${fmt(r.projPg)}</td></tr>
        <tr><th scope="row">Games</th><td>${r.fromProj ? "—" : r.gp}</td><td>${r.expGp}${r.gpDelta ? ` <span class="g">ESPN ${r.espnGp} ${signed(r.gpDelta)}</span>` : ""}</td></tr>
        <tr><th scope="row" title="(per game × games + ${B.meta.replacement} × missed games) ÷ ${B.meta.gamesInSeason}">Value</th><td>${r.fromProj ? "—" : fmt(r.lastValue)}</td><td><b>${fmt(r.value)}</b></td></tr>
      </tbody>
    </table>
    <div class="bars"><span class="lbl sec-t">Δ ${signed(r.delta)} rating across categories · per game</span>${bars(r.catLast, r.catProj, B.meta.rated)}
      <div class="legend"><span><i style="background:var(--line-strong)"></i>${B.meta.statsLabel}</span><span><i style="background:var(--accent)"></i>${B.meta.seasonLabel}</span><span>100 = pool avg</span></div></div>
    <div><span class="lbl sec-t">Adjust</span>
      <div class="adj"><span>Δ</span><input type="range" id="dRange" min="${-B.meta.maxDelta}" max="${B.meta.maxDelta}" step="1" value="${r.delta}" aria-label="Δ rating points"><output id="dOut">${signed(r.delta)}</output></div>
      <div class="adj"><span>Exp MIN</span><input type="range" id="mRange" min="0" max="${B.meta.maxMin}" step="0.5" value="${r.expMin}" aria-label="Expected minutes"><output id="mOut">${fmt(r.expMin)}</output></div>
      <div class="adj"><span>GP Δ</span><input type="range" id="gRange" min="${-r.espnGp}" max="${82 - r.espnGp}" step="1" value="${r.gpDelta}" aria-label="Games more or fewer than ESPN projects"><output id="gOut">${gpOut(r, r.gpDelta)}</output></div>
      <p class="hint">${espnHint}
        ${r.projMin || r.projGp ? `<button class="linkbtn" type="button" id="useEspn">Use ESPN's</button>` : ""}
        ${r.minSet ? ` · <button class="linkbtn" type="button" id="resetMin">Reset minutes</button>` : ""}
        ${r.gpDelta ? ` · <button class="linkbtn" type="button" id="resetGp">Reset games</button>` : ""}</p></div>
    <div><label class="lbl sec-t" for="noteBox">Note</label>
      <textarea id="noteBox" placeholder="Why the adjustment?">${esc(r.note || "")}</textarea></div>
    <div><span class="lbl sec-t">Draft</span>
      ${r.status
        ? `<div class="draftrow">${r.status === "mine" ? `<span class="pill mine">Mine · ${esc(slotName || "?")} $${r.price}</span>` : `<span class="pill taken">Taken</span>`}
           <button class="btn" type="button" id="undoPick">${r.status === "mine" ? "Remove from team" : "Undo"}</button></div>`
        : `<div class="draftrow"><label for="priceIn" title="Defaults to the average paid in ESPN auctions">Price</label><input id="priceIn" type="text" inputmode="numeric" autocomplete="off" value="${Math.round(Math.max(1, r.avg))}">
           <button class="btn primary" type="button" data-pick="mine">Add to my team</button><button class="btn" type="button" data-pick="taken">Mark taken</button></div>`}
    </div>`;
}

// ------------------------------------------------------------------ roster strip + my team

function renderStrip() {
  const slots = B.meta.slots, filled = B.state.filled;
  $("strip").innerHTML = `<span class="lbl">My roster</span>` + slots.map((s, i) => {
    const r = byId.get(filled[i]);
    return `<div class="sl ${r ? "filled" : ""} ${UI.pickSlot === i ? "pick" : ""}" data-slot="${i}" ${r ? `draggable="true" data-drag="${r.id}"` : ""} tabindex="0" role="button" aria-label="${s} slot${r ? `: ${esc(r.name)}` : ", empty"}">
      <span class="pos">${s === "BE" ? "Bench" : s}</span><span class="who ${r ? "" : "empty"}">${r ? esc(lastName(r.name)) : "Drop here"}</span>
      ${r ? `<button class="x" type="button" data-remove="${r.id}" aria-label="Remove ${esc(r.name)} from team" title="Remove from team">×</button>` : ""}</div>`;
  }).join("") + `<button class="btn danger clearbtn" type="button" data-clear ${filled.some((x) => x != null) ? "" : "disabled"}>Clear roster</button>`;
}

function catStrip(c) {
  const sign = c.reverse ? -1 : 1; // better is always to the right
  const vals = c.teams.map((v) => v * sign), mine = c.mine * sign, avg = c.avg * sign;
  const lo = Math.min(...vals), hi = Math.max(...vals), pad = (hi - lo) * 0.08 || 1, W = 480;
  const x = (v) => 8 + (v - lo + pad) / (hi - lo + 2 * pad) * (W - 16);
  let s = `<svg viewBox="0 0 ${W} 26" role="img" aria-label="${esc(c.cat)}: ranked ${ord(c.rank)} of ${vals.length}">`;
  s += `<line x1="8" x2="${W - 8}" y1="13" y2="13" stroke="var(--line)" stroke-width="2"></line>`;
  s += `<line x1="${x(avg)}" x2="${x(avg)}" y1="5" y2="21" stroke="var(--line-strong)" stroke-dasharray="2 2"></line>`;
  vals.slice(1).forEach((v) => (s += `<circle cx="${x(v)}" cy="13" r="4" fill="var(--faint)" opacity=".6"></circle>`));
  s += `<circle cx="${x(mine)}" cy="13" r="6.5" fill="var(--accent)" stroke="var(--surface)" stroke-width="2"></circle>`;
  return s + "</svg>";
}

function renderTeam() {
  const m = B.meta, filled = B.state.filled, me = B.me;
  const mine = filled.filter((x) => x != null).map((id) => byId.get(id)).filter(Boolean);
  const worth = mine.reduce((a, r) => a + r.ours, 0);
  let h = `<div class="slothead"><h3>Roster</h3><button class="btn danger" type="button" data-clear ${mine.length ? "" : "disabled"}>Clear roster</button></div>
    <p class="sub">${me.count} of ${m.rosterSize} · $${me.spent} spent, worth ${money(worth)} by our value. Drag to rearrange, or click one slot and then another.</p>`;
  const firstBench = m.slots.indexOf("BE");
  m.slots.forEach((s, i) => {
    if (i === firstBench) h += `<span class="lbl divider">Bench</span>`;
    const r = byId.get(filled[i]);
    h += `<div class="srow ${r ? "" : "empty"} ${s === "BE" ? "bench" : ""} ${UI.pickSlot === i ? "pick" : ""}" data-slot="${i}" ${r ? `draggable="true" data-drag="${r.id}"` : ""} tabindex="0" role="button" aria-label="${s} slot${r ? `: ${esc(r.name)}` : ", empty"}">
      <span class="pos">${s}</span>
      <span class="nm">${r ? `<b>${esc(r.name)}</b><span>${esc(r.team)} · ${esc(r.pos)} · ${r.expGp} GP</span>` : `<span class="ph">Empty: counts as replacement</span>`}</span>
      ${r ? `<input type="text" inputmode="numeric" autocomplete="off" value="${r.price}" aria-label="Price paid for ${esc(r.name)}" data-price="${r.id}" id="pr-${r.id}">` : "<span></span>"}
      <span class="v" title="Our value">${r ? money(r.ours) : ""}</span>
      ${r ? `<button class="x" type="button" data-remove="${r.id}" aria-label="Remove ${esc(r.name)}" title="Remove from team">×</button>` : "<span></span>"}
    </div>`;
  });
  $("slots").innerHTML = h;

  const t = B.team, n = m.teams;
  const cls = (rk) => (rk <= 3 ? "top" : rk >= n - 2 ? "low" : "mid");
  const isPct = (c) => c.endsWith("%");
  const val = (c, v) => (isPct(c) ? v.toFixed(3).replace(/^0/, "") : Math.round(v).toLocaleString());
  const diff = (c, v, a) => (isPct(c) ? signed((v - a) * 100, 1) + " pts" : a ? signed((v / a - 1) * 100) + "%" : "—");
  const targets = t.targets.length
    ? ` Best-value help in <b>${esc(t.targets[0].cat)}</b>: ${t.targets.map((x) => `<button class="linkbtn" type="button" data-goto="${x.id}">${esc(x.name)}</button> (${x.rating}, worth ${money(x.ours)})`).join(" and ")}.`
    : "";
  $("ranks").innerHTML = `
    <div><h3>Category ranks</h3><p class="sub">Projected ${m.seasonLabel} season totals from your best ${m.counted} of ${m.rosterSize}, against ${n - 1} simulated opponents who get the Taken players and the best remaining by value.${t.filled < m.rosterSize ? ` Your ${m.rosterSize - t.filled} empty slots count as replacement-level players.` : ""}</p></div>
    <div class="overall">
      <div><span class="lbl">Overall</span><span class="v">${ord(t.overall)}</span><span class="s">of ${n} by roto points</span></div>
      <div><span class="lbl">Roto points</span><span class="v">${t.roto}</span><span class="s">of ${t.rotoMax} possible</span></div>
      <div><span class="lbl">H2H cats won</span><span class="v">${t.expectedWins.toFixed(1)}–${(t.categories.length - t.expectedWins).toFixed(1)}</span><span class="s">expected per week vs. an average opponent</span></div>
    </div>
    <div class="catwrap"><table class="cattab" aria-label="Category ranks">
      <thead><tr><th class="l" scope="col">Cat</th><th class="l" scope="col">worse ← league → better</th><th scope="col">Rank</th><th scope="col">Yours</th><th scope="col">vs avg</th></tr></thead>
      <tbody>${t.categories.map((c) => `<tr>
        <td class="cat">${esc(c.cat)}${[c.reverse ? "lower is better" : "", m.rated.includes(c.cat) ? "" : "not in value"].filter(Boolean).map((s) => `<small>${s}</small>`).join("")}</td>
        <td class="strip-c">${catStrip(c)}</td>
        <td><span class="rkb ${cls(c.rank)}">${ord(c.rank)}</span></td>
        <td>${val(c.cat, c.mine)}</td><td>${diff(c.cat, c.mine, c.avg)}</td></tr>`).join("")}</tbody>
    </table></div>
    <p class="callout">${t.strong.length ? `Strong in <b>${t.strong.map(esc).join(", ")}</b>. ` : ""}${t.weak.length ? `Weak in <b>${t.weak.map(esc).join(", ")}</b>: target them with the rest of the draft, or punt.` : "No category ranks in the bottom four."}${targets}</p>`;
}

// ------------------------------------------------------------------ roster actions

function removeMine(id) {
  const r = byId.get(id), prev = snapshotState();
  act("pick", { id, status: null }).then((ok) => ok && toast(`Removed ${r.name} from your team.`, undoTo(prev)));
}
function clearRoster() {
  const n = B.state.filled.filter((x) => x != null).length;
  if (!n) return;
  const prev = snapshotState();
  act("clear-roster").then((ok) => ok && toast(`Cleared ${n} player${n > 1 ? "s" : ""} from your roster.`, undoTo(prev)));
}
async function moveTo(id, slot) {
  const r = byId.get(id);
  const ok = await act("move", { id, slot }); // server prices new players at their average paid
  if (!ok) shake([...document.querySelectorAll(`[data-slot="${slot}"]`)]);
  else UI.sel = id;
  return ok;
}
function slotClick(i) {
  const filled = B.state.filled;
  if (UI.pickSlot == null) {
    if (filled[i] != null) { UI.pickSlot = i; UI.sel = filled[i]; render(); }
    else if (UI.sel != null && !byId.get(UI.sel)?.status) moveTo(UI.sel, i);
    else toast("Drag a player here from the Board, or select one and click this slot.");
    return;
  }
  const id = filled[UI.pickSlot];
  UI.pickSlot = null;
  if (i !== filled.indexOf(id)) moveTo(id, i); else render();
}

// drag and drop, shared by the board rows, the roster strip and My Team
let DRAG = null;
function markTargets(on) {
  const elig = DRAG != null ? byId.get(DRAG)?.elig || [] : [];
  document.querySelectorAll("[data-slot]").forEach((el) => {
    el.classList.remove("ok", "no", "over");
    if (!on || DRAG == null) return;
    const s = B.meta.slots[+el.dataset.slot];
    el.classList.add(s === "UT" || s === "BE" || elig.includes(s) ? "ok" : "no");
  });
}
document.addEventListener("dragstart", (e) => {
  const d = e.target.closest && e.target.closest("[data-drag]");
  if (!d) return;
  DRAG = +d.dataset.drag;
  e.dataTransfer.effectAllowed = "move";
  e.dataTransfer.setData("text/plain", String(DRAG));
  markTargets(true);
});
document.addEventListener("dragend", () => { DRAG = null; markTargets(false); });
document.addEventListener("dragover", (e) => {
  const t = e.target.closest && e.target.closest("[data-slot]");
  if (t && DRAG != null) { e.preventDefault(); t.classList.add("over"); }
});
document.addEventListener("dragleave", (e) => {
  const t = e.target.closest && e.target.closest("[data-slot]");
  if (t && !t.contains(e.relatedTarget)) t.classList.remove("over");
});
document.addEventListener("drop", (e) => {
  const t = e.target.closest && e.target.closest("[data-slot]");
  if (!t || DRAG == null) return;
  e.preventDefault();
  const id = DRAG; DRAG = null; markTargets(false);
  UI.pickSlot = null;
  moveTo(id, +t.dataset.slot);
});

function slotContainerHandlers(el) {
  el.addEventListener("click", (e) => {
    if (e.target.closest("[data-clear]")) return clearRoster();
    const x = e.target.closest("[data-remove]");
    if (x) return removeMine(+x.dataset.remove);
    if (e.target.closest("input")) return;
    const g = e.target.closest("[data-goto]");
    if (g) { UI.sel = +g.dataset.goto; setView("board"); render(); return; }
    const t = e.target.closest("[data-slot]");
    if (t) slotClick(+t.dataset.slot);
  });
  el.addEventListener("keydown", (e) => {
    if ((e.key === "Enter" || e.key === " ") && e.target.matches("[data-slot]")) { e.preventDefault(); slotClick(+e.target.dataset.slot); }
  });
}
slotContainerHandlers($("strip"));
slotContainerHandlers($("slots"));
slotContainerHandlers($("ranks"));
$("slots").addEventListener("change", (e) => {
  const i = e.target.closest("[data-price]");
  if (!i) return;
  const price = readPrice(i.value);
  if (price == null) return renderKeepFocus(); // revert
  act("price", { id: +i.dataset.price, price });
});

// ------------------------------------------------------------------ controls

$("chips").innerHTML = ["ALL", "PG", "SG", "SF", "PF", "C"].map((p) =>
  `<button class="fchip" type="button" data-pos="${p}" aria-pressed="${p === UI.pos}">${p === "ALL" ? "All" : p}</button>`).join("");
$("chips").addEventListener("click", (e) => {
  const b = e.target.closest("[data-pos]");
  if (!b) return;
  UI.pos = b.dataset.pos;
  document.querySelectorAll(".fchip").forEach((c) => c.setAttribute("aria-pressed", c.dataset.pos === UI.pos));
  renderBody();
});

// ESPN abbreviations → [name, primary, secondary]. The swatch shows both colors
// so dark primaries (navy, black) still read on the dark theme.
const NBA_TEAMS = {
  ATL: ["Atlanta Hawks", "#E03A3E", "#C1D32F"], BOS: ["Boston Celtics", "#007A33", "#BA9653"],
  BKN: ["Brooklyn Nets", "#000000", "#FFFFFF"], CHA: ["Charlotte Hornets", "#1D1160", "#00788C"],
  CHI: ["Chicago Bulls", "#CE1141", "#000000"], CLE: ["Cleveland Cavaliers", "#860038", "#FDBB30"],
  DAL: ["Dallas Mavericks", "#00538C", "#B8C4CA"], DEN: ["Denver Nuggets", "#0E2240", "#FEC524"],
  DET: ["Detroit Pistons", "#C8102E", "#1D42BA"], GSW: ["Golden State Warriors", "#1D428A", "#FFC72C"],
  HOU: ["Houston Rockets", "#CE1141", "#C4CED4"], IND: ["Indiana Pacers", "#002D62", "#FDBB30"],
  LAC: ["LA Clippers", "#C8102E", "#1D428A"], LAL: ["Los Angeles Lakers", "#552583", "#FDB927"],
  MEM: ["Memphis Grizzlies", "#5D76A9", "#12173F"], MIA: ["Miami Heat", "#98002E", "#F9A01B"],
  MIL: ["Milwaukee Bucks", "#00471B", "#EEE1C6"], MIN: ["Minnesota Timberwolves", "#0C2340", "#78BE20"],
  NOP: ["New Orleans Pelicans", "#0C2340", "#C8102E"], NYK: ["New York Knicks", "#006BB6", "#F58426"],
  OKC: ["Oklahoma City Thunder", "#007AC1", "#EF3B24"], ORL: ["Orlando Magic", "#0077C0", "#C4CED4"],
  PHL: ["Philadelphia 76ers", "#006BB6", "#ED174C"], PHO: ["Phoenix Suns", "#1D1160", "#E56020"],
  POR: ["Portland Trail Blazers", "#E03A3E", "#000000"], SAC: ["Sacramento Kings", "#5A2D81", "#63727A"],
  SAS: ["San Antonio Spurs", "#C4CED4", "#000000"], TOR: ["Toronto Raptors", "#CE1141", "#000000"],
  UTA: ["Utah Jazz", "#4B2A7B", "#000000"], WAS: ["Washington Wizards", "#002B5C", "#E31837"],
  FA: ["Free agents", "#8A827A", "#CBC6C0"],
};
const inkOn = (hex) => {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.4 ? "#1D1B19" : "#FFFFFF";
};

function renderTeams() {
  const present = new Set(B.rows.map((r) => r.team));
  const codes = Object.keys(NBA_TEAMS).filter((t) => t !== "FA").sort();
  if (present.has("FA")) codes.push("FA");
  const chip = (code, label, title, style = "") =>
    `<button class="tchip" type="button" role="radio" data-team="${code}" aria-checked="${UI.team === code}"` +
    ` tabindex="${UI.team === code ? 0 : -1}" title="${esc(title)}"${style}>${label}</button>`;
  $("teams").innerHTML = chip("ALL", "All", "All teams") + codes.map((t) => {
    const [name, c1, c2] = NBA_TEAMS[t];
    return chip(t, t, name, ` style="--c1:${c1};--c2:${c2};--on:${inkOn(c1)}"`);
  }).join("");
}

function setTeam(code, focus = false) {
  UI.team = code;
  document.querySelectorAll(".tchip").forEach((c) => {
    const on = c.dataset.team === code;
    c.setAttribute("aria-checked", on);
    c.tabIndex = on ? 0 : -1;
    if (on && focus) c.focus();
  });
  renderBody();
}

$("teams").addEventListener("click", (e) => {
  const b = e.target.closest("[data-team]");
  if (!b) return;
  // Clicking the selected team again goes back to all teams.
  setTeam(b.dataset.team === UI.team ? "ALL" : b.dataset.team);
});
$("teams").addEventListener("keydown", (e) => {
  const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
  if (!step) return;
  e.preventDefault();
  const chips = [...document.querySelectorAll(".tchip")];
  const i = chips.findIndex((c) => c.dataset.team === UI.team);
  setTeam(chips[(i + step + chips.length) % chips.length].dataset.team, true);
});
$("q").addEventListener("input", (e) => { UI.q = e.target.value; renderBody(); });
["hideGone", "onlyAdj"].forEach((k) => $(k).addEventListener("change", (e) => { UI[k] = e.target.checked; renderBody(); }));
$("thead").addEventListener("click", (e) => {
  const b = e.target.closest("[data-sort]");
  if (!b) return;
  const k = b.dataset.sort;
  UI.sort = UI.sort.key === k ? { key: k, dir: -UI.sort.dir } : { key: k, dir: k === "name" || k === "rank" ? 1 : -1 };
  renderHead(); renderBody();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "/" && !e.target.closest("input, textarea")) { e.preventDefault(); setView("board"); $("q").focus(); }
});

const tb = $("tbody");
tb.addEventListener("click", (e) => {
  if (e.target.closest("input")) return;
  const sw = e.target.closest("[data-taken]");
  if (sw) {
    const r = byId.get(+sw.dataset.taken);
    UI.sel = r.id;
    if (r.status === "taken") act("pick", { id: r.id, status: null });
    else act("pick", { id: r.id, status: "taken" });
    return;
  }
  const tr = e.target.closest("tr[data-id]");
  if (!tr) return;
  UI.sel = +tr.dataset.id;
  tb.querySelectorAll("tr.sel").forEach((t) => t.classList.remove("sel"));
  tr.classList.add("sel");
  renderDetail();
});
tb.addEventListener("focusin", (e) => {
  const i = e.target.closest("[data-delta],[data-gp],[data-min]");
  if (!i) return;
  i.select();
  const id = +(i.dataset.delta || i.dataset.gp || i.dataset.min);
  if (UI.sel === id) return;
  UI.sel = id;
  tb.querySelectorAll("tr.sel").forEach((t) => t.classList.remove("sel"));
  i.closest("tr").classList.add("sel");
  renderDetail();
});
function readPrice(s) {
  const v = parseNum(s);
  if (v == null || Number.isNaN(v) || v < 1) { toast("Prices are whole dollars, like 34 or $34."); return null; }
  return Math.round(v);
}
function saveCell(input) {
  const v = parseNum(input.value);
  if (input.dataset.delta) {
    if (Number.isNaN(v)) { toast("Δ needs a number of rating points, like +10 or -5."); return renderKeepFocus(); }
    act("adjust", { id: +input.dataset.delta, delta: Math.round(v ?? 0) }); // empty box clears Δ
  } else if (input.dataset.min) {
    if (Number.isNaN(v) || (v != null && v < 0)) { toast(`Expected minutes needs a number from 0 to ${B.meta.maxMin}.`); return renderKeepFocus(); }
    act("adjust", { id: +input.dataset.min, expMin: v }); // empty box resets to ESPN's projection
  } else if (input.dataset.gp) {
    if (Number.isNaN(v)) { toast("GP Δ needs a number of games, like -10 or +5."); return renderKeepFocus(); }
    act("adjust", { id: +input.dataset.gp, gpDelta: Math.round(v ?? 0) }); // empty box goes back to ESPN's games
  }
}
tb.addEventListener("change", (e) => {
  const cell = e.target.closest("[data-delta],[data-gp],[data-min]");
  if (cell) saveCell(cell);
});
tb.addEventListener("keydown", (e) => {
  if (!e.target.matches(".cell")) return;
  if (e.key === "Enter") { e.target.blur(); return; }
  if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
  e.preventDefault();
  const v = parseNum(e.target.value);
  const step = SCRUB[cellKind(e.target)].step * (e.shiftKey ? 5 : 1) * (e.key === "ArrowUp" ? 1 : -1);
  const next = (Number.isNaN(v) || v == null ? 0 : v) + step;
  e.target.value = e.target.dataset.min ? String(Math.max(0, next)) : signedInput(next);
  saveCell(e.target);
});

// Click-and-drag scrubbing on the Exp GP, Exp MIN and Δ cells: drag sideways
// to change the value (Shift for bigger steps); a plain click still types.
const SCRUB = {
  gp: { key: "gpDelta", px: 4, step: 1, min: -82, max: 82 },
  min: { key: "expMin", px: 6, step: 0.5, min: 0, max: 48 },
  delta: { key: "delta", px: 4, step: 1, min: -60, max: 60 },
};
const cellKind = (el) => (el.dataset.delta ? "delta" : el.dataset.min ? "min" : "gp");
const cellId = (el) => +(el.dataset.delta || el.dataset.min || el.dataset.gp);
let scrub = null;

// Update one row's numbers in place, leaving the input being dragged alone.
function patchRow(id, keep) {
  const tr = tb.querySelector(`tr[data-id="${id}"]`), r = byId.get(id);
  if (!tr || !r) return;
  const tmp = document.createElement("tbody");
  tmp.innerHTML = rowHTML(r);
  const fresh = tmp.firstElementChild.children;
  [...tr.children].forEach((td, i) => { if (!td.contains(keep) && fresh[i]) td.innerHTML = fresh[i].innerHTML; });
}
function renderScrub() {
  byId = new Map(B.rows.map((r) => [r.id, r]));
  renderScore(); renderCatRow(); renderStrip(); renderTeam();
  if (scrub) patchRow(scrub.id, scrub.cell);
  if (scrub && UI.sel === scrub.id) renderDetail();
}
const sendScrub = (() => {
  let inflight = false, pending = null;
  return async (body) => {
    pending = body;
    if (inflight) return;
    while (pending) {
      const b = pending; pending = null; inflight = true;
      const data = await api("/api/adjust", b);
      if (data && data.board) { B = data.board; renderScrub(); }
      inflight = false;
    }
  };
})();

tb.addEventListener("pointerdown", (e) => {
  const cell = e.target.closest(".cell");
  if (!cell || e.button !== 0 || document.activeElement === cell) return; // already typing: select text normally
  const v = parseNum(cell.value);
  scrub = { cell, kind: cellKind(cell), id: cellId(cell), pointer: e.pointerId, x: e.clientX,
    start: v == null || Number.isNaN(v) ? 0 : v, moved: false, last: null };
});
document.addEventListener("pointermove", (e) => {
  if (!scrub || e.pointerId !== scrub.pointer) return;
  const dx = e.clientX - scrub.x;
  if (!scrub.moved) {
    if (Math.abs(dx) < 4) return;
    scrub.moved = true;
    scrub.cell.blur();
    window.getSelection()?.removeAllRanges();
    document.body.classList.add("scrubbing");
    try { scrub.cell.setPointerCapture(e.pointerId); } catch (err) { /* capture is best-effort */ }
  }
  e.preventDefault();
  const c = SCRUB[scrub.kind], r = byId.get(scrub.id);
  // Games: keep ESPN's projection + Δ between 0 and 82.
  const [lo, hi] = scrub.kind === "gp" && r ? [-r.espnGp, 82 - r.espnGp] : [c.min, c.max];
  const v = Math.max(lo, Math.min(hi, scrub.start + Math.round(dx / c.px) * c.step * (e.shiftKey ? 5 : 1)));
  if (v === scrub.last) return;
  scrub.last = v;
  scrub.cell.value = scrub.kind === "min" ? v.toFixed(1) : signedInput(v);
  scrub.cell.classList.toggle("edited", scrub.kind === "min" || v !== 0);
  sendScrub({ id: scrub.id, [c.key]: v });
});
function endScrub(e) {
  if (!scrub || (e && e.pointerId !== scrub.pointer)) return;
  const s = scrub;
  scrub = null;
  document.body.classList.remove("scrubbing");
  if (!s.moved) return; // a plain click: let the input take focus for typing
  if (s.last != null) act("adjust", { id: s.id, [SCRUB[s.kind].key]: s.last }); // final value, then full redraw
}
document.addEventListener("pointerup", endScrub);
document.addEventListener("pointercancel", endScrub);

const det = $("detail");
det.addEventListener("input", (e) => {
  if (e.target.id === "dRange") { $("dOut").textContent = signed(+e.target.value); sendAdjust({ id: UI.sel, delta: +e.target.value }); }
  if (e.target.id === "gRange") { $("gOut").textContent = gpOut(byId.get(UI.sel), +e.target.value); sendAdjust({ id: UI.sel, gpDelta: +e.target.value }); }
  if (e.target.id === "mRange") { $("mOut").textContent = fmt(+e.target.value); sendAdjust({ id: UI.sel, expMin: +e.target.value }); }
});
det.addEventListener("change", (e) => {
  if (["dRange", "gRange", "mRange"].includes(e.target.id)) renderKeepFocus(); // redraw bars once the drag ends
  if (e.target.id === "noteBox") act("adjust", { id: UI.sel, note: e.target.value });
});
det.addEventListener("click", (e) => {
  const b = e.target.closest("[data-pick]");
  const r = byId.get(UI.sel);
  if (b && r) {
    if (b.dataset.pick === "taken") return act("pick", { id: r.id, status: "taken" });
    const price = readPrice($("priceIn").value);
    if (price == null) return;
    act("pick", { id: r.id, status: "mine", price });
    return;
  }
  if (!r) return;
  if (e.target.id === "undoPick") {
    if (r.status === "mine") removeMine(r.id);
    else act("pick", { id: r.id, status: null });
  } else if (e.target.id === "useEspn") {
    // Minutes and games default to ESPN's already; set the skill change to ESPN's too.
    act("adjust", { id: r.id, expMin: null, gpDelta: 0, delta: r.espnDelta || 0 });
  } else if (e.target.id === "resetMin") {
    act("adjust", { id: r.id, expMin: null });
  } else if (e.target.id === "resetGp") {
    act("adjust", { id: r.id, gpDelta: 0 });
  }
});

$("resetBtn").addEventListener("click", () => {
  const prev = snapshotState();
  act("reset-adjustments").then((ok) => ok && toast("Cleared all Δ and expected-games edits. Notes were kept.", undoTo(prev)));
});
$("refreshBtn").addEventListener("click", async () => {
  const b = $("refreshBtn");
  b.disabled = true; b.classList.add("busy"); b.textContent = "Refreshing…";
  const ok = await act("refresh");
  b.disabled = false; b.classList.remove("busy"); b.textContent = "Refresh from ESPN";
  if (ok) toast("Player pool refreshed from ESPN.");
});

// ------------------------------------------------------------------ settings

function renderSettings() {
  const el = $("settingsPanel"), m = B.meta, room = B.state.settings, d = m.defaults;
  const scaleCustom = room.marketScale != null;
  const samples = [...B.rows].sort((a, b) => b.avgRaw - a.avgRaw).slice(0, 3);
  const counted = m.rosterSize - (room.ignorePlayers ?? d.ignorePlayers);
  const bench = m.slots.filter((x) => x === "BE").length;
  const scoring = { H2H_CATEGORY: "H2H categories", H2H_MOST_CATEGORIES: "H2H most categories", ROTO: "Roto", H2H_POINTS: "H2H points" }[m.scoringType] || (m.scoringType || "").replace(/_/g, " ").toLowerCase();
  const rep = m.replacement, core = m.core, streamers = m.rosterSize - core;
  el.innerHTML = `
    <section class="set">
      <div class="set-t"><h3>Replacement player</h3>
        <p>The per-game rating of the free agent you pick up when a player is hurt or on IR. His games fill the ones your player misses, so a missed game only costs the gap between them. Set 0 to count missed games as lost.</p></div>
      <div class="set-c">
        <div class="range-row"><input type="range" id="setRep" min="0" max="${m.maxReplacement}" step="1" value="${rep}" aria-label="Replacement player rating">
          <output id="setRepOut">${rep}</output></div>
        <p class="hint">${room.replacement != null ? `<button class="linkbtn" type="button" id="setRepReset">Use default (${d.replacement})</button>` : `Default: a top free agent. The average one is about 86.`}</p>
        <p class="hint" id="setRepEx">${repExample(rep)}</p>
      </div>
    </section>
    <section class="set">
      <div class="set-t"><h3>Core players</h3>
        <p>How many players per team are worth paying for. They share the league's money; the rest of the roster are $1 players you stream. Ours and Edge are priced this way.</p></div>
      <div class="set-c">
        <label class="inline" for="setCore">Pay for the best <select id="setCore">${Array.from({ length: m.rosterSize }, (_, i) => m.rosterSize - i)
          .map((n) => `<option value="${n}" ${n === core ? "selected" : ""}>${n}</option>`).join("")}</select> of ${m.rosterSize}</label>
        <p class="hint">${m.pricedSize} players are priced above $1${streamers ? `; ${streamers} per team are $1 streamers` : ""}.${room.core != null ? ` <button class="linkbtn" type="button" id="setCoreReset">Use default (${d.core})</button>` : ""}</p>
      </div>
    </section>
    <section class="set">
      <div class="set-t"><h3>Enough in a category</h3>
        <p>In head-to-head you win a category or you don't, so strength past winning it is wasted. For the Fit column, your team's rating in a category counts in full up to the first number, less and less above it, and not at all past the second.</p></div>
      <div class="set-c">
        <label class="inline" for="setFadeStart">Start fading at <input class="numin" type="text" inputmode="numeric" id="setFadeStart" value="${m.fade[0]}" aria-label="Start fading at"></label>
        <label class="inline" for="setFadeEnd">Worth nothing past <input class="numin" type="text" inputmode="numeric" id="setFadeEnd" value="${m.fade[1]}" aria-label="Worth nothing past"></label>
        <p class="hint">${room.fadeStart != null || room.fadeEnd != null ? `<button class="linkbtn" type="button" id="setFadeReset">Use default (${d.fade[0]} to ${d.fade[1]})</button>` : `Default. 100 is the average team.`} Punt a category with its checkbox in the team row: Fit then ignores it.${m.punt.length ? ` Punted now: ${m.punt.map(esc).join(", ")}.` : ""}</p>
      </div>
    </section>
    <section class="set">
      <div class="set-t"><h3>Avg paid scale</h3>
        <p>ESPN's average prices come from leagues of every size. They're multiplied by this to fit your league. Auto makes the top ${m.poolSize} prices add up to ${m.teams} × $${m.budget} = $${(m.teams * m.budget).toLocaleString()}.</p></div>
      <div class="set-c">
        <div class="range-row"><input type="range" id="setScale" min="0.5" max="2.5" step="0.01" value="${m.marketScale}" aria-label="Avg paid scale">
          <output id="setScaleOut">×${m.marketScale.toFixed(2)}</output></div>
        <p class="hint">${scaleCustom ? `Custom. <button class="linkbtn" type="button" id="setScaleAuto">Use auto (×${m.autoMarketScale.toFixed(2)})</button>` : "Auto"}</p>
        <p class="hint" id="setScaleEx">${scaleSamples(samples, m.marketScale)}</p>
      </div>
    </section>
    <section class="set">
      <div class="set-t"><h3>Categories in player value</h3>
        <p>Which categories count toward each player's rating, Ours and Edge. Team ranks always show every league category.</p></div>
      <div class="set-c"><div class="catpick" role="group" aria-label="Categories in player value">${m.categories.map((c) => `
        <label class="cp" for="cat-${esc(c)}"><input type="checkbox" id="cat-${esc(c)}" data-cat="${esc(c)}" ${m.rated.includes(c) ? "checked" : ""}>${esc(c)}</label>`).join("")}</div>
        <p class="hint">${room.rated != null ? `Changed from settings.txt. <button class="linkbtn" type="button" id="setCatsReset">Use settings.txt (${d.rated.map(esc).join(", ")})</button>` : "From settings.txt"}</p>
      </div>
    </section>
    <section class="set">
      <div class="set-t"><h3>Players who count</h3>
        <p>Team totals use your best players and drop the rest, as bench players rarely all play.</p></div>
      <div class="set-c">
        <label class="inline" for="setCounted">Best <select id="setCounted">${Array.from({ length: m.rosterSize }, (_, i) => m.rosterSize - i)
          .map((n) => `<option value="${n}" ${n === counted ? "selected" : ""}>${n}</option>`).join("")}</select> of ${m.rosterSize} count</label>
        <p class="hint">${room.ignorePlayers != null ? `<button class="linkbtn" type="button" id="setCountedReset">Use settings.txt (best ${m.rosterSize - d.ignorePlayers})</button>` : "From settings.txt"}</p>
      </div>
    </section>
    <section class="set">
      <div class="set-t"><h3>Reset draft</h3>
        <p>Unmark every taken player and empty your roster. Adjustments, notes and settings stay.</p></div>
      <div class="set-c"><button class="btn danger" type="button" id="resetDraft" ${B.pool.taken || B.me.count ? "" : "disabled"}>Reset draft</button>
        <p class="hint">${B.pool.taken} taken · ${B.me.count} on your team</p></div>
    </section>
    <section class="set">
      <div class="set-t"><h3>League</h3><p>From ESPN. Change these on ESPN, then click Refresh from ESPN.</p></div>
      <div class="set-c"><dl class="facts">
        <dt>League</dt><dd>${esc(m.leagueName)}${m.leagueId ? ` <span class="muted">#${m.leagueId}</span>` : ""}</dd>
        <dt>Format</dt><dd>${m.teams} teams · $${m.budget} ${esc((m.draftType || "").toLowerCase())} · ${esc(scoring)}</dd>
        <dt>Roster</dt><dd>${m.slots.filter((x) => x !== "BE").map(esc).join(", ")}${bench ? `, ${bench} bench` : ""}</dd>
        <dt>Categories</dt><dd>${m.categories.map((c) => esc(c) + (m.reverse.includes(c) ? " (lower is better)" : "")).join(", ")}</dd>
      </dl></div>
    </section>`;
}
// A 140-rated star who plays 50 games, valued at a given replacement rating.
function repExample(rep) {
  const g = B.meta.gamesInSeason, v = (140 * 50 + rep * (g - 50)) / g;
  return `A 140-rated player who plays 50 games is worth <b>${fmt(v)}</b>. Each missed game costs ${fmt((140 - rep) / g, 2)}.`;
}
function scaleSamples(rows, k) {
  return rows.map((r) => `${esc(lastName(r.name))} $${Math.round(r.avgRaw)} → <b>$${Math.round(r.avgRaw * k)}</b>`).join(" · ");
}

const setEl = $("settingsPanel");
setEl.addEventListener("input", (e) => {
  if (e.target.id === "setScale") {
    const k = +e.target.value;
    $("setScaleOut").textContent = "×" + k.toFixed(2);
    $("setScaleEx").innerHTML = scaleSamples([...B.rows].sort((a, b) => b.avgRaw - a.avgRaw).slice(0, 3), k);
    sendSettings({ marketScale: k });
  } else if (e.target.id === "setRep") {
    $("setRepOut").textContent = e.target.value;
    $("setRepEx").innerHTML = repExample(+e.target.value);
    sendSettings({ replacement: +e.target.value });
  }
});
setEl.addEventListener("change", (e) => {
  const t = e.target;
  if (t.id === "setScale" || t.id === "setRep") return renderKeepFocus(); // full redraw once the drag ends
  if (t.dataset.cat) {
    const rated = [...setEl.querySelectorAll("[data-cat]")].filter((c) => c.checked).map((c) => c.dataset.cat);
    if (!rated.length) { t.checked = true; return toast("At least one category has to count."); }
    act("settings", { rated });
  } else if (t.id === "setFadeStart" || t.id === "setFadeEnd") {
    const v = parseNum(t.value);
    if (v == null || Number.isNaN(v)) { toast("Use a team rating, like 110."); return renderKeepFocus(); }
    act("settings", { [t.id === "setFadeStart" ? "fadeStart" : "fadeEnd"]: Math.round(v) });
  } else if (t.id === "setCore") {
    act("settings", { core: +t.value });
  } else if (t.id === "setCounted") {
    act("settings", { ignorePlayers: B.meta.rosterSize - +t.value });
  }
});
setEl.addEventListener("click", (e) => {
  const id = e.target.id;
  if (id === "setScaleAuto") act("settings", { marketScale: null });
  else if (id === "setCatsReset") act("settings", { rated: null });
  else if (id === "setCountedReset") act("settings", { ignorePlayers: null });
  else if (id === "setRepReset") act("settings", { replacement: null });
  else if (id === "setCoreReset") act("settings", { core: null });
  else if (id === "setFadeReset") act("settings", { fadeStart: null, fadeEnd: null });
  else if (id === "resetDraft") {
    const prev = snapshotState(), n = B.pool.taken + B.me.count;
    act("reset-draft").then((ok) => ok && toast(`Reset the draft: ${n} player${n === 1 ? "" : "s"} back in the pool.`, undoTo(prev)));
  }
});

// ------------------------------------------------------------------ tabs + theme

function setView(v) {
  UI.view = v; UI.pickSlot = null;
  history.replaceState(null, "", v === "board" ? location.pathname : "#" + v);
  VIEWS.forEach((k) => {
    $("view-" + k).hidden = v !== k;
    $("tab-" + k).setAttribute("aria-selected", v === k);
  });
}
const VIEWS = ["board", "team", "settings"];
VIEWS.forEach((k) => $("tab-" + k).addEventListener("click", () => { setView(k); render(); }));

function setTheme(t) {
  if (t === "system") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = t;
  document.querySelectorAll("[data-theme-btn]").forEach((b) => b.setAttribute("aria-pressed", b.dataset.themeBtn === t));
  try { localStorage.setItem("draftroom-theme", t); } catch (e) { /* storage blocked */ }
}
document.querySelectorAll("[data-theme-btn]").forEach((b) => b.addEventListener("click", () => setTheme(b.dataset.themeBtn)));
let savedTheme = "system";
try { savedTheme = localStorage.getItem("draftroom-theme") || "system"; } catch (e) { /* storage blocked */ }
setTheme(savedTheme);

// With `python3 -m gui --reload`, reload the page after a server restart or a static-file edit.
async function watchForReload() {
  const version = async () => { try { return await (await fetch("/api/version", { cache: "no-store" })).json(); } catch (e) { return null; } };
  const first = await version();
  if (!first || !first.reload) return;
  setInterval(async () => {
    const now = await version(); // null while the server restarts: keep waiting
    if (now && (now.boot !== first.boot || now.static !== first.static)) location.reload();
  }, 1000);
}
watchForReload();

if (VIEWS.includes(location.hash.slice(1))) setView(location.hash.slice(1));
(async () => {
  const b = await api("/api/board");
  if (b) { B = b; render(); }
  else $("tbody").innerHTML = `<tr><td class="empty-row">Couldn't load the board. Check the terminal running python3 -m gui.</td></tr>`;
})();
