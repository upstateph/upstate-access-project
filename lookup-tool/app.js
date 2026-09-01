/* Tier 2 lookup UI. Posts the address to /api/score (never a query string) and
   renders the access result. No client-side storage of the address. */

const form = document.getElementById("lookup-form");
const statusEl = document.getElementById("status");
const errorEl = document.getElementById("error");
const resultsEl = document.getElementById("results");

const min = (m) => (m == null ? "—" : `${Math.round(m)} min`);
const esc = (s) => String(s ?? "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

let CATEGORIES = {};  // key -> {label, group, count, ...}
loadCategories();

async function loadCategories() {
  const sel = document.getElementById("category");
  const fallback = () => {
    sel.innerHTML = '<option value="fqhc">Community health center (FQHC)</option>';
    CATEGORIES = { fqhc: { key: "fqhc", label: "Community health center (FQHC)", group: "Health care" } };
  };
  try {
    const data = await (await fetch("/api/categories")).json();
    const cats = data.categories || [];
    if (!cats.length) return fallback();
    sel.innerHTML = "";
    const groups = {};
    for (const c of cats) { CATEGORIES[c.key] = c; (groups[c.group] || (groups[c.group] = [])).push(c); }
    for (const [g, items] of Object.entries(groups)) {
      const og = document.createElement("optgroup");
      og.label = g;
      for (const c of items) {
        const o = document.createElement("option");
        o.value = c.key;
        o.textContent = c.label + (c.count ? ` (${c.count})` : "");
        og.appendChild(o);
      }
      sel.appendChild(og);
    }
    const note = document.getElementById("category-note");
    const base = `${cats.length} service type${cats.length === 1 ? "" : "s"} available. ` +
      "Stigma-sensitive categories (reproductive health, HIV care) are withheld " +
      "from this beta until every address is verified.";
    // Composite categories can be partially populated — name the missing piece so
    // a thin result set isn't mistaken for an absence of nearby facilities.
    const showNote = () => {
      const cov = (CATEGORIES[sel.value] || {}).coverage_note;
      note.textContent = cov ? `${cov} ${base}` : base;
    };
    sel.addEventListener("change", showNote);
    showNote();
    note.hidden = false;
  } catch (e) { fallback(); }
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const address = document.getElementById("address").value.trim();
  const category = document.getElementById("category").value;
  if (!address) return showError("Please enter an address to check.", true);
  if (BUSY) return;

  const btn = document.getElementById("submit-btn");
  BUSY = true;
  // aria-disabled, not disabled: a disabled control leaves the focus order, so
  // focus fell to <body> and a screen reader user lost their place mid-wait.
  btn.setAttribute("aria-disabled", "true"); btn.textContent = "Checking\u2026";
  resultsEl.hidden = true;
  resultsEl.setAttribute("aria-busy", "true");
  clearError();
  showStatus("Checking your address. This usually takes 20 to 30 seconds.");

  // No timeout meant a request that never completed left the button disabled
  // and the status frozen, recoverable only by reloading. The wake-up notice
  // that the beta widget shows is deliberately NOT here: this client is served
  // by the local dev server, where "the server is asleep" would be false.
  const ctrl = new AbortController();
  const bail = setTimeout(() => ctrl.abort(), 150000);

  try {
    const resp = await fetch("/api/score", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ address, category }),
      signal: ctrl.signal,
    });
    clearTimeout(bail);
    const data = await resp.json();
    if (!data.ok) return showError(errorText(data), FIELD_ERRORS.has(data.error));
    clearStatus();
    render(data);
  } catch (err) {
    clearTimeout(bail);
    showError(err && err.name === "AbortError"
      ? "The server didn't answer within two and a half minutes."
      : "Could not reach the lookup service. Is the server running?");
  } finally {
    clearTimeout(bail);
    BUSY = false;
    btn.removeAttribute("aria-disabled"); btn.textContent = "Check access";
    resultsEl.removeAttribute("aria-busy");
  }
});

/* Status and error are two always-rendered regions that are never `hidden`.
   Toggling `hidden` removes the node from the accessibility tree, and a live
   region absent from the tree when its text changes announces nothing: that is
   the single most common way a loading state goes silent. Two regions rather
   than one because role cannot be swapped reliably at runtime, and progress
   (polite) and failure (assertive) need different politeness. */
let BUSY = false;

const FIELD_ERRORS = new Set([
  "address_not_found", "missing_address", "address_needs_city",
  "outside_coverage_area",
]);

function showStatus(msg) { statusEl.textContent = msg; }
function clearStatus() { statusEl.textContent = ""; }

function clearError() {
  errorEl.textContent = "";
  const input = document.getElementById("address");
  input.removeAttribute("aria-invalid");
  input.setAttribute("aria-describedby", "address-help");
}

// A bad address is the user's to fix, so flag the field and return the cursor.
// A dead geocoder is not: flagging it there tells someone their correct
// address is wrong.
function showError(msg, isFieldError) {
  clearStatus();
  errorEl.textContent = msg;
  if (!isFieldError) return;
  const input = document.getElementById("address");
  input.setAttribute("aria-invalid", "true");
  input.setAttribute("aria-describedby", "error address-help");
  input.focus();
}

function errorText(d) {
  if (d.error === "address_not_found")
    return "No match for that address. Try including the city, state, and ZIP (e.g. “975 W Faris Rd, Greenville, SC 29605”).";
  if (d.error === "data_not_loaded")
    return "This service’s location data isn’t loaded yet for the pilot area.";
  if (d.error === "geocoder_unavailable")
    return "The address-lookup service (US Census Geocoder) is temporarily unreachable. Please try again in a minute.";
  if (d.error === "no_facilities_with_coordinates")
    return "No mapped locations for this service type in the pilot area yet.";
  if (d.error === "outside_coverage_area") {
    const where = d.resolved_county ? `That address is in ${d.resolved_county}. ` : "That address is outside the pilot area. ";
      return where + "This tool currently covers Greenville County, South Carolina only. Several Upstate towns sit on a county line, so a nearby address may still work \u2014 try one, e.g. 206 S Main St, Greenville, SC 29601.";
  }
  if (d.error === "category_unavailable")
    return "That service type isn’t available in this pilot yet.";
  if (d.error === "bad_request") return "That request couldn’t be read. Please try again.";
  if (d.error === "missing_address") return "Please enter an address.";
  return "Something went wrong: " + (d.detail || d.error || "unknown error");
}

function render(d) {
  const n = d.nearest;
  const dr = d.drive;
  const bk = d.bike;
  const t = d.transit || {};
  const transitReachable = t.available && t.reachable;
  const it = transitReachable ? t.itinerary : null;

  let html = `
    <div class="card">
      <div class="result-head">
        <h2 id="answer-head" tabindex="-1">Nearest ${esc(labelFor(d.category))}</h2>
        <span class="badge">${esc(badgeFor(d.category, n.facility))}</span>
      </div>
      <p class="matched">From ${esc(d.origin.matched_address)}</p>

      <div class="modes">
        <div class="mode">
          <div class="mode-label">🚶 Walk</div>
          <div class="big">${min(n.walk_minutes)}</div>
          <div class="sub">${n.walk_network_mi} mi to ${esc(n.facility.name)}</div>
        </div>
        <div class="mode">
          <div class="mode-label">🚲 Bike</div>
          ${bk
            ? `<div class="big">${min(bk.bike_minutes)}</div>
               <div class="sub">${bk.bike_network_mi} mi to ${esc(bk.facility.name)}</div>`
            : `<div class="big unreach">—</div><div class="sub">no bike estimate</div>`}
        </div>
        <div class="mode">
          <div class="mode-label">🚗 Drive</div>
          ${dr
            ? `<div class="big">${min(dr.drive_minutes)}</div>
               <div class="sub">${dr.drive_network_mi} mi to ${esc(dr.facility.name)}</div>`
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
      <p class="privacy-inline" style="margin-top:8px">Walk: ${routingLabel(n.routing_method)}. Bike: ${bk ? routingLabel(bk.routing_method) : "not available"}. Drive: ${dr ? routingLabel(dr.routing_method) : "not available"}. Transit: Greenlink GTFS schedule (weekday midday).</p>

      <div class="facility">
        <div class="fname">${esc(n.facility.name)}</div>
        <div class="faddr">${esc(n.facility.address)}, ${esc(n.facility.city)}, ${esc(n.facility.state)} ${esc(n.facility.zip)}${n.facility.phone ? " · " + esc(n.facility.phone) : ""}</div>
      </div>
      ${insuranceLine(n.facility)}
      ${hoursLine(n.facility)}
      ${it ? transitBreakdown(it) : ""}
      ${alternatives(d.alternatives)}
      ${equityBlock(d.equity)}
    </div>`;
  resultsEl.innerHTML = html;
  resultsEl.hidden = false;

  // Focus the answer. Without this, focus stays on the button after a wait of
  // twenty-plus seconds and nothing tells a screen reader user the result
  // arrived, or where it went.
  const head = document.getElementById("answer-head");
  if (head) {
    try { head.focus({ preventScroll: true }); } catch (e) { head.focus(); }
    head.scrollIntoView({ block: "nearest" });
  }
}

// Insurance acceptance. Shown ONLY where it can be asserted — health centres,
// by Section 330 requirement. Everywhere else the honest statement is that we
// do not know, and saying nothing would let a reader assume the tool checked.
// A reachable clinic that will not take your insurance is not accessible, so
// an unqualified travel time is an upper bound on real access.
function insuranceLine(fac) {
  if (fac && fac.accepts_medicaid === true) {
    return '<p class="privacy-inline" style="margin:6px 0 0"><b>Accepts Medicaid.</b> '
      + esc(fac.accepts_medicaid_basis || "") + "</p>";
  }
  return '<p class="privacy-inline" style="margin:6px 0 0">Insurance acceptance '
    + "is <b>not verified</b> for this location. Travel time is an upper bound "
    + "on access — call ahead to check they take your coverage.</p>";
}

// Opening hours. Shown only where somebody actually asked; blank means nobody
// has, which is different from "open whenever". A 45-minute trip to a place
// that closed at 4:30 is not a 45-minute trip — three separate reviewers
// raised this, and there is no bulk source for it (HRSA gives hours-per-week
// as one number; OpenStreetMap covers 6% of county health sites), so it
// arrives one phone call at a time.
function hoursLine(fac) {
  // Mirrors dashboard/lookup-widget.js. Operator-published hours are their own
  // trust tier: better than an aggregator, not as good as a phone call.
  if (fac && fac.open_hours && fac.hours_provenance === "published_by_operator") {
    const when = fac.hours_read_on ? ", read " + esc(fac.hours_read_on) : "";
    return '<p class="privacy-inline" style="margin:4px 0 0"><b>Published hours:</b> '
      + esc(fac.open_hours) + " \u2014 from the provider's own website" + when
      + ", not confirmed by phone.</p>";
  }
  if (fac && fac.open_hours) {
    return '<p class="privacy-inline" style="margin:4px 0 0"><b>Hours:</b> '
      + esc(fac.open_hours) + "</p>";
  }
  return '<p class="privacy-inline" style="margin:4px 0 0">Opening hours '
    + "<b>not yet confirmed</b> for this location \u2014 worth calling before "
    + "you travel.</p>";
}

function labelFor(cat) {
  const c = CATEGORIES[cat];
  const label = c ? c.label : cat;
  return label.charAt(0).toLowerCase() + label.slice(1);  // "Nearest community health center…"
}

function badgeFor(cat, fac) {
  if (cat === "fqhc") return (fac.health_center_type || "").includes("Look-Alike") ? "FQHC Look-Alike" : "FQHC";
  // NPPES records carry their matched taxonomy — under the combined behavioral
  // health option that is what tells a therapy practice from a treatment center.
  if (fac && fac.taxonomy) return fac.taxonomy;
  const c = CATEGORIES[cat];
  return c ? (c.group || "Service") : "Service";
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
  // Suffix belongs inside the value branch — otherwise a missing value renders "—%".
  const cell = (v, suf) => (v == null ? "—" : `${v}${suf}`);
  const row = (label, a, b, suf = "") =>
    `<tr><td>${label}</td><td>${cell(a, suf)}</td><td>${cell(b, suf)}</td></tr>`;
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
          ${(eq.households_no_vehicle_pct && eq.households_no_vehicle_pct.tract != null)
            ? row("% households with no vehicle", eq.households_no_vehicle_pct.tract, eq.households_no_vehicle_pct.county, "%")
            : ""}
        </tbody>
      </table>
      <p class="note">ACS ${esc(eq.acs_vintage || "")} 5-year. Tract ${esc(eq.tract_fips)}.</p>
    </div>`;
}
