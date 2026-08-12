#!/usr/bin/env python3
"""Phase 3 lookup server — address in, access result out.

Serves the static lookup UI and a small JSON API that wraps engine.score(). Runs
with stdlib only (no framework).

Privacy by design (docs/privacy-design.md):
  - No accounts, no login.
  - The address is sent via POST **body**, never a URL/query string.
  - Default request logging is DISABLED so the address is never written to logs.
  - Nothing about the request is persisted EXCEPT one de-identified usage record
    (category, tract FIPS, travel times — never the address, coordinates, chosen
    facility, or a timestamp). See record_usage below; UAP_NO_TELEMETRY=1 disables it.
  - Error responses never echo exception text (it can embed the address).

    python lookup-tool/server.py [port]      # default 8138
"""
from __future__ import annotations

import json
import os
import sys
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from socketserver import TCPServer

LOOKUP_DIR = Path(__file__).resolve().parent
REPO_DIR = LOOKUP_DIR.parent
sys.path.insert(0, str(REPO_DIR))          # so `import engine` works
os.chdir(LOOKUP_DIR)                        # serve the static UI from here

from engine.aggregate import anonymize_result  # noqa: E402  (after sys.path setup)
from engine.facilities import CategoryWithheld  # noqa: E402
from engine.geocode import GeocoderUnavailable  # noqa: E402
from engine.score import score              # noqa: E402  (after sys.path setup)

MAX_BODY_BYTES = 64 * 1024  # an address payload is a few hundred bytes

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8138

# De-identified usage telemetry (docs/privacy-design.md). Each successful lookup
# appends ONE line: category, tract FIPS, and travel times — never the address,
# coordinates, matched address, facility, timestamp, or anything else about the
# request. Powers the k-anonymized usage rollup (build_usage_rollup.py).
# Disable entirely with UAP_NO_TELEMETRY=1.
TELEMETRY_FILE = REPO_DIR / "data" / "usage" / "lookups.jsonl"
TELEMETRY_ENABLED = os.environ.get("UAP_NO_TELEMETRY", "") != "1"


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
        TELEMETRY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with TELEMETRY_FILE.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:  # noqa: BLE001 — telemetry must never break a lookup
        pass


class Handler(SimpleHTTPRequestHandler):
    # Privacy: suppress ALL default request logging (no address ever hits a log).
    def log_message(self, *args, **kwargs):
        return

    # DEV ONLY. Locally the dashboard is served static on :8137 (mirroring GitHub
    # Pages) while this API runs on :8138, so the embedded lookup widget makes a
    # cross-origin call. Production is same-origin and sends no CORS headers.
    DEV_ORIGIN = "http://localhost:8137"

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", self.DEV_ORIGIN)
        super().end_headers()

    def do_GET(self):
        # Serve the public category menu; everything else is static.
        if self.path.split("?")[0] == "/api/categories":
            self._serve_categories()
            return
        super().do_GET()

    def _serve_categories(self):
        manifest = REPO_DIR / "dashboard" / "data" / "categories.json"
        try:
            data = json.loads(manifest.read_text())
            # Only expose public-ready categories (non-sensitive, with data), and
            # skip `hidden` ones — those are backing stores for a composite entry
            # and would otherwise appear twice, once inside the composite and once
            # under their own label. For behavioral health that second listing is
            # the exact stigmatizing menu item the composite exists to remove.
            data["categories"] = [c for c in data["categories"]
                                  if c.get("public_ready") and not c.get("hidden")]
            self._json(data, 200)
        except FileNotFoundError:
            self._json({"categories": [], "error": "manifest_missing"}, 503)

    def do_POST(self):
        if self.path.split("?")[0] != "/api/score":
            self.send_error(404)
            return
        try:
            # A negative Content-Length would make rfile.read() read until EOF,
            # blocking this single-threaded server until the client disconnects —
            # one hostile socket would wedge it for everyone.
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
            result = score(address, category)          # address used transiently only
            if result.get("ok"):
                record_usage(category, result)         # de-identified: no address
            self._json(result, 200 if result.get("ok") else 400)
        except GeocoderUnavailable:
            self._json({"ok": False, "error": "geocoder_unavailable"}, 503)
        except CategoryWithheld:
            # Same response whether or not a seed file exists on disk.
            self._json({"ok": False, "error": "category_unavailable"}, 403)
        except ValueError:
            self._json({"ok": False, "error": "bad_request"}, 400)
        except FileNotFoundError:
            # Privacy: never echo str(e) — it names the server's absolute paths and
            # enumerates every facilities_*.json on disk (an existence oracle).
            self._json({"ok": False, "error": "data_not_loaded"}, 503)
        except Exception as e:  # noqa: BLE001
            # Privacy: NEVER echo str(e) — third-party exceptions (requests, OSRM)
            # embed full request URLs, which can contain the address/coordinates.
            self._json({"ok": False, "error": "internal_error",
                        "detail": type(e).__name__}, 500)

    def _json(self, obj, status: int):
        payload = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main() -> None:
    with TCPServer(("127.0.0.1", PORT), Handler) as httpd:
        print(f"Lookup tool at http://localhost:{PORT}  (POST /api/score, no address logging)")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
