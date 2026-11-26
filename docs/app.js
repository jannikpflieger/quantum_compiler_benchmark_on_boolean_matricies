// Renders the result charts and tables from data/results.json. No external libraries.

const COMPILERS = [
  { id: "qiskit", name: "Qiskit (expression)", color: "--s1", dash: "" },
  { id: "qiskit_matrix", name: "Qiskit (matrix)", color: "--s1", dash: "6 4" },
  { id: "tket", name: "tket", color: "--s2", dash: "" },
  { id: "cirq", name: "Cirq", color: "--s3", dash: "" },
  { id: "quilc", name: "quilc", color: "--s4", dash: "" },
  { id: "pennylane", name: "PennyLane", color: "--s5", dash: "" },
  { id: "qibo", name: "Qibo", color: "--s6", dash: "" },
  { id: "bqskit", name: "BQSKit", color: "--s7", dash: "" },
  { id: "qrisp_gray", name: "Qrisp (Gray)", color: "--s8", dash: "" },
  { id: "qrisp_pprm", name: "Qrisp (PPRM)", color: "--s8", dash: "6 4" },
  { id: "reference", name: "Textbook construction", color: "--ref", dash: "2 3" },
];
const CMAP = Object.fromEntries(COMPILERS.map((c) => [c.id, c]));
const TOPOS = [
  { id: "fully", name: "Fully connected" },
  { id: "line", name: "Line" },
  { id: "ring", name: "Ring" },
  { id: "grid", name: "Square grid" },
];
const FUNCS = { and: "AND", or: "OR", xor: "XOR" };
const METRICS = {
  two_qubit: { name: "Two-qubit gates", fmt: (v) => v.toLocaleString("en-US") },
  total: { name: "All gates", fmt: (v) => v.toLocaleString("en-US") },
  compile_time: { name: "Compile time (s)", fmt: (v) => (v < 1 ? v.toFixed(3) : v < 100 ? v.toFixed(1) : v.toFixed(0)) },
};
const DEFAULT_ON = new Set(COMPILERS.map((c) => c.id));

const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
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

let DATA = null;
const state = { func: "and", metric: "two_qubit", on: new Set(DEFAULT_ON), oldFunc: "and", oldTopo: "fully" };
try {
  const saved = JSON.parse(localStorage.getItem("qbc-on-v2") || "null");
  if (Array.isArray(saved)) state.on = new Set(saved);
} catch (e) { /* storage unavailable */ }

function ok(r) { return r.status === "ok" && r.verified !== "failed" && r[state.metric] !== undefined; }

// ---------------------------------------------------------------- generic log-scale line chart
function lineChart(container, title, series, opts) {
  container.innerHTML = "";
  const box = h("div", { class: "chart" });
  box.appendChild(h("h4", {}, title));
  const W = 440, H = 270, m = { l: 52, r: 12, t: 10, b: 34 };
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": title }, box);
  const pts = series.flatMap((s) => s.points);
  const tip = h("div", { class: "tip" });
  box.appendChild(tip);
  container.appendChild(box);
  if (!pts.length) {
    el("text", { x: W / 2, y: H / 2, "text-anchor": "middle" }, svg).textContent = "No successful runs";
    return;
  }
  const xs = opts.xDomain;
  const ys = pts.map((p) => p.y).filter((y) => y > 0);
  let lo = Math.floor(Math.log10(Math.min(...ys)));
  let hi = Math.ceil(Math.log10(Math.max(...ys)));
  if (hi === lo) hi = lo + 1;
  const X = (x) => m.l + ((x - xs[0]) / (xs[1] - xs[0])) * (W - m.l - m.r);
  const Y = (y) => m.t + (1 - (Math.log10(Math.max(y, 10 ** lo)) - lo) / (hi - lo)) * (H - m.t - m.b);
  for (let e = lo; e <= hi; e++) {
    el("line", { x1: m.l, x2: W - m.r, y1: Y(10 ** e), y2: Y(10 ** e), class: "gridline" }, svg);
    const t = el("text", { x: m.l - 6, y: Y(10 ** e) + 4, "text-anchor": "end" }, svg);
    t.textContent = e >= 3 || e < -1 ? `1e${e}` : String(10 ** e);
  }
  el("line", { x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b, class: "axisline" }, svg);
  for (let x = xs[0]; x <= xs[1]; x++) {
    el("text", { x: X(x), y: H - m.b + 15, "text-anchor": "middle" }, svg).textContent = x;
  }
  el("text", { x: (m.l + W - m.r) / 2, y: H - 4, "text-anchor": "middle" }, svg).textContent = opts.xLabel;
  const yl = el("text", { x: 12, y: (m.t + H - m.b) / 2, "text-anchor": "middle", transform: `rotate(-90 12 ${(m.t + H - m.b) / 2})` }, svg);
  yl.textContent = opts.yLabel;
  for (const s of series) {
    if (!s.points.length) continue;
    const col = css(s.color);
    const d = s.points.map((p, i) => `${i ? "L" : "M"}${X(p.x).toFixed(1)},${Y(p.y).toFixed(1)}`).join("");
    el("path", { d, fill: "none", stroke: col, "stroke-width": 2, "stroke-dasharray": s.dash, "stroke-linejoin": "round" }, svg);
    for (const p of s.points) {
      el("circle", { cx: X(p.x), cy: Y(p.y), r: 4, fill: col, stroke: css("--surface"), "stroke-width": 2 }, svg);
    }
  }
  // hover: nearest x column, list all series values
  const hit = el("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" }, svg);
  const cross = el("line", { y1: m.t, y2: H - m.b, stroke: css("--axis"), "stroke-width": 1, visibility: "hidden" }, svg);
  hit.addEventListener("mousemove", (ev) => {
    const r = svg.getBoundingClientRect();
    const sx = ((ev.clientX - r.left) / r.width) * W;
    const x = Math.round(xs[0] + ((sx - m.l) / (W - m.l - m.r)) * (xs[1] - xs[0]));
    if (x < xs[0] || x > xs[1]) return;
    cross.setAttribute("x1", X(x)); cross.setAttribute("x2", X(x)); cross.setAttribute("visibility", "visible");
    const rows = series.map((s) => ({ s, p: s.points.find((p) => p.x === x) })).filter((o) => o.p)
      .sort((a, b) => b.p.y - a.p.y);
    tip.innerHTML = "";
    tip.appendChild(h("div", {}, `${opts.xLabel}: ${x}`));
    if (!rows.length) tip.appendChild(h("div", {}, "no data"));
    for (const { s, p } of rows) {
      const row = h("div");
      const sw = h("span", { class: "sw" });
      sw.style.background = css(s.color);
      row.appendChild(sw);
      row.appendChild(document.createTextNode(`${s.name}: ${opts.fmt(p.y)}`));
      tip.appendChild(row);
    }
    tip.style.display = "block";
    const bx = box.getBoundingClientRect();
    let left = ev.clientX - bx.left + 14;
    if (left + tip.offsetWidth > bx.width) left = ev.clientX - bx.left - tip.offsetWidth - 14;
    tip.style.left = `${Math.max(0, left)}px`;
    tip.style.top = `${ev.clientY - bx.top + 10}px`;
  });
  hit.addEventListener("mouseleave", () => { tip.style.display = "none"; cross.setAttribute("visibility", "hidden"); });
}

function swatch(c) {
  const s = el("svg", { width: 22, height: 10, "aria-hidden": "true" });
  el("line", { x1: 1, x2: 21, y1: 5, y2: 5, stroke: css(c.color), "stroke-width": 2, "stroke-dasharray": c.dash }, s);
  return s;
}

// ---------------------------------------------------------------- main results
function renderLegend() {
  const lg = document.getElementById("legend");
  lg.innerHTML = "";
  for (const c of COMPILERS) {
    const lab = h("label");
    const cb = h("input", { type: "checkbox" });
    cb.checked = state.on.has(c.id);
    cb.addEventListener("change", () => {
      cb.checked ? state.on.add(c.id) : state.on.delete(c.id);
      try { localStorage.setItem("qbc-on-v2", JSON.stringify([...state.on])); } catch (e) { /* ignore */ }
      renderMain();
    });
    lab.append(cb, swatch(c), document.createTextNode(c.name));
    lg.appendChild(lab);
  }
}

function seriesFor(func, topo) {
  return COMPILERS.filter((c) => state.on.has(c.id)).map((c) => ({
    name: c.name, color: c.color, dash: c.dash,
    points: DATA.results.filter((r) => r.compiler === c.id && r.function === func && r.topology === topo && ok(r))
      .map((r) => ({ x: r.n_qubits, y: r[state.metric] })).sort((a, b) => a.x - b.x),
  }));
}

function renderMain() {
  const grid = document.getElementById("charts");
  grid.innerHTML = "";
  const M = METRICS[state.metric];
  for (const t of TOPOS) {
    const div = h("div");
    grid.appendChild(div);
    lineChart(div, `${FUNCS[state.func]} · ${t.name}`, seriesFor(state.func, t.id),
      { xDomain: [3, 10], xLabel: "Qubits", yLabel: M.name, fmt: M.fmt });
  }
  renderMainTable();
}

function renderMainTable() {
  const wrap = document.getElementById("main-table");
  const M = METRICS[state.metric];
  const t = h("table");
  const head = h("tr");
  head.append(h("th", {}, "Compiler"), h("th", {}, "Topology"));
  for (let q = 3; q <= 10; q++) head.appendChild(h("th", { class: "num" }, `${q} q`));
  t.appendChild(head);
  for (const c of COMPILERS) for (const tp of TOPOS) {
    const rows = DATA.results.filter((r) => r.compiler === c.id && r.function === state.func && r.topology === tp.id);
    if (!rows.length) continue;
    const tr = h("tr");
    tr.append(h("td", {}, c.name), h("td", {}, tp.name));
    for (let q = 3; q <= 10; q++) {
      const r = rows.find((x) => x.n_qubits === q);
      let txt = "";
      let cls = "num";
      if (r) {
        if (r.status === "timeout") txt = "timeout";
        else if (r.status !== "ok") txt = "error";
        else if (r.verified === "failed") { txt = `${M.fmt(r[state.metric])} ✗`; cls = "num bad"; }
        else txt = M.fmt(r[state.metric]);
      }
      tr.appendChild(h("td", { class: cls }, txt));
    }
    t.appendChild(tr);
  }
  wrap.innerHTML = "";
  wrap.appendChild(t);
}

function segmented(id, options, get, set) {
  const box = document.getElementById(id);
  box.innerHTML = "";
  for (const [k, label] of Object.entries(options)) {
    const b = h("button", { type: "button", "aria-pressed": String(get() === k) }, label);
    b.addEventListener("click", () => { set(k); segmented(id, options, get, set); });
    box.appendChild(b);
  }
}

// ---------------------------------------------------------------- small functions
function renderSmall() {
  const funcs = [["always0", "Always 0"], ["always1", "Always 1"], ["identity", "Identity"], ["two_of_three", "Two of three"]];
  const t = h("table");
  const head = h("tr");
  head.appendChild(h("th", {}, "Compiler"));
  for (const [, n] of funcs) head.appendChild(h("th", { class: "num" }, n));
  t.appendChild(head);
  for (const c of COMPILERS) {
    const tr = h("tr");
    tr.appendChild(h("td", {}, c.name));
    let any = false;
    for (const [f] of funcs) {
      const r = DATA.results.find((x) => x.compiler === c.id && x.function === f && x.topology === "fully");
      let txt = "–", cls = "num";
      if (r) {
        any = true;
        if (r.status === "timeout") txt = "timeout";
        else if (r.status !== "ok") txt = "error";
        else if (r.verified === "failed") { txt = `${r.two_qubit} ✗`; cls = "num bad"; }
        else txt = `${r.two_qubit} / ${r.total}`;
      }
      tr.appendChild(h("td", { class: cls }, txt));
    }
    if (any) t.appendChild(tr);
  }
  const w = document.getElementById("small-table");
  w.innerHTML = "";
  w.appendChild(t);
}

// ---------------------------------------------------------------- then vs now
function renderOld() {
  const pairs = [
    { name: "Qiskit 2022", old: "qiskit", color: "--s1", dash: "5 4" },
    { name: "Qiskit 2026", now: "qiskit", color: "--s1", dash: "" },
    { name: "tket 2022", old: "tket", color: "--s2", dash: "5 4" },
    { name: "tket 2026", now: "tket", color: "--s2", dash: "" },
    { name: "pyQuil/quilc 2022", old: "pyquil", color: "--s4", dash: "5 4" },
    { name: "quilc 2026", now: "quilc", color: "--s4", dash: "" },
  ];
  const f = state.oldFunc, tp = state.oldTopo;
  const series = pairs.map((p) => ({
    name: p.name, color: p.color, dash: p.dash,
    points: p.old
      ? DATA.thesis_2022.filter((r) => r.compiler === p.old && r.function === f && r.topology === tp && r.n_qubits <= 10)
        .map((r) => ({ x: r.n_qubits, y: r.two_qubit + (r.xy || 0) }))
      : DATA.results.filter((r) => r.compiler === p.now && r.function === f && r.topology === tp && r.status === "ok" && r.verified !== "failed")
        .map((r) => ({ x: r.n_qubits, y: r.two_qubit })),
  }));
  series.forEach((s) => s.points.sort((a, b) => a.x - b.x));
  const lg = document.getElementById("old-legend");
  lg.innerHTML = "";
  for (const s of series) {
    const lab = h("label");
    lab.append(swatch(s), document.createTextNode(s.name));
    lg.appendChild(lab);
  }
  lineChart(document.getElementById("old-chart"), `${FUNCS[f]} · ${TOPOS.find((t) => t.id === tp).name}`, series,
    { xDomain: [3, 10], xLabel: "Qubits", yLabel: "Two-qubit gates", fmt: (v) => v.toLocaleString("en-US") });
}

// ---------------------------------------------------------------- run summary
function renderSummary() {
  const t = h("table");
  const head = h("tr");
  ["Compiler", "Jobs", "Verified", "Wrong result", "Too large to check", "Timeout", "Error", "Largest verified circuit"].forEach((x, i) =>
    head.appendChild(h("th", { class: i ? "num" : "" }, x)));
  t.appendChild(head);
  for (const c of COMPILERS) {
    const rs = DATA.results.filter((r) => r.compiler === c.id);
    if (!rs.length) continue;
    const ver = rs.filter((r) => r.status === "ok" && (r.verified === "full" || r.verified === "sampled"));
    const bad = rs.filter((r) => r.status === "ok" && r.verified === "failed");
    const to = rs.filter((r) => r.status === "timeout");
    const skip = rs.filter((r) => r.status === "ok" && r.verified === "skipped");
    const err = rs.filter((r) => r.status === "error" || r.status === "crash");
    const big = ver.length ? Math.max(...ver.map((r) => r.n_qubits)) : "–";
    const tr = h("tr");
    tr.append(h("td", {}, c.name), h("td", { class: "num" }, rs.length), h("td", { class: "num" }, ver.length),
      h("td", { class: bad.length ? "num bad" : "num" }, bad.length), h("td", { class: "num" }, skip.length),
      h("td", { class: "num" }, to.length),
      h("td", { class: "num" }, err.length), h("td", { class: "num" }, big === "–" ? big : `${big} qubits`));
    t.appendChild(tr);
  }
  const w = document.getElementById("summary-table");
  w.innerHTML = "";
  w.appendChild(t);
}

function fillVersions() {
  for (const [k, v] of Object.entries(DATA.versions)) {
    document.querySelectorAll(`[data-version="${k}"]`).forEach((e) => { e.textContent = v; });
  }
}

function renderAll() {
  renderLegend();
  renderMain();
  renderSmall();
  renderOld();
  renderSummary();
}

async function init() {
  DATA = await (await fetch("data/results.json")).json();
  fillVersions();
  segmented("func-seg", FUNCS, () => state.func, (k) => { state.func = k; renderMain(); });
  segmented("metric-seg", Object.fromEntries(Object.entries(METRICS).map(([k, v]) => [k, v.name])),
    () => state.metric, (k) => { state.metric = k; renderMain(); });
  segmented("old-func-seg", FUNCS, () => state.oldFunc, (k) => { state.oldFunc = k; renderOld(); });
  segmented("old-topo-seg", Object.fromEntries(TOPOS.map((t) => [t.id, t.name])), () => state.oldTopo,
    (k) => { state.oldTopo = k; renderOld(); });
  renderAll();
  // repaint on theme change so colours follow the theme
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", renderAll);
  const btn = document.getElementById("theme");
  btn.addEventListener("click", () => {
    const dark = getComputedStyle(document.documentElement).getPropertyValue("--surface").trim() === "#191919";
    document.documentElement.setAttribute("data-theme", dark ? "light" : "dark");
    renderAll();
  });
}
init();
