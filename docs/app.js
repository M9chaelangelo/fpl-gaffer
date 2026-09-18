/* Gaffer — the interactive page.
 *
 * Reads docs/data.json, which the solve writes. No framework, no build, no
 * CDN: GitHub Pages serves static files, and a dependency that 404s on a
 * Friday evening is worse than no dependency at all.
 *
 * Charts are inline SVG built here rather than by a library, for the same
 * reason. Every bar carries a visible label — light-mode aqua sits below 3:1
 * against the surface, and the palette's relief rule says a label or a table
 * has to carry the value when contrast alone cannot.
 */
"use strict";

const S = { data: null, view: "team", sort: { key: "ep_next", dir: -1 }, cmp: [null, null] };

const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
};

/* --- formatting --------------------------------------------------------- */

const FMT = {
  num:   (v) => v == null ? "—" : (+v).toFixed(1),
  num3:  (v) => v == null ? "—" : (+v).toFixed(3),
  num4:  (v) => v == null ? "—" : (+v).toFixed(4),
  int:   (v) => v == null ? "—" : String(Math.round(v)),
  pct:   (v) => v == null ? "—" : Math.round(v * 100) + "%",
  money: (v) => v == null ? "—" : (+v).toFixed(1),
};
const fmt = (v, kind) => (FMT[kind] || FMT.num)(v);

const byId = (id) => S.data.index.get(id);

/* --- boot --------------------------------------------------------------- */

async function boot() {
  try {
    // Cache-bust: the file is rewritten by a commit, and Pages caches hard.
    const res = await fetch("data.json?v=" + Date.now());
    if (!res.ok) throw new Error("data.json returned " + res.status);
    const d = await res.json();
    d.index = new Map(d.players.map((p) => [p.id, p]));
    d.mine = new Set(d.squad_ids);
    S.data = d;
  } catch (err) {
    $("loading").classList.add("hidden");
    const f = $("failed");
    f.classList.remove("hidden");
    f.textContent = "Could not load the solve: " + err.message +
      ". The page needs data.json beside it — check the last workflow run.";
    return;
  }

  $("loading").classList.add("hidden");
  const d = S.data;
  $("sub").textContent =
    `Gameweek ${d.gw} · closes ${d.deadline}` +
    (d.league && d.league.behind != null
      ? ` · ${d.league.behind} pts off top of ${d.league.teams} in your league` : "");

  for (const v of ["team", "players", "compare", "plan"]) {
    $("tab-" + v).addEventListener("click", () => show(v));
  }
  renderTeam(); renderPlayers(); renderCompare(); renderPlan();
  show("team");
}

function show(v) {
  S.view = v;
  for (const name of ["team", "players", "compare", "plan"]) {
    $("view-" + name).classList.toggle("hidden", name !== v);
    $("tab-" + name).setAttribute("aria-selected", String(name === v));
  }
  window.scrollTo({ top: 0, behavior: "instant" });
}

/* --- team: the pitch ---------------------------------------------------- */

const POS_ORDER = ["GKP", "DEF", "MID", "FWD"];

function renderTeam() {
  const root = $("view-team");
  root.replaceChildren();
  const d = S.data;
  const now = d.weeks[0];
  if (!now) { root.append(el("p", "muted", "No solve yet.")); return; }

  // The headline is the decision, not a summary.
  const moves = now.out.map((o, i) => `${byId(o).name} → ${byId(now.in[i]).name}`).join(" · ");
  const head = el("div", "card");
  head.append(el("div", "headline", now.chip ? `Play the ${now.chip}`
    : moves || "No transfer. Set the team and wait."));
  head.append(el("p", "verdict",
    `Captain ${byId(now.captain).name} · ${now.ep} projected points`));
  if (d.hit_verdict) head.append(el("p", "note", d.hit_verdict));
  root.append(head);

  const pitch = el("div", "pitch");
  const xi = now.xi.map(byId);
  for (const pos of POS_ORDER) {
    const group = xi.filter((p) => p.pos === pos).sort((a, b) => b.ep_next - a.ep_next);
    if (!group.length) continue;
    const row = el("div", "row-pos");
    group.forEach((p) => row.append(playerTile(p, p.id === now.captain)));
    pitch.append(row);
  }
  root.append(pitch);

  const bench = el("div", "card benchbar");
  bench.append(el("span", "label", "Bench — in substitution order"));
  const brow = el("div", "row-pos");
  now.bench.map(byId).forEach((p) => brow.append(playerTile(p, false)));
  bench.append(brow);
  root.append(bench);

  root.append(chartCard(
    "Projected points, your eleven",
    barChart(xi.sort((a, b) => b.ep_next - a.ep_next).map((p) => ({
      label: p.name, value: p.ep_next, sub: p.fixtures[0],
    })), { unit: "pts", series: "var(--series-1)" }),
    "Bars are this gameweek only. Fixture underneath."
  ));
}

function playerTile(p, isCaptain) {
  const n = el("button", "pl");
  n.type = "button";
  n.setAttribute("aria-label", `${p.name}, ${p.pos}, ${fmt(p.ep_next)} projected points`);
  n.append(el("div", "pl-name", p.name));
  n.append(el("div", "pl-opp", p.fixtures[0] || ""));
  n.append(el("div", "pl-xp", fmt(p.ep_next)));
  n.append(el("div", "pl-own", `${p.team} · ${fmt(p.price, "money")}`));
  if (isCaptain) { const b = el("span", "badge badge-c", "C"); n.append(b); }
  else if (p.status && p.status !== "a") { n.append(el("span", "badge badge-f", "!")); }
  // Tapping a player opens him in Compare — the obvious next question.
  n.addEventListener("click", () => { S.cmp[0] = p.id; renderCompare(); show("compare"); });
  return n;
}

/* --- players: filter and sort ------------------------------------------- */

const COLS = [
  { key: "name",      label: "Player",  fmt: null,    text: true },
  { key: "pos",       label: "Pos",     fmt: null,    text: true },
  { key: "team",      label: "Team",    fmt: null,    text: true },
  { key: "price",     label: "£",       fmt: "money" },
  { key: "ep_next",   label: "xP",      fmt: "num" },
  { key: "ep_horizon",label: "xP 5gw",  fmt: "num" },
  { key: "start_prob",label: "Starts",  fmt: "pct" },
  { key: "xg90",      label: "xG90",    fmt: "num3" },
  { key: "xa90",      label: "xA90",    fmt: "num3" },
  { key: "own_overall", label: "Own",   fmt: "pct" },
  { key: "own_league",  label: "League",fmt: "pct" },
];

function renderPlayers() {
  const root = $("view-players");
  root.replaceChildren();

  const f = el("div", "filters");
  const search = el("input"); search.type = "search"; search.placeholder = "Search player…";
  const pos = el("select");
  pos.append(new Option("All positions", ""));
  POS_ORDER.forEach((p) => pos.append(new Option(p, p)));
  const team = el("select");
  team.append(new Option("All teams", ""));
  S.data.teams.forEach((t) => team.append(new Option(t, t)));
  const maxPrice = el("select");
  maxPrice.append(new Option("Any price", ""));
  [5, 6, 7, 8, 9, 10, 12, 15].forEach((v) => maxPrice.append(new Option(`≤ £${v}.0`, String(v))));
  const mineOnly = el("button", "chipbtn", "My squad");
  mineOnly.type = "button"; mineOnly.setAttribute("aria-pressed", "false");
  const fitOnly = el("button", "chipbtn", "Available only");
  fitOnly.type = "button"; fitOnly.setAttribute("aria-pressed", "true");

  f.append(search, pos, team, maxPrice, mineOnly, fitOnly);
  root.append(f);

  const wrap = el("div", "tablewrap");
  const table = el("table");
  wrap.append(table);
  root.append(wrap);
  const count = el("p", "note");
  root.append(count);

  const state = { q: "", pos: "", team: "", max: "", mine: false, fit: true };

  function draw() {
    let rows = S.data.players.filter((p) => {
      if (state.fit && p.status !== "a") return false;
      if (state.mine && !S.data.mine.has(p.id)) return false;
      if (state.pos && p.pos !== state.pos) return false;
      if (state.team && p.team !== state.team) return false;
      if (state.max && p.price > +state.max) return false;
      if (state.q && !p.name.toLowerCase().includes(state.q)) return false;
      return true;
    });

    const { key, dir } = S.sort;
    rows.sort((a, b) => {
      const x = a[key], y = b[key];
      if (typeof x === "string") return dir * x.localeCompare(y);
      return dir * ((x ?? -Infinity) - (y ?? -Infinity));
    });
    rows = rows.slice(0, 250);

    table.replaceChildren();
    const thead = el("thead"), tr = el("tr");
    COLS.forEach((c) => {
      const th = el("th", null, c.label + (S.sort.key === c.key ? (dir < 0 ? " ↓" : " ↑") : ""));
      th.setAttribute("scope", "col");
      th.addEventListener("click", () => {
        S.sort = S.sort.key === c.key ? { key: c.key, dir: -dir } : { key: c.key, dir: -1 };
        draw();
      });
      tr.append(th);
    });
    thead.append(tr); table.append(thead);

    const tb = el("tbody");
    rows.forEach((p) => {
      const r = el("tr");
      if (S.data.mine.has(p.id)) r.className = "mine";
      COLS.forEach((c, i) => {
        const cell = el(i === 0 ? "th" : "td");
        if (i === 0) cell.setAttribute("scope", "row");
        cell.textContent = c.fmt ? fmt(p[c.key], c.fmt) : p[c.key];
        r.append(cell);
      });
      r.addEventListener("click", () => {
        S.cmp[S.cmp[0] == null ? 0 : 1] = p.id;
        renderCompare(); show("compare");
      });
      tb.append(r);
    });
    table.append(tb);
    count.textContent = `${rows.length} shown. Tap a row to compare. Tap a column to sort.`;
  }

  search.addEventListener("input", () => { state.q = search.value.toLowerCase().trim(); draw(); });
  pos.addEventListener("change", () => { state.pos = pos.value; draw(); });
  team.addEventListener("change", () => { state.team = team.value; draw(); });
  maxPrice.addEventListener("change", () => { state.max = maxPrice.value; draw(); });
  mineOnly.addEventListener("click", () => {
    state.mine = !state.mine; mineOnly.setAttribute("aria-pressed", String(state.mine)); draw();
  });
  fitOnly.addEventListener("click", () => {
    state.fit = !state.fit; fitOnly.setAttribute("aria-pressed", String(state.fit)); draw();
  });

  draw();
}

/* --- compare ------------------------------------------------------------ */

function renderCompare() {
  const root = $("view-compare");
  root.replaceChildren();
  const d = S.data;

  const pick = el("div", "card");
  const row = el("div", "pickrow");
  const sels = [0, 1].map((slot) => {
    const s = el("select");
    s.setAttribute("aria-label", slot === 0 ? "First player" : "Second player");
    s.append(new Option("Pick a player…", ""));
    [...d.players]
      .filter((p) => p.status === "a" || d.mine.has(p.id))
      .sort((a, b) => b.ep_horizon - a.ep_horizon)
      .slice(0, 400)
      .forEach((p) => s.append(new Option(`${p.name} (${p.team} ${p.pos}) £${p.price.toFixed(1)}`, p.id)));
    s.value = S.cmp[slot] ?? "";
    s.addEventListener("change", () => {
      S.cmp[slot] = s.value ? +s.value : null;
      renderCompare();
    });
    return s;
  });
  row.append(...sels);
  pick.append(row);
  root.append(pick);

  const [aId, bId] = S.cmp;
  if (aId == null || bId == null) {
    root.append(el("p", "muted",
      "Pick two players. Every metric is drawn so the longer bar is the better number — " +
      "if the incoming player's bars are not visibly longer, the transfer is not obviously right."));
    return;
  }

  const a = byId(aId), b = byId(bId);

  root.append(legend([
    { name: a.name, colour: "var(--series-1)" },
    { name: b.name, colour: "var(--series-2)" },
  ]));

  // One grouped bar per metric, normalised within the metric so the two are
  // comparable. Lower-is-better metrics are inverted, so "longer is better"
  // holds everywhere and the chart never has to be read backwards.
  const rows = d.metrics.map((m) => {
    const av = a[m.key], bv = b[m.key];
    const hi = Math.max(av ?? 0, bv ?? 0) || 1;
    const norm = (v) => v == null ? 0 : (m.higher_better ? v / hi : (hi ? (hi - v) / hi + 0.15 : 0));
    return {
      label: m.label,
      a: { raw: av, w: Math.max(0, Math.min(1, norm(av))), text: fmt(av, m.fmt) },
      b: { raw: bv, w: Math.max(0, Math.min(1, norm(bv))), text: fmt(bv, m.fmt) },
      better: av == null || bv == null ? null : (m.higher_better ? (av > bv ? "a" : av < bv ? "b" : null)
                                                                : (av < bv ? "a" : av > bv ? "b" : null)),
    };
  });

  root.append(chartCard(`${a.name} vs ${b.name}`, compareChart(rows),
    "Bars are normalised within each metric. Price is inverted, so a longer bar is always the better number."));

  const wins = rows.filter((r) => r.better === "a").length;
  const losses = rows.filter((r) => r.better === "b").length;
  const v = el("p", "verdict");
  v.innerHTML = `<strong>${a.name}</strong> leads on ${wins} of ${rows.length} metrics, ` +
                `<strong>${b.name}</strong> on ${losses}.`;
  root.append(v);

  root.append(chartCard("Projected points by gameweek", lineChart([
    { name: a.name, values: a.ep, colour: "var(--series-1)" },
    { name: b.name, values: b.ep, colour: "var(--series-2)" },
  ], d.gameweeks), "The horizon the solver optimises over."));

  root.append(tableCard(rows, a, b));
}

function tableCard(rows, a, b) {
  const c = el("div", "card");
  c.append(el("h3", null, "The same numbers, as a table"));
  const wrap = el("div", "tablewrap");
  const t = el("table");
  const th = el("thead");
  const hr = el("tr");
  ["Metric", a.name, b.name].forEach((h) => { const x = el("th", null, h); x.setAttribute("scope", "col"); hr.append(x); });
  th.append(hr); t.append(th);
  const tb = el("tbody");
  rows.forEach((r) => {
    const tr = el("tr");
    const k = el("th", null, r.label); k.setAttribute("scope", "row");
    tr.append(k, el("td", null, r.a.text), el("td", null, r.b.text));
    tb.append(tr);
  });
  t.append(tb); wrap.append(t); c.append(wrap);
  return c;
}

/* --- plan --------------------------------------------------------------- */

function renderPlan() {
  const root = $("view-plan");
  root.replaceChildren();
  const d = S.data;

  const c = el("div", "card");
  c.append(el("h3", null, `Next ${d.weeks.length} gameweeks`));
  d.weeks.forEach((w) => {
    const r = el("div", "gwrow");
    r.append(el("span", "gwno", "GW" + w.gw));
    if (w.chip) r.append(el("span", "tag", w.chip));
    const moves = el("span", "gwmove");
    if (w.out.length) {
      w.out.forEach((o, i) => {
        if (i) moves.append(document.createTextNode(" · "));
        moves.append(el("span", "o", byId(o).name));
        moves.append(document.createTextNode(" → "));
        moves.append(document.createTextNode(byId(w.in[i]) ? byId(w.in[i]).name : "?"));
      });
    } else {
      moves.append(document.createTextNode("no transfer"));
    }
    r.append(moves);
    if (w.hits) r.append(el("span", "pill", w.hits));
    r.append(el("span", "gwep", fmt(w.ep)));
    c.append(r);
  });
  root.append(c);

  root.append(chartCard("Projected points by gameweek",
    barChart(d.weeks.map((w) => ({ label: "GW" + w.gw, value: w.ep, sub: w.chip || "" })),
             { unit: "pts", series: "var(--series-1)" }),
    "A wildcard week is higher because the squad is rebuilt, not because the week is easier."));

  const pl = d.planner;
  if (pl && pl.chips) {
    const cc = el("div", "card");
    cc.append(el("h3", null, "Chip weeks"));
    Object.values(pl.chips).forEach((ch) => {
      if (!ch.ranked || !ch.ranked.length) return;
      const r = el("div", "gwrow");
      r.append(el("span", "gwmove", ch.name));
      r.append(el("span", "muted", ch.current_gw ? "yours: GW" + ch.current_gw : "unplaced"));
      r.append(el("span", "gwep", `best GW${ch.best_gw} (${ch.best_gain > 0 ? "+" : ""}${ch.best_gain})`));
      cc.append(r);
    });
    root.append(cc);
  }
}

/* --- charts ------------------------------------------------------------- */

function chartCard(title, svg, note) {
  const c = el("div", "card");
  c.append(el("h3", null, title));
  c.append(svg);
  if (note) c.append(el("p", "note", note));
  return c;
}

function legend(items) {
  const l = el("div", "legend");
  items.forEach((i) => {
    const s = el("span");
    const sw = el("span", "swatch");
    sw.style.background = i.colour;
    s.append(sw, document.createTextNode(i.name));
    l.append(s);
  });
  return l;
}

const SVGNS = "http://www.w3.org/2000/svg";
const svgEl = (tag, attrs = {}) => {
  const n = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  return n;
};

/* Chart geometry note.
 *
 * The viewBox width is deliberately close to a phone's CSS width. An SVG is
 * scaled to its container, so a 680-wide viewBox rendered into a 390px column
 * shrinks every label by ~43% — 11px type lands at 6px and the chart becomes
 * a decorative smudge. Keeping the viewBox near the render width keeps the
 * type at the size it says it is.
 *
 * Labels sit ABOVE their bars rather than in a left gutter, for the same
 * reason: a gutter wide enough for "Defensive actions per 90" leaves no room
 * for the bar on a phone, and truncating the label loses the thing the reader
 * needs most.
 */
const VB_W = 420;

/** Horizontal bars, one series, direct-labelled. */
function barChart(rows, { unit = "", series = "var(--series-1)" } = {}) {
  // padR has to clear the widest value label, not the widest bar: the longest
  // bar reaches the full width and its label is drawn beyond that, so a gutter
  // sized for the bar alone clips the number off the right edge.
  const rowH = 32, padR = 60, top = 4;
  const w = VB_W, h = top + rows.length * rowH + 4;
  const max = Math.max(...rows.map((r) => r.value), 1);
  const bw = w - padR - 4;

  const svg = svgEl("svg", {
    class: "chart", viewBox: `0 0 ${w} ${h}`, role: "img",
    "aria-label": rows.map((r) => `${r.label} ${fmt(r.value)}`).join(", "),
  });

  rows.forEach((r, i) => {
    const y = top + i * rowH;
    const len = Math.max(2, (r.value / max) * bw);

    const name = svgEl("text", { x: 2, y: y + 10, "font-size": 11 });
    name.textContent = r.label + (r.sub ? ` · ${r.sub}` : "");
    svg.append(name);

    svg.append(svgEl("rect", { x: 2, y: y + 15, width: len, height: 12, rx: 4, fill: series }));

    const val = svgEl("text", { x: 2 + len + 6, y: y + 25, "font-size": 11, class: "val" });
    val.textContent = fmt(r.value) + (unit ? " " + unit : "");
    svg.append(val);

    const title = svgEl("title");
    title.textContent = `${r.label}: ${fmt(r.value)}${unit ? " " + unit : ""}`;
    svg.append(title);
  });
  return svg;
}

/** Grouped two-series bars for the compare view. */
function compareChart(rows) {
  const rowH = 46, padR = 46, top = 4;
  const w = VB_W, h = top + rows.length * rowH + 4;
  const bw = w - padR - 4;
  const svg = svgEl("svg", {
    class: "chart", viewBox: `0 0 ${w} ${h}`, role: "img",
    "aria-label": "Metric comparison; the table below carries the same numbers.",
  });

  rows.forEach((r, i) => {
    const y = top + i * rowH;
    const label = svgEl("text", { x: 2, y: y + 10, "font-size": 11 });
    label.textContent = r.label;
    svg.append(label);

    // 2px surface gap between the two fills so they never touch.
    [["a", "var(--series-1)", 14], ["b", "var(--series-2)", 29]].forEach(([k, colour, dy]) => {
      const len = Math.max(2, r[k].w * bw);
      svg.append(svgEl("rect", { x: 2, y: y + dy, width: len, height: 13, rx: 4, fill: colour }));
      const v = svgEl("text", { x: 2 + len + 6, y: y + dy + 11, "font-size": 10.5, class: "val" });
      v.textContent = r[k].text;
      svg.append(v);
    });

    const t = svgEl("title");
    t.textContent = `${r.label}: ${r.a.text} vs ${r.b.text}`;
    svg.append(t);
  });
  return svg;
}

/** Two-series line over the horizon, with markers and direct end-labels. */
function lineChart(series, gws) {
  const padL = 30, padR = 58, padT = 12, padB = 22;
  const w = VB_W, h = 180;
  const iw = w - padL - padR, ih = h - padT - padB;
  const all = series.flatMap((s) => s.values).filter((v) => v != null);
  const max = Math.max(...all, 1), min = Math.min(...all, 0);
  const x = (i) => padL + (gws.length === 1 ? iw / 2 : (i / (gws.length - 1)) * iw);
  const y = (v) => padT + ih - ((v - min) / (max - min || 1)) * ih;

  const svg = svgEl("svg", {
    class: "chart", viewBox: `0 0 ${w} ${h}`, role: "img",
    "aria-label": series.map((s) => `${s.name}: ${s.values.join(", ")}`).join("; "),
  });

  for (let i = 0; i <= 4; i++) {
    const yy = padT + (i / 4) * ih;
    svg.append(svgEl("line", { x1: padL, y1: yy, x2: padL + iw, y2: yy, class: "gridline" }));
    const lab = svgEl("text", { x: padL - 4, y: yy + 3, "text-anchor": "end", "font-size": 9, opacity: 0.75 });
    lab.textContent = (max - (i / 4) * (max - min)).toFixed(1);
    svg.append(lab);
  }
  gws.forEach((g, i) => {
    const lab = svgEl("text", { x: x(i), y: h - 6, "text-anchor": "middle", "font-size": 9.5 });
    lab.textContent = "GW" + g;
    svg.append(lab);
  });

  // End-label positions, nudged apart when the two lines finish close together.
  // Without this the labels overprint into an unreadable smudge — which is
  // exactly what a legend cannot fix, because it is the direct labels that
  // stop identity resting on colour alone.
  const ends = series.map((s, si) => ({ si, yy: y(s.values[s.values.length - 1]) }));
  ends.sort((a, b) => a.yy - b.yy);
  const MIN_GAP = 12;
  for (let i = 1; i < ends.length; i++) {
    if (ends[i].yy - ends[i - 1].yy < MIN_GAP) ends[i].yy = ends[i - 1].yy + MIN_GAP;
  }
  const labelY = new Map(ends.map((e) => [e.si, e.yy]));

  series.forEach((s, si) => {
    const pts = s.values.map((v, i) => `${x(i)},${y(v)}`).join(" ");
    svg.append(svgEl("polyline", {
      points: pts, fill: "none", stroke: s.colour, "stroke-width": 2,
      "stroke-linejoin": "round", "stroke-linecap": "round",
    }));
    s.values.forEach((v, i) => {
      svg.append(svgEl("circle", {
        cx: x(i), cy: y(v), r: 4, fill: s.colour,
        stroke: "var(--surface-1)", "stroke-width": 2,
      }));
      const t = svgEl("title");
      t.textContent = `${s.name}, GW${gws[i]}: ${fmt(v)}`;
      svg.append(t);
    });
    const last = s.values.length - 1;
    const lab = svgEl("text", {
      x: x(last) + 7, y: labelY.get(si) + 4, "font-size": 10, class: "val",
    });
    lab.textContent = s.name.length > 9 ? s.name.slice(0, 8) + "…" : s.name;
    svg.append(lab);
  });

  return svg;
}

boot();
