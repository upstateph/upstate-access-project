/* Address-lookup widget, embedded in the Greenville access page.

   This is the same Tier 2 lookup that used to live as a separate app at /lookup/ —
   it now runs inside the county access page so there is ONE tool: county-level
   surface plus "what about my address" in a single place.

   It needs the API (geocoding + GTFS routing), which only exists on a full-stack
   deploy. Three contexts, resolved at runtime:
     - full-stack deploy (Render, VPS): same-origin /api — fully functional
     - local dev on :8137 (static mirror of GitHub Pages): API dev server is on
       :8138, so point there
     - static-only (GitHub Pages): no API — degrade to an explainer that links to
       the working beta rather than showing a form that cannot work

   Privacy: the address goes in a POST body, never a query string, and is never
   stored client-side. */
(function () {
  "use strict";

  const RENDER_BETA = "https://upstate-access-beta.onrender.com";
  const host = document.getElementById("lookup-widget");
  if (!host) return;

  const apiBase = () => (location.port === "8137" ? "http://localhost:8138" : "");
  const api = (path) => apiBase() + path;

  const min = (m) => (m == null ? "—" : `${Math.round(m)} min`);
  const esc = (s) => String(s ?? "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

  let CATEGORIES = {};

  init();

  async function init() {
    let cats = [];
    try {
      const resp = await fetch(api("/api/categories"));
      if (!resp.ok) throw new Error("no api");
      cats = (await resp.json()).categories || [];
      if (!cats.length) throw new Error("empty");
    } catch (e) {
      return renderUnavailable();
    }
    for (const c of cats) CATEGORIES[c.key] = c;
    renderForm(cats);
  }

  /* ---- static-only fallback: say what's true, and where the tool does work ---- */
  function renderUnavailable() {
    host.innerHTML = `
      <p class="panel-sub" style="margin:0 0 10px">
        The address lookup needs a live server to geocode and route, so it can't run on
        this static site. It <b>is</b> running on the free beta:
      </p>
      <p style="margin:0 0 8px">
        <a href="${RENDER_BETA}/greenville-access.html#lookup" target="_blank" rel="noopener"
           style="font-weight:600">Open the address lookup on the beta site →</a>
      </p>
      <p class="panel-sub" style="margin:0">
        The beta sleeps when idle, so the first load can take 30–60 seconds to wake.
        It routes through a public OSRM demo server; self-hosted routing is the gate
        before a real public launch.
      </p>`;
  }

  /* ---- functional form ---- */
  function renderForm(cats) {
    const groups = {};
    for (const c of cats) (groups[c.group] || (groups[c.group] = [])).push(c);
    const options = Object.entries(groups).map(([g, items]) =>
      `<optgroup label="${esc(g)}">` +
      items.map((c) => `<option value="${esc(c.key)}">${esc(c.label)}${c.count ? ` (${c.count})` : ""}</option>`).join("") +
      `</optgroup>`).join("");

    host.innerHTML = `
      <form class="form" id="lw-form">
        <div class="field">
          <label for="lw-address">Street address</label>
          <input id="lw-address" type="text" autocomplete="off"
                 placeholder="e.g. 206 S Main St, Greenville, SC 29601" required />
        </div>
        <div class="field">
          <label for="lw-category">Type of service</label>
          <select id="lw-category">${options}</select>
          <p class="privacy-inline" id="lw-coverage" hidden></p>
          <p class="privacy-inline">${cats.length} service type${cats.length === 1 ? "" : "s"} available.
            Stigma-sensitive categories (reproductive health, HIV care) are withheld
            until every address is verified.</p>
        </div>
        <button type="submit" id="lw-submit">Check this address</button>
        <p class="privacy-inline">🔒 No account, no login. We never store or log your address.
          To compute the result it is sent to the US Census Geocoder (the address) and the
          OSRM routing service (coordinates only).</p>
      </form>
      <section id="lw-status" class="status" hidden></section>
      <section id="lw-results" hidden></section>`;

    document.getElementById("lw-form").addEventListener("submit", onSubmit);

    // A composite category whose members aren't all live returns partial results.
    // Say which part is missing: a behavioral-health search that silently omits
    // every treatment center looks like a finding ("nothing near me") rather than
    // the gap it actually is.
    const sel = document.getElementById("lw-category");
    const coverage = document.getElementById("lw-coverage");
    const showCoverage = () => {
      const note = (CATEGORIES[sel.value] || {}).coverage_note;
      coverage.textContent = note || "";
      coverage.hidden = !note;
    };
    sel.addEventListener("change", showCoverage);
    showCoverage();
  }

  async function onSubmit(e) {
    e.preventDefault();
    const address = document.getElementById("lw-address").value.trim();
    const category = document.getElementById("lw-category").value;
    if (!address) return;

    const btn = document.getElementById("lw-submit");
    const results = document.getElementById("lw-results");
    btn.disabled = true; btn.textContent = "Checking…";
    results.hidden = true;
    showStatus("Geocoding address and computing routes…", false);

    try {
      const resp = await fetch(api("/api/score"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ address, category }),
      });
      const data = await resp.json();
      if (!data.ok) return showStatus(errorText(data), true);
      document.getElementById("lw-status").hidden = true;
      render(data);
    } catch (err) {
      showStatus("Could not reach the lookup service.", true);
    } finally {
      btn.disabled = false; btn.textContent = "Check this address";
    }
  }

  function showStatus(msg, isError) {
    const el = document.getElementById("lw-status");
    el.textContent = msg;
    el.className = "status" + (isError ? " error" : "");
    el.hidden = false;
  }

  function errorText(d) {
    const m = {
      address_not_found: "No match for that address. Try including city, state, and ZIP.",
      data_not_loaded: "This service's location data isn't loaded yet for the pilot area.",
      geocoder_unavailable: "The US Census Geocoder is temporarily unreachable. Try again in a minute.",
      no_facilities_with_coordinates: "No mapped locations for this service type yet.",
      category_unavailable: "That service type isn't available in this pilot yet.",
      outside_coverage_area: "That address is outside the pilot area. This tool currently covers Greenville County, South Carolina only — try an address there, e.g. 206 S Main St, Greenville, SC 29601.",
      bad_request: "That request couldn't be read. Please try again.",
      missing_address: "Please enter an address.",
    };
    return m[d.error] || ("Something went wrong: " + (d.error || "unknown error"));
  }

  function render(d) {
    const n = d.nearest, dr = d.drive, t = d.transit || {};
    const it = t.available && t.reachable ? t.itinerary : null;
    document.getElementById("lw-results").innerHTML = `
      <div class="card">
        <div class="result-head">
          <h3 style="margin:0;font-size:17px">Nearest ${esc(labelFor(d.category))}</h3>
          <span class="badge">${esc(badgeFor(d.category, n.facility))}</span>
        </div>
        <p class="matched">From ${esc(d.origin.matched_address)}</p>
        <div class="modes">
          <div class="mode"><div class="mode-label">🚶 Walk</div>
            <div class="big">${min(n.walk_minutes)}</div>
            <div class="sub">${n.walk_network_mi} mi to ${esc(n.facility.name)}</div></div>
          <div class="mode"><div class="mode-label">🚗 Drive</div>
            ${dr ? `<div class="big">${min(dr.drive_minutes)}</div>
                    <div class="sub">${dr.drive_network_mi} mi to ${esc(dr.facility.name)}</div>`
                 : `<div class="big unreach">—</div><div class="sub">no drive estimate</div>`}</div>
          <div class="mode"><div class="mode-label">🚌 Greenlink transit</div>
            ${it ? `<div class="big">${min(it.total_minutes)}</div>
                    <div class="sub">${it.transfers} transfer${it.transfers === 1 ? "" : "s"} · to ${esc(t.facility.name)}</div>`
                 : `<div class="big unreach">Not reachable</div>
                    <div class="sub">${esc(t.reason || "No transit itinerary")}</div>`}</div>
        </div>
        <p class="privacy-inline" style="margin-top:8px">Walk: ${routingLabel(n.routing_method)}.
          Drive: ${dr ? routingLabel(dr.routing_method) : "not available"}.
          Transit: ${esc(t.model || "Greenlink GTFS schedule")}.</p>
        <div class="facility">
          <div class="fname">${esc(n.facility.name)}</div>
          <div class="faddr">${esc(n.facility.address)}, ${esc(n.facility.city)}, ${esc(n.facility.state)} ${esc(n.facility.zip)}${n.facility.phone ? " · " + esc(n.facility.phone) : ""}</div>
        </div>
        ${it ? breakdown(it, t.model) : ""}
        ${alternatives(d.alternatives)}
        ${equityBlock(d.equity)}
      </div>`;
    document.getElementById("lw-results").hidden = false;
  }

  function labelFor(cat) {
    const c = CATEGORIES[cat];
    const label = c ? c.label : cat;
    return label.charAt(0).toLowerCase() + label.slice(1);
  }
  function badgeFor(cat, fac) {
    if (cat === "fqhc") return (fac.health_center_type || "").includes("Look-Alike") ? "FQHC Look-Alike" : "FQHC";
    // NPPES-sourced records carry the taxonomy they matched. It is far more use
    // than the group name — under one "Mental & behavioral health" option this is
    // what distinguishes a marriage & family therapist from a treatment center.
    if (fac && fac.taxonomy) return fac.taxonomy;
    const c = CATEGORIES[cat];
    return c ? (c.group || "Service") : "Service";
  }
  const routingLabel = (m) => (m === "osrm" ? "real road-network routing (OSRM)" : "straight-line estimate");

  function breakdown(it, model) {
    const legs = (it.legs || []).map((l) =>
      `<li><span class="route">${esc(l.route_id)}</span>${esc(l.board_stop)} (${l.board_time.slice(0, 5)}) → ${esc(l.alight_stop)} (${l.alight_time.slice(0, 5)})</li>`).join("");
    return `<div class="alts">
        <h4>Transit itinerary (${it.transfers} transfer${it.transfers === 1 ? "" : "s"})</h4>
        <p class="matched">Walk ${min(it.walk_to_stop_min)} · wait ${min(it.wait_min)} · ride ${min(it.in_vehicle_min)} · walk ${min(it.walk_from_stop_min)}</p>
        <ul class="legs">${legs}</ul>
        <p class="matched" style="margin:6px 0 0">${esc(model || "")}</p>
      </div>`;
  }

  function alternatives(alts) {
    if (!alts || !alts.length) return "";
    return `<div class="alts"><h4>Other nearby options</h4><ul>` +
      alts.map((a) => `<li><span>${esc(a.facility.name)}</span><span>${min(a.walk_minutes)} walk</span></li>`).join("") +
      `</ul></div>`;
  }

  function equityBlock(eq) {
    if (!eq || !eq.available) {
      return `<div class="equity"><h4>Equity comparison</h4><p class="note">${esc((eq && eq.reason) || "Not available.")}</p></div>`;
    }
    const inc = eq.median_household_income, r = eq.race_ethnicity_pct;
    const pctBelow = inc.pct_of_county_tracts_below;
    const callout = inc.ratio_to_county != null
      ? `<div class="equity-callout">This neighborhood's median household income is
          <b>${Math.round(inc.ratio_to_county * 100)}%</b> of the county median${pctBelow != null
          ? ` — higher than <b>${Math.round(pctBelow)}%</b> of Greenville County neighborhoods.` : "."}</div>`
      : "";
    const cell = (v, suf) => (v == null ? "—" : `${v}${suf}`);
    const row = (label, a, b, suf = "") =>
      `<tr><td>${label}</td><td>${cell(a, suf)}</td><td>${cell(b, suf)}</td></tr>`;
    return `<div class="equity">
        <h4>Equity comparison — this neighborhood vs. Greenville County</h4>
        ${callout}
        <table>
          <thead><tr><th></th><th>This tract</th><th>County</th></tr></thead>
          <tbody>
            ${row("Median household income", inc.tract != null ? "$" + inc.tract.toLocaleString() : null, inc.county != null ? "$" + inc.county.toLocaleString() : null)}
            ${row("% Black", r.tract.black, r.county.black, "%")}
            ${row("% Hispanic", r.tract.hispanic, r.county.hispanic, "%")}
            ${row("% White", r.tract.white, r.county.white, "%")}
            ${(eq.households_no_vehicle_pct && eq.households_no_vehicle_pct.tract != null)
              ? row("% households with no vehicle", eq.households_no_vehicle_pct.tract, eq.households_no_vehicle_pct.county, "%") : ""}
          </tbody>
        </table>
        <p class="note">ACS ${esc(eq.acs_vintage || "")} 5-year. Tract ${esc(eq.tract_fips)}.</p>
      </div>`;
  }
})();
