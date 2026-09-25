/* Gaffer — the interactive page.
 *
 * Reads docs/data.json, which the solve writes. No framework, no build, no
 * CDN: GitHub Pages serves static files, and a dependency that 404s on a
 * Friday evening is worse than no dependency at all.
 *
 * Charts are inline SVG built here rather than by a library, for the same
 * reason — and because every one of them needs a direct label. The palette's
 * relief rule says a label or a table has to carry the value when contrast
 * alone cannot, and on a near-black surface that is most of the time.
 *
 * One thing this page deliberately does NOT do: optimise. The solver is a
 * MILP that runs in a GitHub Action and commits its answer here. The Optimise
 * view writes down what you want and tells you how to ask for it; it cannot
 * re-solve in the browser, and pretending otherwise would be the one lie on
 * the page.
 */
"use strict";

const VIEWS = ["overview", "lineup", "projections", "optimise", "plans", "more"];

const S = {
  data: null,
  view: "overview",
  gw: null,              // which gameweek Overview / Lineup are showing
  proj: "players",       // Projections sub-view
  plans: "table",        // Plans sub-view
  sort: { key: "avg", dir: -1 },
  cmp: [null, null],
  sheet: false,
  more: null,            // which More page is open
  preset: "default",
};

const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
};
const frag = (...kids) => { const f = document.createDocumentFragment(); kids.forEach((k) => k && f.append(k)); return f; };

/* --- formatting --------------------------------------------------------- */

const FMT = {
  num:   (v) => v == null ? "—" : (+v).toFixed(1),
  num2:  (v) => v == null ? "—" : (+v).toFixed(2),
  num3:  (v) => v == null ? "—" : (+v).toFixed(3),
  num4:  (v) => v == null ? "—" : (+v).toFixed(4),
  int:   (v) => v == null ? "—" : String(Math.round(v)),
  pct:   (v) => v == null ? "—" : Math.round(v * 100) + "%",
  pct1:  (v) => v == null ? "—" : (v * 100).toFixed(1) + "%",
  money: (v) => v == null ? "—" : (+v).toFixed(1),
  signed: (v) => v == null ? "—" : (v > 0 ? "+" : "") + (+v).toFixed(1),
};
const fmt = (v, kind) => (FMT[kind] || FMT.num)(v);

const byId = (id) => S.data.index.get(id);

/* Club colours. Presentational only — a kit at 42px cannot carry a crest, and
 * a row of identical grey shirts tells you nothing about who plays whom. */
const CLUB = {
  ARS: "#e3283b", AVL: "#7a003c", BHA: "#0057b8", BOU: "#d3132b", BRE: "#e30613",
  BUR: "#6c1d45", CHE: "#1c4fc4", COV: "#63c3e8", CRY: "#1b458f", EVE: "#1b3ea5",
  FUL: "#e8e8e8", HUL: "#f5a623", IPS: "#1e5fbf", LEE: "#f0f0f0", LEI: "#023474",
  LIV: "#c8102e", LUT: "#f4790b", MCI: "#7cc0ea", MUN: "#d92332", NEW: "#1a1a1a",
  NFO: "#dd0000", SHU: "#ee2737", SOU: "#d71920", SUN: "#d8232a", TOT: "#0e1a3c",
  WHU: "#7a263a", WOL: "#fdb913",
};
const clubColour = (code) => CLUB[code] || "#3a4757";

/* --- boot --------------------------------------------------------------- */

async function boot() {
  try {
    // Cache-bust: the file is rewritten by a commit, and Pages caches hard.
    const res = await fetch("data.json?v=" + Date.now());
    if (!res.ok) throw new Error("data.json returned " + res.status);
    const d = await res.json();
    d.index = new Map(d.players.map((p) => [p.id, p]));
    d.mine = new Set(d.squad_ids || []);
    S.data = d;
    S.gw = d.gw;
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
  $("sub").textContent = `GW${d.gw} · closes ${d.deadline}`;
  renderChips();

  for (const v of VIEWS) $("tab-" + v).addEventListener("click", () => show(v));
  show("overview");
}

function show(v) {
  if (v === "more") {
    S.sheet = !S.sheet;
    renderSheet();
    return;
  }
  S.sheet = false;
  renderSheet();
  S.view = v;
  for (const name of VIEWS) {
    const sec = $("view-" + name);
    if (sec) sec.classList.toggle("hidden", name !== v);
    $("tab-" + name).setAttribute("aria-selected", String(name === v));
  }
  RENDER[v] && RENDER[v]();
  window.scrollTo({ top: 0, behavior: "instant" });
}

/* --- the status chips --------------------------------------------------- */

function renderChips() {
  const d = S.data, root = $("chips");
  root.replaceChildren();
  const diag = d.diagnosis || {};
  const tpl = diag.template;
  const subs = diag.autosubs;
  const weak = (diag.weak_spots || []).length;

  const mk = (tone, label, value, go) => {
    const b = el("button", "chip " + tone);
    b.type = "button";
    b.append(el("span", "dot"));
    b.append(document.createTextNode(label + " "));
    b.append(el("b", null, value));
    b.addEventListener("click", () => { S.plans = "diagnosis"; show("plans"); });
    return b;
  };
  if (tpl) {
    root.append(mk(tpl.share > 0.6 ? "warn" : "good", "Template",
      fmt(tpl.share, "pct")));
  }
  root.append(mk(weak > 2 ? "bad" : weak ? "warn" : "good", "Weak spots",
    String(weak)));
  if (subs) {
    root.append(mk(subs.any_autosub > 0.4 ? "warn" : "good", "Any autosub",
      fmt(subs.any_autosub, "pct")));
  }
}

/* --- the More sheet ----------------------------------------------------- */

const MORE_PAGES = [
  ["wildcard", "The wildcard", "M4 7h16M4 12h10M4 17h7"],
  ["compare", "Compare players", "M12 3v18M7 8 3 12l4 4M17 8l4 4-4 4"],
  ["teamform", "Team form", "M3 17l5-6 4 4 7-9"],
  ["cleansheets", "Clean sheets", "M12 3 5 6v6c0 4 3 7 7 9 4-2 7-5 7-9V6Z"],
  ["boards", "Leaderboards", "M6 21V9M12 21V3M18 21v-7"],
  ["setup", "How this is set up", "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6M4 12h2m12 0h2M12 4v2m0 12v2"],
];

function renderSheet() {
  let sheet = document.querySelector(".sheet");
  if (!S.sheet) { if (sheet) sheet.remove(); setMoreIcon(false); return; }
  if (sheet) return;
  sheet = el("div", "sheet");
  for (const [key, label, path] of MORE_PAGES) {
    const b = el("button");
    b.type = "button";
    const svg = svgEl("svg", { viewBox: "0 0 24 24" });
    svg.append(svgEl("path", { d: path }));
    b.append(svg, document.createTextNode(label));
    b.addEventListener("click", () => { S.more = key; S.sheet = false; renderSheet(); goMore(); });
    sheet.append(b);
  }
  document.body.append(sheet);
  setMoreIcon(true);
}

function setMoreIcon(open) {
  const svg = $("more-icon");
  if (!svg) return;
  svg.replaceChildren(svgEl("path", { d: open ? "M5 5l14 14M19 5 5 19" : "M3 6h18M3 12h18M3 18h18" }));
}

function goMore() {
  S.view = "more";
  for (const name of VIEWS) {
    const sec = $("view-" + name);
    if (sec) sec.classList.toggle("hidden", name !== "more");
    $("tab-" + name).setAttribute("aria-selected", String(name === "more"));
  }
  renderMore();
  window.scrollTo({ top: 0, behavior: "instant" });
}

/* --- shared bits -------------------------------------------------------- */

function section(title, right) {
  const h = el("div", "sec-head");
  h.append(el("h2", null, title), el("span", "spacer"));
  if (right) h.append(right);
  return h;
}

function segmented(options, current, onPick, plain) {
  const s = el("div", "seg" + (plain ? " plain" : ""));
  for (const [key, label] of options) {
    const b = el("button", null, label);
    b.type = "button";
    b.setAttribute("aria-pressed", String(key === current));
    b.addEventListener("click", () => onPick(key));
    s.append(b);
  }
  return s;
}

function tile(label, value, key) {
  const t = el("div", "tile" + (key ? " key" : ""));
  t.append(el("span", "label", label));
  t.append(el("div", "v", value));
  return t;
}

function weekFor(gw) {
  return (S.data.weeks || []).find((w) => w.gw === gw) || (S.data.weeks || [])[0];
}

function fixtureFor(p, gw) {
  const i = S.data.gameweeks.indexOf(gw);
  return i >= 0 && p.fixtures ? (p.fixtures[i] || "") : "";
}

function epFor(p, gw) {
  const wc = S.data.wildcard;
  if (wc && p.ep_wc) {
    const i = wc.gws.indexOf(gw);
    if (i >= 0) return p.ep_wc[i];
  }
  const j = S.data.gameweeks.indexOf(gw);
  return j >= 0 && p.ep ? p.ep[j] : p.ep_next;
}

/* --- OVERVIEW ----------------------------------------------------------- */

function renderOverview() {
  const root = $("view-overview");
  root.replaceChildren();
  const d = S.data;
  const weeks = d.weeks || [];
  if (!weeks.length) { root.append(el("p", "muted", "No solve yet.")); return; }

  const dist = d.distribution;
  const head = el("div", "card bracket");
  const now = weekFor(S.gw);
  head.append(el("div", "label", `Gameweek ${now.gw}`));
  const line = el("div");
  line.append(el("span", "big big-xl accent", fmt(now.ep)));
  line.append(el("span", "label", " projected"));
  head.append(line);
  if (dist && now.gw === weeks[0].gw) {
    head.append(el("p", "note",
      `Median ${dist.median}. Beats 40 in ${fmt(dist.thresholds["40"], "pct1")} ` +
      `of weeks, 60 in ${fmt(dist.thresholds["60"], "pct1")}, ` +
      `80 in ${fmt(dist.thresholds["80"], "pct1")}.`));
  }
  const moves = (now.out || []).map((o, i) =>
    `${byId(o).name} → ${byId(now.in[i]).name}`).join(" · ");
  head.append(el("p", "verdict muted",
    now.chip ? `Play the ${now.chip}` : (moves || "No transfer. Set the team and wait.")));
  root.append(head);

  root.append(section("The horizon"));
  const strip = el("div", "strip");
  for (const w of weeks) {
    const n = el("button", "node" + (w.gw === S.gw ? " bracket" : ""));
    n.type = "button";
    n.setAttribute("aria-pressed", String(w.gw === S.gw));
    n.append(el("div", "gwno", "GW" + w.gw));
    const pts = el("div", "pts" + (w.gw === S.gw ? " accent" : ""));
    pts.append(document.createTextNode(fmt(w.ep)));
    pts.append(el("small", null, "pts"));
    n.append(pts);
    // The range: one standard deviation each way, where we have a curve for
    // it. It is the first week only — later weeks have no distribution yet,
    // and inventing one would be worse than leaving the bar off.
    if (dist && w.gw === weeks[0].gw) {
      const lo = -Math.round(dist.sd), hi = Math.round(dist.sd);
      const bar = el("div", "range");
      const tick = el("i");
      tick.style.left = "50%";
      bar.append(tick);
      n.append(bar);
      const nums = el("div", "rangenums");
      nums.append(el("span", null, String(lo)), el("span", null, "+" + hi));
      n.append(nums);
    }
    /* The moves, named. A node that says "2 transfers" makes you open it to
       find out which two — and that is the whole decision. */
    const ins = (w.in || []).map(byId), outs = (w.out || []).map(byId);
    if (ins.length && ins.length <= 3) {
      const list = el("div", "moves");
      outs.forEach((o, i) => {
        const line = el("div");
        line.append(el("span", "dim", o.name));
        line.append(el("span", null, " \u21b3 " + (ins[i] ? ins[i].name : "")));
        list.append(line);
      });
      n.append(list);
    } else if (ins.length) {
      n.append(el("div", "moves dim", `${ins.length} moves`));
    }
    const foot = el("div", "foot");
    foot.append(el("span", null, w.chip ? w.chip : "—"));
    foot.append(el("span", null, w.hits ? `−${w.hits * 4}` : "\u21c4 " + (w.in || []).length));
    n.append(foot);
    n.addEventListener("click", () => { S.gw = w.gw; renderOverview(); });
    strip.append(n);
  }
  root.append(strip);

  const c = el("div", "card");
  c.append(section("Projected points by gameweek"));
  c.append(dotChart(weeks.map((w) => ({
    label: "GW" + w.gw, value: w.ep, sub: w.chip || "",
  })), { unit: "pts", series: "var(--accent)" }));
  c.append(el("p", "note",
    "Each week's eleven, captain included, chips priced in. The scale is " +
    "zoomed to the weeks shown and labelled at both ends — five weeks within " +
    "six points of each other are all one bar on a scale from zero."));
  root.append(c);

  if (d.hit_verdict) {
    const h = el("div", "card flat");
    h.append(el("div", "label", "Is a hit worth it?"));
    h.append(el("p", "verdict muted", d.hit_verdict));
    root.append(h);
  }
}

/* --- LINEUP ------------------------------------------------------------- */

function renderLineup() {
  const root = $("view-lineup");
  root.replaceChildren();
  const d = S.data;
  const w = weekFor(S.gw);
  if (!w) { root.append(el("p", "muted", "No solve yet.")); return; }

  const bar = el("div", "card flat");
  const row = el("div", "filters");
  row.append(segmented((d.weeks || []).map((x) => [String(x.gw), "GW" + x.gw]),
    String(w.gw), (k) => { S.gw = +k; renderLineup(); }, true));
  bar.append(row);
  root.append(bar);

  const head = el("div", "sec-head");
  head.append(el("h2", null, `${w.chip || "No chip"} · ${fmt(w.ep)} projected`));
  root.append(head);
  root.append(el("p", "sec-note", `Captain ${byId(w.captain).name}.`));

  root.append(pitch(w));

  const dist = d.distribution;
  if (dist && w.gw === (d.weeks[0] || {}).gw) {
    const c = el("div", "card");
    c.append(section("What this eleven might score"));
    c.append(distributionCurve(dist));
    const t = el("div", "tiles");
    t.append(tile("Mean", fmt(dist.mean), true));
    t.append(tile("Median", String(dist.median)));
    t.append(tile("Std dev", fmt(dist.sd)));
    c.append(t);
    const t2 = el("div", "tiles");
    for (const k of ["40", "60", "80"]) {
      t2.append(tile(k + "+ pts", fmt(dist.thresholds[k], "pct1")));
    }
    c.append(t2);
    c.append(el("p", "note",
      "Built by convolving each player's own points distribution — appearance, " +
      "goals, assists, clean sheet, defensive contribution — not simulated. " +
      "It assumes players are independent, which is wrong in the direction " +
      "that matters: when a side wins 4-0 its attackers return together. The " +
      "real curve is wider than this one."));
    root.append(c);
  }

  const dna = d.dna;
  if (dna && w.gw === (d.weeks[0] || {}).gw) {
    const c = el("div", "card");
    c.append(section("Points DNA", el("span", "verdictval accent", fmt(dna.total) + " pts")));
    c.append(el("p", "sec-note", "Where the projected points come from."));
    c.append(stackedBar(dna.rows));
    c.append(dnaTable(dna));
    c.append(el("p", "note",
      "“Other” is everything the component model does not reach — bonus above " +
      "all, plus saves, the goals-conceded penalty and cards. Naming it beats " +
      "folding it quietly into the parts that are modelled."));
    root.append(c);
  }
}

function pitch(w) {
  const wrap = el("div", "pitch");
  const xi = w.xi.map(byId);
  for (const pos of ["GKP", "DEF", "MID", "FWD"]) {
    const group = xi.filter((p) => p.pos === pos)
      .sort((a, b) => epFor(b, w.gw) - epFor(a, w.gw));
    if (!group.length) continue;
    const r = el("div", "row-pos");
    group.forEach((p) => r.append(playerTile(p, w, p.id === w.captain)));
    wrap.append(r);
  }
  const bench = el("div", "benchband");
  bench.append(el("span", "label", "Bench — in substitution order"));
  const br = el("div", "row-pos");
  (w.bench || []).map(byId).forEach((p) => br.append(playerTile(p, w, false)));
  bench.append(br);
  wrap.append(bench);
  return wrap;
}

function playerTile(p, w, isCaptain) {
  const n = el("button", "pl");
  n.type = "button";
  const xp = epFor(p, w.gw);
  n.setAttribute("aria-label",
    `${p.name}, ${p.pos}, ${fmt(xp)} projected points, ${fixtureFor(p, w.gw)}`);
  const kit = el("div", "kit");
  kit.style.background = clubColour(p.team);
  n.append(kit);
  n.append(el("div", "pl-xp", fmt(xp)));
  n.append(el("div", "pl-name", p.name));
  n.append(el("div", "pl-opp", fixtureFor(p, w.gw) || p.team));
  if (isCaptain) n.append(el("span", "badge badge-c", "C"));
  else if (p.status && p.status !== "a") n.append(el("span", "badge badge-f", "!"));
  n.addEventListener("click", () => { S.cmp[0] = p.id; S.more = "compare"; goMore(); });
  return n;
}

function dnaTable(dna) {
  const LABEL = {
    goals: "Goals", assists: "Assists", clean_sheets: "Clean sheets",
    defcon: "Def. contribution", appearance: "Appearance",
    other: "Bonus, saves & other",
  };
  const COLOUR = {
    goals: "var(--blue)", assists: "var(--accent)", clean_sheets: "var(--green)",
    defcon: "var(--teal)", appearance: "var(--ink-3)", other: "var(--purple)",
  };
  const wrap = el("div", "tablewrap");
  const t = el("table");
  const hr = el("tr");
  ["Source", "Points", "Share", "Events"].forEach((h, i) =>
    hr.append(el("th", i ? "num" : null, h)));
  t.append(hr);
  for (const r of dna.rows) {
    const tr = el("tr");
    const name = el("td");
    const sw = el("span", "swatch");
    sw.style.background = COLOUR[r.key];
    sw.style.marginRight = "7px";
    name.append(sw, document.createTextNode(LABEL[r.key] || r.key));
    tr.append(name);
    tr.append(el("td", "num", fmt(r.points)));
    tr.append(el("td", "num dim", fmt(r.share, "pct")));
    tr.append(el("td", "num dim", r.key === "other" ? "—" : "~" + fmt(r.events)));
    t.append(tr);
  }
  const tot = el("tr");
  tot.append(el("td", null, "Total"));
  tot.append(el("td", "num accent", fmt(dna.total)));
  tot.append(el("td", "num dim", "100%"));
  tot.append(el("td", "num dim", ""));
  t.append(tot);
  wrap.append(t);
  return wrap;
}

/* --- PROJECTIONS -------------------------------------------------------- */

function renderProjections() {
  const root = $("view-projections");
  root.replaceChildren();
  root.append(segmented([
    ["players", "Players"], ["teams", "Teams"], ["fixtures", "Fixtures"],
  ], S.proj, (k) => { S.proj = k; renderProjections(); }));
  if (S.proj === "players") projPlayers(root);
  else if (S.proj === "teams") projTeams(root);
  else projFixtures(root);
}

function projPlayers(root) {
  const d = S.data;
  const state = { q: "", pos: "", team: "", max: "", mine: false };

  const filters = el("div", "filters");
  const search = el("input");
  search.type = "search"; search.placeholder = "Search";
  const pos = el("select");
  [["", "All positions"], ["GKP", "GKP"], ["DEF", "DEF"], ["MID", "MID"], ["FWD", "FWD"]]
    .forEach(([v, l]) => { const o = el("option", null, l); o.value = v; pos.append(o); });
  const team = el("select");
  const anyT = el("option", null, "All clubs"); anyT.value = ""; team.append(anyT);
  (d.teams || []).forEach((t) => { const o = el("option", null, t); o.value = t; team.append(o); });
  const price = el("select");
  [["", "Any price"], ["5", "≤ 5.0"], ["7", "≤ 7.0"], ["9", "≤ 9.0"], ["12", "≤ 12.0"]]
    .forEach(([v, l]) => { const o = el("option", null, l); o.value = v; price.append(o); });
  const mineBtn = el("button", "btn", "My squad");
  mineBtn.type = "button";
  mineBtn.setAttribute("aria-pressed", "false");
  filters.append(search, pos, team, price, mineBtn);
  root.append(filters);

  const wrap = el("div", "tablewrap tall");
  root.append(wrap);
  const foot = el("p", "note");
  root.append(foot);

  const gws = d.gameweeks || [];
  const draw = () => {
    let rows = d.players.filter((p) => {
      if (state.mine && !d.mine.has(p.id)) return false;
      if (state.pos && p.pos !== state.pos) return false;
      if (state.team && p.team !== state.team) return false;
      if (state.max && (p.price || 0) > +state.max) return false;
      if (state.q && !p.name.toLowerCase().includes(state.q)) return false;
      return true;
    });
    const avg = (p) => (p.ep || []).length
      ? p.ep.reduce((a, b) => a + b, 0) / p.ep.length : (p.ep_next || 0);
    const key = S.sort.key, dir = S.sort.dir;
    rows.sort((a, b) => {
      const va = key === "avg" ? avg(a) : (key.startsWith("gw")
        ? (a.ep || [])[+key.slice(2)] : a[key]);
      const vb = key === "avg" ? avg(b) : (key.startsWith("gw")
        ? (b.ep || [])[+key.slice(2)] : b[key]);
      if (va == null) return 1;
      if (vb == null) return -1;
      return typeof va === "string" ? dir * va.localeCompare(vb) : dir * (va - vb);
    });
    const shown = rows.slice(0, 120);

    // The colour scale is fixed to the visible rows, so the eye compares like
    // with like as you filter.
    const all = shown.flatMap((p) => p.ep || []).filter((v) => v != null);
    const lo = Math.min(...all, 0), hi = Math.max(...all, 1);

    const t = el("table");
    const hr = el("tr");
    const th = (label, k) => {
      const h = el("th", null, label + (S.sort.key === k ? (dir < 0 ? " ↓" : " ↑") : ""));
      h.addEventListener("click", () => {
        if (S.sort.key === k) S.sort.dir *= -1; else { S.sort.key = k; S.sort.dir = -1; }
        draw();
      });
      return h;
    };
    hr.append(th("Name", "name"), th("Club", "team"), th("Price", "price"), th("Avg", "avg"));
    gws.forEach((g, i) => hr.append(th("GW" + g, "gw" + i)));
    t.append(hr);

    for (const p of shown) {
      const tr = el("tr");
      const nm = el("td");
      nm.append(document.createTextNode(p.name));
      if (d.mine.has(p.id)) {
        const b = el("span", "pill", "mine");
        b.style.marginLeft = "6px";
        nm.append(b);
      }
      tr.append(nm);
      const tc = el("td", "num");
      const sw = el("span", "swatch");
      sw.style.background = clubColour(p.team);
      sw.style.marginRight = "5px";
      tc.append(sw, document.createTextNode(p.team));
      tr.append(tc);
      tr.append(el("td", "num", fmt(p.price, "money")));
      const av = el("td", "num heat");
      av.textContent = fmt(avg(p), "num2");
      av.style.background = "rgba(61,139,212," + (0.10 + 0.5 * norm(avg(p), lo, hi)) + ")";
      tr.append(av);
      (p.ep || []).forEach((v) => {
        const c = el("td", "num heat", fmt(v, "num2"));
        c.style.background = heatColour(norm(v, lo, hi));
        tr.append(c);
      });
      tr.addEventListener("click", () => { S.cmp[0] = p.id; S.more = "compare"; goMore(); });
      t.append(tr);
    }
    wrap.replaceChildren(t);
    foot.textContent = `${shown.length} of ${rows.length} shown. ` +
      "Tap any row to compare. Every cell prints its value — the fill is a " +
      "second channel, never the only one.";
  };

  search.addEventListener("input", () => { state.q = search.value.toLowerCase().trim(); draw(); });
  pos.addEventListener("change", () => { state.pos = pos.value; draw(); });
  team.addEventListener("change", () => { state.team = team.value; draw(); });
  price.addEventListener("change", () => { state.max = price.value; draw(); });
  mineBtn.addEventListener("click", () => {
    state.mine = !state.mine;
    mineBtn.setAttribute("aria-pressed", String(state.mine));
    mineBtn.classList.toggle("ghost-accent", state.mine);
    draw();
  });
  draw();
}

const norm = (v, lo, hi) => hi === lo ? 0.5 : Math.max(0, Math.min(1, (v - lo) / (hi - lo)));
function heatColour(t) {
  // Cool to warm through the surface colour, so the middle of the scale is
  // the background and both ends read as a departure from it.
  return t < 0.5
    ? `rgba(61,139,212,${(0.5 - t) * 0.7})`
    : `rgba(242,101,58,${(t - 0.5) * 0.85})`;
}

function projTeams(root) {
  const d = S.data;
  const st = d.strengths || {};
  const codes = Object.keys(st);
  if (!codes.length) {
    root.append(el("p", "note", "No team strengths in this solve."));
    return;
  }
  const c = el("div", "card");
  c.append(section("Attack and defence"));
  c.append(el("p", "sec-note",
    "Every club, measured rather than rated. Up is a better attack; right is " +
    "a better defence. Recent form is folded in, so a side on a run moves."));
  c.append(teamScatter(st));
  root.append(c);

  const form = d.team_form || [];
  if (form.length) {
    const f = el("div", "card");
    f.append(section("Form", el("span", "verdictval dim", "last few matches")));
    f.append(el("p", "sec-note",
      "Goals scored and conceded against what the fixtures warranted, " +
      "time-decayed and opponent-adjusted. 1.00 is exactly to expectation."));
    const wrap = el("div", "tablewrap");
    const t = el("table");
    const hr = el("tr");
    ["Club", "Attack", "Defence", "Form"].forEach((h, i) =>
      hr.append(el("th", i ? "num" : null, h)));
    t.append(hr);
    for (const r of form) {
      const tr = el("tr");
      const tc = el("td");
      const sw = el("span", "swatch");
      sw.style.background = clubColour(r.team);
      sw.style.marginRight = "6px";
      tc.append(sw, document.createTextNode(r.team));
      tr.append(tc);
      tr.append(el("td", "num", fmt(r.attack, "num2")));
      tr.append(el("td", "num", fmt(r.defence, "num2")));
      const fc = el("td", "num " + (r.form > 1.03 ? "good" : r.form < 0.97 ? "bad" : "dim"));
      fc.textContent = fmt(r.form, "num2");
      tr.append(fc);
      t.append(tr);
    }
    wrap.append(t);
    f.append(wrap);
    f.append(el("p", "note", "Defence above 1.00 means leakier than it should have been."));
    root.append(f);
  }
}

function projFixtures(root) {
  const d = S.data;
  const ticker = d.ticker || {};
  const gws = (d.gameweeks || []).filter((g) => (ticker[String(g)] || []).length);
  if (gws.length) {
    const c = el("div", "card");
    c.append(section("The ticker"));
    c.append(el("p", "sec-note", "Every match in the horizon, by gameweek."));
    const wrap = el("div", "tablewrap");
    const grid = el("div", "ticker");
    for (const g of gws) {
      const col = el("div", "tickcol");
      col.append(el("div", "label", "GW" + g));
      for (const m of ticker[String(g)]) {
        const cell = el("div", "match");
        cell.append(half(m.h), half(m.a));
        cell.title = `${m.h} v ${m.a}`;
        col.append(cell);
      }
      grid.append(col);
    }
    wrap.append(grid);
    c.append(wrap);
    c.append(el("p", "note", "Home on the left, away on the right."));
    root.append(c);
  }

  const fx = (d.diagnosis || {}).fixtures;
  if (!fx) { root.append(el("p", "note", "No fixture matrix in this solve.")); return; }
  const c = el("div", "card");
  c.append(section("Fixture distribution",
    el("span", "verdictval " + (fx.favourable > 0.5 ? "good" : "warn"),
      fmt(fx.favourable, "pct") + " favourable")));
  c.append(el("p", "sec-note", "How your eleven spreads across strength matchups."));
  c.append(fixtureMatrix(fx));
  c.append(el("p", "note",
    "Your side down, the side it faces across. Favourable means a mismatch in " +
    "your favour — strong against weak. Strong against strong is not " +
    "favourable, it is even. Captain counts twice." +
    (fx.unplaced ? ` ${fx.unplaced} player(s) had no opponent to place.` : "")));
  root.append(c);

  const cs = d.clean_sheets || [];
  if (cs.length) {
    const s = el("div", "card");
    s.append(section("Clean sheet odds"));
    s.append(barChart(cs.map((r) => ({
      label: r.team, value: r.cs_prob * 100, sub: "xGC " + fmt(r.xgc, "num2"),
    })), { unit: "%", series: "var(--green)" }));
    root.append(s);
  }
}

/** One half of a fixture pill: a club code on its own colour, with the ink
 *  chosen by luminance rather than guessed — Fulham's white and Newcastle's
 *  black both have to stay readable. */
function half(code) {
  const bg = clubColour(code);
  const h = el("span", "mhalf", code);
  h.style.background = bg;
  h.style.color = pickInk(bg);
  return h;
}

function fixtureMatrix(fx) {
  const wrap = el("div", "tablewrap");
  const t = el("table", "matrix");
  const hr = el("tr");
  hr.append(el("th", null, "You ↓ vs →"));
  fx.tiers.forEach((x) => hr.append(el("th", null, x)));
  hr.append(el("th", null, "Total"));
  t.append(hr);
  fx.tiers.forEach((mine, i) => {
    const tr = el("tr");
    tr.append(el("th", null, mine));
    fx.tiers.forEach((theirs, j) => {
      const v = fx.grid[mine][theirs];
      const td = el("td");
      const cell = el("div",
        "cell " + (j > i ? "fav" : j < i ? "unfav" : ""),
        v.points ? fmt(v.points) : "–");
      td.append(cell);
      tr.append(td);
    });
    const td = el("td");
    td.append(el("div", "cell tot", fmt(fx.row_totals[mine])));
    tr.append(td);
    t.append(tr);
  });
  const tot = el("tr");
  tot.append(el("th", null, "Total"));
  fx.tiers.forEach((x) => {
    const td = el("td");
    td.append(el("div", "cell tot", fmt(fx.col_totals[x])));
    tot.append(td);
  });
  const g = el("td");
  g.append(el("div", "cell grand", fmt(fx.total)));
  tot.append(g);
  t.append(tot);
  wrap.append(t);
  return wrap;
}

/* --- OPTIMISE ----------------------------------------------------------- */

const PRESETS = {
  default:  { label: "Default", rivalry: 0.35, ceiling: 6, hit: 6, note: "The settings the solve is running now." },
  highrisk: { label: "High risk", rivalry: 0.7, ceiling: 10, hit: 4, note: "Chase differentials, take hits sooner, weight the tail." },
  lowrisk:  { label: "Low risk", rivalry: 0.1, ceiling: 3, hit: 9, note: "Own the template, hold transfers, ignore the tail." },
  optimistic: { label: "Optimistic", rivalry: 0.5, ceiling: 8, hit: 5, note: "Assume the projections are right and act on them." },
  safe:     { label: "Safe", rivalry: 0.0, ceiling: 0, hit: 12, note: "Expected points only. No leverage, no chasing." },
};

function renderOptimise() {
  const root = $("view-optimise");
  root.replaceChildren();

  const warn = el("div", "card flat");
  warn.append(el("div", "label", "Read this first"));
  warn.append(el("p", "verdict muted",
    "This page cannot re-solve. The optimiser is a mixed-integer program that " +
    "runs in a GitHub Action and commits its answer here as a static file — " +
    "there is no solver in the browser to move when you move a slider."));
  warn.append(el("p", "note",
    "What it does instead: shows you the settings the last solve ran with, " +
    "lets you build a different set, and gives you the exact config to paste " +
    "and the workflow to run. The honest version of a control panel that has " +
    "no engine behind it."));
  root.append(warn);

  root.append(section("Presets"));
  const grid = el("div", "presets");
  for (const [key, p] of Object.entries(PRESETS)) {
    const b = el("button", "preset" + (key === S.preset ? " bracket" : ""));
    b.type = "button";
    b.setAttribute("aria-pressed", String(key === S.preset));
    const svg = svgEl("svg", { viewBox: "0 0 24 24", width: 20, height: 20,
      stroke: "currentColor", fill: "none", "stroke-width": 1.6 });
    svg.append(svgEl("path", { d: PRESET_ICON[key] || "M4 12h16" }));
    b.append(svg, document.createTextNode(p.label));
    b.addEventListener("click", () => { S.preset = key; renderOptimise(); });
    grid.append(b);
  }
  root.append(grid);

  const p = PRESETS[S.preset];
  const c = el("div", "card");
  c.append(section("Objective"));
  c.append(el("p", "sec-note", p.note));
  c.append(slider("Differential appetite", p.rivalry, 0, 1,
    ["Template", "Balanced", "Chase rank"],
    "How far the solver will trade expected points for leverage against the " +
    "managers above you. config: rivalry"));
  c.append(slider("Weight on the tail", p.ceiling / 12, 0, 1,
    ["Mean only", "Balanced", "Hauls"],
    "How much a player's chance of a double-digit week tilts the armband on " +
    "a Triple Captain. config: ceiling_weight"));
  c.append(slider("Bar for taking a hit", p.hit / 15, 0, 1,
    ["Hit freely", "Balanced", "Never"],
    "Points a hit must gain across the horizon before it is recommended. " +
    "config: hit_threshold"));
  root.append(c);

  const out = el("div", "card");
  out.append(section("To run this"));
  const pre = el("pre");
  pre.style.cssText = "font:12px/1.55 var(--mono);color:var(--ink-2);overflow-x:auto;margin:8px 0 0";
  pre.textContent =
    `# config.yaml\nrivalry: ${p.rivalry}\nceiling_weight: ${p.ceiling}\n` +
    `hit_threshold: ${p.hit}\n\n` +
    `# then run the workflow\ngh workflow run gaffer.yml -f force=true`;
  out.append(pre);
  out.append(el("p", "note",
    "Or press Run workflow on the gaffer action with force on. It solves, " +
    "rewrites data.json and this page updates on the next load."));
  root.append(out);
}

const PRESET_ICON = {
  default: "M4 16c3 0 3-8 6-8s3 8 6 8 4-3 4-3",
  highrisk: "M3 17 10 10l4 4 7-8M17 6h4v4",
  lowrisk: "M3 7l7 7 4-4 7 8M17 18h4v-4",
  optimistic: "M12 3 4 19h16Z",
  safe: "M12 3 5 6v6c0 4 3 7 7 9 4-2 7-5 7-9V6Z",
};

function slider(name, value, min, max, ends, note) {
  const box = el("div", "slider");
  const head = el("div", "head");
  head.append(el("span", "name", name), el("span", "spacer"));
  const v = el("span", "v", fmt(value * 100, "int") + "%");
  head.append(v);
  box.append(head);
  const input = el("input");
  input.type = "range"; input.min = String(min); input.max = String(max);
  input.step = "0.01"; input.value = String(value);
  input.disabled = true;
  box.append(input);
  const e = el("div", "ends");
  ends.forEach((label, i) => {
    const s = el("span", i === Math.round(value * (ends.length - 1)) ? "on" : null, label);
    e.append(s);
  });
  box.append(e);
  box.append(el("p", "note", note));
  return box;
}

/* --- PLANS -------------------------------------------------------------- */

function renderPlans() {
  const root = $("view-plans");
  root.replaceChildren();
  root.append(segmented([
    ["table", "Plan"], ["distribution", "Curve"],
    ["diagnosis", "Health"], ["exposure", "Clubs"],
  ], S.plans, (k) => { S.plans = k; renderPlans(); }));

  const d = S.data;
  if (S.plans === "table") plansTable(root);
  else if (S.plans === "distribution") plansDistribution(root);
  else if (S.plans === "exposure") plansExposure(root);
  else plansDiagnosis(root);
}

function plansTable(root) {
  const d = S.data;
  const weeks = d.weeks || [];
  const total = weeks.reduce((a, w) => a + w.ep - 4 * (w.hits || 0), 0);
  const c = el("div", "card bracket");
  c.append(el("div", "label",
    `GW${weeks[0].gw}–${weeks[weeks.length - 1].gw}`));
  const line = el("div");
  line.append(el("span", "big big-xl accent", fmt(total)));
  line.append(el("span", "label", " pts"));
  c.append(line);
  if (d.distribution) {
    c.append(el("p", "note", `±${fmt(d.distribution.sd)} on the first week alone.`));
  }
  root.append(c);

  const wrap = el("div", "tablewrap");
  const t = el("table");
  const hr = el("tr");
  ["GW", "Chip", "Hits", "Points"].forEach((h, i) =>
    hr.append(el("th", i > 1 ? "num" : null, h)));
  t.append(hr);
  for (const w of weeks) {
    const tr = el("tr");
    const gwc = el("td");
    gwc.append(el("div", null, "GW" + w.gw));
    const moves = (w.out || []).map((o, i) =>
      `${byId(o).name}→${byId(w.in[i]).name}`).join(", ");
    // Under the gameweek, not beside it: a wildcard names thirteen moves and
    // would push the two columns this row exists for off the screen.
    const sub = el("div", "sub", moves || "roll");
    sub.style.cssText = "white-space:normal;max-width:190px";
    gwc.append(sub);
    tr.append(gwc);
    tr.append(el("td", "dim", w.chip || "—"));
    tr.append(el("td", "num " + (w.hits ? "bad" : "dim"), w.hits ? "−" + w.hits * 4 : "0"));
    tr.append(el("td", "num", fmt(w.ep)));
    tr.addEventListener("click", () => { S.gw = w.gw; show("lineup"); });
    t.append(tr);
  }
  wrap.append(t);
  const c2 = el("div", "card");
  c2.append(section("Week by week"));
  c2.append(wrap);
  c2.append(el("p", "note", "Tap a row to see that week's eleven."));
  root.append(c2);

  const pl = d.planner;
  if (pl && pl.plan) {
    const p = el("div", "card");
    p.append(section("Your own plan",
      el("span", "verdictval " + (pl.plan.legal ? "good" : "bad"),
        pl.plan.legal ? "legal" : "breaks the rules")));
    p.append(el("p", "sec-note",
      `The solver's line scores ${fmt(pl.solver_total)}. Yours scores ` +
      `${fmt(pl.plan.total_ep)} — ${fmt(Math.abs(pl.gap))} ` +
      (pl.gap < 0 ? "behind." : "ahead.")));
    for (const v of (pl.plan.violations || [])) {
      p.append(el("p", "note bad", `GW${v.gw}: ${v.message}`));
    }
    root.append(p);
  }
}

function plansDistribution(root) {
  const d = S.data;
  if (!d.distribution) { root.append(el("p", "note", "No distribution in this solve.")); return; }
  const c = el("div", "card");
  c.append(section("This gameweek's distribution"));
  c.append(distributionCurve(d.distribution));
  const t = el("div", "tiles");
  t.append(tile("Mean", fmt(d.distribution.mean), true));
  t.append(tile("Median", String(d.distribution.median)));
  t.append(tile("Risk (sd)", fmt(d.distribution.sd)));
  c.append(t);
  c.append(el("p", "note",
    "One gameweek, exactly convolved. A horizon curve needs the later weeks' " +
    "distributions too, and those are not built yet — a five-week curve drawn " +
    "from one week's spread would be a straight lie about the uncertainty."));
  root.append(c);
}

function plansExposure(root) {
  const d = S.data;
  const rows = (d.diagnosis || {}).exposure || [];
  if (!rows.length) { root.append(el("p", "note", "No exposure data.")); return; }
  const c = el("div", "card");
  c.append(section("Swing by club"));
  c.append(el("p", "sec-note", "Which clubs your week actually turns on."));
  const max = Math.max(...rows.map((r) => Math.abs(r.diff)), 0.5);
  for (const r of rows) {
    const row = el("div", "exprow");
    row.append(el("span", "t", r.team));
    const track = el("div", "exptrack");
    const bar = el("i");
    const w = Math.max(3, Math.abs(r.diff) / max * 100);
    bar.style.width = w + "%";
    bar.style.background = r.diff >= 0 ? clubColour(r.team) : "var(--surface-2)";
    if (r.diff < 0) {
      bar.style.border = "1px dashed " + clubColour(r.team);
      bar.style.boxSizing = "border-box";
    }
    track.append(bar);
    row.append(track);
    row.append(el("span", "n", `you ${fmt(r.you, "num2")} · field ${fmt(r.field, "num2")}`));
    c.append(row);
  }
  const lg = el("div", "legend");
  const a = el("span"), b = el("span");
  const s1 = el("span", "swatch"); s1.style.background = "var(--ink-2)";
  const s2 = el("span", "swatch"); s2.style.border = "1px dashed var(--ink-2)";
  a.append(s1, document.createTextNode("You own more than the field"));
  b.append(s2, document.createTextNode("You own less than the field"));
  lg.append(a, b);
  c.append(lg);
  c.append(el("p", "note",
    "“You” counts the players you carry, captain twice over. “Field” is the " +
    "same figure for the average manager. A club you do not own still swings " +
    "you — the other way — so the gap is the exposure, not the holding."));
  root.append(c);
}

function plansDiagnosis(root) {
  const d = S.data;
  const diag = d.diagnosis || {};

  const weak = diag.weak_spots || [];
  const c = el("div", "card");
  c.append(section("Weak spots",
    el("span", "verdictval " + (weak.length > 2 ? "bad" : weak.length ? "warn" : "good"),
      weak.length ? `${weak.length} found` : "none")));
  c.append(el("p", "sec-note",
    "Starters out-projected by a similar-priced or cheaper alternative."));
  if (!weak.length) {
    c.append(el("p", "note", "Nobody in the eleven is being beaten for the money."));
  }
  for (const r of weak) {
    const row = el("div", "listrow");
    const dot = el("span", "swatch");
    dot.style.background = "var(--red)";
    dot.style.borderRadius = "50%";
    row.append(dot);
    const g = el("div", "grow");
    g.append(el("div", "nm", r.out_name));
    g.append(el("div", "sub", fmt(r.out_ep) + " pts"));
    row.append(g);
    row.append(el("span", "swap",
      `↗ ${r.in_name} +${fmt(r.gain)} · £${fmt(r.in_price, "money")}m`));
    row.addEventListener("click", () => {
      S.cmp = [r.out, r.in]; S.more = "compare"; goMore();
    });
    c.append(row);
  }
  c.append(el("p", "note",
    "Single swaps only — same position, no dearer than the man plus the bank. " +
    "The optimiser finds deeper multi-player moves beyond these."));
  root.append(c);

  const subs = diag.autosubs;
  if (subs) {
    const a = el("div", "card");
    a.append(section("Player availability",
      el("span", "verdictval " + (subs.any_autosub > 0.3 ? "warn" : "good"),
        fmt(subs.any_autosub, "pct") + " chance of an autosub")));
    a.append(el("p", "sec-note",
      "How likely the bench is needed, and what it costs when it is."));
    const t = el("div", "tiles");
    t.append(tile("Any autosub", fmt(subs.any_autosub, "pct"), true));
    t.append(tile("Pts lost", fmt(subs.expected_points_lost)));
    t.append(tile("Avg miss", fmt(subs.avg_miss, "pct")));
    a.append(t);
    for (const r of subs.riskiest) {
      const row = el("div", "listrow");
      const g = el("div", "grow");
      g.append(el("div", "nm", r.name));
      g.append(el("div", "sub", fmt(r.ep) + " pts projected"));
      row.append(g);
      row.append(el("span", "sub", fmt(r.miss, "pct") + " miss"));
      a.append(row);
    }
    a.append(el("p", "note",
      "The two numbers are different on purpose. The chance somebody does not " +
      "play is what makes a week fragile; the points are what it does to you. " +
      "A deep bench shrinks the second and leaves the first alone."));
    root.append(a);
  }

  const tpl = diag.template;
  if (tpl) {
    const t = el("div", "card");
    t.append(section("Template",
      el("span", "verdictval " + (tpl.share > 0.6 ? "warn" : "good"),
        fmt(tpl.share, "pct") + " template")));
    t.append(el("p", "sec-note",
      `Share of your eleven owned by more than ${fmt(tpl.threshold, "pct")} of ` +
      `the game. Mean ownership ${fmt(tpl.mean_ownership, "pct")}.`));
    t.append(el("p", "note",
      "A template team cannot gain rank and cannot lose it. Whether that is " +
      "what you want depends on where you are in the table."));
    root.append(t);
  }
}

/* --- MORE --------------------------------------------------------------- */

function renderMore() {
  const root = $("view-more");
  root.replaceChildren();
  const back = el("button", "btn", "← All sections");
  back.type = "button";
  back.addEventListener("click", () => { S.sheet = true; renderSheet(); });
  root.append(back);

  const page = S.more || "wildcard";
  if (page === "wildcard") moreWildcard(root);
  else if (page === "compare") moreCompare(root);
  else if (page === "teamform") { S.proj = "teams"; projTeams(root); }
  else if (page === "cleansheets") { S.proj = "fixtures"; projFixtures(root); }
  else if (page === "boards") moreBoards(root);
  else moreSetup(root);
}

function moreWildcard(root) {
  const d = S.data, wc = d.wildcard;
  if (!wc) {
    const c = el("div", "card");
    c.append(section("No wildcard drafted"));
    c.append(el("p", "sec-note",
      "Put the gameweek in config.yaml under chip_plan: wc and the next run " +
      "drafts the squad."));
    root.append(c);
    return;
  }
  const head = el("div", "card bracket");
  head.append(el("div", "label", `The GW${wc.for_gw} wildcard`));
  head.append(el("div", "big big-l",
    `${fmt(wc.cost, "money")}m spent · ${fmt(wc.in_bank, "money")}m left`));
  head.append(el("p", "note",
    `${wc.change.keep.length} of your fifteen survive, ${wc.change.buy.length} ` +
    `arrive. Drafted over GW${wc.gws[0]}–GW${wc.gws[wc.gws.length - 1]} from ` +
    `${wc.pool_size} candidates.`));
  root.append(head);

  const wk = wc.weeks[0];
  root.append(pitch({ gw: wk.gw, xi: wk.xi, bench: wk.bench, captain: wk.captain }));

  root.append(chips2("Sold", wc.change.sell, "var(--red)"));
  root.append(chips2("Bought", wc.change.buy, "var(--green)"));
  root.append(chips2("Kept", wc.change.keep, "var(--ink-3)"));

  const c = el("div", "card");
  c.append(section("The run you are buying"));
  c.append(dotChart(wc.weeks.map((w) => ({
    label: "GW" + w.gw, value: w.ep, sub: w.chip || "",
  })), { unit: "pts", series: "var(--accent)" }));
  root.append(c);

  if (wc.swaps && wc.swaps.length) {
    const s = el("div", "card");
    s.append(section("The closest calls"));
    for (const r of wc.swaps.slice(0, 8)) {
      const row = el("div", "listrow");
      const g = el("div", "grow");
      g.append(el("div", "nm", byId(r.out).name));
      g.append(el("div", "sub", "nearest: " + (r.in ? byId(r.in).name : "—")));
      row.append(g);
      row.append(el("span", "sub", r.gap == null ? "—" : "costs " + fmt(r.gap, "num2")));
      row.addEventListener("click", () => {
        S.cmp = [r.out, r.in || null]; S.more = "compare"; renderMore();
      });
      s.append(row);
    }
    s.append(el("p", "note",
      "Points over the whole draft horizon, holding the other fourteen fixed. " +
      "Near zero is a coin toss — take the player you want to watch."));
    root.append(s);
  }
}

function chips2(title, ids, colour) {
  const c = el("div", "card flat");
  c.append(el("span", "label", `${title} — ${ids.length}`));
  const row = el("div", "chips-row");
  if (!ids.length) row.append(el("span", "pill", "nobody"));
  ids.map(byId).forEach((p) => {
    const s = el("span", "pill", `${p.name} ${fmt(p.price, "money")}`);
    s.style.color = colour;
    row.append(s);
  });
  c.append(row);
  return c;
}

function moreCompare(root) {
  const d = S.data;
  const pick = (slot) => {
    const sel = el("select");
    const none = el("option", null, "— pick a player —");
    none.value = "";
    sel.append(none);
    [...d.players].sort((a, b) => (b.ep_next || 0) - (a.ep_next || 0))
      .slice(0, 400)
      .forEach((p) => {
        const o = el("option", null, `${p.name} · ${p.team} · ${fmt(p.price, "money")}`);
        o.value = String(p.id);
        if (S.cmp[slot] === p.id) o.selected = true;
        sel.append(o);
      });
    sel.addEventListener("change", () => {
      S.cmp[slot] = sel.value ? +sel.value : null;
      renderMore();
    });
    return sel;
  };
  const f = el("div", "filters");
  f.append(pick(0), pick(1));
  root.append(f);

  const [a, b] = S.cmp.map((id) => id ? byId(id) : null);
  if (!a && !b) {
    root.append(el("p", "note", "Pick one or two players."));
    return;
  }
  const c = el("div", "card");
  c.append(section(b ? `${a.name} vs ${b.name}` : a.name));
  const wrap = el("div", "tablewrap");
  const t = el("table");
  const hr = el("tr");
  hr.append(el("th", null, "Metric"), el("th", "num", a ? a.name : "—"));
  if (b) hr.append(el("th", "num", b.name));
  t.append(hr);
  for (const m of d.metrics) {
    const tr = el("tr");
    tr.append(el("td", null, m.label));
    const va = a ? a[m.key] : null, vb = b ? b[m.key] : null;
    const better = (x, y) => x == null || y == null ? "" :
      ((m.higher_better ? x > y : x < y) ? " good" : "");
    tr.append(el("td", "num" + better(va, vb), fmt(va, m.fmt)));
    if (b) tr.append(el("td", "num" + better(vb, va), fmt(vb, m.fmt)));
    t.append(tr);
  }
  wrap.append(t);
  c.append(wrap);
  root.append(c);

  if (a && a.ep) {
    const ch = el("div", "card");
    ch.append(section("Projection over the horizon"));
    const series = [{ name: a.name, colour: "var(--accent)", values: a.ep }];
    if (b && b.ep) series.push({ name: b.name, colour: "var(--blue)", values: b.ep });
    ch.append(lineChart(series, d.gameweeks));
    root.append(ch);
  }
}

const BOARDS = [
  ["projected", "Projected", "projected", "num"],
  ["captains", "Captains", "captain_return", "num"],
  ["differentials", "Differentials", "leverage", "num"],
  ["goals", "Goals", "xg", "num3"],
  ["assists", "Assists", "xa", "num3"],
  ["defcon", "Def. contribution", "expected", "num3"],
  ["movers", "Price movers", "net_transfers", "int"],
];

function moreBoards(root) {
  const b = S.data.boards;
  if (!b) { root.append(el("p", "note", "No leaderboards in this solve.")); return; }
  for (const [key, title, valueKey, kind] of BOARDS) {
    const rows = b[key] || [];
    if (!rows.length) continue;
    const c = el("div", "card");
    c.append(section(title));
    for (const r of rows.slice(0, 10)) {
      const row = el("div", "listrow");
      const g = el("div", "grow");
      g.append(el("div", "nm", r.name));
      g.append(el("div", "sub",
        `${r.team} · £${fmt(r.price, "money")}` +
        (r.fixture ? ` · ${r.fixture}` : "") +
        (r.own != null ? ` · ${fmt(r.own, "pct")} owned` : "")));
      row.append(g);
      row.append(el("span", "big big-m accent", fmt(r[valueKey], kind)));
      row.addEventListener("click", () => { S.cmp[0] = r.id; S.more = "compare"; renderMore(); });
      c.append(row);
    }
    root.append(c);
  }
}

function moreSetup(root) {
  const d = S.data;
  const c = el("div", "card");
  c.append(section("How this is set up"));
  c.append(el("p", "sec-note",
    "Projections blend Solio Analytics' public feed with a local model: " +
    "shrunk points-per-90 scaled by expected minutes and fixture, with team " +
    "attack and defence measured from expected goals rather than the FPL " +
    "difficulty rating, and recent form folded in on top."));
  const t = el("div", "tiles");
  t.append(tile("Gameweek", String(d.gw), true));
  t.append(tile("Players", String(d.players.length)));
  t.append(tile("Horizon", (d.gameweeks || []).length + " GWs"));
  c.append(t);
  c.append(el("p", "note",
    "The solve runs in a GitHub Action and commits data.json here. Nothing " +
    "on this page computes a recommendation; it renders one."));
  root.append(c);

  const lg = d.league || {};
  if (lg.behind != null) {
    const l = el("div", "card");
    l.append(section("Your league"));
    l.append(el("p", "verdict muted",
      `${lg.behind} points off ${lg.leader} in a ${lg.teams}-team league.`));
    root.append(l);
  }
}

/* --- charts ------------------------------------------------------------- */

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
 */
const VB_W = 420;

function dotChart(rows, { unit = "", series = "var(--accent)" } = {}) {
  const padL = 4, padR = 56, rowH = 26, padT = 18;
  const h = rows.length * rowH + padT + 14;
  const vals = rows.map((r) => r.value || 0);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const pad = Math.max(0.6, (hi - lo) * 0.25);
  const aLo = lo - pad, aHi = hi + pad;
  const track = VB_W - padL - padR;
  const X = (v) => padL + ((v - aLo) / (aHi - aLo || 1)) * track;

  const svg = svgEl("svg", {
    class: "chart", viewBox: `0 0 ${VB_W} ${h}`, role: "img",
    "aria-label": rows.map((r) => `${r.label}: ${fmt(r.value)}`).join("; "),
  });
  // The axis is drawn and labelled at both ends, because a scale that does
  // not start at zero has to say so on its face.
  svg.append(svgEl("line", {
    x1: padL, y1: padT - 7, x2: padL + track, y2: padT - 7, class: "axis",
  }));
  const a1 = svgEl("text", { x: padL, y: padT - 11, "font-size": 9 });
  a1.textContent = fmt(aLo);
  const a2 = svgEl("text", { x: padL + track, y: padT - 11, "font-size": 9, "text-anchor": "end" });
  a2.textContent = fmt(aHi);
  svg.append(a1, a2);

  rows.forEach((r, i) => {
    const y = padT + i * rowH + 11;
    const lab = svgEl("text", { x: padL, y: y - 7, "font-size": 10 });
    lab.textContent = r.label + (r.sub ? " · " + r.sub : "");
    svg.append(lab);
    svg.append(svgEl("line", {
      x1: padL, y1: y + 4, x2: padL + track, y2: y + 4,
      stroke: "var(--surface-2)", "stroke-width": 1,
    }));
    svg.append(svgEl("line", {
      x1: X(aLo), y1: y + 4, x2: X(r.value), y2: y + 4,
      stroke: series, "stroke-width": 2, opacity: 0.4,
    }));
    svg.append(svgEl("circle", {
      cx: X(r.value), cy: y + 4, r: 4.5, fill: series,
      stroke: "var(--surface-0)", "stroke-width": 2,
    }));
    const v = svgEl("text", {
      x: VB_W - padR + 6, y: y + 8, "font-size": 10.5, class: "val",
    });
    v.textContent = fmt(r.value) + (unit ? " " + unit : "");
    svg.append(v);
  });
  return svg;
}

function barChart(rows, { unit = "", series = "var(--accent)" } = {}) {
  const padL = 4, padR = 54, rowH = 27, padT = 6;
  const h = rows.length * rowH + padT + 4;
  const max = Math.max(...rows.map((r) => r.value || 0), 1);
  const svg = svgEl("svg", {
    class: "chart", viewBox: `0 0 ${VB_W} ${h}`, role: "img",
    "aria-label": rows.map((r) => `${r.label}: ${fmt(r.value)}`).join("; "),
  });
  rows.forEach((r, i) => {
    const y = padT + i * rowH;
    const lab = svgEl("text", { x: padL, y: y + 9, "font-size": 10 });
    lab.textContent = r.label + (r.sub ? " · " + r.sub : "");
    svg.append(lab);
    svg.append(svgEl("rect", {
      x: padL, y: y + 13, width: VB_W - padL - padR, height: 9, rx: 3,
      fill: "var(--surface-2)",
    }));
    const w = Math.max(2, (r.value || 0) / max * (VB_W - padL - padR));
    svg.append(svgEl("rect", {
      x: padL, y: y + 13, width: w, height: 9, rx: 3, fill: series,
    }));
    const v = svgEl("text", {
      x: VB_W - padR + 6, y: y + 21, "font-size": 10.5, class: "val",
    });
    v.textContent = fmt(r.value) + (unit ? " " + unit : "");
    svg.append(v);
  });
  return svg;
}

/* The points curve. Filled area under a line, the mean marked, and the
 * thresholds printed beside it — the numbers are the point of the chart, the
 * shape is context for them. */
function distributionCurve(dist) {
  const padL = 30, padR = 10, padT = 10, padB = 24;
  const h = 170, iw = VB_W - padL - padR, ih = h - padT - padB;
  const pmf = dist.pmf || [];
  // Trim the long empty tails so the curve fills the box.
  let lo = 0, hi = pmf.length - 1;
  while (lo < hi && pmf[lo] < 1e-5) lo++;
  while (hi > lo && pmf[hi] < 1e-5) hi--;
  lo = Math.max(0, lo - 2); hi = Math.min(pmf.length - 1, hi + 2);
  const slice = pmf.slice(lo, hi + 1);
  const peak = Math.max(...slice, 1e-9);
  const x = (i) => padL + (i / Math.max(1, slice.length - 1)) * iw;
  const y = (v) => padT + ih - (v / peak) * ih;

  const svg = svgEl("svg", {
    class: "chart", viewBox: `0 0 ${VB_W} ${h}`, role: "img",
    "aria-label": `Points distribution, mean ${dist.mean}, standard deviation ${dist.sd}`,
  });
  const pts = slice.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  svg.append(svgEl("polygon", {
    points: `${padL},${padT + ih} ${pts} ${padL + iw},${padT + ih}`,
    fill: "rgba(45,201,180,0.16)",
  }));
  svg.append(svgEl("polyline", {
    points: pts, fill: "none", stroke: "var(--teal)", "stroke-width": 2,
    "stroke-linejoin": "round",
  }));
  const mx = x(Math.round(dist.mean) - lo);
  svg.append(svgEl("line", {
    x1: mx, y1: padT, x2: mx, y2: padT + ih,
    stroke: "var(--teal)", "stroke-width": 1.5, "stroke-dasharray": "4 3",
  }));
  const ml = svgEl("text", { x: mx + 5, y: padT + 10, "font-size": 10, class: "val" });
  ml.textContent = "mean " + fmt(dist.mean);
  svg.append(ml);

  const ticks = 5;
  for (let i = 0; i <= ticks; i++) {
    const v = lo + (i / ticks) * (hi - lo);
    const tx = x((v - lo));
    const t = svgEl("text", {
      x: tx, y: h - 7, "text-anchor": "middle", "font-size": 9.5,
    });
    t.textContent = String(Math.round(v));
    svg.append(t);
  }
  const yl = svgEl("text", {
    x: 8, y: padT + ih / 2, "font-size": 9, transform: `rotate(-90 8 ${padT + ih / 2})`,
    "text-anchor": "middle",
  });
  yl.textContent = "probability";
  svg.append(yl);
  return svg;
}

function stackedBar(rows) {
  const h = 34, w = VB_W;
  const total = rows.reduce((a, r) => a + Math.max(0, r.points), 0) || 1;
  const COLOUR = {
    goals: "var(--blue)", assists: "var(--accent)", clean_sheets: "var(--green)",
    defcon: "var(--teal)", appearance: "var(--ink-3)", other: "var(--purple)",
  };
  const svg = svgEl("svg", {
    class: "chart", viewBox: `0 0 ${w} ${h}`, role: "img",
    "aria-label": rows.map((r) => `${r.key} ${Math.round(r.share * 100)}%`).join(", "),
  });
  let cx = 0;
  for (const r of rows) {
    const bw = Math.max(0, r.points) / total * w;
    if (bw <= 0.5) continue;
    svg.append(svgEl("rect", {
      x: cx, y: 4, width: bw, height: 22, fill: COLOUR[r.key] || "var(--ink-3)",
    }));
    cx += bw;
  }
  return svg;
}

function teamScatter(strengths) {
  const padL = 34, padR = 16, padT = 16, padB = 30;
  const h = 300, iw = VB_W - padL - padR, ih = h - padT - padB;
  const rows = Object.entries(strengths).map(([team, v]) => ({
    team, atk: v.attack, def: v.defence,
  }));
  const ax = rows.map((r) => r.atk), dx = rows.map((r) => r.def);
  const aLo = Math.min(...ax), aHi = Math.max(...ax);
  const dLo = Math.min(...dx), dHi = Math.max(...dx);
  // Defence reversed: conceding less is better, so better goes right.
  const X = (d) => padL + (1 - norm(d, dLo, dHi)) * iw;
  const Y = (a) => padT + ih - norm(a, aLo, aHi) * ih;

  const svg = svgEl("svg", {
    class: "chart", viewBox: `0 0 ${VB_W} ${h}`, role: "img",
    "aria-label": "Clubs by attack and defence strength",
  });
  svg.append(svgEl("rect", {
    x: padL, y: padT, width: iw, height: ih, fill: "none", stroke: "var(--line)",
  }));
  const midA = (aLo + aHi) / 2, midD = (dLo + dHi) / 2;
  svg.append(svgEl("line", {
    x1: X(midD), y1: padT, x2: X(midD), y2: padT + ih,
    stroke: "var(--line)", "stroke-dasharray": "3 4",
  }));
  svg.append(svgEl("line", {
    x1: padL, y1: Y(midA), x2: padL + iw, y2: Y(midA),
    stroke: "var(--line)", "stroke-dasharray": "3 4",
  }));

  // Nudge labels apart vertically when clubs land on the same spot — the
  // whole value of this chart is reading the names off it.
  const placed = [];
  rows.sort((a, b) => Y(a.atk) - Y(b.atk));
  for (const r of rows) {
    let px = X(r.def), py = Y(r.atk);
    for (const q of placed) {
      if (Math.abs(q.x - px) < 26 && Math.abs(q.y - py) < 13) py = q.y + 13;
    }
    placed.push({ x: px, y: py });
    const g = svgEl("g");
    const label = r.team;
    const w = label.length * 7.2 + 9;
    g.append(svgEl("rect", {
      x: px - w / 2, y: py - 9, width: w, height: 16, rx: 3,
      fill: clubColour(label),
    }));
    const t = svgEl("text", {
      x: px, y: py + 3, "text-anchor": "middle", "font-size": 10,
      "font-weight": 700, fill: pickInk(clubColour(label)),
    });
    t.textContent = label;
    g.append(t);
    svg.append(g);
  }

  const xl = svgEl("text", {
    x: padL + iw / 2, y: h - 8, "text-anchor": "middle", "font-size": 10,
  });
  xl.textContent = "better defence →";
  svg.append(xl);
  const yl = svgEl("text", {
    x: 11, y: padT + ih / 2, "font-size": 10, "text-anchor": "middle",
    transform: `rotate(-90 11 ${padT + ih / 2})`,
  });
  yl.textContent = "better attack →";
  svg.append(yl);
  return svg;
}

/* White or near-black on a club colour, whichever the eye can actually read.
 * Relative luminance, not a guess at "is it dark". */
function pickInk(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex);
  if (!m) return "#fff";
  const n = parseInt(m[1], 16);
  const ch = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  });
  const L = 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
  return L > 0.42 ? "#0b0f16" : "#ffffff";
}

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

  // End-label positions, nudged apart when the two lines finish close
  // together — direct labels are what stop identity resting on colour alone.
  const ends = series.map((s, si) => ({ si, yy: y(s.values[s.values.length - 1]) }));
  ends.sort((a, b) => a.yy - b.yy);
  for (let i = 1; i < ends.length; i++) {
    if (ends[i].yy - ends[i - 1].yy < 12) ends[i].yy = ends[i - 1].yy + 12;
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
        cx: x(i), cy: y(v), r: 3.5, fill: s.colour,
        stroke: "var(--surface-0)", "stroke-width": 2,
      }));
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

const RENDER = {
  overview: renderOverview,
  lineup: renderLineup,
  projections: renderProjections,
  optimise: renderOptimise,
  plans: renderPlans,
  more: renderMore,
};

boot();
