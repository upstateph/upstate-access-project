#!/usr/bin/env python3
"""Bundle the dashboards into self-contained HTML files for shareable previews.

Inlines styles.css + the page script and embeds the data files behind a tiny fetch
shim, so each page runs with no external requests (Artifact CSP / email attachment
friendly). The interactive address lookup needs the backend, so it is replaced with
a note rather than a dead link.

    python deploy/build_artifact.py
      ->  deploy/artifact.html          (statewide tracker)
      ->  deploy/artifact-access.html   (Greenville access map: rollup, time-of-day,
                                         crash corridors — the demo page)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DASH = REPO / "dashboard"


def bundle(page: str, script: str, data_files: list[str], title: str,
           out_name: str, body_tweaks=None) -> None:
    css = (DASH / "styles.css").read_text()
    js = (DASH / script).read_text()
    embed = {f"data/{name}": json.loads((DASH / "data" / name).read_text())
             for name in data_files}

    body = (DASH / page).read_text()
    body = body[body.index("<body>") + len("<body>"):body.index("</body>")]
    body = body.replace(f'<script src="{script}"></script>', "")
    if body_tweaks:
        body = body_tweaks(body)

    shim = (
        "<script>\n"
        "const __EMBED = " + json.dumps(embed, separators=(",", ":")) + ";\n"
        "const __origFetch = window.fetch ? window.fetch.bind(window) : null;\n"
        "window.fetch = (u, ...a) => (u in __EMBED)\n"
        "  ? Promise.resolve({ ok: true, json: () => Promise.resolve(__EMBED[u]) })\n"
        "  : (__origFetch ? __origFetch(u, ...a) : Promise.reject(new Error('offline')));\n"
        "</script>"
    )
    html = (
        f"<title>{title}</title>\n"
        f"<style>\n{css}\n</style>\n"
        f"{body}\n"
        f"{shim}\n"
        f"<script>\n{js}\n</script>\n"
    )
    out = REPO / "deploy" / out_name
    out.write_text(html)
    print(f"Wrote {out.relative_to(REPO)} ({len(html) // 1024} KB, self-contained).")


def statewide_tweaks(body: str) -> str:
    # The tier-2 cross-link targets need the backend — replace with a note panel.
    note = ('    <section class="panel">\n'
            '      <h2 style="margin:0 0 4px;font-size:16px">Greenville County pilot</h2>\n'
            '      <p class="panel-sub" style="margin:0">The interactive address lookup '
            '(walk / drive / Greenlink transit to essential services) needs the live '
            'deployment; the tract- and ZIP-level access map is bundled alongside this '
            'file as artifact-access.html.</p>\n'
            '    </section>\n\n    <!-- KPI tiles -->')
    return re.sub(r"<!-- Tier 2 cross-link -->.*?<!-- KPI tiles -->", note, body, flags=re.DOTALL)


def access_tweaks(body: str) -> str:
    # Standalone file: the back-link points at the statewide artifact next to it.
    return body.replace('href="index.html"', 'href="artifact.html"')


def main() -> None:
    bundle("index.html", "app.js",
           ["dashboard.json", "sc_counties.geojson"],
           "South Carolina Pedestrian Safety & Health-Equity Tracker",
           "artifact.html", statewide_tweaks)
    bundle("greenville-access.html", "greenville-access.js",
           ["access_rollup_tract_45045.json", "access_rollup_zcta_45045.json",
            "tracts_45045.geojson", "zcta_45045.geojson",
            "service_span_tract_45045.json", "crash_corridors_45045.json"],
           "Greenville County FQHC Access — Upstate Access Project",
           "artifact-access.html", access_tweaks)


if __name__ == "__main__":
    main()
