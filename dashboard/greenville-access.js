/* Greenville County FQHC access — Tier 2 rollup view.
   Renders the modeled tract-level access dataset over tract boundaries. Vanilla JS. */

const SVGNS = "http://www.w3.org/2000/svg";
const fmt1 = (n) => (n == null ? "—" : Number(n).toLocaleString(undefined, { maximumFractionDigits: 1 }));

function el(tag, attrs = {}, text) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) (k === "class") ? (e.className = v) : e.setAttribute(k, v);
  if (text != null) e.textContent = text;
  return e;
}
function svg(tag, attrs = {}) {
  const e = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
}
const cssVar = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

let ROLLUP = null, GEO = null, CURRENT = null, SELECTED = null;

init();

async function init() {
  try {
    ROLLUP = await (await fetch("data/access_rollup_45045.json")).json();
    GEO = await (await fetch("data/tracts_45045.geojson")).json();
  } catch (e) {
    document.getElementById("subtitle").textContent =
      "Could not load the access rollup — run fetch_tract_geojson.py and build_access_rollup.py.";
    return;
  }
  const s = ROLLUP.summary;
  document.getElementById("subtitle").textContent =
    `Modeled travel time from ${s.n_tracts} tracts to the nearest of ${ROLLUP.tracts.length && "7"} FQHCs, ` +
    `by walk and Greenlink transit.`;
  document.getElementById("main").hidden = false;
  renderMethod();
  renderKPIs();
  buildMetricSelect();
  renderChoropleth();
  renderEquity();
  renderPrivacy();
  renderFooter();
}

function renderMethod() {
  const p = document.getElementById("method-panel");
  p.innerHTML =
    `<p style="margin:0 0 6px"><b>What this shows.</b> For each census tract, we compute how long it
     takes to reach the nearest Federally Qualified Health Center from a representative point in the
     tract — walking, and by Greenlink transit (allowing up to one transfer). FQHCs are the pilot
     category (spec §10); the same rollup extends to other categories as they're added.</p>
     <p class="panel-sub" style="margin:0">${escapeHtml(ROLLUP.model_notes)}</p>`;
}

function renderKPIs() {
  const s = ROLLUP.summary;
  const tiles = [
    { val: fmt1(s.walk_min_median) + " min", label: "Median walk to nearest FQHC", danger: s.walk_min_median > 30 },
    { val: s.pct_tracts_transit_reachable + "%", label: "Tracts transit-reachable (≤1 transfer)", danger: s.pct_tracts_transit_reachable < 60 },
    { val: String(s.n_tracts_no_transit), label: "Tracts with no ≤1-transfer FQHC trip", danger: true },
    { val: s.transit_min_median == null ? "—" : fmt1(s.transit_min_median) + " min", label: "Median transit time (reachable tracts)" },
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

function metrics() {
  const m = [
    { key: "walk_min", label: "Walk time to nearest FQHC", fmt: (v) => v == null ? "—" : fmt1(v) + " min", get: (t) => t.walk_min, worseHigh: true },
    { key: "transit", label: "Transit reachability", fmt: (v) => v == null ? "no ≤1-transfer trip" : fmt1(v) + " min", get: (t) => (t.transit_reachable ? t.transit_min : null), worseHigh: true, categorical: true },
  ];
  if (ROLLUP.acs_income_joined) {
    m.push({ key: "median_household_income", label: "Median household income", fmt: (v) => v == null ? "—" : "$" + Math.round(v).toLocaleString(), get: (t) => t.median_household_income, worseHigh: false });
  }
  return m;
}

function buildMetricSelect() {
  const sel = document.getElementById("metric-select");
  sel.innerHTML = "";
  for (const m of metrics()) sel.append(el("option", { value: m.key }, m.label));
  CURRENT = metrics()[0].key;
  sel.value = CURRENT;
  sel.onchange = () => { CURRENT = sel.value; renderChoropleth(); };
}

/* ---- choropleth (shared projection approach with the main dashboard) ---- */
function projectAll() {
  let minLon = Infinity, maxLon = -Infinity, minLat = Infinity, maxLat = -Infinity;
  const each = (geom, fn) => {
    const polys = geom.type === "Polygon" ? [geom.coordinates] : geom.coordinates;
    for (const poly of polys) for (const ring of poly) for (const [lo, la] of ring) fn(lo, la);
  };
  for (const f of GEO.features) each(f.geometry, (lo, la) => {
    if (lo < minLon) minLon = lo; if (lo > maxLon) maxLon = lo;
    if (la < minLat) minLat = la; if (la > maxLat) maxLat = la;
  });
  const W = 640, H = 470, pad = 12;
  const midLat = (minLat + maxLat) / 2, kx = Math.cos(midLat * Math.PI / 180);
  const gw = (maxLon - minLon) * kx, gh = maxLat - minLat;
  const scale = Math.min((W - 2 * pad) / gw, (H - 2 * pad) / gh);
  const offX = (W - gw * scale) / 2, offY = (H - gh * scale) / 2;
  return { W, H, project: (lo, la) => [offX + (lo - minLon) * kx * scale, offY + (maxLat - la) * scale] };
}
function pathFor(geom, project) {
  const polys = geom.type === "Polygon" ? [geom.coordinates] : geom.coordinates;
  let d = "";
  for (const poly of polys) for (const ring of poly) {
    ring.forEach(([lo, la], i) => { const [x, y] = project(lo, la); d += (i ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1); });
    d += "Z";
  }
  return d;
}
function ramp() { return ["--seq-0", "--seq-1", "--seq-2", "--seq-3", "--seq-4"].map(cssVar); }
function thresholds(vals, bins) {
  const v = vals.filter((x) => x != null).slice().sort((a, b) => a - b);
  const th = [];
  for (let i = 1; i < bins; i++) th.push(v[Math.floor((i / bins) * v.length)]);
  return th;
}
function bin(val, th) { if (val == null) return -1; let i = 0; while (i < th.length && val >= th[i]) i++; return i; }

function renderChoropleth() {
  const metric = metrics().find((m) => m.key === CURRENT);
  const byTract = Object.fromEntries(ROLLUP.tracts.map((t) => [t.tract_fips, t]));
  const vals = ROLLUP.tracts.map((t) => metric.get(t));
  const th = thresholds(vals, 5), rmp = ramp();
  const { W, H, project } = projectAll();
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Greenville tracts access choropleth" });

  for (const f of GEO.features) {
    const geoid = String(f.properties.GEOID);
    const t = byTract[geoid];
    const val = t ? metric.get(t) : null;
    const isUnreachable = metric.key === "transit" && t && !t.transit_reachable;
    const fill = val == null ? (isUnreachable ? cssVar("--seq-0") : cssVar("--seq-0")) : rmp[bin(val, th)];
    const path = svg("path", { d: pathFor(f.geometry, project), fill, class: "county-shape" + (geoid === SELECTED ? " sel" : "") });
    path.dataset.fips = geoid;
    const label = t ? metric.fmt(val) : "no data";
    const walkTxt = t ? `Walk ${fmt1(t.walk_min)} min` : "";
    const transitTxt = t ? (t.transit_reachable ? `Transit ${fmt1(t.transit_min)} min` : "No ≤1-transfer transit") : "";
    path.addEventListener("mousemove", (ev) => showTip(ev, `<b>Tract ${escapeHtml(t ? t.name : geoid)}</b><br>${escapeHtml(metric.label)}: ${label}<br>${walkTxt}<br>${transitTxt}`));
    path.addEventListener("mouseleave", hideTip);
    path.addEventListener("click", () => { SELECTED = SELECTED === geoid ? null : geoid; renderChoropleth(); });
    s.append(path);
  }
  document.getElementById("choropleth").replaceChildren(s);
  renderLegend(metric, th, rmp);
}

function renderLegend(metric, th, rmp) {
  const host = document.getElementById("map-legend");
  host.innerHTML = "";
  host.append(el("h4", {}, metric.key === "median_household_income" ? "Lower → higher" : "Faster → slower"));
  const round = metric.key === "median_household_income" ? (x) => "$" + Math.round(x / 1000) + "k" : (x) => fmt1(x) + "m";
  for (let i = 0; i < rmp.length; i++) {
    let text;
    if (i === 0) text = `< ${round(th[0])}`;
    else if (i === rmp.length - 1) text = `≥ ${round(th[th.length - 1])}`;
    else text = `${round(th[i - 1])} – ${round(th[i])}`;
    const row = el("div", { class: "row" });
    row.append(el("span", { class: "swatch", style: `background:${rmp[i]}` }));
    row.append(document.createTextNode(text));
    host.append(row);
  }
  if (metric.key === "transit") {
    const row = el("div", { class: "row" });
    row.append(el("span", { class: "swatch", style: `background:${cssVar("--seq-0")}` }));
    row.append(document.createTextNode("no ≤1-transfer trip"));
    host.append(row);
  }
  document.getElementById("map-note").textContent =
    metric.key === "transit"
      ? "Greyed tracts have no FQHC reachable within one Greenlink transfer (weekday midday)."
      : `Darker = ${metric.worseHigh ? "longer" : "higher"} ${metric.label.toLowerCase()}.`;
}

/* ---- equity ---- */
function renderEquity() {
  const sub = document.getElementById("equity-sub");
  const body = document.getElementById("equity-body");
  if (!ROLLUP.acs_income_joined) {
    sub.textContent = "Income overlay not yet populated.";
    body.innerHTML =
      '<div class="notice">Once tract-level Census ACS is pulled, this panel compares FQHC access ' +
      'against neighborhood income — the core equity question. To enable it:<br>' +
      '1. Get a free Census API key at <a href="https://api.census.gov/data/key_signup.html" target="_blank" rel="noopener">api.census.gov/data/key_signup.html</a><br>' +
      '2. <code>export CENSUS_API_KEY=your_key</code><br>' +
      '3. <code>python fetch_census_acs.py --tracts 45045 &amp;&amp; python build_access_rollup.py</code>, then reload.</div>';
    return;
  }
  const rows = ROLLUP.tracts.filter((t) => t.median_household_income != null && t.walk_min != null);
  const byInc = rows.slice().sort((a, b) => a.median_household_income - b.median_household_income);
  const k = Math.floor(byInc.length / 3) || 1;
  const meanWalk = (arr) => arr.reduce((s, t) => s + t.walk_min, 0) / arr.length;
  const low = byInc.slice(0, k), high = byInc.slice(-k);
  sub.textContent = `${rows.length} tracts with income + access data.`;
  body.innerHTML =
    `<p class="panel-sub">Lowest-income third of tracts: <b>${fmt1(meanWalk(low))} min</b> mean walk to an FQHC; ` +
    `highest-income third: <b>${fmt1(meanWalk(high))} min</b>.</p>`;
}

function renderPrivacy() {
  const p = document.getElementById("privacy-panel");
  p.innerHTML =
    `<div class="panel-head"><h2>Privacy — how a real usage rollup would work</h2></div>
     <p style="margin:0 0 8px">This page is a <b>modeled</b> surface, so it contains no personal data.
     When the lookup tool is used by real people, results are de-identified (address, coordinates, and
     chosen facility are dropped — only the tract and travel times remain) and rolled up to tract level
     with a <b>k-anonymity threshold of ${ROLLUP && 25}</b>: any tract with fewer than that many lookups
     is suppressed entirely, failing closed. That machinery lives in <code>engine/aggregate.py</code>.</p>
     <p class="panel-sub" style="margin:0">See <a href="../docs/privacy-design.md">docs/privacy-design.md</a>.</p>`;
}

function renderFooter() {
  document.getElementById("footer-sources").innerHTML =
    "Access: engine (Census Geocoder + Greenlink GTFS + HRSA FQHCs) · Tract boundaries: Census TIGERweb";
}

/* ---- tooltip ---- */
const tip = document.getElementById("tooltip");
function showTip(ev, html) {
  tip.innerHTML = html; tip.hidden = false;
  const pad = 14; let x = ev.clientX + pad, y = ev.clientY + pad;
  const r = tip.getBoundingClientRect();
  if (x + r.width > innerWidth) x = ev.clientX - r.width - pad;
  if (y + r.height > innerHeight) y = ev.clientY - r.height - pad;
  tip.style.left = x + "px"; tip.style.top = y + "px";
}
function hideTip() { tip.hidden = true; }
function escapeHtml(s) { return String(s ?? "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }
