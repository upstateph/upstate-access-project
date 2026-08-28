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
    betaNotice();
  }

  /* ---- static-only fallback ---- */
  // SS (FQHC practitioner, 28 Aug): a patient who clicks "I'm looking for
  // care" and lands on paragraphs has hit a dead end, whatever the paragraphs
  // say. So the static site's care door is ONE button, styled like the real
  // submit button, and the explanation is one small line under it.
  function renderUnavailable() {
    host.innerHTML = `
      <p style="margin:0 0 10px">
        <a href="${RENDER_BETA}/" target="_blank" rel="noopener" id="lw-open-beta"
           style="display:inline-block;background:var(--accent,#1f6feb);color:#fff;
                  font-weight:700;font-size:17px;padding:12px 22px;border-radius:8px;
                  text-decoration:none">Check my address →</a>
      </p>
      <p class="panel-sub" style="margin:0">
        Opens the live version of this tool. Free. The first load can take up
        to a minute to start.
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

    // SS (FQHC practitioner) twice, TM, and KD: too much text. The second SS
    // note named the mechanism — a wall of words makes a busy person fear they
    // are missing fine print, so they don't start at all. That is a VOLUME
    // problem, not a reading-level one, and a fourth rewrite of the same
    // paragraphs would not have fixed it.
    //
    // So: two fields, one button, and one short line each. Nothing was deleted.
    // The service count, the withheld categories, and the composite-coverage
    // note moved to where they are actually load-bearing — behind a five-word
    // summary, and into the RESULTS, where they explain what you are looking at
    // rather than standing between you and the search box.
    host.innerHTML = `
      <form class="form" id="lw-form">
        <div class="field">
          <label for="lw-address">Where are you starting from?</label>
          <input id="lw-address" type="text" autocomplete="off"
                 placeholder="e.g. 206 S Main St, Greenville" required />
          <p class="privacy-inline" style="margin:3px 0 0">Any address works:
            home, a shelter, a library. No ZIP code needed.</p>
        </div>
        <div class="field">
          <label for="lw-category">What do you need?</label>
          <select id="lw-category">${options}</select>
          <details class="privacy-inline" style="margin:3px 0 0">
            <summary style="cursor:pointer">Not seeing what you need?</summary>
            <p style="margin:4px 0 0">${cats.length} service type${cats.length === 1 ? "" : "s"}
              are listed today. Some, like HIV care and reproductive health, are
              not. We only add a service after a person checks every address,
              because a wrong address there can put someone at risk.</p>
          </details>
        </div>
        <button type="submit" id="lw-submit">Check my address</button>
        <div class="privacy-inline">🔒 We never save your address.
          <details style="display:inline-block"><summary style="cursor:pointer;text-decoration:underline">Where
          does it go?</summary> No account, no login. To find your location the
          address is sent once to the US Census Geocoder, and only map
          coordinates go to the OSRM routing service. Neither we nor this site
          keep any of it.</details></div>
      </form>
      <section id="lw-status" class="status" hidden></section>
      <section id="lw-results" hidden></section>`;

    document.getElementById("lw-form").addEventListener("submit", onSubmit);
  }

  // A composite category whose members aren't all live returns partial results,
  // and a behavioral-health search that silently omits every treatment center
  // looks like a finding ("nothing near me") rather than the gap it is. That
  // still has to be said — but it belongs WITH the results it qualifies, not
  // stacked above the search box where it is one more thing to read first.
  function coverageLine(cat) {
    const note = (CATEGORIES[cat] || {}).coverage_note;
    if (!note) return "";
    return '<p class="privacy-inline" style="margin:6px 0 0">' + esc(note) + "</p>";
  }

  /* ---- slow-request notice ----------------------------------------------

     A lookup genuinely takes 21-27 seconds, measured on the live beta with
     everything warm and working. It is not the hosting: profiling puts ~21 of
     those seconds inside three OSRM /table requests to the public FOSSGIS
     demo, run sequentially because that server's policy is one request per
     second. Sleep is a SECOND, additive cause — the free tier naps after ~15
     minutes idle and takes up to a minute to wake.

     An earlier version of this notice blamed sleep alone. That would have been
     wrong on most requests, since the twenty-five seconds happens every time.

     The page load itself cannot be narrated: if the server is asleep the
     browser is still waiting for HTML and none of our script is running. What
     is fixable is the wait after submit, which previously showed "Geocoding
     address and computing routes…" frozen for half a minute — indistinguishable
     from a hung tool. A reviewer who concludes it is broken does not write to
     say so; they just stop, and the feedback is lost without being given. */
  const WAKE_NOTICES = [
    [5000, "Still working. This normally takes 20 to 30 seconds. It routes " +
           "walking, driving and cycling against a shared public map server, " +
           "one request at a time, then plans the bus trip against Greenlink's " +
           "real timetable."],
    [35000, "Longer than usual. If this is the first check in a while, the free " +
            "server also has to wake up, which can add another minute. Nothing " +
            "is broken. It's worth waiting out once."],
  ];
  // 90 s was too tight: a cold start can spend up to 60 s waking the server and
  // THEN 27 s on the lookup, so a legitimate request would have been aborted
  // just before it answered. 150 s clears the worst realistic case.
  const REQUEST_TIMEOUT_MS = 150000;

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

    // Escalate the message rather than the spinner, so the wait is explained
    // while it is happening instead of after it fails.
    const timers = WAKE_NOTICES.map(([ms, msg]) =>
      setTimeout(() => showStatus(msg, false), ms));
    // No timeout at all meant a cold start that never completed left the button
    // disabled and the message frozen, with no way back except a page reload.
    const ctrl = new AbortController();
    const bail = setTimeout(() => ctrl.abort(), REQUEST_TIMEOUT_MS);
    const clearTimers = () => { timers.forEach(clearTimeout); clearTimeout(bail); };

    try {
      const resp = await fetch(api("/api/score"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ address, category }),
        signal: ctrl.signal,
      });
      clearTimers();
      const data = await resp.json();
      if (!data.ok) return showStatus(errorText(data), true);
      document.getElementById("lw-status").hidden = true;
      render(data);
    } catch (err) {
      clearTimers();
      showStatus(err && err.name === "AbortError"
        ? "No answer after two and a half minutes, which is longer than even a " +
          "cold start should take. Try once more. If it fails again, the " +
          "routing service is probably down."
        : "Could not reach the lookup service.", true);
    } finally {
      clearTimers();
      btn.disabled = false; btn.textContent = "Check this address";
    }
  }

  /* Standing notice, beta host only. A returning reader who already knows the
     server sleeps waits instead of leaving. Deliberately not shown on the
     Pages mirror, on localhost, or on a future VPS, where it would be false. */
  function betaNotice() {
    if (!/(^|\.)onrender\.com$/.test(location.hostname)) return;
    const el = document.createElement("p");
    el.className = "panel-sub";
    el.style.cssText = "margin:0 0 12px;padding:8px 10px;border-radius:6px;" +
      "background:#fff8e6;border:1px solid #f0dca8";
    // A reviewer (KD) read the old wording ("Beta, and slow on purpose rather
    // than broken") as leftover internal dev notes. Plainer now.
    el.textContent = "This is a free test site. A check takes about 20 to 30 " +
      "seconds, because it plans real road and bus trips one at a time. If " +
      "nobody has used the site for a while, the first check can take an " +
      "extra minute to wake the server up.";
    host.prepend(el);
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
      bad_request: "That request couldn't be read. Please try again.",
      missing_address: "Please enter an address.",
      address_needs_city: "Add the city, for example \"206 S Main St, Greenville\". Without it that street matched somewhere far outside the county. No ZIP code needed.",
    };
    if (d.error === "outside_coverage_area") {
    const where = d.resolved_county ? `That address is in ${d.resolved_county}. ` : "That address is outside the pilot area. ";
      return where + "This tool currently covers Greenville County, South Carolina only. Several Upstate towns sit on a county line, so a nearby address may still work \u2014 try one, e.g. 206 S Main St, Greenville, SC 29601.";
    }
    return m[d.error] || ("Something went wrong: " + (d.error || "unknown error"));
  }

  function render(d) {
    const n = d.nearest, dr = d.drive, bk = d.bike, t = d.transit || {};
    const it = t.available && t.reachable ? t.itinerary : null;
    document.getElementById("lw-results").innerHTML = `
      <div class="card">
        <div class="result-head">
          <h3 style="margin:0;font-size:17px">Closest ${esc(labelFor(d.category))} you can reach</h3>
          <span class="badge">${esc(badgeFor(d.category, n.facility))}</span>
        </div>
        <p class="matched">From ${esc(d.origin.matched_address)}</p>
        <div class="modes">
          <div class="mode"><div class="mode-label">🚶 Walk</div>
            <div class="big">${min(n.walk_minutes)}</div>
            <div class="sub">${n.walk_network_mi} mi to ${esc(n.facility.name)}</div></div>
          <div class="mode"><div class="mode-label">🚲 Bike</div>
            ${bk ? `<div class="big">${min(bk.bike_minutes)}</div>
                   <div class="sub">${bk.bike_network_mi} mi to ${esc(bk.facility.name)}</div>`
                 : `<div class="big unreach">—</div><div class="sub">no bike estimate</div>`}
          </div>
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
          Bike: ${bk ? routingLabel(bk.routing_method) : "not available"}.
          Drive: ${dr ? routingLabel(dr.routing_method) : "not available"}.
          Transit: ${esc(t.model || "Greenlink GTFS schedule")}.</p>
        <div class="facility">
          <div class="fname">${esc(n.facility.name)}</div>
          ${n.facility.legal_name ? `<div class="faddr">registered as ${esc(n.facility.legal_name)}</div>` : ""}
          <div class="faddr">${esc(n.facility.address)}, ${esc(n.facility.city)}, ${esc(n.facility.state)} ${esc(n.facility.zip)}${n.facility.phone ? " · " + esc(n.facility.phone) : ""}</div>
        </div>
        ${insuranceLine(n.facility)}
      ${hoursLine(n.facility)}
        ${coverageLine(d.category)}
        ${tripContextLine(d.category)}
        ${ridesLine()}
        ${it ? breakdown(it, t.model) : ""}
        ${alternatives(d.alternatives)}
        ${equityBlock(d.equity)}
      </div>`;
    document.getElementById("lw-results").hidden = false;
  }

  // Insurance acceptance. Shown ONLY where it can be asserted — health centers,
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
      + "on access. Call ahead to check they take your coverage.</p>";
  }

  // Trip-burden context, per category. SS (28 Aug): a walk that is fine for a
  // one-off visit is a different proposition for care that repeats on a
  // schedule. Only categories where the recurrence is a plain fact get a line;
  // inventing one for every category would dilute the two that matter.
  const TRIP_CONTEXT = {
    dialysis: "Dialysis usually happens three times a week, so this trip " +
      "repeats. A long or unreliable trip is a much bigger burden here than " +
      "for a one-time visit.",
    behavioral_health: "Counseling and treatment are usually recurring " +
      "appointments, so this trip may repeat weekly. Worth weighing the " +
      "round trip, not just one leg.",
  };
  function tripContextLine(cat) {
    const msg = TRIP_CONTEXT[cat];
    if (!msg) return "";
    return '<p class="privacy-inline" style="margin:6px 0 0">' + esc(msg) + "</p>";
  }

  // Free rides exist and almost nobody is told: SC Medicaid members can book
  // non-emergency medical transportation through ModivCare, the state's
  // broker. Number and rules verified against scdhhs.gov (transportation-
  // beneficiary-information) 28 Aug 2026: Greenville County is Region 1,
  // 1-866-910-7688, at least three days ahead, Mon-Fri 8-5. The line is
  // self-gating ("Have SC Medicaid?") so showing it on every result is honest.
  // No eligibility promises, and no transit-substitution rules: the
  // quarter-mile claim was checked 23 Aug and refuted.
  function ridesLine() {
    return '<p class="privacy-inline" style="margin:6px 0 0"><b>Have SC ' +
      "Medicaid?</b> Free rides to covered appointments can be arranged " +
      "through ModivCare, the state's ride service: <b>1-866-910-7688</b> " +
      "(call at least 3 days ahead, Mon-Fri 8-5).</p>";
  }

  // Opening hours. Shown only where somebody actually asked; blank means nobody
  // has, which is different from "open whenever". A 45-minute trip to a place
  // that closed at 4:30 is not a 45-minute trip — three separate reviewers
  // raised this, and there is no bulk source for it (HRSA gives hours-per-week
  // as one number; OpenStreetMap covers 6% of county health sites), so it
  // arrives one phone call at a time.
  function hoursLine(fac) {
    // Three tiers of trust (data-pipeline/triangulate_hours.py): a phone call
    // to the facility publishes alone; two agreeing public sources publish as
    // "reported"; anything less says so plainly. The label IS the product —
    // a wrong "open now" causes the exact wasted trip this tool exists to
    // prevent, so the reader always sees how sure we are.
    if (fac && fac.open_hours && fac.hours_provenance === "phone_verified") {
      const when = fac.hours_verified_on ? " (confirmed by phone, " + esc(fac.hours_verified_on) + ")" : " (confirmed by phone)";
      return '<p class="privacy-inline" style="margin:4px 0 0"><b>Hours:</b> '
        + esc(fac.open_hours) + when + "</p>";
    }
    if (fac && fac.open_hours && fac.hours_provenance === "reported") {
      const srcs = (fac.hours_sources || []).length;
      return '<p class="privacy-inline" style="margin:4px 0 0"><b>Reported hours:</b> '
        + esc(fac.open_hours) + " \u2014 from " + (srcs || "public")
        + " public listings, not yet confirmed with the facility. Worth a call "
        + "if the trip is long.</p>";
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

  // Alternatives carry their STREET, not just their name. Corporate chains
  // enumerate several clinics under one legal name — three of the county's
  // dialysis centers are all "TOTAL RENAL CARE INC" at three different
  // addresses — so a name-only list reads as the same place repeated, which
  // looks like a bug and hides a real choice between three locations.
  function alternatives(alts) {
    if (!alts || !alts.length) return "";
    return `<div class="alts"><h4>Other nearby options</h4><ul>` +
      alts.map((a) => {
        const street = a.facility.address ? ` · ${esc(a.facility.address)}` : "";
        return `<li><span>${esc(a.facility.name)}${street}</span>` +
               `<span>${min(a.walk_minutes)} walk</span></li>`;
      }).join("") +
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
          ? `, higher than <b>${Math.round(pctBelow)}%</b> of Greenville County neighborhoods.` : "."}</div>`
      : "";
    const cell = (v, suf) => (v == null ? "—" : `${v}${suf}`);
    const row = (label, a, b, suf = "") =>
      `<tr><td>${label}</td><td>${cell(a, suf)}</td><td>${cell(b, suf)}</td></tr>`;
    return `<div class="equity">
        <h4>Equity comparison: this neighborhood vs. Greenville County</h4>
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
