/* Housing-unit check: one address, four car-free answers.
 *
 * Deliberately renders four separate facts and never a composite. If you are
 * tempted to add a "3 of 4 — pretty good" badge here, read the page copy first:
 * which of the four failed is the actionable part, and a summary hides it.
 *
 * Privacy: the address goes out in a POST body, never a query string, and is
 * never written to storage or to the console.
 */
(function () {
  "use strict";

  // Static pages are served on :8137 by dashboard/serve.py, while the API runs
  // on :8138. In production both are the same origin.
  const apiBase = () => (location.port === "8137" ? "http://localhost:8138" : "");

  const form = document.getElementById("housing-form");
  const input = document.getElementById("addr");
  const button = document.getElementById("go");
  const statusEl = document.getElementById("status");
  const resultEl = document.getElementById("result");

  const esc = (s) => String(s == null ? "" : s)
    .replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  const mins = (m) => (m == null ? "not reachable" : `${Math.round(m)} min`);

  function setStatus(msg, isError) {
    if (!msg) { statusEl.hidden = true; return; }
    statusEl.hidden = false;
    statusEl.textContent = msg;
    statusEl.style.borderLeftColor = isError ? "#9a3412" : "";
  }

  const ERRORS = {
    address_not_found:
      "That address could not be found. Check the street number and spelling, " +
      "and include the city.",
    missing_address: "Enter an address first.",
    address_needs_city:
      "Add the city, for example \"206 S Main St, Greenville\". Without it that " +
      "street matched somewhere far outside the county. No ZIP code needed.",
    geocoder_unavailable:
      "The address lookup service is not responding right now. Try again shortly.",
    data_not_loaded:
      "The destination data has not been loaded on this server yet.",
    bad_request: "That request could not be read.",
    internal_error: "Something went wrong computing this one.",
  };

  function errorText(d) {
    if (d.error === "outside_coverage_area") {
      const where = d.resolved_county
        ? `That address is in ${d.resolved_county}.`
        : "That address falls outside the modeled county.";
      return `${where} This tool models ${d.coverage || "Greenville County"} only, ` +
             "so it cannot answer for that unit. That is a coverage boundary, not " +
             "a failing result for the address.";
    }
    return ERRORS[d.error] || "That did not work.";
  }

  function renderNeed(n) {
    const ok = !!n.reachable;
    const how = ok
      ? `${n.by === "walk" ? "on foot" : "by Greenlink"} · nearest: ${esc(n.nearest || "unknown")}`
      : (n.walk_min != null
          ? `nearest is ${esc(n.nearest || "unknown")}, ${Math.round(n.walk_min)} min walk, and no dependable bus trip`
          : "no reachable destination of this type");
    return `<li class="need ${ok ? "yes" : "no"}">
      <span class="mark" aria-hidden="true">${ok ? "✓" : "✕"}</span>
      <span class="body">
        <span class="what">${esc(n.label)}</span>
        <span class="how">${how}</span>
      </span>
      <span class="time">${ok ? esc(mins(n.best_min)) : "not reachable"}</span>
    </li>`;
  }

  function render(d) {
    const order = ["fqhc", "dss", "workforce", "grocery"];
    const items = order.filter((k) => d.needs && d.needs[k])
                       .map((k) => renderNeed(d.needs[k])).join("");

    let note;
    if (d.n_reachable === 4) {
      note = "All four are reachable without a car. Travel times still vary a lot; " +
             "a 100-minute trip is reachable and is still most of a day.";
    } else if (d.n_reachable === 0) {
      note = "None of the four is reachable without a car from this address.";
    } else {
      note = `Reachable: ${d.n_reachable} of 4. Not reachable: ` +
             `${(d.unreachable || []).join(", ")}.`;
    }

    resultEl.hidden = false;
    resultEl.innerHTML =
      `<ul class="need-list">${items}</ul>
       <p class="verdict-note">${esc(note)}</p>
       <p class="fine" style="margin-top:10px">${esc(d.model || "")}</p>
       <p class="fine">This is information for a decision, not the decision.</p>`;
  }

  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    const address = (input.value || "").trim();
    if (!address) { setStatus(ERRORS.missing_address, true); return; }

    resultEl.hidden = true;
    button.disabled = true;
    setStatus("Checking four destinations. This takes a few seconds.", false);

    try {
      const resp = await fetch(apiBase() + "/api/housing", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ address }),
      });
      const data = await resp.json();
      if (!data.ok) { setStatus(errorText(data), true); return; }
      setStatus("", false);
      render(data);
    } catch (err) {
      // Never surface the raw error: fetch failures can embed the request URL.
      setStatus("Could not reach the lookup service. If you are viewing this as a " +
                "static page, the API is not running here.", true);
    } finally {
      button.disabled = false;
    }
  });
})();
