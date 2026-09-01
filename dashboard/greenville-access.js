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
let LOAD_SEQ = 0;

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
  const seq = ++LOAD_SEQ;  // token: a stale in-flight load must never win a later one
  const f = FILES[GEOGRAPHY];
  let rollup, geo;
  try {
    rollup = await (await fetch(f.rollup)).json();
    geo = await (await fetch(f.geojson)).json();
  } catch (e) {
    if (seq !== LOAD_SEQ) return;
    document.getElementById("subtitle").textContent =
      `Could not load the ${GEOGRAPHY} rollup — run fetch_${GEOGRAPHY === "tract" ? "tract" : "zcta"}_geojson.py and build_access_rollup.py.`;
    return;
  }
  if (seq !== LOAD_SEQ) return;
  ROLLUP = rollup;
  GEO = geo;
  const unit = ROLLUP.unit_label;
  document.getElementById("subtitle").textContent =
    `Modeled travel time from ${ROLLUP.summary.n_units} ${unit}s to the easiest FQHC to reach — nearest on foot or by car, best-connected by bus.`;
  document.getElementById("map-title").textContent = `Access by ${unit === "ZIP" ? "ZIP code" : "census tract"}`;
  document.getElementById("main").hidden = false;
  renderMethod();
  renderKPIs();
  buildMetricSelect();
  renderChoropleth();
  renderServiceSpan();
  renderRouteDiagnostics();
  renderEquity();
  renderPrivacy();
  renderFooter();
}

/* ---- service span (time-of-day) ---- */
let SPAN = null, SPAN_LOADED = false, SPAN_PROMISE = null;
async function renderServiceSpan() {
  const panel = document.getElementById("service-span-panel");
  if (!SPAN_LOADED) {
    // Share one in-flight request: two overlapping renders (a geography toggle
    // fired before the first load settles) must not let a failing sibling null out
    // a value the other already fetched — that would strand the panel hidden with
    // SPAN_LOADED already true, so no later render could retry.
    try {
      SPAN_PROMISE = SPAN_PROMISE || fetch("data/service_span_tract_45045.json").then((r) => r.json());
      SPAN = await SPAN_PROMISE;
      SPAN_LOADED = true;
    } catch (e) { SPAN_PROMISE = null; }
  }
  if (!SPAN) { panel.hidden = true; return; }
  panel.hidden = false;

  const base = SPAN.summary[SPAN.baseline_window];
  document.getElementById("service-span-sub").textContent =
    `Modeled ≤1-transfer Greenlink trip from each census tract to whichever FQHC the bus reaches fastest — not necessarily the nearest one — at four departure windows.`;

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

  // Read the direction out of the data rather than assuming midday is the best
  // case — with a wait cap in place it is in fact the worst.
  const ranked = SPAN.windows
    .map((w) => SPAN.summary[w.key])
    .filter((s) => s.transit_min_median != null)
    .sort((a, b) => a.transit_min_median - b.transit_min_median);
  const best = ranked[0], worst = ranked[ranked.length - 1];
  const delta = best && worst ? Math.round(worst.transit_min_median - best.transit_min_median) : null;
  const reach = SPAN.windows.map((w) => SPAN.summary[w.key].pct_reachable).filter((v) => v != null);
  const reachSpread = reach.length ? Math.max(...reach) - Math.min(...reach) : 0;

  document.getElementById("service-span-body").innerHTML =
    `<div style="overflow-x:auto"><table class="span-table">
       <caption class="visually-hidden">Tracts reachable and median trip time by
         departure window, with the number of tracts that lose access compared
         with midday.</caption>
       <thead><tr><th scope="col">Departure window</th><th scope="col">Tracts reachable</th><th scope="col">Median trip</th><th scope="col">Tracts losing access vs midday</th></tr></thead>
       <tbody>${rows}</tbody>
     </table></div>
     <p class="panel-sub" style="margin-top:8px">${
       delta != null && delta > 0
         ? `Which tracts can reach a health center barely moves by time of day (a ${fmt1(reachSpread)}-point spread), but how long it takes does: the median trip runs <b>${fmt1(best.transit_min_median)} min</b> at its best (${escapeHtml(best.label)}) and <b>${fmt1(worst.transit_min_median)} min</b> at its worst (${escapeHtml(worst.label)}) — a <b>${delta}-minute</b> penalty for traveling at the wrong hour. Midday, when a routine appointment is most likely to be scheduled, is the thinnest service of the day.`
         : "Reachability and trip times are similar across the modeled windows."
     }</p>
     <p class="panel-sub">${escapeHtml(SPAN.model_notes)}</p>`;
}

function renderMethod() {
  const unit = ROLLUP.unit_label;
  const p = document.getElementById("method-panel");
  // Two physician reviewers independently read the access model as being DERIVED
  // from the pedestrian-crash data — one asked whether it "breaks down by mode of
  // transportation since it was pedestrian deaths", the other listed bus routes
  // among what was missing when GTFS is the entire backbone of the transit model.
  // The tracker itself left the site on 2026-08-27, but readers arrived from
  // outreach that described both, so the denial stays.
  p.innerHTML =
    `<p style="margin:0 0 6px"><b>What this shows.</b> For each ${unit}, we compute how long it takes to
     reach a Federally Qualified Health Center from a representative point — walking, driving,
     and by Greenlink transit (allowing up to one transfer), routed on
     <b>Greenlink's published GTFS schedule and the real road network</b>. Walking and driving go to the
     <b>nearest</b> FQHC; transit goes to whichever one the bus reaches fastest, which is not always the
     nearest. FQHCs are the pilot category
     (spec §10); the same rollup extends to other categories as they're added.</p>
     <!-- The full "not built from crash data" explanation now lives in the
          #what-this-is panel above, which is the first thing on the page. Two
          consecutive panels making the same denial read as defensive, so this
          keeps one sentence for anyone who scrolled straight to the methods. -->
     <p style="margin:0 0 6px"><b>What it does not use.</b> No crash or
     pedestrian-fatality data goes into these travel times — see
     <a href="#what-this-is">what this page measures</a> above.</p>
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

/* Distinct fill for "no data / no trip" so it can never be confused with the
   best-quantile bin color (finding: 70 unreachable tracts rendered identically
   to the fastest ones). */
function hatchDefs() {
  const defs = svg("defs");
  const pat = svg("pattern", { id: "nodata-hatch", width: "6", height: "6",
                               patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" });
  pat.append(svg("rect", { width: "6", height: "6", fill: cssVar("--panel") }));
  pat.append(svg("line", { x1: "0", y1: "0", x2: "0", y2: "6",
                           stroke: cssVar("--ink-soft"), "stroke-width": "1.6", opacity: "0.55" }));
  defs.append(pat);
  return defs;
}
const NO_DATA_FILL = "url(#nodata-hatch)";
const HATCH_SWATCH_CSS =
  "background:repeating-linear-gradient(45deg,transparent,transparent 3px,var(--ink-soft) 3px,var(--ink-soft) 4.5px)";
function thresholds(vals, bins) {
  const v = vals.filter((x) => x != null).slice().sort((a, b) => a - b);
  if (!v.length) return [];
  const th = [];
  for (let i = 1; i < bins; i++) th.push(v[Math.floor((i / bins) * v.length)]);
  // Short or tied value lists (e.g. only 6 of 22 ZIPs have a transit time) produce
  // duplicate quantiles, which would render zero-width legend rows like
  // "45.8m – 45.8m" whose color is painted on no polygon at all. Dedupe so the
  // number of bins always matches the number of distinct classes.
  return [...new Set(th)];
}
function bin(val, th) { if (val == null) return -1; let i = 0; while (i < th.length && val >= th[i]) i++; return i; }

/* ---- pan / zoom -----------------------------------------------------------
   The choropleth is a whole county at ~700px wide, so a downtown tract is a few
   pixels across and effectively unreadable. Zoom is what makes the tract-level
   detail usable at all.

   Implemented as a transform on a wrapper <g> rather than by rewriting the
   viewBox, so the projected path data never changes and nothing has to be
   re-rendered while panning.

   The one subtlety worth stating: tracts are CLICKABLE (select) and HOVERABLE
   (tooltip), so a drag must not register as a click. Anything past a few pixels
   of movement suppresses the click that the browser fires afterwards.
*/
function attachZoom(svgEl, W, H) {
  const layer = svg("g");
  while (svgEl.firstChild) layer.append(svgEl.firstChild);
  svgEl.append(layer);

  let scale = 1, tx = 0, ty = 0;
  const MIN = 1, MAX = 12;
  const apply = () => layer.setAttribute("transform", `translate(${tx} ${ty}) scale(${scale})`);

  // Convert a pointer position to SVG user units, so zoom anchors on the cursor
  // rather than the center — anchoring on the center makes it feel like the map
  // is fighting you.
  const toSvg = (ev) => {
    const r = svgEl.getBoundingClientRect();
    return { x: ((ev.clientX - r.left) / r.width) * W, y: ((ev.clientY - r.top) / r.height) * H };
  };

  function zoomAt(px, py, factor) {
    const next = Math.min(MAX, Math.max(MIN, scale * factor));
    if (next === scale) return;
    tx = px - ((px - tx) / scale) * next;
    ty = py - ((py - ty) / scale) * next;
    scale = next;
    if (scale === MIN) { tx = 0; ty = 0; }
    clamp(); apply();
  }

  // Keep at least part of the map on screen at every zoom level.
  function clamp() {
    const maxX = 0, minX = W - W * scale;
    const maxY = 0, minY = H - H * scale;
    tx = Math.min(maxX, Math.max(minX, tx));
    ty = Math.min(maxY, Math.max(minY, ty));
  }

  svgEl.addEventListener("wheel", (ev) => {
    ev.preventDefault();
    const { x, y } = toSvg(ev);
    zoomAt(x, y, ev.deltaY < 0 ? 1.15 : 1 / 1.15);
  }, { passive: false });

  // Pointer bookkeeping. Tracked in a Map rather than as a single "dragging"
  // flag because touch needs two: `touchAction: none` above switches OFF the
  // browser's native pinch, so if we do not implement pinch ourselves a phone
  // user can pan but cannot zoom at all — strictly worse than never having
  // disabled it. The +/- buttons are not a substitute on a small screen.
  const active = new Map();
  let moved = 0, lastX = 0, lastY = 0, pinchDist = 0;

  const center = () => {
    const pts = [...active.values()];
    return {
      x: pts.reduce((s, p) => s + p.x, 0) / pts.length,
      y: pts.reduce((s, p) => s + p.y, 0) / pts.length,
    };
  };
  const spread = () => {
    const [a, b] = [...active.values()];
    return Math.hypot(a.x - b.x, a.y - b.y);
  };

  svgEl.addEventListener("pointerdown", (ev) => {
    active.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    svgEl.setPointerCapture(ev.pointerId);
    if (active.size === 1) {
      moved = 0; lastX = ev.clientX; lastY = ev.clientY;
    } else if (active.size === 2) {
      pinchDist = spread();
      const c = center(); lastX = c.x; lastY = c.y;
    }
  });

  svgEl.addEventListener("pointermove", (ev) => {
    if (!active.has(ev.pointerId)) return;
    active.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    const r = svgEl.getBoundingClientRect();

    if (active.size >= 2) {
      // Pinch: scale by the change in finger separation, anchored on the
      // midpoint, and pan by the midpoint's own movement so the gesture feels
      // attached to the map rather than to the center of the element.
      const dist = spread();
      const c = center();
      if (pinchDist > 0 && dist > 0) {
        const sx = ((c.x - r.left) / r.width) * W;
        const sy = ((c.y - r.top) / r.height) * H;
        zoomAt(sx, sy, dist / pinchDist);
      }
      tx += ((c.x - lastX) / r.width) * W;
      ty += ((c.y - lastY) / r.height) * H;
      pinchDist = dist; lastX = c.x; lastY = c.y;
      moved += 10;                 // a pinch is never a tap
      clamp(); apply();
      return;
    }

    const dx = ev.clientX - lastX, dy = ev.clientY - lastY;
    moved += Math.abs(dx) + Math.abs(dy);
    tx += (dx / r.width) * W; ty += (dy / r.height) * H;
    lastX = ev.clientX; lastY = ev.clientY;
    clamp(); apply();
  });

  const endDrag = (ev) => {
    if (!active.has(ev.pointerId)) return;
    active.delete(ev.pointerId);
    try { svgEl.releasePointerCapture(ev.pointerId); } catch (e) {}
    if (active.size === 1) {
      // Lifting one finger mid-pinch: re-anchor on the remaining one so the
      // map does not jump.
      const p = [...active.values()][0];
      lastX = p.x; lastY = p.y; pinchDist = 0;
    }
  };
  svgEl.addEventListener("pointerup", endDrag);
  svgEl.addEventListener("pointercancel", endDrag);
  // Suppress the click the browser fires after a drag, so panning across the
  // map does not select whichever tract you happened to finish on.
  svgEl.addEventListener("click", (ev) => {
    if (moved > 4) { ev.stopPropagation(); ev.preventDefault(); moved = 0; }
  }, true);

  svgEl.style.cursor = "grab";
  svgEl.style.touchAction = "none";
  return {
    reset: () => { scale = 1; tx = 0; ty = 0; apply(); },
    zoomIn: () => zoomAt(W / 2, H / 2, 1.4),
    zoomOut: () => zoomAt(W / 2, H / 2, 1 / 1.4),
  };
}

function zoomControls(ctl) {
  const wrap = document.createElement("div");
  wrap.className = "zoom-controls";
  for (const [label, fn, aria] of [["+", ctl.zoomIn, "Zoom in"],
                                   ["\u2212", ctl.zoomOut, "Zoom out"],
                                   ["Reset", ctl.reset, "Reset zoom"]]) {
    const b = document.createElement("button");
    b.type = "button"; b.textContent = label; b.setAttribute("aria-label", aria);
    b.addEventListener("click", fn);
    wrap.append(b);
  }
  return wrap;
}

function renderChoropleth() {
  const metric = metrics().find((m) => m.key === CURRENT) || metrics()[0];
  const byId = unitsById();
  const th = thresholds(ROLLUP.units.map((u) => metric.get(u)), 5);
  const rmp = ramp().slice(0, th.length + 1);  // one class per distinct threshold
  const { W, H, project } = projectAll();
  // "Greenville access choropleth" told a screen reader user the picture
  // exists and nothing about what is in it. The name now says what is being
  // shown, and the equivalent table below carries the actual figures: a map
  // driven by mousemove tooltips and pointer drag has no keyboard path to its
  // data, so the data has to exist somewhere that does.
  const s = svg("svg", {
    viewBox: `0 0 ${W} ${H}`, role: "img",
    "aria-label": `Map of Greenville County: ${metric.label} by ` +
      `${ROLLUP.unit_label === "ZIP" ? "ZIP code" : "census tract"}, ` +
      `${ROLLUP.units.length} areas shaded from low to high. ` +
      `The same figures are listed in the table below the map.`,
  });
  s.append(hatchDefs());

  for (const f of GEO.features) {
    const gid = String(f.properties.GEOID);
    const u = byId[gid];
    const val = u ? metric.get(u) : null;
    const fill = val == null ? NO_DATA_FILL : rmp[bin(val, th)];
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
  const host = document.getElementById("choropleth");
  host.replaceChildren(s);
  host.append(zoomControls(attachZoom(s, W, H)));
  renderLegend(metric, th, rmp);
  renderMapTable(metric);
}

/* The map's data, as a table.

   Every route into the choropleth was pointer-only: mousemove for the tooltip,
   pointerdown/move for the pan, wheel for the zoom, click to select. A
   keyboard or screen reader user could reach the +, - and Reset buttons and
   nothing else, so the entire dataset behind the page's centrepiece was
   unavailable to them. Making 123 tract paths individually focusable would
   trade that for a 123-stop tab trap, so the accessible equivalent is a table:
   the standard answer for a complex image, and genuinely more useful than the
   map for looking up one tract. Collapsed by default so the visual layout is
   unchanged. Sorted worst-first, because that is the order the page is about. */
function renderMapTable(metric) {
  const host = document.getElementById("map-table");
  if (!host) return;
  const unitWord = ROLLUP.unit_label === "ZIP" ? "ZIP code" : "Census tract";

  const rows = ROLLUP.units.slice().sort((a, b) => {
    const av = metric.get(a), bv = metric.get(b);
    if (av == null) return 1;
    if (bv == null) return -1;
    return metric.worseHigh ? bv - av : av - bv;
  });

  // Walk, drive and transit are always shown, so a metric that IS one of them
  // would otherwise appear twice in the same row.
  const dupes = { walk_min: 1, drive_min: 1, transit: 1 };
  const showMetricCol = !dupes[metric.key];

  const body = rows.map((u) => {
    const gid = String(u.id);
    return `<tr>
      <th scope="row" style="text-align:left;font-weight:500">${escapeHtml(unitName(u, gid))}</th>
      ${showMetricCol ? `<td>${escapeHtml(metric.fmt(metric.get(u)))}</td>` : ""}
      <td>${u.walk_min == null ? "—" : fmt1(u.walk_min) + " min"}</td>
      <td>${u.drive_min == null ? "—" : fmt1(u.drive_min) + " min"}</td>
      <td>${u.transit_reachable ? fmt1(u.transit_min) + " min" : "no \u22641-transfer trip"}</td>
    </tr>`;
  }).join("");

  host.innerHTML = `
    <details>
      <summary style="cursor:pointer;font-weight:600">
        Show this map as a table (${rows.length} ${unitWord.toLowerCase()}s)</summary>
      <p class="panel-sub" style="margin:6px 0 10px">Every area on the map above,
        worst first by ${escapeHtml(metric.label.toLowerCase())}. Walk, drive and
        transit are to the nearest health center.</p>
      <div style="overflow-x:auto;max-height:60vh;overflow-y:auto">
        <table class="span-table">
          <caption class="visually-hidden">${escapeHtml(metric.label)} by
            ${unitWord.toLowerCase()}, with walk, drive and transit time to the
            nearest health center. ${rows.length} rows, worst first.</caption>
          <thead><tr>
            <th scope="col">${unitWord}</th>
            ${showMetricCol ? `<th scope="col">${escapeHtml(metric.label)}</th>` : ""}
            <th scope="col">Walk</th>
            <th scope="col">Drive</th>
            <th scope="col">Transit</th>
          </tr></thead>
          <tbody>${body}</tbody>
        </table>
      </div>
    </details>`;
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
  const round = metric.legendRound || ((x) => fmt1(x) + " min");
  if (th.length) {
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
  } else {
    host.append(el("div", { class: "row" }, "no values for this metric"));
  }
  const anyNull = ROLLUP.units.some((u) => metric.get(u) == null);
  if (anyNull || metric.key === "transit") {
    const row = el("div", { class: "row" });
    row.append(el("span", { class: "swatch", style: HATCH_SWATCH_CSS }));
    row.append(document.createTextNode(
      metric.key === "transit" ? "no ≤1-transfer trip" : "no data"));
    host.append(row);
  }
  document.getElementById("map-note").textContent =
    metric.key === "transit"
      ? "Grayed areas have no FQHC reachable within one Greenlink transfer (weekday midday)."
      : metric.key === "pct_no_vehicle"
      ? "Darker = larger share of households with no vehicle available (ACS B08201) — the population with no alternative to walking or transit."
      : `Darker = ${metric.worseHigh ? "longer" : "higher"} ${metric.label.toLowerCase().replace("fqhc", "FQHC")}.`;
}

/* ---- route diagnostics: the operational layer ---- */
let ROUTES = null, ROUTES_LOADED = false, ROUTES_PROMISE = null;
async function renderRouteDiagnostics() {
  const panel = document.getElementById("route-panel");
  if (!ROUTES_LOADED) {
    try {
      ROUTES_PROMISE = ROUTES_PROMISE || fetch("data/route_diagnostics_45045.json").then((r) => r.json());
      ROUTES = await ROUTES_PROMISE;
      ROUTES_LOADED = true;
    } catch (e) { ROUTES_PROMISE = null; }
  }
  if (!ROUTES) { panel.hidden = true; return; }
  panel.hidden = false;

  const b = ROUTES.baseline;
  document.getElementById("route-sub").textContent =
    `Each tract's trip attributed to the routes it actually rides, then re-routed against ` +
    `a denser timetable to price the change. Baseline: ${b.n_reachable} of ${b.n_total} tracts ` +
    `dependably reachable, median ${fmt1(b.median_total_min)} min.`;

  const routeRows = ROUTES.routes.slice(0, 8).map((r) => `<tr>
      <td>Route ${escapeHtml(r.route_id)}</td>
      <td>${r.n_tracts_boarding}</td>
      <td>${r.median_headway_min == null ? "—" : Math.round(r.median_headway_min) + " min"}</td>
      <td>${fmt1(r.median_wait_min)} min</td>
      <td>${fmt1(r.median_in_vehicle_min)} min</td>
      <td>${fmt1(r.median_total_min)} min</td></tr>`).join("");

  const scenRows = ROUTES.scenarios.map((s) => `<tr>
      <td>Route ${escapeHtml(s.route_id)} at ${s.factor}× frequency</td>
      <td>${Math.round(s.headway_before_min)} → ${Math.round(s.headway_after_min)} min</td>
      <td>${s.n_tracts_improved}</td>
      <td>${s.median_minutes_saved_per_improved_tract == null ? "—" : fmt1(s.median_minutes_saved_per_improved_tract) + " min"}</td>
      <td>${s.delta_tracts_under_threshold >= 0 ? "+" : ""}${s.delta_tracts_under_threshold}</td></tr>`).join("");

  const best = ROUTES.scenarios.slice().sort(
    (a, b2) => (b2.median_minutes_saved_per_improved_tract || 0) - (a.median_minutes_saved_per_improved_tract || 0))[0];

  document.getElementById("route-body").innerHTML = `
    <h3 style="font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:var(--ink-soft);margin:6px 0 8px">
      Where the time goes, by route</h3>
    <div style="overflow-x:auto"><table class="span-table">
      <caption class="visually-hidden">Greenlink routes, with tracts boarding,
        midday headway, and median wait, ride and total trip time.</caption>
      <thead><tr><th scope="col">Route</th><th scope="col">Tracts boarding here</th><th scope="col">Midday headway</th>
        <th scope="col">Median wait</th><th scope="col">Median ride</th><th scope="col">Median trip</th></tr></thead>
      <tbody>${routeRows}</tbody></table></div>

    <h3 style="font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:var(--ink-soft);margin:18px 0 8px">
      What doubling a route's frequency would buy</h3>
    <div style="overflow-x:auto"><table class="span-table">
      <caption class="visually-hidden">Modeled headway scenarios: tracts
        improved, median time saved, and tracts gained under the threshold.</caption>
      <thead><tr><th scope="col">Change</th><th scope="col">Headway</th><th scope="col">Tracts improved</th>
        <th scope="col">Median time saved</th><th scope="col">Tracts gained under ${Math.round(ROUTES.threshold_min)} min</th></tr></thead>
      <tbody>${scenRows}</tbody></table></div>

    <p class="panel-sub" style="margin-top:10px"><b>Read it this way.</b> ${(() => {
      const hw = ROUTES.routes.map((r) => r.median_headway_min);
      const band = hw.filter((h) => h >= 65 && h <= 70).length;
      // "Every route runs a 65–70 minute headway" shipped here and in a
      // LinkedIn post, and the table above refuted it: route 602 runs 35.
      // Say what the data says, and let the sentence follow the data.
      return band === hw.length
        ? "Every Greenlink route here runs a <b>65–70 minute</b> midday headway"
        : `${band} of the ${hw.length} routes ridden here run a <b>65–70 minute</b> midday headway`;
    })()}, so no single route is the bottleneck — doubling any
    one of them barely moves the county median, because the median tract doesn't ride it. The gains
    are concentrated and real for the tracts that do: ${best ? `doubling route ${escapeHtml(best.route_id)}
    saves ${fmt1(best.median_minutes_saved_per_improved_tract)} minutes for each of the
    ${best.n_tracts_improved} tracts it touches` : ""}. County-wide medians hide route-level wins,
    which is why a service decision needs this table rather than the headline number.</p>
    <p class="panel-sub"><b>Not modeled:</b> vehicles, operators, and layover. Doubling a route's
    frequency roughly doubles its peak vehicle requirement — the cost side of every row above, and
    the first question a planner will ask. ${escapeHtml(ROUTES.model_notes)}</p>`;
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
     <p class="panel-sub" style="margin:0">See <a href="https://github.com/upstateph/upstate-access-project/blob/main/docs/privacy-design.md" target="_blank" rel="noopener">docs/privacy-design.md</a>.</p>`;
}

function renderFooter() {
  document.getElementById("footer-sources").innerHTML =
    `Access: engine (Census Geocoder + Greenlink GTFS + HRSA FQHCs; walk/drive via ${
      ROLLUP.routing_method === "osrm" ? "OSRM road-network routing" : "straight-line estimate"
    }) · Boundaries: Census TIGERweb`;
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

/* ---- citation copy (KD: professionals need suggested citation language) ---- */
(function () {
  const btn = document.getElementById("cite-copy");
  if (!btn) return;
  btn.addEventListener("click", async () => {
    const base = document.getElementById("cite-line").textContent.replace(/\s+/g, " ").trim();
    const today = new Date().toISOString().slice(0, 10);
    try {
      await navigator.clipboard.writeText(base + " Accessed " + today + ".");
      btn.textContent = "Copied";
      setTimeout(() => { btn.textContent = "Copy"; }, 1500);
    } catch (e) {
      // Clipboard can be blocked (permissions, non-secure context). Select the
      // citation so copying is one keystroke instead of a drag.
      const range = document.createRange();
      range.selectNodeContents(document.getElementById("cite-line"));
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      btn.textContent = "Selected — press Ctrl/Cmd+C";
    }
  });
})();
