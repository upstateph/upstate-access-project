/* Quick exit.
 *
 * The realistic privacy threat for this tool is not the network. Addresses
 * already travel in POST bodies, nothing is logged, and there are no accounts.
 * The threat is the device and the room: a shared phone, a browser history
 * entry, someone walking up behind you.
 *
 * So this does the two things that actually help in that moment:
 *   1. leaves immediately, and
 *   2. REPLACES the current history entry rather than adding to it, so pressing
 *      Back does not return to what was on screen.
 *
 * It cannot erase entries already in history. A tool that implied otherwise
 * would be worse than one that says plainly what it does, which is why the
 * button's own help text says "does not erase history".
 *
 * Escape pressed three times in quick succession does the same thing, for when
 * reaching for a button is not fast enough.
 */
(function () {
  "use strict";

  var SAFE_URL = "https://www.weather.gov/gsp/";   // innocuous, local, plausible
  var ESCAPE_COUNT = 3;
  var ESCAPE_WINDOW_MS = 1200;

  function leave() {
    try {
      // Replace, don't push: Back must not come here.
      window.location.replace(SAFE_URL);
    } catch (e) {
      window.location.href = SAFE_URL;
    }
  }

  function mount() {
    if (document.getElementById("quick-exit")) return;
    var b = document.createElement("button");
    b.id = "quick-exit";
    b.type = "button";
    b.textContent = "Quick exit";
    b.setAttribute("aria-label",
      "Quick exit: leave this page immediately. Does not erase browser history.");
    b.title = "Leaves this page at once. Press Escape three times to do the same. " +
              "This does not erase your browser history.";
    b.addEventListener("click", leave);
    document.body.appendChild(b);
  }

  var hits = [];
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    var now = (e.timeStamp || 0);
    hits.push(now);
    hits = hits.filter(function (t) { return now - t < ESCAPE_WINDOW_MS; });
    if (hits.length >= ESCAPE_COUNT) leave();
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})();
