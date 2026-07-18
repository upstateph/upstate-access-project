#!/usr/bin/env python3
"""Bundle the statewide dashboard into ONE self-contained HTML for a shareable preview.

Inlines styles.css + app.js and embeds the data (dashboard.json + sc_counties.geojson)
behind a tiny fetch shim, so the page runs with no external requests (Artifact CSP).
The interactive address lookup + Greenville access map need the backend, so this
preview links out to them with a note rather than dead links.

    python deploy/build_artifact.py   ->   deploy/artifact.html
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DASH = REPO / "dashboard"
OUT = REPO / "deploy" / "artifact.html"


def main() -> None:
    css = (DASH / "styles.css").read_text()
    js = (DASH / "app.js").read_text()
    dashboard = json.loads((DASH / "data" / "dashboard.json").read_text())
    counties = json.loads((DASH / "data" / "sc_counties.geojson").read_text())

    body = (DASH / "index.html").read_text()
    body = body[body.index("<body>") + len("<body>"):body.index("</body>")]
    body = body.replace('<script src="app.js"></script>', "")

    # The tier-2 cross-link targets need the backend — replace with a note panel.
    note = ('    <section class="panel">\n'
            '      <h2 style="margin:0 0 4px;font-size:16px">Greenville County pilot</h2>\n'
            '      <p class="panel-sub" style="margin:0">The interactive address lookup '
            '(walk / drive / Greenlink transit to essential services) and the tract- and '
            'ZIP-level access map are part of the full deployment. This preview is the '
            'statewide tracker.</p>\n'
            '    </section>\n\n    <!-- KPI tiles -->')
    body = re.sub(r"<!-- Tier 2 cross-link -->.*?<!-- KPI tiles -->", note, body, flags=re.DOTALL)

    embed = {"data/dashboard.json": dashboard, "data/sc_counties.geojson": counties}
    shim = (
        "<script>\n"
        "const __EMBED = " + json.dumps(embed) + ";\n"
        "const __origFetch = window.fetch ? window.fetch.bind(window) : null;\n"
        "window.fetch = (u, ...a) => (u in __EMBED)\n"
        "  ? Promise.resolve({ ok: true, json: () => Promise.resolve(__EMBED[u]) })\n"
        "  : (__origFetch ? __origFetch(u, ...a) : Promise.reject(new Error('offline')));\n"
        "</script>"
    )

    html = (
        "<title>South Carolina Pedestrian Safety & Health-Equity Tracker</title>\n"
        f"<style>\n{css}\n</style>\n"
        f"{body}\n"
        f"{shim}\n"
        f"<script>\n{js}\n</script>\n"
    )
    OUT.write_text(html)
    print(f"Wrote {OUT.relative_to(REPO)} ({len(html) // 1024} KB, self-contained).")


if __name__ == "__main__":
    main()
