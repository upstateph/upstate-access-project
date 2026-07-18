/* Tier 2 lookup UI. Posts the address to /api/score (never a query string) and
   renders the access result. No client-side storage of the address. */

const form = document.getElementById("lookup-form");
const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");

const min = (m) => (m == null ? "—" : `${Math.round(m)} min`);
const esc = (s) => String(s ?? "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const address = document.getElementById("address").value.trim();
  const category = document.getElementById("category").value;
  if (!address) return;

  const btn = document.getElementById("submit-btn");
  btn.disabled = true; btn.textContent = "Checking…";
  resultsEl.hidden = true;
  showStatus("Geocoding address and computing routes…", false);

  try {
    const resp = await fetch("/api/score", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ address, category }),
    });
    const data = await resp.json();
    if (!data.ok) return showStatus(errorText(data), true);
    statusEl.hidden = true;
    render(data);
  } catch (err) {
    showStatus("Could not reach the lookup service. Is the server running?", true);
  } finally {
    btn.disabled = false; btn.textContent = "Check access";
  }
});

function showStatus(msg, isError) {
  statusEl.textContent = msg;
  statusEl.className = "status" + (isError ? " error" : "");
  statusEl.hidden = false;
}

function errorText(d) {
  if (d.error === "address_not_found")
    return "No match for that address. Try including the city, state, and ZIP (e.g. “975 W Faris Rd, Greenville, SC 29605”).";
  if (d.error === "data_not_loaded")
    return "Facility data isn’t loaded yet. Run fetch_hrsa_fqhc.py first.";
  if (d.error === "missing_address") return "Please enter an address.";
  return "Something went wrong: " + (d.detail || d.error || "unknown error");
}

function render(d) {
  const n = d.nearest;
  const dr = d.drive;
  const t = d.transit || {};
  const transitReachable = t.available && t.reachable;
  const it = transitReachable ? t.itinerary : null;

  let html = `
    <div class="card">
      <div class="result-head">
        <h2>Nearest ${esc(labelFor(d.category))}</h2>
        <span class="badge">${esc(n.facility.health_center_type || "").includes("Look-Alike") ? "FQHC Look-Alike" : "FQHC"}</span>
      </div>
      <p class="matched">From ${esc(d.origin.matched_address)}</p>

      <div class="modes">
        <div class="mode">
          <div class="mode-label">🚶 Walk</div>
          <div class="big">${min(n.walk_minutes)}</div>
          <div class="sub">${n.walk_network_km} km to ${esc(n.facility.name)}</div>
        </div>
        <div class="mode">
          <div class="mode-label">🚗 Drive</div>
          ${dr
            ? `<div class="big">${min(dr.drive_minutes)}</div>
               <div class="sub">${dr.drive_network_km} km to ${esc(dr.facility.name)}</div>`
            : `<div class="big unreach">—</div><div class="sub">no drive estimate</div>`}
        </div>
        <div class="mode">
          <div class="mode-label">🚌 Greenlink transit</div>
          ${it
            ? `<div class="big">${min(it.total_minutes)}</div>
               <div class="sub">${it.transfers} transfer${it.transfers === 1 ? "" : "s"} · to ${esc(t.facility.name)}</div>`
            : `<div class="big unreach">Not reachable</div>
               <div class="sub">${esc(t.reason || "No transit itinerary")}</div>`}
        </div>
      </div>
      <p class="privacy-inline" style="margin-top:8px">Walk &amp; drive: ${routingLabel(n.routing_method)}. Transit: Greenlink GTFS schedule (weekday midday).</p>

      <div class="facility">
        <div class="fname">${esc(n.facility.name)}</div>
        <div class="faddr">${esc(n.facility.address)}, ${esc(n.facility.city)}, ${esc(n.facility.state)} ${esc(n.facility.zip)}${n.facility.phone ? " · " + esc(n.facility.phone) : ""}</div>
      </div>
      ${it ? transitBreakdown(it) : ""}
      ${alternatives(d.alternatives)}
      ${equityBlock(d.equity)}
    </div>`;
  resultsEl.innerHTML = html;
  resultsEl.hidden = false;
}

function labelFor(cat) {
  return { fqhc: "community health center (FQHC)" }[cat] || cat;
}

function routingLabel(method) {
  return method === "osrm" ? "real road-network routing (OSRM)" : "straight-line estimate";
}

function transitBreakdown(it) {
  const legs = (it.legs || []).map((l) =>
    `<li><span class="route">${esc(l.route_id)}</span>${esc(l.board_stop)} (${l.board_time.slice(0,5)}) → ${esc(l.alight_stop)} (${l.alight_time.slice(0,5)})</li>`
  ).join("");
  return `
    <div class="alts">
      <h3>Transit itinerary (${it.transfers} transfer${it.transfers===1?"":"s"}, weekday midday)</h3>
      <p class="matched">Walk ${min(it.walk_to_stop_min)} · wait ${min(it.wait_min)} · ride ${min(it.in_vehicle_min)} · walk ${min(it.walk_from_stop_min)}</p>
      <ul class="legs">${legs}</ul>
    </div>`;
}

function alternatives(alts) {
  if (!alts || !alts.length) return "";
  const rows = alts.map((a) =>
    `<li><span>${esc(a.facility.name)}</span><span>${min(a.walk_minutes)} walk</span></li>`
  ).join("");
  return `<div class="alts"><h3>Other nearby options</h3><ul>${rows}</ul></div>`;
}

function equityBlock(eq) {
  if (!eq || !eq.available) {
    const reason = eq && eq.reason ? eq.reason : "Run fetch_census_acs.py (needs a Census API key) to enable the equity comparison.";
    return `<div class="equity"><h3>Equity comparison</h3><p class="note">${esc(reason)}</p></div>`;
  }
  const inc = eq.median_household_income;
  const r = eq.race_ethnicity_pct;
  const pctBelow = inc.pct_of_county_tracts_below;  // % of county tracts with lower income
  const callout = (inc.ratio_to_county != null)
    ? `<div class="equity-callout">This neighborhood's median household income is
        <b>${Math.round(inc.ratio_to_county * 100)}%</b> of the county median${pctBelow != null
        ? ` — higher than <b>${Math.round(pctBelow)}%</b> of Greenville County neighborhoods.` : "."}</div>`
    : "";
  const row = (label, a, b, suf = "") =>
    `<tr><td>${label}</td><td>${a == null ? "—" : a}${suf}</td><td>${b == null ? "—" : b}${suf}</td></tr>`;
  return `
    <div class="equity">
      <h3>Equity comparison — this neighborhood vs. Greenville County</h3>
      ${callout}
      <table>
        <thead><tr><th></th><th>This tract</th><th>County</th></tr></thead>
        <tbody>
          ${row("Median household income", inc.tract != null ? "$" + inc.tract.toLocaleString() : null, inc.county != null ? "$" + inc.county.toLocaleString() : null)}
          ${row("% Black", r.tract.black, r.county.black, "%")}
          ${row("% Hispanic", r.tract.hispanic, r.county.hispanic, "%")}
          ${row("% White", r.tract.white, r.county.white, "%")}
        </tbody>
      </table>
      <p class="note">ACS ${esc(eq.acs_vintage || "")} 5-year. Tract ${esc(eq.tract_fips)}.</p>
    </div>`;
}
