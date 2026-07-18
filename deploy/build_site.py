#!/usr/bin/env python3
"""Assemble the static site into dist/ for deployment.

dist/ layout:
  dist/index.html, greenville-access.html, *.css, *.js, data/   (from dashboard/)
  dist/lookup/index.html, styles.css, app.js                    (from lookup-tool/)
  dist/docs/*.md                                                (from docs/)

The dashboard portion (dist/, minus /lookup and the API) is fully static and can be
uploaded to any static host on its own. The lookup tool needs the API (app_server.py).

    python deploy/build_site.py
"""
from __future__ import annotations

import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DIST = REPO / "dist"
DASHBOARD = REPO / "dashboard"
LOOKUP = REPO / "lookup-tool"
DOCS = REPO / "docs"


def main() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    # Dashboard: everything except the dev-only serve.py
    for item in DASHBOARD.iterdir():
        if item.name == "serve.py":
            continue
        dest = DIST / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)

    # Lookup UI (frontend only; the API is served by app_server.py)
    (DIST / "lookup").mkdir()
    for name in ("index.html", "styles.css", "app.js"):
        shutil.copy2(LOOKUP / name, DIST / "lookup" / name)

    # Docs (linked from the pages)
    (DIST / "docs").mkdir()
    for md in DOCS.glob("*.md"):
        shutil.copy2(md, DIST / "docs" / md.name)

    n = sum(1 for _ in DIST.rglob("*") if _.is_file())
    print(f"Built dist/ with {n} files.")
    print("  static dashboard: dist/index.html  ·  lookup: dist/lookup/index.html")


if __name__ == "__main__":
    main()
