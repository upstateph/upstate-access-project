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
from engine.facilities import CategoryWithheld  # noqa: E402
from engine.geocode import GeocoderUnavailable  # noqa: E402
from engine.score import score              # noqa: E402

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
        super().end_headers()

    def do_GET(self):
        if self.path.split("?")[0] == "/api/categories":
            self._serve_categories()
            return
        super().do_GET()

    def _serve_categories(self):
        try:
            data = json.loads(CATEGORIES_MANIFEST.read_text())
            data["categories"] = [c for c in data["categories"] if c.get("public_ready")]
            self._json(data, 200)
        except FileNotFoundError:
            self._json({"categories": [], "error": "manifest_missing"}, 503)

    def do_POST(self):
        if self.path.split("?")[0] != "/api/score":
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

    def _json(self, obj, status):
        payload = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


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
        print(f"Upstate Access Project serving on http://{HOST}:{PORT}  "
              f"(dashboard at /, lookup at /lookup/)", flush=True)
        httpd.serve_forever()
        print("Shut down cleanly.", flush=True)


if __name__ == "__main__":
    main()
