// Renders charts and tables from data/results.json. No external libraries.

// ---------------------------------------------------------------- definitions
const FAMILIES = {
  function: { name: "Uses the Boolean function", ids: ["qiskit", "tket", "quilc", "qrisp_pprm", "qrisp_gray", "mqt", "reference"] },
  matrix: { name: "Generic matrix synthesis", ids: ["qiskit_matrix", "cirq", "pennylane", "qibo", "bqskit"] },
};
const COMPILERS = [
  { id: "qiskit", name: "Qiskit (expression)", color: "--s1", dash: "" },
  { id: "tket", name: "tket", color: "--s2", dash: "" },
  { id: "quilc", name: "quilc", color: "--s3", dash: "" },
  { id: "qrisp_pprm", name: "Qrisp (PPRM)", color: "--s4", dash: "" },
  { id: "qrisp_gray", name: "Qrisp (Gray)", color: "--s5", dash: "" },
  { id: "mqt", name: "MQT", color: "--s6", dash: "" },
  { id: "reference", name: "Textbook construction", color: "--ref", dash: "2 3" },
  { id: "qiskit_matrix", name: "Qiskit (matrix)", color: "--s1", dash: "" },
  { id: "cirq", name: "Cirq", color: "--s2", dash: "" },
  { id: "pennylane", name: "PennyLane", color: "--s3", dash: "" },
  { id: "qibo", name: "Qibo", color: "--s4", dash: "" },
  { id: "bqskit", name: "BQSKit", color: "--s5", dash: "" },
];
const CMAP = Object.fromEntries(COMPILERS.map((c) => [c.id, c]));
const TOPOS = [
  { id: "fully", name: "Fully connected" },
  { id: "line", name: "Line" },
  { id: "ring", name: "Ring" },
  { id: "grid", name: "Square grid" },
  { id: "heavy_hex", name: "IBM heavy-hex (57 q)" },
  { id: "sycamore", name: "Google Sycamore (54 q)" },
];
const TNAME = Object.fromEntries(TOPOS.map((t) => [t.id, t.name]));
const FUNCS = [
  ["and", "Multiple AND", "x₀ ∧ x₁ ∧ … ∧ xₙ₋₁"],
  ["or", "Multiple OR", "x₀ ∨ x₁ ∨ … ∨ xₙ₋₁"],
  ["xor", "Multiple XOR", "x₀ ⊕ x₁ ⊕ … ⊕ xₙ₋₁"],
  ["always0", "Always 0", "A ∧ ¬A"],
  ["always1", "Always 1", "A ∨ ¬A"],
  ["identity", "Identity", "A"],
  ["two_of_three", "Two of three", "(A ∧ B) ∨ (B ∧ C) ∨ (A ∧ C)"],
  ["majority", "Majority", "1 if more than half of the n inputs are 1 (n odd)"],
  ["less_than", "Comparator", "a < b for two k-bit numbers a, b"],
  ["adder", "Adder", "a + b for two k-bit numbers, k + 1 output bits"],
  ["random", "Random truth table", "uniformly random output bit for each input (fixed seed)"],
];
const FNAME = Object.fromEntries(FUNCS.map((f) => [f[0], f[1]]));
const SIZES = { and: [3, 16], or: [3, 16], xor: [3, 16], always0: [2, 2], always1: [2, 2], identity: [2, 2],
  two_of_three: [4, 4], majority: [4, 12], less_than: [3, 11], adder: [4, 13], random: [3, 9] };
const OUTPUTS = { adder: "k + 1" };
const nfmt = (v) => (v >= 100 ? Math.round(v).toLocaleString("en-US") : String(+v.toPrecision(3)));
const METRICS = {
  two: { name: "Two-qubit gates", fmt: nfmt },
  d: { name: "Depth", fmt: nfmt },
  d2: { name: "Two-qubit depth", fmt: nfmt },
  T: { name: "T gates", fmt: nfmt },
  rot: { name: "Arbitrary rotations", fmt: nfmt },
  ct: { name: "Compile time (s)", fmt: (v) => (v < 1 ? v.toFixed(3) : v < 100 ? v.toFixed(1) : v.toFixed(0)) },
  mem: { name: "Peak memory (MB)", fmt: (v) => v.toFixed(0) },
  esp: { name: "Est. success probability", fmt: (v) => (v >= 0.01 ? (100 * v).toFixed(1) + " %" : v.toExponential(1)) },
};

// ---------------------------------------------------------------- helpers
const css = (v) => (v.startsWith("--") ? getComputedStyle(document.documentElement).getPropertyValue(v).trim() : v);
const svgNS = "http://www.w3.org/2000/svg";
function el(tag, attrs = {}, parent) {
  const e = document.createElementNS(svgNS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
}
function h(tag, attrs = {}, text) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (text !== undefined) e.textContent = text;
  return e;
}
function store(key, val) { try { localStorage.setItem(key, JSON.stringify(val)); } catch (e) { /* ignore */ } }
function load(key, def) { try { const v = JSON.parse(localStorage.getItem(key)); return v ?? def; } catch (e) { return def; } }

let DATA = null;
let LAYOUTS = null;
let IDX = new Map();
const key = (c, f, t, q) => `${c}|${f}|${t}|${q}`;
const verified = (r) => r && r.s === "ok" && (r.v === "full" || r.v === "sampled");
const usable = (r) => r && r.s === "ok" && (r.v === "full" || r.v === "sampled" || r.v === "skipped");

const state = {
  func: load("qbc-func", "and"), family: load("qbc-family", "function"), metric: "two",
  off: new Set(load("qbc-off-v3", [])), covTopo: "fully",
  lvlFunc: "and", lvlTopo: "fully", ancFunc: "and", ancTopo: "fully", ancMetric: "two",
  oldFunc: "and", oldTopo: "fully",
};

function segmented(id, options, get, set) {
  const box = document.getElementById(id);
  box.innerHTML = "";
  for (const [k, label] of options) {
    const b = h("button", { type: "button", "aria-pressed": String(get() === k) }, label);
    b.addEventListener("click", () => { set(k); segmented(id, options, get, set); });
    box.appendChild(b);
  }
}
function selectBox(id, options, value, onchange) {
  const s = document.getElementById(id);
  s.innerHTML = "";
  for (const [k, label] of options) {
    const o = h("option", { value: k }, label);
    if (String(k) === String(value)) o.selected = true;
    s.appendChild(o);
  }
  s.onchange = () => onchange(s.value);
}
function swatch(c) {
  const s = el("svg", { width: 22, height: 10, "aria-hidden": "true" });
  el("line", { x1: 1, x2: 21, y1: 5, y2: 5, stroke: css(c.color), "stroke-width": 2, "stroke-dasharray": c.dash || "" }, s);
  return s;
}

// ---------------------------------------------------------------- line chart (log y, zero row)
function lineChart(container, title, series, opts) {
  container.innerHTML = "";
  const box = h("div", { class: "chart" });
  box.appendChild(h("h4", {}, title));
  const W = 400, H = 250, m = { l: 50, r: 10, t: 10, b: 34 };
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": title }, box);
  const tip = h("div", { class: "tip" });
  box.appendChild(tip);
  container.appendChild(box);
  const pts = series.flatMap((s) => s.points);
  if (!pts.length) {
    el("text", { x: W / 2, y: H / 2, "text-anchor": "middle" }, svg).textContent = "No verified results";
    return;
  }
  let [x0, x1] = opts.xDomain;
  if (x1 === x0) { x0 -= 1; x1 += 1; }
  const pos = pts.map((p) => p.y).filter((y) => y > 0);
  const hasZero = pts.some((p) => p.y <= 0);
  let lo = pos.length ? Math.floor(Math.log10(Math.min(...pos))) : 0;
  let hi = pos.length ? Math.ceil(Math.log10(Math.max(...pos))) : 1;
  if (hi === lo) hi = lo + 1;
  const bottom = H - m.b - (hasZero ? 18 : 0);
  const X = (x) => m.l + ((x - x0) / (x1 - x0)) * (W - m.l - m.r);
  const Y = (y) => (y <= 0 ? H - m.b - 4 : m.t + (1 - (Math.log10(y) - lo) / (hi - lo)) * (bottom - m.t));
  const step = hi - lo > 6 ? 2 : 1;
  for (let e = lo; e <= hi; e += step) {
    el("line", { x1: m.l, x2: W - m.r, y1: Y(10 ** e), y2: Y(10 ** e), class: "gridline" }, svg);
    const t = el("text", { x: m.l - 6, y: Y(10 ** e) + 4, "text-anchor": "end" }, svg);
    t.textContent = e >= 4 || e < -2 ? `1e${e}` : String(+(10 ** e).toPrecision(1));
  }
  if (hasZero) el("text", { x: m.l - 6, y: H - m.b, "text-anchor": "end" }, svg).textContent = "0";
  el("line", { x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b, class: "axisline" }, svg);
  const xstep = x1 - x0 > 9 ? 2 : 1;
  for (let x = Math.ceil(x0); x <= x1; x += xstep) {
    el("text", { x: X(x), y: H - m.b + 15, "text-anchor": "middle" }, svg).textContent = x;
  }
  el("text", { x: (m.l + W - m.r) / 2, y: H - 4, "text-anchor": "middle" }, svg).textContent = opts.xLabel;
  const yl = el("text", { x: 11, y: (m.t + H - m.b) / 2, "text-anchor": "middle", transform: `rotate(-90 11 ${(m.t + H - m.b) / 2})` }, svg);
  yl.textContent = opts.yLabel;
  const surf = css("--surface");
  for (const s of series) {
    if (!s.points.length) continue;
    const col = css(s.color);
    const d = s.points.map((p, i) => `${i ? "L" : "M"}${X(p.x).toFixed(1)},${Y(p.y).toFixed(1)}`).join("");
    el("path", { d, fill: "none", stroke: col, "stroke-width": 2, "stroke-dasharray": s.dash || "", "stroke-linejoin": "round" }, svg);
    for (const p of s.points) {
      el("circle", { cx: X(p.x), cy: Y(p.y), r: 4, fill: p.hollow ? surf : col, stroke: p.hollow ? col : surf, "stroke-width": 2 }, svg);
    }
  }
  const hit = el("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" }, svg);
  const cross = el("line", { y1: m.t, y2: H - m.b, stroke: css("--axis"), "stroke-width": 1, visibility: "hidden" }, svg);
  const move = (ev) => {
    const r = svg.getBoundingClientRect();
    const sx = ((ev.clientX - r.left) / r.width) * W;
    const x = Math.round(x0 + ((sx - m.l) / (W - m.l - m.r)) * (x1 - x0));
    if (x < x0 || x > x1) return;
    cross.setAttribute("x1", X(x)); cross.setAttribute("x2", X(x)); cross.setAttribute("visibility", "visible");
    const rows = series.map((s) => ({ s, p: s.points.find((p) => p.x === x) })).filter((o) => o.p).sort((a, b) => b.p.y - a.p.y);
    tip.innerHTML = "";
    tip.appendChild(h("div", {}, `${opts.xLabel}: ${x}`));
    if (!rows.length) tip.appendChild(h("div", {}, "no data"));
    for (const { s, p } of rows) {
      const row = h("div");
      const sw = h("span", { class: "sw" });
      sw.style.background = css(s.color);
      row.append(sw, document.createTextNode(`${s.name}: ${opts.fmt(p.y)}${p.note ? " " + p.note : ""}`));
      tip.appendChild(row);
    }
    tip.style.display = "block";
    const bx = box.getBoundingClientRect();
    let left = ev.clientX - bx.left + 14;
    if (left + tip.offsetWidth > bx.width) left = ev.clientX - bx.left - tip.offsetWidth - 14;
    tip.style.left = `${Math.max(0, left)}px`;
    tip.style.top = `${ev.clientY - bx.top + 10}px`;
  };
  hit.addEventListener("mousemove", move);
  hit.addEventListener("touchstart", (ev) => move(ev.touches[0]), { passive: true });
  hit.addEventListener("mouseleave", () => { tip.style.display = "none"; cross.setAttribute("visibility", "hidden"); });
}

function points(c, f, t, metric) {
  const out = [];
  for (const r of DATA.results) {
    if (r.c !== c || r.f !== f || r.t !== t) continue;
    if (!usable(r) || r[metric] === undefined || r[metric] === null) continue;
    out.push({ x: r.q, y: r[metric], hollow: r.v === "skipped", note: r.v === "skipped" ? "(not simulated)" : "" });
  }
  return out.sort((a, b) => a.x - b.x);
}

// ---------------------------------------------------------------- hero tiles
function renderTiles() {
  const main = DATA.results.filter((r) => !r.st || r.st === "main");
  const comps = new Set(main.map((r) => r.c).filter((c) => c !== "reference"));
  const ok = DATA.results.filter(verified).length;
  const bad = DATA.results.filter((r) => r.s === "ok" && r.v === "failed").length;
  const latest = DATA.latest;
  const tiles = [
    [comps.size, "compilers"], [new Set(main.map((r) => r.f)).size, "Boolean functions"],
    [new Set(main.map((r) => r.t)).size, "qubit layouts"], [DATA.results.length.toLocaleString("en-US"), "compile jobs"],
    [ok.toLocaleString("en-US"), "circuits verified"], [bad, "wrong circuits found"],
    [new Date((latest.run_id || "").slice(0, 10)).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }),
      `latest run, ${latest.mode} versions`],
  ];
  const box = document.getElementById("tiles");
  box.innerHTML = "";
  for (const [v, k] of tiles) {
    const t = h("div", { class: "tile" });
    t.append(h("div", { class: "v" }, String(v)), h("div", { class: "k" }, k));
    box.appendChild(t);
  }
}

// ---------------------------------------------------------------- method tables and layout figures
function renderMethod() {
  const tb = document.getElementById("func-table");
  tb.innerHTML = "";
  for (const [id, name, def] of FUNCS) {
    const tr = h("tr");
    const [a, b] = SIZES[id];
    tr.append(h("td", {}, name), h("td", {}, def), h("td", { class: "num" }, OUTPUTS[id] || "1"),
      h("td", { class: "num" }, a === b ? String(a) : `${a} – ${b}`));
    tb.appendChild(tr);
  }
  for (const [k, v] of Object.entries(DATA.latest.versions || {})) {
    document.querySelectorAll(`[data-version="${k}"]`).forEach((e) => { e.textContent = v; });
  }
  const row = document.getElementById("topo-row");
  row.innerHTML = "";
  const graphs = [
    ["Fully connected", circlePos(6), allPairs(6)],
    ["Line", [...Array(6).keys()].map((i) => [i, 0]), [...Array(5).keys()].map((i) => [i, i + 1])],
    ["Ring", circlePos(6), [...Array(6).keys()].map((i) => [i, (i + 1) % 6])],
    ["Square grid", [...Array(9).keys()].map((i) => [i % 3, Math.floor(i / 3)]),
      [...Array(9).keys()].flatMap((i) => [i % 3 < 2 ? [i, i + 1] : null, i < 6 ? [i, i + 3] : null]).filter(Boolean)],
    ["IBM heavy-hex, 57 qubits", LAYOUTS.heavy_hex.pos, LAYOUTS.heavy_hex.edges],
    ["Google Sycamore, 54 qubits", LAYOUTS.sycamore.pos, LAYOUTS.sycamore.edges],
  ];
  for (const [name, pos, edges] of graphs) {
    const fig = h("figure");
    const svg = el("svg", { viewBox: "0 0 160 110", "aria-hidden": "true" }, fig);
    const xs = pos.map((p) => p[0]), ys = pos.map((p) => p[1]);
    const [ax, bx, ay, by] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    const sc = Math.min(140 / (bx - ax || 1), 90 / (by - ay || 1));
    const P = pos.map(([x, y]) => [80 + (x - (ax + bx) / 2) * sc, 55 + (y - (ay + by) / 2) * sc]);
    const r = pos.length > 20 ? 2.4 : 6;
    for (const [a, b] of edges) el("line", { x1: P[a][0], y1: P[a][1], x2: P[b][0], y2: P[b][1] }, svg);
    for (const [x, y] of P) el("circle", { cx: x, cy: y, r, style: pos.length > 20 ? "stroke-width:1" : "" }, svg);
    fig.appendChild(h("figcaption", {}, name));
    row.appendChild(fig);
  }
  const to = DATA.results.find((r) => r.s === "timeout" && r.c !== "bqskit");
  if (to && to.to) document.getElementById("timeout-note").textContent = `${to.to} s`;
}
function circlePos(n) { return [...Array(n).keys()].map((i) => [Math.sin((2 * Math.PI * i) / n), -Math.cos((2 * Math.PI * i) / n)]); }
function allPairs(n) { const e = []; for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) e.push([i, j]); return e; }

// ---------------------------------------------------------------- main results
function familyCompilers() { return FAMILIES[state.family].ids.map((id) => CMAP[id]); }

function renderLegend() {
  const lg = document.getElementById("legend");
  lg.innerHTML = "";
  for (const c of familyCompilers()) {
    const lab = h("label");
    const cb = h("input", { type: "checkbox" });
    cb.checked = !state.off.has(c.id);
    cb.addEventListener("change", () => {
      cb.checked ? state.off.delete(c.id) : state.off.add(c.id);
      store("qbc-off-v3", [...state.off]);
      renderCharts();
    });
    lab.append(cb, swatch(c), document.createTextNode(c.name));
    lg.appendChild(lab);
  }
}

function renderCharts() {
  const grid = document.getElementById("charts");
  grid.innerHTML = "";
  const M = METRICS[state.metric];
  const comps = familyCompilers().filter((c) => !state.off.has(c.id));
  for (const t of TOPOS) {
    const div = h("div");
    grid.appendChild(div);
    const series = comps.map((c) => ({ ...c, points: points(c.id, state.func, t.id, state.metric) }));
    lineChart(div, t.name, series, { xDomain: SIZES[state.func], xLabel: "Qubits", yLabel: M.name, fmt: M.fmt });
  }
  renderMainTable();
}

function cellText(r, metric, fmt) {
  if (!r) return ["", ""];
  if (r.s === "timeout") return ["⏱", ""];
  if (r.s === "memory") return ["M", ""];
  if (r.s !== "ok") return ["!", ""];
  if (r.v === "failed") return [`${fmt(r[metric])} ✗`, "bad"];
  if (r.v === "skipped") return [`${fmt(r[metric])}*`, ""];
  return [r[metric] === undefined ? "–" : fmt(r[metric]), ""];
}

function renderMainTable() {
  const wrap = document.getElementById("main-table");
  const M = METRICS[state.metric];
  const [a, b] = SIZES[state.func];
  const t = h("table");
  const head = h("tr");
  head.append(h("th", {}, "Compiler"), h("th", {}, "Layout"));
  for (let q = a; q <= b; q++) head.appendChild(h("th", { class: "num" }, `${q} q`));
  t.appendChild(head);
  for (const c of familyCompilers()) for (const tp of TOPOS) {
    if (!DATA.results.some((r) => r.c === c.id && r.f === state.func && r.t === tp.id)) continue;
    const tr = h("tr");
    tr.append(h("td", {}, c.name), h("td", {}, tp.name));
    for (let q = a; q <= b; q++) {
      const [txt, cls] = cellText(IDX.get(key(c.id, state.func, tp.id, q)), state.metric, M.fmt);
      tr.appendChild(h("td", { class: `num ${cls}` }, txt));
    }
    t.appendChild(tr);
  }
  wrap.innerHTML = "";
  wrap.appendChild(t);
  wrap.appendChild(h("p", { class: "note", style: "padding:0 10px" }, "⏱ timeout, M memory limit, ! error, ✗ wrong result, * not simulated (too large)."));
}

// ---------------------------------------------------------------- coverage
function coverage(c, f, t) {
  const [a, b] = SIZES[f];
  const rows = DATA.results.filter((r) => r.c === c && r.f === f && r.t === t).sort((x, y) => x.q - y.q);
  if (!rows.length) return null;
  let best = null, why = "", n = 0;
  for (const r of rows) {
    if (verified(r)) { best = r.q; n++; continue; }
    if (r.s === "ok" && r.v === "skipped") { n++; best = best; why = why || `${r.q}*`; continue; }
    why = why || (r.s === "timeout" ? `⏱ ${r.q}` : r.s === "memory" ? `M ${r.q}` : r.s !== "ok" ? `! ${r.q}` : `✗ ${r.q}`);
  }
  const total = b - a + 1;
  return { best, why, frac: n / total };
}

function renderCoverage() {
  const t = h("table");
  const head = h("tr");
  head.appendChild(h("th", {}, "Compiler"));
  for (const [f, name] of FUNCS) head.appendChild(h("th", { class: "num" }, name));
  t.appendChild(head);
  for (const fam of Object.values(FAMILIES)) {
    const g = h("tr", { class: "grp" });
    g.appendChild(h("td", { colspan: FUNCS.length + 1 }, fam.name));
    t.appendChild(g);
    for (const id of fam.ids) {
      const tr = h("tr");
      tr.appendChild(h("td", {}, CMAP[id].name));
      for (const [f] of FUNCS) {
        const cv = coverage(id, f, state.covTopo);
        const td = h("td", { class: "cov" });
        if (!cv) { td.textContent = "∅"; td.style.color = css("--ink-2"); }
        else {
          td.textContent = cv.best ? String(cv.best) : "–";
          if (cv.why) { td.appendChild(document.createTextNode(" ")); td.appendChild(h("small", {}, cv.why)); }
          td.style.background = `color-mix(in srgb, var(--s1) ${Math.round(8 + 50 * cv.frac)}%, var(--surface))`;
          td.title = `${Math.round(100 * cv.frac)} % of the tested sizes compiled correctly`;
        }
        tr.appendChild(td);
      }
      t.appendChild(tr);
    }
  }
  const w = document.getElementById("coverage-table");
  w.innerHTML = "";
  w.appendChild(t);
}

// ---------------------------------------------------------------- hardware and noise
const HW = [["heavy_hex", "ibm"], ["sycamore", "google"], ["fully", "ionq"]];
const hwState = { func: "and", size: 6 };

function renderNoiseTable() {
  const t = h("table");
  const head = h("tr");
  ["Platform", "Layout used", "1-qubit error", "2-qubit error", "Source"].forEach((x) => head.appendChild(h("th", {}, x)));
  t.appendChild(head);
  for (const [topo, k] of HW) {
    const n = DATA.noise[k];
    const tr = h("tr");
    tr.append(h("td", {}, n.name), h("td", {}, TNAME[topo]), h("td", { class: "num" }, n.e1.toExponential(1)),
      h("td", { class: "num" }, n.e2.toExponential(2)), h("td", { class: "note" }, n.source));
    t.appendChild(tr);
  }
  const w = document.getElementById("noise-table");
  w.innerHTML = "";
  w.appendChild(t);
}

function renderHardware() {
  const sizes = [];
  for (let q = SIZES[hwState.func][0]; q <= SIZES[hwState.func][1]; q++) sizes.push([q, `${q}`]);
  if (!sizes.some(([q]) => q === hwState.size)) hwState.size = sizes[Math.min(3, sizes.length - 1)][0];
  selectBox("hw-size", sizes, hwState.size, (v) => { hwState.size = +v; renderHardware(); });
  const t = h("table");
  const head = h("tr");
  head.appendChild(h("th", {}, "Compiler"));
  for (const [topo, k] of HW) head.appendChild(h("th", {}, DATA.noise[k].name.split(" (")[0]));
  t.appendChild(head);
  const rows = [];
  for (const c of COMPILERS) {
    const cells = HW.map(([topo]) => IDX.get(key(c.id, hwState.func, topo, hwState.size)));
    if (cells.every((r) => !r)) continue;
    rows.push([c, cells]);
  }
  rows.sort((a, b) => Math.max(...b[1].map((r) => (verified(r) ? r.esp || 0 : 0))) - Math.max(...a[1].map((r) => (verified(r) ? r.esp || 0 : 0))));
  for (const [c, cells] of rows) {
    const tr = h("tr");
    tr.appendChild(h("td", {}, c.name));
    for (const r of cells) {
      const td = h("td");
      if (!r) td.textContent = "";
      else if (r.s === "timeout") td.textContent = "timeout";
      else if (r.s === "memory") td.textContent = "memory limit";
      else if (r.s !== "ok") td.textContent = "error";
      else if (r.v === "failed") { td.textContent = "wrong result"; td.className = "bad"; }
      else {
        const m = h("div", { class: "meter" });
        const tr2 = h("div", { class: "track" });
        const f = h("div", { class: "fill" });
        f.style.width = `${Math.max(0.5, 100 * (r.esp || 0))}%`;
        tr2.appendChild(f);
        m.append(tr2, h("span", {}, METRICS.esp.fmt(r.esp || 0)));
        td.appendChild(m);
        td.appendChild(h("div", { class: "note" }, `${r.two.toLocaleString("en-US")} two-qubit, ${(r.one ?? 0).toLocaleString("en-US")} single-qubit gates`));
      }
      tr.appendChild(td);
    }
    t.appendChild(tr);
  }
  const w = document.getElementById("hw-table");
  w.innerHTML = "";
  w.appendChild(t);
}

// ---------------------------------------------------------------- studies
const RAMP = (i, n) => `color-mix(in srgb, var(--s1) ${Math.round(30 + (70 * i) / Math.max(1, n - 1))}%, var(--surface))`;

function renderLevels() {
  const grid = document.getElementById("lvl-charts");
  grid.innerHTML = "";
  const groups = [
    ["Qiskit", [["qiskit:o0", "level 0"], ["qiskit:o1", "level 1"], ["qiskit:o2", "level 2"], ["qiskit", "level 3"]]],
    ["tket", [["tket:o0", "level 0"], ["tket:o1", "level 1"], ["tket", "level 2"]]],
    ["MQT", [["mqt", "line-aware"], ["mqt:cost", "cost-aware"]]],
  ];
  for (const [name, items] of groups) {
    const div = h("div");
    grid.appendChild(div);
    const series = items.map(([id, label], i) => ({
      name: `${name} ${label}`, color: RAMP(i, items.length), dash: "", points: points(id, state.lvlFunc, state.lvlTopo, "two"),
    }));
    // colours are computed values, not variables
    series.forEach((s) => { s.color = resolveMix(s.color); });
    lineChart(div, `${name} · ${FNAME[state.lvlFunc]}`, series,
      { xDomain: SIZES[state.lvlFunc], xLabel: "Qubits", yLabel: "Two-qubit gates", fmt: nfmt });
    const lg = h("div", { class: "legend" });
    for (const s of series) { const l = h("label"); l.append(swatch(s), document.createTextNode(s.name)); lg.appendChild(l); }
    div.appendChild(lg);
  }
}
// resolve a color-mix() expression into an rgb() string so that SVG attributes can use it
function resolveMix(expr) {
  const probe = h("span");
  probe.style.color = expr;
  document.body.appendChild(probe);
  const v = getComputedStyle(probe).color;
  probe.remove();
  return v;
}

const ANC = [
  ["noaux_v24", "No helper (V24)", "0"], ["1_clean_b95", "1 clean (B95)", "1"], ["1_clean_kg24", "1 clean (KG24)", "1"],
  ["2_clean_kg24", "2 clean (KG24)", "2"], ["n_clean_m15", "k−2 clean (M15, V-chain)", "k−2"],
  ["1_dirty_kg24", "1 dirty (KG24)", "1"], ["n_dirty_i15", "k−2 dirty (I15)", "k−2"],
];
function renderAncilla() {
  const metric = state.ancMetric;
  const series = ANC.map(([id, name], i) => ({
    name, color: `--s${i + 1}`, dash: "", points: points(`qiskit_mcx:${id}`, state.ancFunc, state.ancTopo, metric),
  }));
  const lg = document.getElementById("anc-legend");
  lg.innerHTML = "";
  for (const s of series) { const l = h("label"); l.append(swatch(s), document.createTextNode(s.name)); lg.appendChild(l); }
  const M = { two: METRICS.two, d: METRICS.d, u: { name: "Qubits used", fmt: nfmt } }[metric];
  lineChart(document.getElementById("anc-chart"), `${FNAME[state.ancFunc]} · ${TNAME[state.ancTopo]}`, series,
    { xDomain: [4, 16], xLabel: "Logical qubits", yLabel: M.name, fmt: M.fmt });
}

// ---------------------------------------------------------------- 2022 vs now
function renderOld() {
  const pairs = [
    { name: "Qiskit 2022", old: "qiskit", color: "--s1", dash: "5 4" },
    { name: "Qiskit now", now: "qiskit", color: "--s1", dash: "" },
    { name: "tket 2022", old: "tket", color: "--s2", dash: "5 4" },
    { name: "tket now", now: "tket", color: "--s2", dash: "" },
    { name: "pyQuil/quilc 2022", old: "pyquil", color: "--s3", dash: "5 4" },
    { name: "quilc now", now: "quilc", color: "--s3", dash: "" },
  ];
  const f = state.oldFunc, tp = state.oldTopo;
  const series = pairs.map((p) => ({
    name: p.name, color: p.color, dash: p.dash,
    points: (p.old
      ? DATA.thesis_2022.filter((r) => r.compiler === p.old && r.function === f && r.topology === tp).map((r) => ({ x: r.n_qubits, y: r.two_qubit + (r.xy || 0) }))
      : points(p.now, f, tp, "two")).sort((a, b) => a.x - b.x),
  }));
  const lg = document.getElementById("old-legend");
  lg.innerHTML = "";
  for (const s of series) { const l = h("label"); l.append(swatch(s), document.createTextNode(s.name)); lg.appendChild(l); }
  const xmax = Math.max(10, ...series.flatMap((s) => s.points.map((p) => p.x)));
  lineChart(document.getElementById("old-chart"), `${FNAME[f]} · ${TNAME[tp]}`, series,
    { xDomain: [3, xmax], xLabel: "Qubits", yLabel: "Two-qubit gates", fmt: nfmt });
}

// ---------------------------------------------------------------- over time
const histState = { func: "and", topo: "fully", size: 6 };
function renderRuns() {
  const t = h("table");
  const head = h("tr");
  ["Run", "Versions", "Jobs", "Qiskit", "tket", "Cirq", "quilc", "Qrisp", "MQT (qmap)"].forEach((x, i) => head.appendChild(h("th", { class: i === 2 ? "num" : "" }, x)));
  t.appendChild(head);
  for (const r of [...DATA.runs].reverse()) {
    const v = r.versions || {};
    const tr = h("tr");
    tr.append(h("td", {}, r.label || r.run_id), h("td", {}, r.mode), h("td", { class: "num" }, r.jobs ?? ""),
      h("td", {}, v.qiskit || ""), h("td", {}, v.pytket || ""), h("td", {}, v["cirq-core"] || ""), h("td", {}, v.quilc || ""),
      h("td", {}, v.qrisp || ""), h("td", {}, v["mqt-qmap"] || ""));
    t.appendChild(tr);
  }
  const w = document.getElementById("runs-table");
  w.innerHTML = "";
  w.appendChild(t);
}
function renderHistory() {
  const sizes = [];
  for (let q = SIZES[histState.func][0]; q <= SIZES[histState.func][1]; q++) sizes.push([q, String(q)]);
  if (!sizes.some(([q]) => q === histState.size)) histState.size = sizes[0][0];
  selectBox("hist-size", sizes, histState.size, (v) => { histState.size = +v; renderHistory(); });
  const runs = DATA.runs.map((r) => r.run_id);
  const t = h("table");
  const head = h("tr");
  head.appendChild(h("th", {}, "Compiler"));
  for (const r of DATA.runs) head.appendChild(h("th", { class: "num" }, (r.run_id || "").slice(0, 10) + (r.run_id.endsWith("initial") ? " (first)" : "")));
  t.appendChild(head);
  for (const c of COMPILERS) {
    const vals = runs.map((run) => DATA.history.find((x) => x[0] === run && x[1] === c.id && x[2] === histState.func && x[4] === histState.topo
      && (x[3] + (histState.func === "adder" ? x[3] / 2 + 1 : 1)) === histState.size));
    if (vals.every((v) => !v)) continue;
    const tr = h("tr");
    tr.appendChild(h("td", {}, c.name));
    for (const v of vals) {
      if (!v) { tr.appendChild(h("td", { class: "num" }, "–")); continue; }
      const bad = v[6] === "failed";
      tr.appendChild(h("td", { class: bad ? "num bad" : "num" }, v[5].toLocaleString("en-US") + (bad ? " ✗" : "")));
    }
    t.appendChild(tr);
  }
  const w = document.getElementById("hist-table");
  w.innerHTML = "";
  w.appendChild(t);
  w.appendChild(h("p", { class: "note", style: "padding:0 10px" }, "Two-qubit gates per run. – means not run, not finished or (for the first run) not part of that study."));
}

// ---------------------------------------------------------------- text
function renderText() {
  const T = window.SITE_TEXT;
  if (!T) return;
  const f = document.getElementById("findings");
  f.innerHTML = T.findings;
  document.getElementById("discussion-body").innerHTML = T.discussion;
  document.getElementById("improve").innerHTML = T.improve;
  document.getElementById("limits").innerHTML = T.limits;
}

// ---------------------------------------------------------------- wiring
function renderAll() {
  renderTiles();
  renderMethod();
  renderLegend();
  renderCharts();
  renderCoverage();
  renderNoiseTable();
  renderHardware();
  renderLevels();
  renderAncilla();
  renderOld();
  renderRuns();
  renderHistory();
  renderText();
}

async function init() {
  [DATA, LAYOUTS] = await Promise.all([
    fetch("data/results.json").then((r) => r.json()), fetch("data/layouts.json").then((r) => r.json()),
  ]);
  for (const r of DATA.results) IDX.set(key(r.c, r.f, r.t, r.q), r);
  const funcOpts = FUNCS.map(([k, n]) => [k, n]);
  selectBox("func-sel", funcOpts, state.func, (v) => { state.func = v; store("qbc-func", v); renderCharts(); });
  segmented("family-seg", Object.entries(FAMILIES).map(([k, v]) => [k, v.name]), () => state.family,
    (k) => { state.family = k; store("qbc-family", k); renderLegend(); renderCharts(); });
  segmented("metric-seg", Object.entries(METRICS).map(([k, v]) => [k, v.name]), () => state.metric,
    (k) => { state.metric = k; renderCharts(); });
  segmented("cov-topo-seg", TOPOS.map((t) => [t.id, t.name]), () => state.covTopo, (k) => { state.covTopo = k; renderCoverage(); });
  selectBox("hw-func", funcOpts.filter(([k]) => SIZES[k][1] > 2), hwState.func, (v) => { hwState.func = v; renderHardware(); });
  const lvlF = [["and", "AND"], ["or", "OR"], ["xor", "XOR"], ["majority", "Majority"], ["adder", "Adder"]];
  const st = [["fully", "Fully connected"], ["heavy_hex", "IBM heavy-hex"]];
  segmented("lvl-func-seg", lvlF, () => state.lvlFunc, (k) => { state.lvlFunc = k; renderLevels(); });
  segmented("lvl-topo-seg", st, () => state.lvlTopo, (k) => { state.lvlTopo = k; renderLevels(); });
  segmented("anc-func-seg", [["and", "AND"], ["or", "OR"]], () => state.ancFunc, (k) => { state.ancFunc = k; renderAncilla(); });
  segmented("anc-topo-seg", st, () => state.ancTopo, (k) => { state.ancTopo = k; renderAncilla(); });
  segmented("anc-metric-seg", [["two", "Two-qubit gates"], ["d", "Depth"], ["u", "Qubits used"]], () => state.ancMetric,
    (k) => { state.ancMetric = k; renderAncilla(); });
  segmented("old-func-seg", [["and", "AND"], ["or", "OR"], ["xor", "XOR"]], () => state.oldFunc, (k) => { state.oldFunc = k; renderOld(); });
  segmented("old-topo-seg", TOPOS.slice(0, 4).map((t) => [t.id, t.name]), () => state.oldTopo, (k) => { state.oldTopo = k; renderOld(); });
  selectBox("hist-func", funcOpts, histState.func, (v) => { histState.func = v; renderHistory(); });
  selectBox("hist-topo", TOPOS.map((t) => [t.id, t.name]), histState.topo, (v) => { histState.topo = v; renderHistory(); });
  renderAll();
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", renderAll);
  document.getElementById("theme").addEventListener("click", () => {
    const dark = css("--surface") === "#191919";
    document.documentElement.setAttribute("data-theme", dark ? "light" : "dark");
    renderAll();
  });
}
init();
