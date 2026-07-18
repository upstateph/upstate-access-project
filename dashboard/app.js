/* Upstate Access Project — Tier 1 dashboard logic.
   Vanilla JS, no dependencies. Renders from data/dashboard.json (+ optional
   data/sc_counties.geojson for the choropleth). Degrades gracefully when the
   Census ACS overlay hasn't been pulled yet (acs_available === false). */

const SVGNS = "http://www.w3.org/2000/svg";
const fmt = (n) => (n == null ? "—" : n.toLocaleString());
const fmt1 = (n) => (n == null ? "—" : Number(n).toLocaleString(undefined, { maximumFractionDigits: 1 }));
const money = (n) => (n == null ? "—" : "$" + Math.round(n).toLocaleString());
const pct = (n) => (n == null ? "—" : fmt1(n) + "%");

function el(tag, attrs = {}, text) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v; else e.setAttribute(k, v);
  }
  if (text != null) e.textContent = text;
  return e;
}
function svg(tag, attrs = {}) {
  const e = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
}
function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

let DATA = null;
let GEO = null;
let SELECTED = null; // county_fips

init();

async function init() {
  try {
    DATA = await (await fetch("data/dashboard.json")).json();
  } catch (e) {
    document.getElementById("subtitle").textContent =
      "Could not load data/dashboard.json — run the data pipeline first (see README).";
    return;
  }
  try {
    GEO = await (await fetch("data/sc_counties.geojson")).json();
  } catch (e) {
    GEO = null; // map is optional
  }

  const yrs = DATA.years;
  document.getElementById("subtitle").textContent =
    `${fmt(DATA.state_total)} pedestrian fatalities across ${DATA.counties.length} counties, ` +
    `${yrs[0]}–${yrs[yrs.length - 1]}. Source: NHTSA FARS` +
    (DATA.acs_available ? ` · equity overlay: Census ACS ${DATA.acs_vintage} 5-year.` : `.`);

  document.getElementById("main").hidden = false;
  renderContext();
  renderKPIs();
  renderTrend();
  buildMetricSelect();
  renderChoropleth();
  renderEquity();
  renderTable();
  renderFooter();
}

/* ---------- Context ---------- */
function renderContext() {
  const c = DATA.context;
  const p = document.getElementById("context-panel");
  if (!c) { p.hidden = true; return; }
  p.innerHTML = "";
  const rank = el("p", { class: "rank-line" });
  rank.append(el("span", { class: "rank-badge" }, `#${c.state_rank}`));
  rank.append(document.createTextNode(
    ` most dangerous state for people walking — ${c.report} (${c.publisher}). ` +
    `${c.state_annual_deaths_per_100k} deaths per 100k residents/yr, ${c.coverage_period}.`
  ));
  p.append(rank);
  p.append(el("p", {}, c.state_rank_note));
  p.append(el("p", {}, c.framing));
  if (c.metros?.length) {
    const wrap = el("div", { class: "metros" });
    for (const m of c.metros) wrap.append(el("span", { class: "metro-chip" }, `${m.name} · #${m.national_rank} nationally`));
    p.append(wrap);
  }
}

/* ---------- KPI tiles ---------- */
function renderKPIs() {
  const yrs = DATA.years;
  const last = yrs[yrs.length - 1];
  const lastVal = DATA.state_totals_by_year[String(last)];
  const first = yrs[0];
  const firstVal = DATA.state_totals_by_year[String(first)];
  const changePct = firstVal ? Math.round(((lastVal - firstVal) / firstVal) * 100) : null;

  const tiles = [
    { val: fmt(DATA.state_total), label: `Pedestrian fatalities, ${first}–${last}`, danger: true },
    { val: fmt(lastVal), label: `In ${last} (most recent year)` },
    { val: DATA.context ? `#${DATA.context.state_rank}` : "—", label: "State danger rank (Dangerous by Design)", danger: true },
    { val: changePct == null ? "—" : (changePct >= 0 ? "+" : "") + changePct + "%", label: `Change ${first} → ${last}` },
  ];
  const row = document.getElementById("kpi-row");
  row.innerHTML = "";
  for (const t of tiles) {
    const k = el("div", { class: "kpi" });
    k.append(el("div", { class: "val" + (t.danger ? " danger" : "") }, t.val));
    k.append(el("div", { class: "label" }, t.label));
    row.append(k);
  }
}

/* ---------- Trend line chart ---------- */
function renderTrend() {
  const yrs = DATA.years;
  const vals = yrs.map((y) => DATA.state_totals_by_year[String(y)]);
  const W = 720, H = 260, m = { t: 16, r: 16, b: 34, l: 40 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const maxV = Math.max(...vals) * 1.12;
  const x = (i) => m.l + (yrs.length === 1 ? iw / 2 : (i / (yrs.length - 1)) * iw);
  const y = (v) => m.t + ih - (v / maxV) * ih;

  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Statewide pedestrian fatalities by year" });

  // y gridlines
  const ticks = 4;
  for (let i = 0; i <= ticks; i++) {
    const v = (maxV / ticks) * i;
    const yy = y(v);
    s.append(svg("line", { x1: m.l, x2: W - m.r, y1: yy, y2: yy, class: "grid-line" }));
    const lbl = svg("text", { x: m.l - 8, y: yy + 4, "text-anchor": "end", class: "axis-label" });
    lbl.textContent = Math.round(v);
    s.append(lbl);
  }
  // x labels
  yrs.forEach((yr, i) => {
    const t = svg("text", { x: x(i), y: H - 12, "text-anchor": "middle", class: "axis-label" });
    t.textContent = yr;
    s.append(t);
  });
  // area + line
  const linePts = vals.map((v, i) => `${x(i)},${y(v)}`).join(" ");
  const areaPts = `${x(0)},${y(0)} ${linePts} ${x(vals.length - 1)},${y(0)}`;
  s.append(svg("polygon", { points: areaPts, fill: cssVar("--accent"), "fill-opacity": "0.10" }));
  s.append(svg("polyline", { points: linePts, fill: "none", stroke: cssVar("--accent"), "stroke-width": "2.5", "stroke-linejoin": "round" }));
  // dots + values
  vals.forEach((v, i) => {
    s.append(svg("circle", { cx: x(i), cy: y(v), r: "3.5", fill: cssVar("--accent") }));
    const t = svg("text", { x: x(i), y: y(v) - 9, "text-anchor": "middle", class: "axis-label", fill: cssVar("--ink") });
    t.textContent = v;
    s.append(t);
  });
  document.getElementById("trend-chart").replaceChildren(s);

  const avg = Math.round(DATA.state_total / yrs.length);
  document.getElementById("trend-sub").textContent =
    `Averaging ~${avg} pedestrian deaths per year statewide. Single-year counts are noisy; the multi-year level is the signal.`;
}

/* ---------- Metric definitions ---------- */
function metrics() {
  const base = [
    { key: "ped_total", label: "Total pedestrian fatalities", fmt: fmt, get: (c) => c.ped_total, worseHigh: true },
    { key: "avg_annual_ped", label: "Avg pedestrian fatalities / yr", fmt: fmt1, get: (c) => c.avg_annual_ped, worseHigh: true },
  ];
  if (DATA.population_available) {
    base.push({
      key: "ped_per_100k_pop",
      label: "Deaths per 100k residents (total)",
      fmt: fmt1, get: (c) => c.ped_per_100k_pop, worseHigh: true,
    });
  }
  if (DATA.acs_available) {
    base.push(
      { key: "ped_rate_per_100k_annual", label: "Fatality rate per 100k / yr", fmt: fmt1, get: (c) => c.ped_rate_per_100k_annual, worseHigh: true },
      { key: "median_household_income", label: "Median household income", fmt: money, get: (c) => c.median_household_income, worseHigh: false },
      { key: "pct_black", label: "% Black or African American", fmt: pct, get: (c) => c.pct_black, worseHigh: true },
      { key: "pct_hispanic", label: "% Hispanic or Latino", fmt: pct, get: (c) => c.pct_hispanic, worseHigh: true },
    );
  }
  return base;
}
let CURRENT_METRIC = null;

function buildMetricSelect() {
  const sel = document.getElementById("metric-select");
  sel.innerHTML = "";
  for (const m of metrics()) sel.append(el("option", { value: m.key }, m.label));
  CURRENT_METRIC = metrics()[0].key;
  sel.value = CURRENT_METRIC;
  sel.onchange = () => { CURRENT_METRIC = sel.value; renderChoropleth(); };
}

/* ---------- Choropleth ---------- */
function colorRamp() {
  return ["--seq-0", "--seq-1", "--seq-2", "--seq-3", "--seq-4"].map(cssVar);
}
function quantileThresholds(values, bins) {
  const v = values.filter((x) => x != null).slice().sort((a, b) => a - b);
  if (!v.length) return [];
  const th = [];
  for (let i = 1; i < bins; i++) th.push(v[Math.floor((i / bins) * v.length)]);
  return th;
}
function binIndex(val, thresholds) {
  if (val == null) return -1;
  let i = 0;
  while (i < thresholds.length && val >= thresholds[i]) i++;
  return i;
}

function projectAll() {
  // Compute bounds across all SC county coords, return projector.
  let minLon = Infinity, maxLon = -Infinity, minLat = Infinity, maxLat = -Infinity;
  const eachCoord = (geom, fn) => {
    const polys = geom.type === "Polygon" ? [geom.coordinates] : geom.coordinates;
    for (const poly of polys) for (const ring of poly) for (const [lon, lat] of ring) fn(lon, lat);
  };
  for (const f of GEO.features) eachCoord(f.geometry, (lon, lat) => {
    if (lon < minLon) minLon = lon; if (lon > maxLon) maxLon = lon;
    if (lat < minLat) minLat = lat; if (lat > maxLat) maxLat = lat;
  });
  const W = 640, H = 440, pad = 12;
  const midLat = (minLat + maxLat) / 2;
  const kx = Math.cos((midLat * Math.PI) / 180); // shrink lon near mid-latitude
  const gw = (maxLon - minLon) * kx, gh = maxLat - minLat;
  const scale = Math.min((W - 2 * pad) / gw, (H - 2 * pad) / gh);
  const offX = (W - gw * scale) / 2, offY = (H - gh * scale) / 2;
  const project = (lon, lat) => [
    offX + (lon - minLon) * kx * scale,
    offY + (maxLat - lat) * scale, // flip y
  ];
  return { W, H, project, eachCoord };
}

function pathFor(geom, project) {
  const polys = geom.type === "Polygon" ? [geom.coordinates] : geom.coordinates;
  let d = "";
  for (const poly of polys) for (const ring of poly) {
    ring.forEach(([lon, lat], i) => {
      const [px, py] = project(lon, lat);
      d += (i === 0 ? "M" : "L") + px.toFixed(1) + " " + py.toFixed(1);
    });
    d += "Z";
  }
  return d;
}

function renderChoropleth() {
  const host = document.getElementById("choropleth");
  if (!GEO) { host.innerHTML = '<p class="panel-sub">County map unavailable — run <code>fetch_geojson.py</code>.</p>'; return; }
  const metric = metrics().find((m) => m.key === CURRENT_METRIC);
  const byFips = Object.fromEntries(DATA.counties.map((c) => [c.county_fips, c]));
  const values = DATA.counties.map((c) => metric.get(c));
  const thresholds = quantileThresholds(values, 5);
  const ramp = colorRamp();

  const { W, H, project } = projectAll();
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "South Carolina counties choropleth" });

  for (const f of GEO.features) {
    const fips = String(f.id);
    const c = byFips[fips];
    const val = c ? metric.get(c) : null;
    const bi = binIndex(val, thresholds);
    const fill = bi < 0 ? cssVar("--seq-0") : ramp[bi];
    const p = svg("path", { d: pathFor(f.geometry, project), fill, class: "county-shape" + (fips === SELECTED ? " sel" : "") });
    p.dataset.fips = fips;
    const name = c ? c.name : f.properties?.NAME || fips;
    p.addEventListener("mousemove", (ev) => showTip(ev, `<b>${name}</b><br>${metric.label}: ${metric.fmt(val)}<br>Total deaths: ${fmt(c?.ped_total)}`));
    p.addEventListener("mouseleave", hideTip);
    p.addEventListener("click", () => selectCounty(fips));
    s.append(p);
  }
  host.replaceChildren(s);
  renderLegend(metric, thresholds, ramp);
}

function renderLegend(metric, thresholds, ramp) {
  const host = document.getElementById("map-legend");
  host.innerHTML = "";
  host.append(el("h4", {}, "Lower → higher"));
  const labels = [];
  const round = metric.key === "median_household_income" ? (x) => "$" + Math.round(x / 1000) + "k" : (x) => fmt1(x);
  for (let i = 0; i < ramp.length; i++) {
    let text;
    if (i === 0) text = `< ${round(thresholds[0])}`;
    else if (i === ramp.length - 1) text = `≥ ${round(thresholds[thresholds.length - 1])}`;
    else text = `${round(thresholds[i - 1])} – ${round(thresholds[i])}`;
    labels.push(text);
    const row = el("div", { class: "row" });
    row.append(el("span", { class: "swatch", style: `background:${ramp[i]}` }));
    row.append(document.createTextNode(text));
    host.append(row);
  }
  document.getElementById("map-note").textContent =
    metric.worseHigh
      ? `Darker = higher ${metric.label.toLowerCase()}.`
      : `Darker = higher ${metric.label.toLowerCase()} (context, not a risk measure).`;
}

/* ---------- Equity overlay ---------- */
function renderEquity() {
  const body = document.getElementById("equity-body");
  const sub = document.getElementById("equity-sub");
  if (!DATA.acs_available) {
    sub.textContent = "Not yet populated.";
    body.innerHTML =
      '<div class="notice">The equity overlay compares each county\'s pedestrian-fatality rate against ' +
      'income and race/ethnicity from the Census ACS. To enable it:<br>' +
      '1. Get a free Census API key at <a href="https://api.census.gov/data/key_signup.html" target="_blank" rel="noopener">api.census.gov/data/key_signup.html</a><br>' +
      '2. <code>export CENSUS_API_KEY=your_key</code><br>' +
      '3. <code>python fetch_census_acs.py &amp;&amp; python build_dashboard_data.py</code>, then reload.</div>';
    return;
  }

  const rows = DATA.counties.filter((c) => c.ped_rate_per_100k_annual != null && c.median_household_income != null);
  sub.textContent = `Pedestrian-fatality rate vs. county median household income (dot size ∝ population). ${rows.length} counties with complete ACS data.`;

  // Income terciles → mean rate, to surface a disparity in plain numbers.
  const byInc = rows.slice().sort((a, b) => a.median_household_income - b.median_household_income);
  const t = Math.floor(byInc.length / 3) || 1;
  const meanRate = (arr) => arr.reduce((s, c) => s + c.ped_rate_per_100k_annual, 0) / arr.length;
  const lowInc = byInc.slice(0, t), highInc = byInc.slice(-t);
  const lowMean = meanRate(lowInc), highMean = meanRate(highInc);

  body.innerHTML = "";
  const insight = el("p", { class: "panel-sub" });
  const ratio = highMean ? (lowMean / highMean).toFixed(1) : "—";
  insight.innerHTML =
    `The lowest-income third of SC counties averages <b>${fmt1(lowMean)}</b> pedestrian deaths per 100k/yr, ` +
    `versus <b>${fmt1(highMean)}</b> in the highest-income third` +
    (highMean ? ` — about <b>${ratio}×</b> higher.` : ".");
  body.append(insight);
  body.append(scatterChart(rows));
}

function scatterChart(rows) {
  const W = 720, H = 320, m = { t: 14, r: 16, b: 42, l: 52 };
  const iw = W - m.l - m.r, ih = H - m.t - m.b;
  const xs = rows.map((c) => c.median_household_income);
  const ys = rows.map((c) => c.ped_rate_per_100k_annual);
  const pops = rows.map((c) => c.population || 0);
  const xMin = Math.min(...xs) * 0.95, xMax = Math.max(...xs) * 1.02;
  const yMax = Math.max(...ys) * 1.12;
  const pMax = Math.max(...pops) || 1;
  const X = (v) => m.l + ((v - xMin) / (xMax - xMin)) * iw;
  const Y = (v) => m.t + ih - (v / yMax) * ih;
  const R = (p) => 3 + Math.sqrt(p / pMax) * 12;

  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Income vs pedestrian fatality rate" });
  // gridlines + y ticks
  for (let i = 0; i <= 4; i++) {
    const v = (yMax / 4) * i, yy = Y(v);
    s.append(svg("line", { x1: m.l, x2: W - m.r, y1: yy, y2: yy, class: "grid-line" }));
    const tl = svg("text", { x: m.l - 8, y: yy + 4, "text-anchor": "end", class: "axis-label" });
    tl.textContent = fmt1(v); s.append(tl);
  }
  // x ticks
  for (let i = 0; i <= 4; i++) {
    const v = xMin + ((xMax - xMin) / 4) * i, xx = X(v);
    const tl = svg("text", { x: xx, y: H - 24, "text-anchor": "middle", class: "axis-label" });
    tl.textContent = "$" + Math.round(v / 1000) + "k"; s.append(tl);
  }
  // axis labels
  const xlab = svg("text", { x: m.l + iw / 2, y: H - 6, "text-anchor": "middle", class: "axis-label" });
  xlab.textContent = "Median household income"; s.append(xlab);
  const ylab = svg("text", { x: 14, y: m.t + ih / 2, "text-anchor": "middle", class: "axis-label", transform: `rotate(-90 14 ${m.t + ih / 2})` });
  ylab.textContent = "Fatalities / 100k / yr"; s.append(ylab);

  for (const c of rows) {
    const dot = svg("circle", { cx: X(c.median_household_income), cy: Y(c.ped_rate_per_100k_annual), r: R(c.population || 0), fill: cssVar("--accent"), "fill-opacity": "0.5", stroke: cssVar("--accent"), class: "dot" });
    dot.addEventListener("mousemove", (ev) => showTip(ev, `<b>${c.name}</b><br>Income: ${money(c.median_household_income)}<br>Rate: ${fmt1(c.ped_rate_per_100k_annual)}/100k/yr<br>Pop: ${fmt(c.population)}`));
    dot.addEventListener("mouseleave", hideTip);
    dot.addEventListener("click", () => selectCounty(c.county_fips));
    s.append(dot);
  }
  const box = el("div", { class: "chart" });
  box.append(s);
  return box;
}

/* ---------- County table ---------- */
let sortKey = "ped_total", sortAsc = false;
function renderTable() {
  const table = document.getElementById("county-table");
  const cols = [
    { key: "name", label: "County", get: (c) => c.name, fmt: (v) => v, align: "left" },
    { key: "ped_total", label: "Total deaths", get: (c) => c.ped_total, fmt: fmt, bar: true },
    { key: "avg_annual_ped", label: "Avg / yr", get: (c) => c.avg_annual_ped, fmt: fmt1 },
  ];
  if (DATA.population_available) {
    cols.push({ key: "ped_per_100k_pop", label: "Per 100k pop", get: (c) => c.ped_per_100k_pop, fmt: fmt1 });
  }
  if (DATA.acs_available) {
    cols.push(
      { key: "ped_rate_per_100k_annual", label: "Rate /100k/yr", get: (c) => c.ped_rate_per_100k_annual, fmt: fmt1 },
      { key: "median_household_income", label: "Median income", get: (c) => c.median_household_income, fmt: money },
      { key: "pct_black", label: "% Black", get: (c) => c.pct_black, fmt: pct },
      { key: "pct_hispanic", label: "% Hispanic", get: (c) => c.pct_hispanic, fmt: pct },
    );
  }

  const thead = el("thead");
  const trh = el("tr");
  for (const col of cols) {
    const th = el("th", {}, col.label);
    if (col.key === sortKey) th.classList.add("sorted", sortAsc ? "asc" : "desc");
    th.onclick = () => {
      if (sortKey === col.key) sortAsc = !sortAsc;
      else { sortKey = col.key; sortAsc = col.key === "name"; }
      renderTable();
    };
    trh.append(th);
  }
  thead.append(trh);

  const rows = DATA.counties.slice().sort((a, b) => {
    const av = colGet(cols, sortKey)(a), bv = colGet(cols, sortKey)(b);
    if (av == null) return 1; if (bv == null) return -1;
    if (typeof av === "string") return sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
    return sortAsc ? av - bv : bv - av;
  });
  const maxTotal = Math.max(...DATA.counties.map((c) => c.ped_total));

  const tbody = el("tbody");
  for (const c of rows) {
    const tr = el("tr");
    tr.dataset.fips = c.county_fips;
    if (c.county_fips === SELECTED) tr.classList.add("sel");
    tr.onclick = () => selectCounty(c.county_fips);
    for (const col of cols) {
      const v = col.get(c);
      const td = el("td");
      if (col.align === "left") td.style.textAlign = "left";
      if (v == null) { td.className = "na"; td.textContent = "—"; }
      else if (col.bar) {
        td.className = "bar-cell";
        const bar = el("span", { class: "bar", style: `width:${(v / maxTotal) * 100}%` });
        td.append(bar, el("span", {}, col.fmt(v)));
      } else td.textContent = col.fmt(v);
      tr.append(td);
    }
    tbody.append(tr);
  }
  table.replaceChildren(thead, tbody);
}
function colGet(cols, key) {
  const c = cols.find((x) => x.key === key);
  return c ? c.get : () => null;
}

/* ---------- Selection sync ---------- */
function selectCounty(fips) {
  SELECTED = SELECTED === fips ? null : fips;
  document.querySelectorAll(".county-shape").forEach((p) => p.classList.toggle("sel", p.dataset.fips === SELECTED));
  document.querySelectorAll("#county-table tbody tr").forEach((tr) => tr.classList.toggle("sel", tr.dataset.fips === SELECTED));
  const row = document.querySelector(`#county-table tbody tr[data-fips="${SELECTED}"]`);
  if (row) row.scrollIntoView({ block: "nearest" });
}

/* ---------- Tooltip ---------- */
const tip = document.getElementById("tooltip");
function showTip(ev, html) {
  tip.innerHTML = html;
  tip.hidden = false;
  const pad = 14;
  let x = ev.clientX + pad, y = ev.clientY + pad;
  const r = tip.getBoundingClientRect();
  if (x + r.width > window.innerWidth) x = ev.clientX - r.width - pad;
  if (y + r.height > window.innerHeight) y = ev.clientY - r.height - pad;
  tip.style.left = x + "px";
  tip.style.top = y + "px";
}
function hideTip() { tip.hidden = true; }

/* ---------- Footer ---------- */
function renderFooter() {
  const f = document.getElementById("footer-sources");
  const parts = [`Data: NHTSA FARS ${DATA.years[0]}–${DATA.years[DATA.years.length - 1]}`];
  if (DATA.acs_available) parts.push(`Census ACS ${DATA.acs_vintage} 5-year`);
  f.innerHTML = parts.join(" · ");
  if (DATA.context?.sources?.length) {
    f.append(document.createTextNode(" · Context: "));
    DATA.context.sources.forEach((s, i) => {
      if (i) f.append(document.createTextNode(", "));
      f.append(el("a", { href: s.url, target: "_blank", rel: "noopener" }, s.title));
    });
  }
}
