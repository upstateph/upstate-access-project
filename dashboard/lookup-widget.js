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
           style="display:inline-block;background:var(--accent,#0b6b5b);color:var(--on-accent,#fff);
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
      <!-- novalidate, with the required attribute kept for its semantics: it
           still maps to aria-required, so the field is announced as required.
           The browser's own validation bubble was doing this, and it
           auto-dismisses, is not reliably announced, and vanishes on the next
           keystroke. The handler below puts the message in the role=alert
           region instead, where it persists and is read out. -->
      <form class="form" id="lw-form" novalidate>
        <div class="field">
          <label for="lw-address">Where are you starting from?</label>
          <!-- autocomplete stays OFF on purpose, and a future accessibility
               audit should not "fix" it. Browser autofill would write the
               address into the device's form history, which is precisely the
               shared-phone threat quick-exit.js exists for. The help text is
               wired up with aria-describedby instead, so a screen reader user
               hears the same guidance a sighted one reads. -->
          <input id="lw-address" type="text" autocomplete="off"
                 autocorrect="off" spellcheck="false" enterkeyhint="go"
                 aria-describedby="lw-address-help"
                 placeholder="e.g. 206 S Main St, Greenville" required />
          <p class="privacy-inline" id="lw-address-help" style="margin:3px 0 0">Home, a shelter, a
            library, anywhere. Street and city is enough.</p>
        </div>
        <div class="field">
          <label for="lw-category">What do you need?</label>
          <select id="lw-category">${options}</select>
          <details class="privacy-inline" style="margin:3px 0 0">
            <summary style="cursor:pointer">Not seeing what you need?</summary>
            <p style="margin:4px 0 0">${cats.length} services are listed. HIV care
              and reproductive health are not, yet. I check every address by
              phone first, because a wrong one there can put someone at risk.</p>
          </details>
        </div>
        <button type="submit" id="lw-submit">Check my address</button>
        <div class="privacy-inline">🔒 I never save your address.
          <details style="display:inline-block"><summary style="cursor:pointer;text-decoration:underline">Where
          does it go?</summary> No account, no login. To find your location the
          address is sent once to the US Census Geocoder, and only map
          coordinates go to the OSRM routing service. Nothing is kept, not by
          me and not by this site.</details></div>
      </form>
      <p id="lw-status" class="status" role="status"></p>
      <p id="lw-error" class="status error" role="alert"></p>
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

  // `disabled` on the in-flight button looked right and broke keyboard use: a
  // disabled control is removed from the focus order, so the browser dropped
  // focus to <body> and a screen reader user lost their place for the whole
  // 25-second wait, then had to hunt for the result. aria-disabled keeps the
  // button focusable and announced as unavailable; BUSY does the real guarding.
  let BUSY = false;

  async function onSubmit(e) {
    e.preventDefault();
    if (BUSY) return;
    const input = document.getElementById("lw-address");
    const address = input.value.trim();
    const category = document.getElementById("lw-category").value;
    if (!address) {
      return showError("Please enter an address to check.", true);
    }

    const btn = document.getElementById("lw-submit");
    const results = document.getElementById("lw-results");
    BUSY = true;
    btn.setAttribute("aria-disabled", "true");
    btn.textContent = "Checking\u2026";
    results.hidden = true;
    results.setAttribute("aria-busy", "true");
    clearError();
    // Plain language on purpose. "Geocoding address and computing routes" is
    // the one string on the patient path written for the person who built it.
    showStatus("Checking your address. This usually takes 20 to 30 seconds.");

    // Escalate the message rather than the spinner, so the wait is explained
    // while it is happening instead of after it fails.
    const timers = WAKE_NOTICES.map(([ms, msg]) =>
      setTimeout(() => showStatus(msg), ms));
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
      if (!data.ok) return showError(errorText(data), FIELD_ERRORS.has(data.error));
      clearStatus();
      render(data);
    } catch (err) {
      clearTimers();
      showError(err && err.name === "AbortError"
        ? "No answer after two and a half minutes, which is longer than even a " +
          "cold start should take. Try once more. If it fails again, the " +
          "routing service is probably down."
        : "Could not reach the lookup service.");
    } finally {
      clearTimers();
      BUSY = false;
      btn.removeAttribute("aria-disabled");
      // Was "Check this address" here and "Check my address" in the markup, so
      // the button quietly renamed itself after every search. A control whose
      // accessible name changes on its own is a real defect for anyone
      // navigating by name, and confusing for everyone else.
      btn.textContent = "Check my address";
      results.removeAttribute("aria-busy");
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
    // Two reviewers tripped on this box: KD read it as leftover dev notes,
    // and SS counted it in "text heavy". It was 51 words, the most visually
    // prominent thing above the form, and about hosting rather than care.
    // WAKE_NOTICES already explains the delay AT 5s AND 35s, while someone is
    // actually waiting, which is when the explanation is welcome instead of an
    // obstacle. So this keeps only what has to be said before you commit.
    el.textContent = "Free test site. A check takes 20 to 30 seconds.";
    host.prepend(el);
  }

  /* Status and error are two separate regions, both rendered from first paint,
     both left EMPTY rather than hidden.

     The old single element was toggled with the `hidden` attribute, which takes
     the node out of the accessibility tree. A live region that is not in the
     tree when its text changes announces nothing at all: that is the documented
     and most common way live regions silently fail. So this one is never
     hidden and never display:none. Only the text changes, and `.status:empty`
     in the stylesheet collapses the empty box visually without removing it.

     Two regions rather than one because the politeness differs and `role`
     cannot be swapped reliably at runtime: progress is role="status" (polite,
     waits for a pause in speech), a failure is role="alert" (assertive,
     interrupts). Before this, a screen reader user pressed the button and heard
     nothing for the twenty-five seconds the lookup takes, then nothing when it
     landed. */
  function showStatus(msg) {
    document.getElementById("lw-status").textContent = msg;
  }

  function clearStatus() {
    document.getElementById("lw-status").textContent = "";
  }

  function clearError() {
    document.getElementById("lw-error").textContent = "";
    const input = document.getElementById("lw-address");
    if (input) {
      input.removeAttribute("aria-invalid");
      input.setAttribute("aria-describedby", "lw-address-help");
    }
  }

  // A bad address is the user's to fix, so mark the field invalid and put the
  // cursor back in it. A dead geocoder is not: flagging the field there would
  // tell someone their correct address is wrong. role="alert" announces both.
  const FIELD_ERRORS = new Set([
    "address_not_found", "missing_address", "address_needs_city",
    "outside_coverage_area",
  ]);

  function showError(msg, isFieldError) {
    clearStatus();
    document.getElementById("lw-error").textContent = msg;
    const input = document.getElementById("lw-address");
    if (input && isFieldError) {
      input.setAttribute("aria-invalid", "true");
      input.setAttribute("aria-describedby", "lw-error lw-address-help");
      input.focus();
    }
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

  // Pick the ONE thing to lead with.
  //
  // First attempt led with "the fastest car-free option" and headlined a
  // 93-MINUTE WALK for an address whose bike time was 27 minutes and whose bus
  // does not run. Two faults: it ignored cycling, and more importantly it
  // dressed up "you cannot realistically get here without a car" as an answer.
  //
  // So walking counts only while it is plausible, a bus trip counts whenever
  // one dependably exists, and when neither holds the headline says so
  // outright. That is not a failure state, it is the finding this whole tool
  // exists to surface, and burying it under a big number would be the one
  // dishonest thing the results screen could do.
  const WALK_LIMIT_MIN = 45;

  function headline(d) {
    const n = d.nearest, t = d.transit || {};
    const it = t.available && t.reachable ? t.itinerary : null;
    const walk = n && n.walk_minutes != null ? n.walk_minutes : null;
    const bus = it ? it.total_minutes : null;

    if (walk != null && walk <= WALK_LIMIT_MIN && (bus == null || walk <= bus)) {
      return { kind: "ok", mins: walk, verb: "walk", facility: n.facility };
    }
    if (bus != null) {
      return { kind: "ok", mins: bus, verb: "by bus", facility: t.facility };
    }
    return { kind: "car", facility: (d.drive && d.drive.facility) || n.facility,
             walk: walk, bike: d.bike ? d.bike.bike_minutes : null,
             drive: d.drive ? d.drive.drive_minutes : null };
  }

  function render(d) {
    const n = d.nearest, dr = d.drive, bk = d.bike, t = d.transit || {};
    const it = t.available && t.reachable ? t.itinerary : null;
    const h = headline(d);
    const fac = (h && h.facility) || n.facility;

    const otherModes = `
      <div class="modes">
        <div class="mode"><div class="mode-label">Walk</div>
          <div class="big">${min(n.walk_minutes)}</div>
          <div class="sub">${n.walk_network_mi} mi</div></div>
        <div class="mode"><div class="mode-label">Bike</div>
          ${bk ? `<div class="big">${min(bk.bike_minutes)}</div><div class="sub">${bk.bike_network_mi} mi</div>`
               : `<div class="big unreach">—</div><div class="sub">no estimate</div>`}</div>
        <div class="mode"><div class="mode-label">Drive</div>
          ${dr ? `<div class="big">${min(dr.drive_minutes)}</div><div class="sub">${dr.drive_network_mi} mi</div>`
               : `<div class="big unreach">—</div><div class="sub">no estimate</div>`}</div>
        <div class="mode"><div class="mode-label">Bus</div>
          ${it ? `<div class="big">${min(it.total_minutes)}</div>
                  <div class="sub">${it.transfers} transfer${it.transfers === 1 ? "" : "s"}</div>`
               : `<div class="big unreach">No bus</div>
                  <div class="sub">${esc(t.reason || "no route")}</div>`}</div>
      </div>
      <p class="privacy-inline" style="margin-top:8px">Walk: ${routingLabel(n.routing_method)}.
        Bike: ${bk ? routingLabel(bk.routing_method) : "not available"}.
        Drive: ${dr ? routingLabel(dr.routing_method) : "not available"}.
        Bus: ${esc(t.model || "Greenlink timetable")}.</p>`;

    document.getElementById("lw-results").innerHTML = `
      <div class="card">
        <div class="result-head">
          <h3 id="lw-answer-head" tabindex="-1"
              style="margin:0;font-size:15px;color:var(--ink-soft);font-weight:600">
            Closest ${esc(labelFor(d.category))}<span class="visually-hidden">. ${esc(spokenSummary(d, h, fac))} Full result follows.</span></h3>
          <span class="badge">${esc(badgeFor(d.category, fac))}</span>
        </div>

        ${h.kind === "ok"
          ? `<p class="answer"><span class="answer-num">${min(h.mins)}</span>
               <span class="answer-verb">${esc(h.verb)}</span></p>`
          : `<p class="answer"><span class="answer-num hard">Hard to reach<br>without a car</span></p>
             <p class="answer-note">${[
                 h.walk != null ? min(h.walk) + " walk" : null,
                 h.bike != null ? min(h.bike) + " bike" : null,
                 h.drive != null ? min(h.drive) + " drive" : null,
                 "no dependable bus",
               ].filter(Boolean).join(" · ")}</p>`}

        <div class="facility">
          <div class="fname">${esc(fac.name)}</div>
          ${fac.legal_name ? `<div class="faddr">registered as ${esc(fac.legal_name)}</div>` : ""}
          <div class="faddr">${esc(fac.address)}, ${esc(fac.city)}${fac.phone ? " · " + esc(fac.phone) : ""}</div>
        </div>

        ${insuranceLine(fac)}
        ${hoursLine(fac)}
        ${tripContextLine(d.category)}

        <details class="more"><summary>Other ways to get there</summary>${otherModes}</details>
        ${it ? `<details class="more"><summary>Bus route, step by step</summary>${breakdown(it, t.model)}</details>` : ""}
        ${alternatives(d.alternatives)}
        ${equityBlock(d.equity)}
        <details class="more"><summary>Free rides, and what this is based on</summary>
          ${ridesLine()}
          ${coverageLine(d.category)}
          <p class="privacy-inline" style="margin:6px 0 0">From ${esc(d.origin.matched_address)}.
            Times are estimates, not a timetable. Call ahead to check hours and coverage.</p>
        </details>
      </div>`;
    const results = document.getElementById("lw-results");
    results.hidden = false;

    /* Move focus to the answer.

       The user pressed a button and waited twenty-five seconds. Without this,
       focus is still on the button, the new content is somewhere below it, and
       a screen reader user has no signal that anything arrived: they have to
       guess that it worked and go looking. The heading carries a hidden
       one-sentence answer so the first thing spoken IS the answer, not the word
       "Closest". preventScroll keeps the viewport where the sighted user left
       it; scrollIntoView then places the card deliberately. */
    const head = document.getElementById("lw-answer-head");
    if (head) {
      try { head.focus({ preventScroll: true }); } catch (e) { head.focus(); }
      head.scrollIntoView({ block: "nearest" });
    }
  }

  /* The spoken form of the headline. `min()` renders "12 min", which a screen
     reader may read as "12 min" or "12 m"; speech gets the word spelled out.
     Kept in sync with headline() above, which decides what the answer IS. */
  function spokenSummary(d, h, fac) {
    const name = (fac && fac.name) || "the nearest location";
    if (h && h.kind === "ok") {
      const mins = Math.round(h.mins);
      const how = h.verb === "walk" ? "walk" : "by bus";
      return `${mins} minute${mins === 1 ? "" : "s"} ${how} to ${name}.`;
    }
    const parts = [];
    if (h && h.walk != null) parts.push(`${Math.round(h.walk)} minutes walking`);
    if (h && h.bike != null) parts.push(`${Math.round(h.bike)} minutes cycling`);
    if (h && h.drive != null) parts.push(`${Math.round(h.drive)} minutes driving`);
    parts.push("no dependable bus");
    return `Hard to reach without a car: ${name}, ${parts.join(", ")}.`;
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
    // Fourth tier, added 31 Aug: hours the operator publishes on its own site.
    // Stronger than an aggregator listing, weaker than a phone call. Earned its
    // own tier the day the SC Free Clinic Association directory turned out to be
    // stale on names, phone numbers, a ZIP and every satellite's hours while the
    // clinic's own page was current.
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
    return `<details class="more"><summary>Other nearby options (${alts.length})</summary>
      <div class="alts"><ul>` +
      alts.map((a) => {
        const street = a.facility.address ? ` · ${esc(a.facility.address)}` : "";
        return `<li><span>${esc(a.facility.name)}${street}</span>` +
               `<span>${min(a.walk_minutes)} walk</span></li>`;
      }).join("") +
      `</ul></div></details>`;
  }

  function equityBlock(eq) {
    if (!eq || !eq.available) return "";
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
    return `<details class="more"><summary>How this neighborhood compares</summary>
      <div class="equity">
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
      </div></details>`;
  }
})();
