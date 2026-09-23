"use strict";
// Draft Room frontend. The server owns all state and math (gui/board.py);
// this file renders the snapshot it returns and sends edits back.

const $ = (id) => document.getElementById(id);
let B = null; // latest board snapshot
let byId = new Map();
const UI = { q: "", pos: "ALL", hideGone: false, onlyAdj: false, sort: { key: "rank", dir: 1 },
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
const sendWeight = liveSender("weight");
const sendAdjust = liveSender("adjust");

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
  renderMeta(); renderScore(); renderCatRow(); renderHead(); renderBody(); renderStrip(); renderDetail(); renderTeam();
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
  $("weight").value = Math.round(B.state.weight * 100);
  weightLabel();
}

function weightLabel() {
  const p = +$("weight").value;
  $("wOut").textContent = `${p}/${100 - p}`;
  $("wOut").title = `${p}% per game, ${100 - p}% full season`;
}

function renderScore() {
  const me = B.me, m = B.market;
  $("sBudget").textContent = money(me.budgetLeft);
  $("sMax").textContent = `max bid ${money(me.maxBid)}`;
  $("sRoster").textContent = `${me.count} / ${B.meta.rosterSize}`;
  $("sRosterSub").textContent = me.count ? me.names.map(lastName).join(", ") : "No picks yet";
  $("sInfl").textContent = m.inflation.toFixed(2) + "×";
  $("sInflSub").textContent = `${m.drafted} drafted · $${m.moneyLeft.toLocaleString()} left in league`;
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
    el.innerHTML = `<div class="cr-head"><span class="lbl">My team</span><span class="v" id="crOverall"></span><span class="s" id="crSub"></span></div>` +
      t.categories.map((c, i) => `<div class="cc" id="cc-${i}">
        <span class="lbl">${esc(c.cat)}</span>
        <span class="col"><i></i></span>
        <span class="nums"><span class="rv"></span><span class="rk"></span></span>
        <span class="dchip"></span></div>`).join("");
  }
  $("crOverall").textContent = `${ord(t.overall)} of ${n}`;
  $("crSub").textContent = `100 = average team${t.filled < B.meta.rosterSize ? ` · ${B.meta.rosterSize - t.filled} empty slots at replacement` : ""}`;
  const next = {};
  t.categories.forEach((c, i) => {
    const cell = $(`cc-${i}`), r = c.rating;
    next[c.cat] = r;
    const bar = cell.querySelector(".col i");
    // Diverging from the 100 midline: up = better than the average team, down = worse. ±40 fills a half.
    bar.classList.toggle("below", r < 100);
    bar.style.height = `${Math.min(Math.abs(r - 100), 40) / 40 * 50}%`;
    cell.querySelector(".rv").textContent = Math.round(r);
    const rk = cell.querySelector(".rk");
    rk.textContent = ord(c.rank);
    rk.className = "rk " + (c.rank <= 3 ? "top" : c.rank >= n - 2 ? "low" : "mid");
    cell.title = `${c.cat}: rating ${Math.round(r)}, ${ord(c.rank)} of ${n}${c.reverse ? " (lower totals are better)" : ""}`;
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
$("catrow").addEventListener("click", () => { setView("team"); render(); });
$("catrow").addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setView("team"); render(); }
});

// ------------------------------------------------------------------ board table

const GROUPS = () => [
  { label: "", span: 2 },
  { label: B.meta.statsLabel, span: 3 },
  { label: `${B.meta.seasonLabel} outlook`, span: 4, cls: "g-out" },
  { label: "Auction $", span: 5, cls: "g-ours" },
];
const COLS = [
  { key: "rank", label: "Rk", title: "Rank by value" },
  { key: "name", label: "Player", cls: "l" },
  { key: "gp", label: "GP", title: "Games played last season" },
  { key: "lastPg", label: "Per gm", title: "Per-game rating (100 = pool average)" },
  { key: "lastSeason", label: "Season", title: "Full-season rating. Missed games pull it down." },
  { key: "expGp", label: "Exp GP", title: "Expected games. Default: halfway between last season and ESPN's projection. Clear to reset." },
  { key: "delta", label: "Δ %", title: "Overall change. Scales every counting stat and shot attempt." },
  { key: "projPg", label: "Per gm", title: "Projected per-game rating" },
  { key: "value", label: "Value", title: "Blend of projected per-game and full-season ratings" },
  { key: "espn", label: "ESPN", title: "ESPN's suggested auction value for this league" },
  { key: "avg", label: "Avg paid", title: "Average price in ESPN auction drafts" },
  { key: "ours", label: "Ours", cls: "ours-h", title: "Our value before the draft" },
  { key: "edge", label: "Edge", cls: "ours-h", title: "Ours − Avg paid" },
  { key: "bid", label: "Bid to", cls: "ours-h", title: "Ours adjusted for inflation" },
];

function renderHead() {
  const g = `<tr class="grp">${GROUPS().map((g) => `<th colspan="${g.span}" class="${g.cls || ""}">${g.label ? `<span>${esc(g.label)}</span>` : ""}</th>`).join("")}</tr>`;
  const c = `<tr>${COLS.map((c) => {
    const s = UI.sort.key === c.key ? ` aria-sort="${UI.sort.dir < 0 ? "descending" : "ascending"}"` : "";
    return `<th class="${c.cls || ""}"${s} scope="col"><button type="button" data-sort="${c.key}" title="${esc(c.title || "")}">${c.label}</button></th>`;
  }).join("")}</tr>`;
  $("thead").innerHTML = g + c;
}

function visibleRows() {
  const q = norm(UI.q.trim());
  const rows = B.rows.filter((r) =>
    (!q || norm(r.name).includes(q) || norm(r.team).includes(q)) &&
    (UI.pos === "ALL" || r.elig.includes(UI.pos)) &&
    (!UI.hideGone || !r.status) &&
    (!UI.onlyAdj || r.delta || r.gpSet || r.note));
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
  return `<span class="pill ${r.status}">${r.status === "mine" ? "Mine" : "Taken"} $${r.price}</span>`;
}
function badges(r) {
  let s = injuryPill(r.inj);
  if (r.fromProj) s += `<span class="pill proj" title="No ${B.meta.statsLabel} games. Based on ESPN's projection.">ESPN proj</span>`;
  else if (r.gp < 25) s += `<span class="pill low" title="Only ${r.gp} games last season">${r.gp} GP</span>`;
  return s;
}

function rowHTML(r) {
  const e = r.edge, ecls = e >= 3 ? "pos" : e <= -3 ? "neg" : "";
  const drag = r.status === "taken" ? "" : ` draggable="true" data-drag="${r.id}" title="Drag onto a roster slot"`;
  return `<tr data-id="${r.id}" class="${UI.sel === r.id ? "sel" : ""} ${r.status ? "gone" : ""}">
    <td class="rk">${r.rank}</td>
    <td class="l"><div class="pcell"${drag}><span class="pname">${esc(r.name)}${statusPill(r)}</span><span class="psub">${esc(r.team)} · ${esc(r.pos)}${badges(r)}</span></div></td>
    <td>${r.fromProj ? "—" : r.gp}</td>
    <td>${fmt(r.lastPg)}</td>
    <td>${r.fromProj ? "—" : fmt(r.lastSeason)}</td>
    <td><input class="cell ${r.gpSet ? "edited" : ""}" type="text" inputmode="numeric" autocomplete="off" value="${r.expGp}" aria-label="Expected games for ${esc(r.name)}" data-gp="${r.id}" id="g-${r.id}"></td>
    <td><input class="cell ${r.delta ? "edited" : ""}" type="text" inputmode="text" autocomplete="off" value="${signedInput(r.delta)}" placeholder="0" aria-label="Δ percent for ${esc(r.name)}" data-delta="${r.id}" id="d-${r.id}"></td>
    <td>${fmt(r.projPg)}</td>
    <td class="val">${fmt(r.value)}</td>
    <td>${money(r.espn)}</td>
    <td>${money(r.avg)}</td>
    <td class="ours">${money(r.ours)}</td>
    <td class="ours"><span class="edge ${ecls}">${signed(e)}</span></td>
    <td class="ours">${r.status ? "—" : money(r.bid)}</td>
  </tr>`;
}

function renderBody() {
  const rows = visibleRows();
  $("tbody").innerHTML = rows.length ? rows.map(rowHTML).join("")
    : `<tr><td colspan="${COLS.length}" class="empty-row">No players match${UI.q ? ` “${esc(UI.q)}”` : ""}. Clear the search or turn off a filter.</td></tr>`;
}

// ------------------------------------------------------------------ detail panel

function bars(before, after, cats) {
  const MAX = 250, x0 = 44, w = 206, rh = 24;
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

function renderDetail() {
  const el = $("detail"), r = byId.get(UI.sel);
  if (!r) { el.innerHTML = `<p class="muted">Select a player to see their category breakdown.</p>`; return; }
  const slotName = r.status === "mine" ? B.meta.slots[B.state.filled.indexOf(r.id)] : null;
  const espnHint = r.fromProj
    ? `No ${B.meta.statsLabel} games, so this uses ESPN's projection (${r.projGp} GP).`
    : `Last season ${r.gp} GP · ESPN projects ${r.projGp || "—"} GP${r.espnDelta != null ? ` and ${signed(r.espnDelta)}% volume` : ""}.`;
  el.innerHTML = `
    <div><h2>${esc(r.name)}</h2>
      <div class="dsub"><span>${esc(r.team)} · ${esc(r.pos)}</span><span class="num">${r.line.map((v) => fmt(v)).join(" / ")} pts/reb/ast</span>${injuryPill(r.inj, true)}</div></div>
    <div class="kv">
      <div><span class="lbl">Value rank</span><span class="v">#${r.rank}</span></div>
      <div><span class="lbl">ESPN rank</span><span class="v">#${r.espnRank ?? "—"}</span></div>
      <div><span class="lbl">Avg paid</span><span class="v">${money(r.avg)}</span></div>
      <div><span class="lbl">Ours</span><span class="v">${money(r.ours)}</span></div>
      <div><span class="lbl">Edge</span><span class="v ${r.edge >= 3 ? "up" : r.edge <= -3 ? "down" : ""}">${signed(r.edge)}</span></div>
      <div><span class="lbl">Bid to</span><span class="v">${r.status ? "—" : money(r.bid)}</span></div>
    </div>
    <table class="rtab" aria-label="Ratings">
      <thead><tr><th scope="col">Rating</th><th scope="col">${B.meta.statsLabel}</th><th scope="col">${B.meta.seasonLabel}</th></tr></thead>
      <tbody>
        <tr><th scope="row">Per game</th><td>${fmt(r.lastPg)}</td><td>${fmt(r.projPg)}</td></tr>
        <tr><th scope="row">Season</th><td>${r.fromProj ? "—" : `${fmt(r.lastSeason)} <span class="g">${r.gp}g</span>`}</td><td>${fmt(r.projSeason)} <span class="g">${r.expGp}g</span></td></tr>
        <tr><th scope="row">Value</th><td></td><td><b>${fmt(r.value)}</b></td></tr>
      </tbody>
    </table>
    <div class="bars"><span class="lbl sec-t">Δ ${signed(r.delta)}% across categories · per game</span>${bars(r.catLast, r.catProj, B.meta.rated)}
      <div class="legend"><span><i style="background:var(--line-strong)"></i>${B.meta.statsLabel}</span><span><i style="background:var(--accent)"></i>${B.meta.seasonLabel}</span><span>100 = pool avg</span></div></div>
    <div><span class="lbl sec-t">Adjust</span>
      <div class="adj"><span>Δ</span><input type="range" id="dRange" min="-50" max="50" step="1" value="${r.delta}" aria-label="Δ percent"><output id="dOut">${signed(r.delta)}%</output></div>
      <div class="adj"><span>Exp GP</span><input type="range" id="gRange" min="0" max="82" step="1" value="${r.expGp}" aria-label="Expected games"><output id="gOut">${r.expGp}</output></div>
      <p class="hint">${espnHint}
        ${r.espnDelta != null || r.projGp ? `<button class="linkbtn" type="button" id="useEspn">Use ESPN's</button>` : ""}
        ${r.gpSet ? ` · <button class="linkbtn" type="button" id="resetGp">Reset games</button>` : ""}</p></div>
    <div><label class="lbl sec-t" for="noteBox">Note</label>
      <textarea id="noteBox" placeholder="Why the adjustment?">${esc(r.note || "")}</textarea></div>
    <div><span class="lbl sec-t">Draft</span>
      ${r.status
        ? `<div class="draftrow">${r.status === "mine" ? `<span class="pill mine">Mine · ${esc(slotName || "?")} $${r.price}</span>` : `<span class="pill taken">Taken $${r.price}</span>`}
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
    ? ` Best-value help in <b>${esc(t.targets[0].cat)}</b>: ${t.targets.map((x) => `<button class="linkbtn" type="button" data-goto="${x.id}">${esc(x.name)}</button> (${x.rating}, bid to $${x.bid})`).join(" and ")}.`
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
$("q").addEventListener("input", (e) => { UI.q = e.target.value; renderBody(); });
["hideGone", "onlyAdj"].forEach((k) => $(k).addEventListener("change", (e) => { UI[k] = e.target.checked; renderBody(); }));
$("weight").addEventListener("input", (e) => { weightLabel(); sendWeight({ weight: +e.target.value / 100 }); });
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
  const tr = e.target.closest("tr[data-id]");
  if (!tr) return;
  UI.sel = +tr.dataset.id;
  tb.querySelectorAll("tr.sel").forEach((t) => t.classList.remove("sel"));
  tr.classList.add("sel");
  renderDetail();
});
tb.addEventListener("focusin", (e) => {
  const i = e.target.closest("[data-delta],[data-gp]");
  if (!i) return;
  const id = +(i.dataset.delta || i.dataset.gp);
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
    if (Number.isNaN(v)) { toast("Δ needs a number, like +5, -10 or 5%."); return renderKeepFocus(); }
    act("adjust", { id: +input.dataset.delta, delta: Math.round(v ?? 0) }); // empty box clears Δ
  } else if (input.dataset.gp) {
    if (Number.isNaN(v) || (v != null && v < 0)) { toast("Expected games needs a number from 0 to 82."); return renderKeepFocus(); }
    act("adjust", { id: +input.dataset.gp, expGp: v == null ? null : Math.round(v) }); // empty box resets to default
  }
}
tb.addEventListener("change", (e) => {
  const cell = e.target.closest("[data-delta],[data-gp]");
  if (cell) saveCell(cell);
});
tb.addEventListener("keydown", (e) => {
  if (!e.target.matches(".cell")) return;
  if (e.key === "Enter") { e.target.blur(); return; }
  if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
  e.preventDefault();
  const v = parseNum(e.target.value);
  const step = (e.shiftKey ? 5 : 1) * (e.key === "ArrowUp" ? 1 : -1);
  const next = (Number.isNaN(v) || v == null ? 0 : v) + step;
  e.target.value = e.target.dataset.delta ? signedInput(next) : String(Math.max(0, next));
  saveCell(e.target);
});

const det = $("detail");
det.addEventListener("input", (e) => {
  if (e.target.id === "dRange") { $("dOut").textContent = signed(+e.target.value) + "%"; sendAdjust({ id: UI.sel, delta: +e.target.value }); }
  if (e.target.id === "gRange") { $("gOut").textContent = e.target.value; sendAdjust({ id: UI.sel, expGp: +e.target.value }); }
});
det.addEventListener("change", (e) => {
  if (e.target.id === "dRange" || e.target.id === "gRange") renderKeepFocus(); // redraw bars once the drag ends
  if (e.target.id === "noteBox") act("adjust", { id: UI.sel, note: e.target.value });
});
det.addEventListener("click", (e) => {
  const b = e.target.closest("[data-pick]");
  const r = byId.get(UI.sel);
  if (b && r) {
    const price = readPrice($("priceIn").value);
    if (price == null) return;
    act("pick", { id: r.id, status: b.dataset.pick, price });
    return;
  }
  if (!r) return;
  if (e.target.id === "undoPick") {
    if (r.status === "mine") removeMine(r.id);
    else act("pick", { id: r.id, status: null });
  } else if (e.target.id === "useEspn") {
    const body = { id: r.id };
    if (r.espnDelta != null) body.delta = r.espnDelta;
    if (r.projGp) body.expGp = r.projGp;
    act("adjust", body);
  } else if (e.target.id === "resetGp") {
    act("adjust", { id: r.id, expGp: null });
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

// ------------------------------------------------------------------ tabs + theme

function setView(v) {
  UI.view = v; UI.pickSlot = null;
  history.replaceState(null, "", v === "team" ? "#team" : location.pathname);
  $("view-board").hidden = v !== "board";
  $("view-team").hidden = v !== "team";
  $("tab-board").setAttribute("aria-selected", v === "board");
  $("tab-team").setAttribute("aria-selected", v === "team");
}
$("tab-board").addEventListener("click", () => { setView("board"); render(); });
$("tab-team").addEventListener("click", () => { setView("team"); render(); });

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

if (location.hash === "#team") setView("team");
(async () => {
  const b = await api("/api/board");
  if (b) { B = b; render(); }
  else $("tbody").innerHTML = `<tr><td class="empty-row">Couldn't load the board. Check the terminal running python3 -m gui.</td></tr>`;
})();
