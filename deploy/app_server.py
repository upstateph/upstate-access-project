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
import sys
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingTCPServer

REPO_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = REPO_DIR / "dist"
sys.path.insert(0, str(REPO_DIR))          # so `import engine` works

from engine.geocode import GeocoderUnavailable  # noqa: E402
from engine.score import score              # noqa: E402

PORT = int(os.environ.get("PORT", "8000"))
HOST = os.environ.get("HOST", "0.0.0.0")
CATEGORIES_MANIFEST = DIST_DIR / "data" / "categories.json"


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
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            address = (body.get("address") or "").strip()
            category = (body.get("category") or "fqhc").strip()
            if not address:
                self._json({"ok": False, "error": "missing_address"}, 400)
                return
            result = score(address, category)      # address used transiently only
            self._json(result, 200 if result.get("ok") else 400)
        except GeocoderUnavailable:
            self._json({"ok": False, "error": "geocoder_unavailable"}, 503)
        except FileNotFoundError as e:
            self._json({"ok": False, "error": "data_not_loaded", "detail": str(e)}, 503)
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


def main() -> None:
    if not DIST_DIR.exists():
        sys.exit("dist/ not found — run `python deploy/build_site.py` first.")
    ThreadingTCPServer.allow_reuse_address = True
    with ThreadingTCPServer((HOST, PORT), Handler) as httpd:
        print(f"Upstate Access Project serving on http://{HOST}:{PORT}  "
              f"(dashboard at /, lookup at /lookup/)")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
