#!/usr/bin/env python3
"""Assemble the static site into dist/ for deployment.

dist/ layout:
  dist/index.html, greenville-access.html, *.css, *.js, data/   (from dashboard/)
  dist/lookup/index.html                                        (redirect stub)

docs/*.md are NOT published: no page links them (the privacy panel links the
GitHub copy), and they describe project history — including the pedestrian-
safety tracker, which was removed from the site on 2026-08-27
(archive/pedestrian-safety-tracker/).

The dashboard portion (dist/, minus /lookup and the API) is fully static and can be
uploaded to any static host on its own. The lookup tool needs the API (app_server.py).

    python deploy/build_site.py
"""
from __future__ import annotations

import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# Regenerated into dashboard/data/ by the pipeline, and deliberately NOT
# published. Keeps removed work (the pedestrian-safety tracker, off the site
# 2026-08-27 and archived) from leaking back in, and keeps sc_counties.geojson
# there as a pipeline input without shipping it.
#
# MODULE SCOPE ON PURPOSE, 4 Sep 2026. tools/weekly_debug.py imports this rather
# than keeping its own copy. check_dist_current compares the newest file in
# dashboard/ against the newest in dist/, and every night build_dashboard_data.py
# rewrites dashboard/data/dashboard.json, which is on this list. That made the
# freshness check WARN on every single scheduled run: permanently, and for a
# file that is excluded by design. A check that cries wolf nightly is how a real
# stale deploy gets ignored.
EXCLUDE_DATA = {"dashboard.json", "crash_corridors_45045.json",
                "fars_ped_points_45045.json", "sc_counties.geojson"}

DIST = REPO / "dist"
DASHBOARD = REPO / "dashboard"
LOOKUP = REPO / "lookup-tool"


def main() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    # Dashboard: everything except the dev-only serve.py, and everything in
    # EXCLUDE_DATA at module scope.
    for item in DASHBOARD.iterdir():
        if item.name == "serve.py":
            continue
        dest = DIST / item.name
        if item.is_dir():
            shutil.copytree(item, dest,
                            ignore=lambda d, names: [n for n in names if n in EXCLUDE_DATA])
        else:
            shutil.copy2(item, dest)

    # The published category manifest is served as a STATIC file from dist/, which
    # bypasses the public_ready filter /api/categories applies. Strip withheld
    # categories at build time so a seeded-but-unverified sensitive category can't
    # disclose its availability (or facility count) through the static copy.
    manifest = DIST / "data" / "categories.json"
    if manifest.exists():
        import json
        doc = json.loads(manifest.read_text())
        before = len(doc.get("categories", []))
        doc["categories"] = [c for c in doc.get("categories", [])
                             if c.get("public_ready") and not c.get("hidden")]
        manifest.write_text(json.dumps(doc, indent=2, ensure_ascii=False))
        print(f"  categories.json: published {len(doc['categories'])} of {before} "
              "(withheld categories stripped)")

        # Bake the maintenance line into the static page. It has to happen here
        # rather than in the widget, because the widget reads /api/categories and
        # GitHub Pages has no API: on Pages the widget degrades, and a freshness
        # line that only appears on the beta would be missing from the version
        # every printed flyer points at.
        import datetime as _d
        idx = DIST / "index.html"
        if idx.exists() and doc.get("generated_on"):
            d = _d.date.fromisoformat(doc["generated_on"])
            line = (f"{doc['live_facilities']:,} places across "
                    f"{doc['live_categories']} kinds of service. "
                    f"Last rebuilt {d.strftime('%-d %B %Y')}.")
            html = idx.read_text(encoding="utf-8")
            marker = '<p class="fine" id="site-freshness">'
            if marker in html:
                start = html.index(marker) + len(marker)
                end = html.index("</p>", start)
                idx.write_text(html[:start] + line + html[end:], encoding="utf-8")
                print(f"  freshness line: {line}")
            else:
                print("  WARN: #site-freshness not found in index.html; line not set")

    # The address lookup is no longer a separate app — it's embedded in the
    # Greenville access page (dashboard/lookup-widget.js) so there is ONE tool.
    # /lookup/ is kept only as a redirect, because that URL is already circulating.
    (DIST / "lookup").mkdir()
    (DIST / "lookup" / "index.html").write_text(
        '<!doctype html><meta charset="utf-8">'
        '<title>Address lookup — Upstate Access Project</title>'
        '<meta http-equiv="refresh" content="0; url=../greenville-access.html#lookup">'
        '<link rel="canonical" href="../greenville-access.html">'
        '<p>The address lookup now lives on the '
        '<a href="../greenville-access.html#lookup">Greenville County access page</a>.</p>\n'
    )

    # Belt and braces on the thing that must never happen. Nothing copies
    # facility data into dist/ today, and that is incidental rather than
    # enforced: it holds because dashboard/data/ happens not to contain
    # facilities_*.json. If that ever changes, this fails the build instead of
    # shipping a directory of stigma-sensitive addresses.
    SENSITIVE = ("abortion", "reproductive_health", "hiv_ryan_white", "substance_use")
    leaked = [p.relative_to(DIST) for p in DIST.rglob("facilities_*.json")
              if any(k in p.name for k in SENSITIVE)]
    if leaked:
        raise SystemExit(f"REFUSING TO BUILD: sensitive facility data in dist/: {leaked}")
    print(f"  sensitive-data check: no facilities_* file for {len(SENSITIVE)} "
          f"withheld categories in dist/")

    n = sum(1 for _ in DIST.rglob("*") if _.is_file())
    print(f"Built dist/ with {n} files.")
    print("  static dashboard: dist/index.html  ·  lookup: dist/lookup/index.html")


if __name__ == "__main__":
    main()
