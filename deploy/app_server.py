#!/usr/bin/env python3
"""Unified production server: static site (dashboard + lookup) + JSON API.

Serves the built `dist/` site and the two API endpoints the lookup tool needs:
  GET  /api/categories   -> public category menu
  POST /api/score        -> engine.score(address, category)

Run `deploy/build_site.py` first to produce `dist/`. Configuration via env:
  PORT (default 8000), HOST (default 0.0.0.0), CENSUS_API_KEY, OSRM_* (see engine).

Privacy (docs/privacy-design.md): the address arrives in the POST body only, all
request logging is disabled, and nothing about a request is persisted.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import signal
import sys
import threading
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingTCPServer

REPO_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = REPO_DIR / "dist"
sys.path.insert(0, str(REPO_DIR))          # so `import engine` works

from engine.aggregate import anonymize_result  # noqa: E402
from engine.facilities import CategoryWithheld, is_known_category  # noqa: E402
from engine.geocode import GeocoderUnavailable  # noqa: E402
from engine.score import score              # noqa: E402
from engine.housing import housing_score  # noqa: E402

PORT = int(os.environ.get("PORT", "8000"))
HOST = os.environ.get("HOST", "0.0.0.0")
CATEGORIES_MANIFEST = DIST_DIR / "data" / "categories.json"
MAX_BODY_BYTES = 64 * 1024

# De-identified usage telemetry — same contract as lookup-tool/server.py: category,
# tract, travel times; never the address, coordinates, facility, or a timestamp.
# The UI tells users this count is kept, so the production server must actually
# keep it (and honor UAP_NO_TELEMETRY=1). This server is threaded, so appends are
# serialized with a lock.
TELEMETRY_FILE = REPO_DIR / "data" / "usage" / "lookups.jsonl"
# Self-listing suggestions. Local only and gitignored: it holds a submitter's
# name and email, which is personal data this project has no reason to publish.
SUGGESTIONS_FILE = REPO_DIR / "data" / "submissions" / "suggestions.jsonl"
_SUGGEST_LOCK = threading.Lock()
TELEMETRY_ENABLED = os.environ.get("UAP_NO_TELEMETRY", "") != "1"
_TELEMETRY_LOCK = threading.Lock()


def record_usage(category: str, result: dict) -> None:
    """Append a de-identified usage record. Never raises; never sees the address."""
    if not TELEMETRY_ENABLED:
        return
    try:
        rec = anonymize_result(result)
        if rec is None:
            return
        line = json.dumps({
            "category": category,
            "tract_fips": rec.tract_fips,
            "walk_minutes": rec.walk_minutes,
            "transit_minutes": rec.transit_minutes,
            "transit_reachable": rec.transit_reachable,
        })
        with _TELEMETRY_LOCK:
            TELEMETRY_FILE.parent.mkdir(parents=True, exist_ok=True)
            with TELEMETRY_FILE.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
    except Exception:  # noqa: BLE001 — telemetry must never break a lookup
        pass


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIST_DIR), **kwargs)

    def log_message(self, *args, **kwargs):  # privacy: no request logging
        return

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        # A click from a result page to a clinic's own website must not carry
        # this origin in the Referer header: the destination would learn the
        # visitor arrived from a health-access lookup. Costs nothing, and it is
        # the kind of leak that is invisible until it matters.
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def do_GET(self):
        if self.path.split("?")[0] == "/api/categories":
            self._serve_categories()
            return
        super().do_GET()

    def _serve_categories(self):
        try:
            data = json.loads(CATEGORIES_MANIFEST.read_text())
            # `hidden` entries back a composite category; listing them separately
            # would duplicate them and re-expose the label the composite hides.
            data["categories"] = [c for c in data["categories"]
                                  if c.get("public_ready") and not c.get("hidden")]
            self._json(data, 200)
        except FileNotFoundError:
            self._json({"categories": [], "error": "manifest_missing"}, 503)


    # ── Organization self-listing (PROTOTYPE) ────────────────────────────────
    # A reviewer asked whether organizations could add themselves. They can
    # SUGGEST themselves; nothing they submit appears in the tool.
    #
    # That is the whole design, and it is not friction for its own sake. Every
    # address in this project is verified by a person before publication,
    # because a wrong address is a wasted trip for someone who could not afford
    # the first one, and for the withheld categories it is a safety problem. A
    # self-serve listing that published on submit would discard the one property
    # the project is actually built around.
    #
    # So a submission becomes a row on the same verification worksheet a phone
    # call produces, and it waits for the same phone call. The form says so
    # plainly rather than implying a listing is imminent.
    def _handle_suggest(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            length = -1
        if length < 0 or length > MAX_BODY_BYTES:
            return self._json({"ok": False, "error": "bad_request"}, 400)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return self._json({"ok": False, "error": "bad_request"}, 400)
        if not isinstance(body, dict):
            return self._json({"ok": False, "error": "bad_request"}, 400)

        # Coerce and sanitize EVERY field the same way. A non-string value
        # crashed the handler outright: {"name": ["x"]} raised AttributeError on
        # .strip(), which returned an empty body rather than an error, so the
        # client showed nothing at all. Angle brackets are stripped because no
        # organization name, address or hours string legitimately contains them,
        # and this file is a queue a human will later paste into other tools.
        def field(key, limit):
            v = body.get(key)
            if not isinstance(v, (str, int, float)):
                return ""
            return str(v).replace("<", "").replace(">", "").strip()[:limit]

        name = field("name", 200)
        address = field("address", 200)
        if not name or not address:
            return self._json({"ok": False, "error": "missing_fields"}, 400)

        # Only the fields a verifier needs. Notably NOT a free-text description:
        # this is a queue for checking facts, not a place to publish copy, and an
        # open text box invites content nobody has agreed to host.
        rec = {
            "name": name,
            "address": address,
            "city": field("city", 100),
            "zip": field("zip", 10),
            "phone": field("phone", 40),
            "category": field("category", 60),
            "hours": field("hours", 200),
            "accepts": field("accepts", 200),
            "contact_name": field("contact_name", 100),
            "contact_email": field("contact_email", 120),
            "submitted_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            "status": "unverified",
        }
        try:
            SUGGESTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with _SUGGEST_LOCK:
                with SUGGESTIONS_FILE.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec) + "\n")
        except Exception:
            return self._json({"ok": False, "error": "could_not_record"}, 500)
        return self._json({"ok": True, "status": "queued_for_verification"}, 200)

    def do_POST(self):
        route = self.path.split("?")[0]
        if route == "/api/suggest":
            return self._handle_suggest()
        if route == "/api/housing":
            return self._handle_housing()
        if route != "/api/score":
            self.send_error(404)
            return
        try:
            try:
                length = int(self.headers.get("Content-Length", 0))
            except (TypeError, ValueError):
                length = -1
            if length < 0 or length > MAX_BODY_BYTES:
                self._json({"ok": False, "error": "bad_request"}, 400)
                return
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                self._json({"ok": False, "error": "bad_request"}, 400)
                return
            address = (body.get("address") or "").strip()
            category = (body.get("category") or "fqhc").strip()
            if not address:
                self._json({"ok": False, "error": "missing_address"}, 400)
                return
            # A category the manifest never declares is a CLIENT error, but it
            # used to reach the file layer and surface as 503 "data_not_loaded",
            # so a typo read as a server outage and a real missing-data incident
            # read as a typo. Answer exactly as for a withheld category: same
            # code, same body, so this adds no oracle.
            if not is_known_category(category):
                self._json({"ok": False, "error": "category_unavailable"}, 403)
                return
            result = score(address, category)      # address used transiently only
            if result.get("ok"):
                record_usage(category, result)     # de-identified: no address
            self._json(result, 200 if result.get("ok") else 400)
        except GeocoderUnavailable:
            self._json({"ok": False, "error": "geocoder_unavailable"}, 503)
        except CategoryWithheld:
            # Same response whether or not a seed file exists on disk.
            self._json({"ok": False, "error": "category_unavailable"}, 403)
        except ValueError:
            self._json({"ok": False, "error": "bad_request"}, 400)
        except FileNotFoundError:
            # Privacy: never echo str(e) — it names on-disk files (existence oracle).
            self._json({"ok": False, "error": "data_not_loaded"}, 503)
        except Exception as e:  # noqa: BLE001
            # Privacy: NEVER echo str(e) — third-party exceptions (requests, OSRM)
            # embed full request URLs, which can contain the address/coordinates.
            self._json({"ok": False, "error": "internal_error",
                        "detail": type(e).__name__}, 500)


    def _handle_housing(self):
        """POST /api/housing -> car-free access to the four placement needs.

        One address in, four travel times out. Same privacy contract as
        /api/score: the address is used transiently, never logged, and never
        echoed back in an error body.
        """
        # The route dispatch above happens before do_POST's try block, so this
        # handler carries its own. Without it an exception escapes uncaught, and
        # the rule that matters here is the one on str(e): third-party
        # exceptions embed full request URLs, which can carry the address.
        try:
            try:
                length = int(self.headers.get("Content-Length", 0))
            except (TypeError, ValueError):
                length = -1
            if length < 0 or length > MAX_BODY_BYTES:
                self._json({"ok": False, "error": "bad_request"}, 400)
                return
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                self._json({"ok": False, "error": "bad_request"}, 400)
                return
            address = (body.get("address") or "").strip()
            if not address:
                self._json({"ok": False, "error": "missing_address"}, 400)
                return
            result = housing_score(address)    # address used transiently only
            self._json(result, 200 if result.get("ok") else 400)
        except GeocoderUnavailable:
            self._json({"ok": False, "error": "geocoder_unavailable"}, 503)
        except CategoryWithheld:
            self._json({"ok": False, "error": "category_unavailable"}, 403)
        except ValueError:
            self._json({"ok": False, "error": "bad_request"}, 400)
        except FileNotFoundError:
            # Never echo str(e): it names on-disk files (existence oracle).
            self._json({"ok": False, "error": "data_not_loaded"}, 503)
        except Exception as e:  # noqa: BLE001
            self._json({"ok": False, "error": "internal_error",
                        "detail": type(e).__name__}, 500)

    def _json(self, obj, status):
        payload = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def report_feed_freshness() -> None:
    """Print the GTFS feed's service window at startup, loudly if it has expired.

    The image bakes the feed in at build time, and Docker will happily reuse a
    cached layer, so a rebuilt container can ship a months-old timetable. An
    expired feed does not error — the router just plans against a dead schedule —
    so this is the only place that staleness becomes visible.
    """
    try:
        from engine.transit import feed_status
        st = feed_status()
    except Exception:  # noqa: BLE001 — never block startup on a freshness check
        return
    if not st.get("available"):
        print(f"WARNING: transit unavailable — {st.get('reason')}", flush=True)
    elif st.get("expired"):
        print(f"WARNING: GTFS feed is STALE: {st['reason']}. Transit results are "
              "being computed from an expired timetable. Rebuild with "
              "--build-arg GTFS_REFRESH=$(date +%F).", flush=True)
    else:
        print(f"GTFS feed: service {st['first_service']}–{st['last_service']} "
              f"({st['days_left']} days left).", flush=True)


def install_shutdown_handlers(httpd) -> None:
    """Shut down cleanly on SIGTERM/SIGINT.

    Linux gives PID 1 no default signal dispositions: a signal with no explicitly
    registered handler is discarded. In a container this process IS PID 1, so
    without these handlers `docker stop` is ignored for its full timeout and the
    container is then SIGKILLed — dropping in-flight requests. Registering them
    makes termination graceful whether or not an init process is present.
    """
    def _shutdown(_signum, _frame):
        # shutdown() blocks until serve_forever() returns, so calling it from this
        # handler (which runs in the thread sitting inside serve_forever) would
        # deadlock. Hand it to a helper thread.
        threading.Thread(target=httpd.shutdown, daemon=True).start()

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _shutdown)


def main() -> None:
    if not DIST_DIR.exists():
        sys.exit("dist/ not found — run `python deploy/build_site.py` first.")
    ThreadingTCPServer.allow_reuse_address = True
    with ThreadingTCPServer((HOST, PORT), Handler) as httpd:
        install_shutdown_handlers(httpd)
        report_feed_freshness()
        print(f"Upstate Access Project serving on http://{HOST}:{PORT}  "
              f"(dashboard at /, lookup at /lookup/)", flush=True)
        httpd.serve_forever()
        print("Shut down cleanly.", flush=True)


if __name__ == "__main__":
    main()
