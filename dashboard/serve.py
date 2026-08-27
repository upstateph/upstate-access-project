#!/usr/bin/env python3
"""Minimal static server for the static site (dashboard/).

Serves this directory on http://localhost:8137. chdir's to an absolute path up
front so it doesn't depend on the launch process's working directory.

    python3 serve.py [port]
"""
import http.server
import os
import socketserver
import sys

# Serve from an EXPLICIT directory rather than chdir'ing. SimpleHTTPRequestHandler
# calls os.getcwd() on every request, so relying on ambient cwd means the server
# 500s on every request if that directory later becomes unreadable — while still
# accepting connections, so it looks up. Seen in practice with a long-running dev
# server: "PermissionError: [Errno 1] Operation not permitted" from os.getcwd().
DASHBOARD_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8137


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DASHBOARD_DIR, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as httpd:
    print(f"Serving dashboard at http://localhost:{PORT}")
    httpd.serve_forever()
