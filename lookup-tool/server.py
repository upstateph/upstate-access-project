#!/usr/bin/env python3
"""Phase 3 lookup server — address in, access result out.

Serves the static lookup UI and a small JSON API that wraps engine.score(). Runs
with stdlib only (no framework).

Privacy by design (docs/privacy-design.md):
  - No accounts, no login.
  - The address is sent via POST **body**, never a URL/query string.
  - Default request logging is DISABLED so the address is never written to logs.
  - Nothing about the request is persisted anywhere.

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

from engine.score import score              # noqa: E402  (after sys.path setup)

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8138


class Handler(SimpleHTTPRequestHandler):
    # Privacy: suppress ALL default request logging (no address ever hits a log).
    def log_message(self, *args, **kwargs):
        return

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

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
            result = score(address, category)          # address used transiently only
            self._json(result, 200 if result.get("ok") else 400)
        except FileNotFoundError as e:
            self._json({"ok": False, "error": "data_not_loaded", "detail": str(e)}, 503)
        except Exception as e:  # noqa: BLE001 — return a clean error, don't leak a trace
            self._json({"ok": False, "error": "internal_error", "detail": str(e)}, 500)

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
