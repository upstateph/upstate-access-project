/* Greenville County FQHC access — Tier 2 rollup view.
   Renders modeled access (walk / drive / transit) over census tracts OR ZIP codes.
   Vanilla JS, no dependencies. */

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

let ROLLUP = null, GEO = null, GEOGRAPHY = "tract", CURRENT = null, SELECTED = null;

const FILES = {
  tract: { rollup: "data/access_rollup_tract_45045.json", geojson: "data/tracts_45045.geojson" },
  zcta: { rollup: "data/access_rollup_zcta_45045.json", geojson: "data/zcta_45045.geojson" },
};

init();

async function init() {
  document.getElementById("geo-select").addEventListener("change", (e) => {
    GEOGRAPHY = e.target.value; SELECTED = null; loadGeography();
  });
  await loadGeography();
}

async function loadGeography() {
  const f = FILES[GEOGRAPHY];
  try {
    ROLLUP = await (await fetch(f.rollup)).json();
    GEO = await (await fetch(f.geojson)).json();
  } catch (e) {
    document.getElementById("subtitle").textContent =
      `Could not load the ${GEOGRAPHY} rollup — run fetch_${GEOGRAPHY === "tract" ? "tract" : "zcta"}_geojson.py and build_access_rollup.py.`;
    return;
  }
  const unit = ROLLUP.unit_label;
  document.getElementById("subtitle").textContent =
    `Modeled travel time from ${ROLLUP.summary.n_units} ${unit}s to the nearest FQHC, by walk, drive, and Greenlink transit.`;
  document.getElementById("map-title").textContent = `Access by ${unit === "ZIP" ? "ZIP code" : "census tract"}`;
  document.getElementById("main").hidden = false;
  renderMethod();
  renderKPIs();
  buildMetricSelect();
  renderChoropleth();
  renderServiceSpan();
  renderCrashCorridors();
  renderEquity();
  renderPrivacy();
  renderFooter();
}

/* ---- service span (time-of-day) ---- */
let SPAN = null, SPAN_LOADED = false;
async function renderServiceSpan() {
  const panel = document.getElementById("service-span-panel");
  if (!SPAN_LOADED) {
    SPAN_LOADED = true;
    try { SPAN = await (await fetch("data/service_span_tract_45045.json")).json(); }
    catch (e) { SPAN = null; }
  }
  if (!SPAN) { panel.hidden = true; return; }
  panel.hidden = false;

  const base = SPAN.summary[SPAN.baseline_window];
  document.getElementById("service-span-sub").textContent =
    `Modeled ≤1-transfer Greenlink trip to the nearest FQHC from each census tract, at four departure windows.`;

  const rows = SPAN.windows.map((w) => {
    const s = SPAN.summary[w.key];
    const isBase = w.key === SPAN.baseline_window;
    return `<tr${isBase ? ' class="base"' : ""}>
      <td>${escapeHtml(s.label)}${isBase ? " (baseline)" : ""}</td>
      <td>${fmt1(s.pct_reachable)}%</td>
      <td>${s.transit_min_median == null ? "—" : fmt1(s.transit_min_median) + " min"}</td>
      <td>${isBase ? "—" : s.n_lost_vs_midday}</td>
    </tr>`;
  }).join("");

  const worst = SPAN.windows
    .map((w) => SPAN.summary[w.key])
    .filter((s) => s.transit_min_median != null)
    .sort((a, b) => b.transit_min_median - a.transit_min_median)[0];
  const delta = worst && base.transit_min_median != null
    ? Math.round(worst.transit_min_median - base.transit_min_median) : null;

  document.getElementById("service-span-body").innerHTML =
    `<div style="overflow-x:auto"><table class="span-table">
       <thead><tr><th>Departure window</th><th>Tracts reachable</th><th>Median trip</th><th>Tracts losing access vs midday</th></tr></thead>
       <tbody>${rows}</tbody>
     </table></div>
     <p class="panel-sub" style="margin-top:8px">${
       delta != null && delta > 0
         ? `Coverage barely moves by time of day — Greenlink's hub-and-spoke network runs all service hours — but trip times do: the median ${escapeHtml(worst.label)} trip is <b>${delta} minutes longer</b> than midday. The time-of-day penalty is a <b>frequency and timing</b> problem, not a coverage problem.`
         : "Reachability and trip times are similar across the modeled windows."
     }</p>
     <p class="panel-sub">${escapeHtml(SPAN.model_notes)}</p>`;
}

function renderMethod() {
  const unit = ROLLUP.unit_label;
  const p = document.getElementById("method-panel");
  p.innerHTML =
    `<p style="margin:0 0 6px"><b>What this shows.</b> For each ${unit}, we compute how long it takes to
     reach the nearest Federally Qualified Health Center from a representative point — walking, driving,
     and by Greenlink transit (allowing up to one transfer). FQHCs are the pilot category (spec §10);
     the same rollup extends to other categories as they're added.</p>
     <p class="panel-sub" style="margin:0">${escapeHtml(ROLLUP.model_notes)}</p>`;
}

function renderKPIs() {
  const s = ROLLUP.summary, unit = ROLLUP.unit_label;
  const tiles = [
    { val: fmt1(s.walk_min_median) + " min", label: `Median walk to nearest FQHC`, danger: s.walk_min_median > 30 },
    { val: fmt1(s.drive_min_median) + " min", label: `Median drive to nearest FQHC` },
    { val: s.pct_units_transit_reachable + "%", label: `${cap(unit)}s transit-reachable (≤1 transfer)`, danger: s.pct_units_transit_reachable < 60 },
    { val: String(s.n_units_no_transit), label: `${cap(unit)}s with no ≤1-transfer FQHC trip`, danger: true },
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
    { key: "drive_min", label: "Drive time to nearest FQHC", fmt: (v) => v == null ? "—" : fmt1(v) + " min", get: (t) => t.drive_min, worseHigh: true },
    { key: "transit", label: "Transit time (reachability)", fmt: (v) => v == null ? "no ≤1-transfer trip" : fmt1(v) + " min", get: (t) => (t.transit_reachable ? t.transit_min : null), worseHigh: true, categorical: true },
  ];
  if (ROLLUP.acs_income_joined) {
    m.push({ key: "median_household_income", label: "Median household income", fmt: (v) => v == null ? "—" : "$" + Math.round(v).toLocaleString(), get: (t) => t.median_household_income, worseHigh: false, legendHeader: "Lower → higher", legendRound: (x) => "$" + Math.round(x / 1000) + "k" });
  }
  if (ROLLUP.units.some((u) => u.pct_no_vehicle != null)) {
    m.push({ key: "pct_no_vehicle", label: "% households with no vehicle", fmt: (v) => v == null ? "—" : fmt1(v) + "%", get: (t) => t.pct_no_vehicle, worseHigh: true, legendHeader: "Fewer → more car-free", legendRound: (x) => fmt1(x) + "%" });
  }
  return m;
}

function buildMetricSelect() {
  const sel = document.getElementById("metric-select");
  const prev = CURRENT;
  sel.innerHTML = "";
  for (const m of metrics()) sel.append(el("option", { value: m.key }, m.label));
  CURRENT = metrics().some((m) => m.key === prev) ? prev : metrics()[0].key;
  sel.value = CURRENT;
  sel.onchange = () => { CURRENT = sel.value; renderChoropleth(); };
}

/* ---- choropleth ---- */
function unitsById() { return Object.fromEntries(ROLLUP.units.map((u) => [String(u.id), u])); }

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
  const metric = metrics().find((m) => m.key === CURRENT) || metrics()[0];
  const byId = unitsById();
  const th = thresholds(ROLLUP.units.map((u) => metric.get(u)), 5), rmp = ramp();
  const { W, H, project } = projectAll();
  const s = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Greenville access choropleth" });

  for (const f of GEO.features) {
    const gid = String(f.properties.GEOID);
    const u = byId[gid];
    const val = u ? metric.get(u) : null;
    const fill = val == null ? cssVar("--seq-0") : rmp[bin(val, th)];
    const path = svg("path", { d: pathFor(f.geometry, project), fill, class: "county-shape" + (gid === SELECTED ? " sel" : "") });
    path.dataset.fips = gid;
    const label = u ? metric.fmt(val) : "no data";
    const detail = u
      ? `Walk ${fmt1(u.walk_min)} min · Drive ${fmt1(u.drive_min)} min<br>${u.transit_reachable ? "Transit " + fmt1(u.transit_min) + " min" : "No ≤1-transfer transit"}`
      : "";
    path.addEventListener("mousemove", (ev) => showTip(ev, `<b>${escapeHtml(unitName(u, gid))}</b><br>${escapeHtml(metric.label)}: ${label}<br>${detail}`));
    path.addEventListener("mouseleave", hideTip);
    path.addEventListener("click", () => { SELECTED = SELECTED === gid ? null : gid; renderChoropleth(); });
    s.append(path);
  }
  document.getElementById("choropleth").replaceChildren(s);
  renderLegend(metric, th, rmp);
}

function unitName(u, gid) {
  const label = ROLLUP.unit_label;
  if (label === "ZIP") return "ZIP " + (u ? u.name : gid);
  return "Tract " + (u ? u.name : gid);
}

function renderLegend(metric, th, rmp) {
  const host = document.getElementById("map-legend");
  host.innerHTML = "";
  host.append(el("h4", {}, metric.legendHeader || "Faster → slower"));
  const round = metric.legendRound || ((x) => fmt1(x) + "m");
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
      ? "Greyed areas have no FQHC reachable within one Greenlink transfer (weekday midday)."
      : metric.key === "pct_no_vehicle"
      ? "Darker = larger share of households with no vehicle available (ACS B08201) — the population with no alternative to walking or transit."
      : `Darker = ${metric.worseHigh ? "longer" : "higher"} ${metric.label.toLowerCase().replace("fqhc", "FQHC")}.`;
}

/* ---- crash corridors ---- */
let CRASH = null, CRASH_GEO = null, CRASH_LOADED = false;
async function renderCrashCorridors() {
  const panel = document.getElementById("crash-panel");
  if (!CRASH_LOADED) {
    CRASH_LOADED = true;
    try {
      CRASH = await (await fetch("data/crash_corridors_45045.json")).json();
      CRASH_GEO = await (await fetch("data/tracts_45045.geojson")).json();
    } catch (e) { CRASH = null; }
  }
  if (!CRASH || !CRASH_GEO) { panel.hidden = true; return; }
  panel.hidden = false;

  const s = CRASH.summary;
  const yrs = CRASH.years || [];
  document.getElementById("crash-sub").textContent =
    `${s.total_deaths_located} pedestrian deaths (FARS, ${yrs[0]}–${yrs[yrs.length - 1]}) over the modeled walking routes from each tract to its nearest FQHC.`;

  // Projection over the tract bbox (same approach as the choropleth, but local
  // so this panel works regardless of the tract/ZIP toggle above).
  let minLon = Infinity, maxLon = -Infinity, minLat = Infinity, maxLat = -Infinity;
  const each = (geom, fn) => {
    const polys = geom.type === "Polygon" ? [geom.coordinates] : geom.coordinates;
    for (const poly of polys) for (const ring of poly) for (const [lo, la] of ring) fn(lo, la);
  };
  for (const f of CRASH_GEO.features) each(f.geometry, (lo, la) => {
    if (lo < minLon) minLon = lo; if (lo > maxLon) maxLon = lo;
    if (la < minLat) minLat = la; if (la > maxLat) maxLat = la;
  });
  const W = 640, H = 470, pad = 12;
  const midLat = (minLat + maxLat) / 2, kx = Math.cos(midLat * Math.PI / 180);
  const scale = Math.min((W - 2 * pad) / ((maxLon - minLon) * kx), (H - 2 * pad) / (maxLat - minLat));
  const offX = (W - (maxLon - minLon) * kx * scale) / 2, offY = (H - (maxLat - minLat) * scale) / 2;
  const project = (lo, la) => [offX + (lo - minLon) * kx * scale, offY + (maxLat - la) * scale];

  const svgEl = svg("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Crash corridors map" });

  // Tract outlines, unfilled — context only.
  for (const f of CRASH_GEO.features) {
    svgEl.append(svg("path", { d: pathFor(f.geometry, project), fill: "none",
                               stroke: cssVar("--line"), "stroke-width": "0.7" }));
  }
  // Corridors: routes with nearby deaths in danger red, the rest soft accent.
  for (const r of CRASH.corridors.slice().reverse()) {  // draw deadly ones last (on top)
    let d = "";
    r.geometry.forEach(([la, lo], i) => { const [x, y] = project(lo, la); d += (i ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1); });
    const hot = r.n_deaths_near > 0;
    const path = svg("path", { d, fill: "none",
      stroke: hot ? cssVar("--danger") : cssVar("--accent"),
      "stroke-width": hot ? "2.2" : "1", opacity: hot ? "0.9" : "0.35",
      "stroke-linecap": "round", "stroke-linejoin": "round" });
    path.addEventListener("mousemove", (ev) => showTip(ev,
      `<b>Tract ${escapeHtml(r.tract_name)} → ${escapeHtml(r.fqhc_name)}</b><br>` +
      `${fmt1(r.walk_minutes)} min walk` +
      (hot ? `<br>${r.n_deaths_near} pedestrian death${r.n_deaths_near === 1 ? "" : "s"} within ${Math.round(CRASH.proximity_m)} m` +
             (r.n_deaths_near_dark ? ` (${r.n_deaths_near_dark} in darkness)` : "") : "")));
    path.addEventListener("mouseleave", hideTip);
    svgEl.append(path);
  }
  // Crash points: filled = dark conditions, hollow = daylight/other.
  for (const p of CRASH.points) {
    const [x, y] = project(p.lon, p.lat);
    const c = svg("circle", { cx: x.toFixed(1), cy: y.toFixed(1), r: p.n_ped_deaths > 1 ? "4" : "2.8",
      fill: p.dark ? cssVar("--danger") : "none",
      stroke: cssVar("--danger"), "stroke-width": "1.2", opacity: "0.85" });
    c.addEventListener("mousemove", (ev) => showTip(ev,
      `<b>${p.year}</b> · ${p.n_ped_deaths} pedestrian death${p.n_ped_deaths === 1 ? "" : "s"}<br>${escapeHtml(p.light)}` +
      (p.hour != null ? ` · ~${String(p.hour).padStart(2, "0")}:00` : "")));
    c.addEventListener("mouseleave", hideTip);
    svgEl.append(c);
  }
  document.getElementById("crash-map").replaceChildren(svgEl);

  // Legend.
  const legend = document.getElementById("crash-legend");
  legend.innerHTML = "";
  legend.append(el("h4", {}, "Layers"));
  const lrow = (swatchStyle, label) => {
    const row = el("div", { class: "row" });
    row.append(el("span", { class: "swatch", style: swatchStyle }));
    row.append(document.createTextNode(label));
    legend.append(row);
  };
  lrow(`background:${cssVar("--danger")}`, "Death(s) in darkness");
  lrow(`background:transparent;border:1.5px solid ${cssVar("--danger")}`, "Death(s) in daylight / other");
  lrow(`background:${cssVar("--danger")};height:3px;align-self:center`, "Walk route with a death within 150 m");
  lrow(`background:${cssVar("--accent")};height:2px;opacity:.45;align-self:center`, "Other modeled walk route to an FQHC");

  // Summary + worst corridors.
  const hot = CRASH.corridors.filter((r) => r.n_deaths_near > 0);
  const topRows = hot.slice(0, 8).map((r) =>
    `<tr><td>Tract ${escapeHtml(r.tract_name)} → ${escapeHtml(r.fqhc_name)}</td>` +
    `<td>${fmt1(r.walk_minutes)} min</td><td>${r.n_deaths_near}</td><td>${r.n_deaths_near_dark}</td></tr>`).join("");
  document.getElementById("crash-body").innerHTML =
    `<p class="panel-sub" style="margin-top:10px"><b>${s.deaths_near_any_corridor} of ${s.total_deaths_located}</b> located pedestrian deaths
     (<b>${fmt1(s.pct_deaths_near_any_corridor)}%</b>) occurred within ${Math.round(CRASH.proximity_m)} m of a modeled walking route
     to a community health center — the corridors people must walk to reach care overlap the corridors where pedestrians die.</p>
     ${hot.length ? `<div style="overflow-x:auto"><table class="span-table">
       <thead><tr><th>Corridor (tract → FQHC)</th><th>Walk</th><th>Deaths within 150 m</th><th>…in darkness</th></tr></thead>
       <tbody>${topRows}</tbody></table></div>` : ""}
     <p class="panel-sub" style="margin-top:8px">${escapeHtml(CRASH.model_notes)}</p>`;
}

/* ---- equity ---- */
function renderEquity() {
  const sub = document.getElementById("equity-sub");
  const body = document.getElementById("equity-body");
  if (!ROLLUP.acs_income_joined) {
    const why = ROLLUP.geography === "zcta"
      ? "Income overlay is tract-based; switch to census tracts (and pull tract ACS) to see access vs. income."
      : "Once tract-level Census ACS is pulled, this panel compares FQHC access against neighborhood income.";
    sub.textContent = "Income overlay not populated for this view.";
    body.innerHTML =
      `<div class="notice">${why}<br>1. Free Census key at <a href="https://api.census.gov/data/key_signup.html" target="_blank" rel="noopener">api.census.gov/data/key_signup.html</a><br>` +
      '2. <code>export CENSUS_API_KEY=your_key</code><br>' +
      '3. <code>python fetch_census_acs.py --tracts 45045 &amp;&amp; python build_access_rollup.py</code>, then reload.</div>';
    return;
  }
  const unit = ROLLUP.unit_label;
  const rows = ROLLUP.units.filter((t) => t.median_household_income != null && t.walk_min != null);
  const byInc = rows.slice().sort((a, b) => a.median_household_income - b.median_household_income);
  const k = Math.floor(byInc.length / 3) || 1;
  const meanWalk = (arr) => arr.reduce((s, t) => s + t.walk_min, 0) / arr.length;
  const meanTransitPct = (arr) => 100 * arr.filter((t) => t.transit_reachable).length / arr.length;
  const low = byInc.slice(0, k), high = byInc.slice(-k);
  sub.textContent = `${rows.length} ${unit}s with income + access data.`;
  let html =
    `<p class="panel-sub">Lowest-income third of ${unit}s: <b>${fmt1(meanWalk(low))} min</b> mean walk to an FQHC, ` +
    `<b>${fmt1(meanTransitPct(low))}%</b> transit-reachable; ` +
    `highest-income third: <b>${fmt1(meanWalk(high))} min</b>, <b>${fmt1(meanTransitPct(high))}%</b> transit-reachable.</p>`;

  const veh = ROLLUP.units.filter((t) => t.pct_no_vehicle != null && t.walk_min != null);
  if (veh.length) {
    const byVeh = veh.slice().sort((a, b) => b.pct_no_vehicle - a.pct_no_vehicle);
    const kv = Math.floor(byVeh.length / 3) || 1;
    const carFree = byVeh.slice(0, kv);
    html +=
      `<p class="panel-sub">The third of ${unit}s with the <b>most car-free households</b> ` +
      `(mean <b>${fmt1(carFree.reduce((s, t) => s + t.pct_no_vehicle, 0) / carFree.length)}%</b> of households without a vehicle): ` +
      `<b>${fmt1(meanWalk(carFree))} min</b> mean walk to an FQHC, <b>${fmt1(meanTransitPct(carFree))}%</b> transit-reachable. ` +
      `For these households, walking and Greenlink aren't one option among several — they're the only way to reach care.</p>`;
  }
  body.innerHTML = html;
}

function renderPrivacy() {
  const p = document.getElementById("privacy-panel");
  p.innerHTML =
    `<div class="panel-head"><h2>Privacy — how a real usage rollup would work</h2></div>
     <p style="margin:0 0 8px">This page is a <b>modeled</b> surface, so it contains no personal data.
     When the lookup tool is used by real people, results are de-identified (address, coordinates, and
     chosen facility are dropped — only the area and travel times remain) and rolled up with a
     <b>k-anonymity threshold of 25</b>: any area with fewer than that many lookups is suppressed entirely,
     failing closed. That machinery lives in <code>engine/aggregate.py</code>.</p>
     <p class="panel-sub" style="margin:0">See <a href="../docs/privacy-design.md">docs/privacy-design.md</a>.</p>`;
}

function renderFooter() {
  document.getElementById("footer-sources").innerHTML =
    "Access: engine (Census Geocoder + Greenlink GTFS + HRSA FQHCs) · Boundaries: Census TIGERweb";
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
function cap(s) { return s ? s[0].toUpperCase() + s.slice(1) : s; }
