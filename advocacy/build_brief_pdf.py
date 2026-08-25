#!/usr/bin/env python3
"""Generate one-page PDF policy briefs from the project's published data.

Two audience variants (positioning per project rules — CLAUDE.md):
  officials, leads with pedestrian safety and access-to-care framing
  partners  — full framing including equity detail, for agencies/nonprofits

The crash-corridor map is drawn as VECTOR graphics straight from the data files
(no image conversion). Every number, including the downtown walk/transit example,
which is cached by data-pipeline/build_lookup_example.py, is read from published
JSON rather than hard-coded, so re-running after a data refresh keeps the brief
honest.

    python advocacy/build_brief_pdf.py --url https://... --email you@example.com
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "dashboard" / "data"

INK = HexColor("#1a1f2b")
SOFT = HexColor("#5b6472")
ACCENT = HexColor("#1f6feb")
DANGER = HexColor("#b4232a")
LINE = HexColor("#e4e7ec")


def load():
    rollup = json.loads((DATA / "access_rollup_tract_45045.json").read_text())
    span = json.loads((DATA / "service_span_tract_45045.json").read_text())
    crash = json.loads((DATA / "crash_corridors_45045.json").read_text())
    tracts = json.loads((DATA / "tracts_45045.geojson").read_text())
    dash = json.loads((DATA / "dashboard.json").read_text())
    example_path = REPO / "data" / "processed" / "lookup_example_downtown.json"
    example = json.loads(example_path.read_text()) if example_path.exists() else None
    return rollup, span, crash, tracts, dash, example


def draw_map(c, crash, tracts, x0, y0, w, h):
    """Vector crash-corridor map into the given box (page points)."""
    lons, lats = [], []

    def walk(geom, fn):
        polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        for poly in polys:
            for ring in poly:
                for lo, la in ring:
                    fn(lo, la)

    for f in tracts["features"]:
        walk(f["geometry"], lambda lo, la: (lons.append(lo), lats.append(la)))
    min_lon, max_lon, min_lat, max_lat = min(lons), max(lons), min(lats), max(lats)
    import math
    kx = math.cos(math.radians((min_lat + max_lat) / 2))
    scale = min(w / ((max_lon - min_lon) * kx), h / (max_lat - min_lat))
    ox = x0 + (w - (max_lon - min_lon) * kx * scale) / 2
    oy = y0 + (h - (max_lat - min_lat) * scale) / 2

    def P(lo, la):
        return ox + (lo - min_lon) * kx * scale, oy + (la - min_lat) * scale

    c.setLineWidth(0.4)
    c.setStrokeColor(LINE)
    for f in tracts["features"]:
        geom = f["geometry"]
        polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        for poly in polys:
            for ring in poly:
                p = c.beginPath()
                for i, (lo, la) in enumerate(ring):
                    xx, yy = P(lo, la)
                    (p.moveTo if i == 0 else p.lineTo)(xx, yy)
                p.close()
                c.drawPath(p, stroke=1, fill=0)

    for r in sorted(crash["corridors"], key=lambda r: r["n_deaths_near"]):
        hot = r["n_deaths_near"] > 0
        c.setStrokeColor(DANGER if hot else ACCENT)
        c.setLineWidth(1.1 if hot else 0.35)
        p = c.beginPath()
        for i, (la, lo) in enumerate(r["geometry"]):
            xx, yy = P(lo, la)
            (p.moveTo if i == 0 else p.lineTo)(xx, yy)
        c.drawPath(p, stroke=1, fill=0)

    for pt in crash["points"]:
        xx, yy = P(pt["lon"], pt["lat"])
        c.setStrokeColor(DANGER)
        c.setLineWidth(0.6)
        if pt["dark"]:
            c.setFillColor(DANGER)
            c.circle(xx, yy, 1.7, stroke=0, fill=1)
        else:
            c.circle(xx, yy, 1.7, stroke=1, fill=0)


def build(variant: str, url: str, email: str, out: Path) -> None:
    rollup, span, crash, tracts, dash, example = load()
    s = rollup["summary"]
    cs = crash["summary"]
    sp = span["summary"]
    prox = int(round(crash.get("proximity_m", 150)))
    W, H = letter
    m = 0.75 * inch
    c = canvas.Canvas(str(out), pagesize=letter)

    officials = variant == "officials"

    # Header
    c.setFillColor(ACCENT)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(m, H - m + 14, "UPSTATE ACCESS PROJECT  ·  GREENVILLE COUNTY DATA BRIEF")
    c.setFillColor(INK)
    title = ("Pedestrian safety and access to everyday services in Greenville County"
             if officials else
             "Can Greenville County residents actually reach care? Transit, walking, and safety")
    # Fit the title to the page instead of truncating at a character count.
    # title[:86] cut both titles mid-word at 17pt ("...Greenville Cou", "Transit,
    # walking" running off the edge), a character budget can't know the rendered
    # width. Shrink until it fits, which keeps the whole sentence.
    size = 17.0
    while size > 11 and c.stringWidth(title, "Helvetica-Bold", size) > (W - 2 * m):
        size -= 0.5
    c.setFont("Helvetica-Bold", size)
    c.drawString(m, H - m - 6, title)
    c.setFillColor(SOFT)
    c.setFont("Helvetica", 9.5)
    yrs = crash["years"]
    c.drawString(m, H - m - 22,
                 f"Nikhil Jain, DO, MPH · modeled from public data (NHTSA FARS {yrs[0]}–{yrs[-1]}, "
                 f"Greenlink GTFS, HRSA, Census ACS 2024)")

    # Three stat callouts
    # The lead callout used to be "N of M pedestrian deaths occurred within
    # <prox> m of a walking route to a health center". That interpretation is
    # WITHDRAWN — a null model captures more deaths (~59%) routing every tract to
    # a RANDOMLY CHOSEN health center than to the real nearest one, so the
    # statistic measures how much arterial road a route covers, not risk.
    # It is replaced with the plain fatality count, which is a FARS fact and
    # claims nothing about overlap. Do not reinstate the corridor version: these
    # PDFs are the attachments on the partner letters.
    stats = [
        (f"{cs['total_deaths_located']}",
         f"pedestrian deaths in Greenville County, {yrs[0]}-{yrs[-1]}, among the "
         "worst rates in the country (NHTSA FARS)"),
        (f"{s['n_units_no_transit']} of {s['n_units']}",
         "census tracts have no Greenlink trip to a community health center "
         "within one transfer"),
    ]
    if example and example.get("transit_reachable"):
        stats.append((
            f"{example['transit_wait_minutes']:.0f} min",
            f"of a {example['transit_total_minutes']:.0f}-minute midday transit trip to care "
            f"from downtown is spent waiting. The same trip is a "
            f"{example['walk_minutes']:.0f}-minute walk; frequency, not coverage, is the gap"))
    else:
        worst = max((sp[w] for w in sp if sp[w].get("transit_min_median")),
                    key=lambda x: x["transit_min_median"], default=None)
        base = sp.get(span.get("baseline_window", "wk_12"), {})
        stats.append((
            f"+{round(worst['transit_min_median'] - base['transit_min_median'])} min"
            if worst and base.get("transit_min_median") else "—",
            "longer median transit trip to care off-midday, frequency, not coverage, "
            "is the gap"))
    y = H - m - 46
    bw = (W - 2 * m - 24) / 3
    for i, (big, small) in enumerate(stats):
        bx = m + i * (bw + 12)
        c.setFillColor(DANGER if i == 0 else INK)
        c.setFont("Helvetica-Bold", 20)
        c.drawString(bx, y - 16, big)
        c.setFillColor(SOFT)
        c.setFont("Helvetica", 8)
        # crude wrap
        words, lines, cur = small.split(), [], ""
        for wd in words:
            if len(cur) + len(wd) + 1 > 34:
                lines.append(cur)
                cur = wd
            else:
                cur = (cur + " " + wd).strip()
        lines.append(cur)
        for j, ln in enumerate(lines[:5]):
            c.drawString(bx, y - 30 - j * 9.5, ln)

    # Map
    map_top = y - 86
    map_h = 3.35 * inch
    draw_map(c, crash, tracts, m, map_top - map_h, W - 2 * m - 2.1 * inch, map_h)

    # Map legend + reading
    lx = W - m - 1.95 * inch
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 9.5)
    # Descriptive map, not a finding. The heading previously read "Walking routes
    # to care vs. pedestrian deaths", which asserts the withdrawn overlap by
    # juxtaposition even with the stat callout gone.
    c.drawString(lx, map_top - 12, "Walking routes to care,")
    c.drawString(lx, map_top - 23, "with pedestrian deaths")
    items = [
        (DANGER, True, "death in darkness"),
        (DANGER, False, "death in daylight/other"),
        (DANGER, None, f"route with a death within {prox} m"),
        (ACCENT, None, "other modeled walking route"),
    ]
    ly = map_top - 40
    for color, filled, label in items:
        c.setStrokeColor(color)
        if filled is None:
            c.setLineWidth(1.4)
            c.line(lx, ly + 2.5, lx + 10, ly + 2.5)
        else:
            c.setLineWidth(0.8)
            if filled:
                c.setFillColor(color)
                c.circle(lx + 5, ly + 2.5, 2.2, stroke=0, fill=1)
            else:
                c.circle(lx + 5, ly + 2.5, 2.2, stroke=1, fill=0)
        c.setFillColor(SOFT)
        c.setFont("Helvetica", 8)
        c.drawString(lx + 15, ly, label)
        ly -= 12
    c.setFillColor(SOFT)
    c.setFont("Helvetica", 8)
    # The reading used to be "on the N worst corridors, every nearby death
    # happened in darkness, pointing at lighting and crossings". That is the
    # WITHDRAWN companion claim: 84.1% of ALL county pedestrian deaths occur in
    # darkness versus 85.7% near these corridors, so "every nearby death was in
    # darkness" restates the base rate for pedestrian deaths generally and says
    # nothing about these routes. Do not reinstate it, these PDFs are the
    # attachments on the partner and elected-official letters. What replaces it
    # is what the map can honestly carry: it is descriptive context, plus the
    # frequency finding, which survives.
    # State the withdrawal in the brief itself. The website says it plainly on
    # the same map, and a recipient may read both; a brief that shows the map
    # while staying silent about the retracted conclusion is the version that
    # looks worse later. It also means the reader learns it from us first.
    reading = (["An earlier version of this brief drew a",
                "safety conclusion from this map. It was",
                "withdrawn: a null model refutes it, so",
                "the map is context only.",
                "", f"Median trips run {sp['wk_08']['transit_min_median']:.0f} min at 8 am and",
                f"{sp['sat_12']['transit_min_median']:.0f} min Saturday vs "
                f"{sp['wk_12']['transit_min_median']:.0f} min midday:",
                "same coverage, thinner frequency."])
    for ln in reading:
        ly -= 10
        c.drawString(lx, ly, ln)

    # Ask / next steps
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 10.5)
    ask_y = map_top - map_h - 22
    c.drawString(m, ask_y, "What this offers" if officials else "Invitation to collaborate")
    c.setFont("Helvetica", 9)
    c.setFillColor(SOFT)
    ask = (
        "Free, open, corridor-level data for road-safety and transit planning, structured to plug into "
        "Greenlink's Transit Development Plan and the county's road and safety work. I'd welcome the chance "
        "to share the analysis with your office."
        if officials else
        "Open data and methods for aligning safety-net access, transit planning, and pedestrian-safety "
        "investment, available for joint analysis, data collection partnerships, and community validation."
    )
    words, lines, cur = ask.split(), [], ""
    for wd in words:
        if len(cur) + len(wd) + 1 > 105:
            lines.append(cur)
            cur = wd
        else:
            cur = (cur + " " + wd).strip()
    lines.append(cur)
    for j, ln in enumerate(lines):
        c.drawString(m, ask_y - 13 - j * 11, ln)

    # Method and limits. The bottom third of the page was empty, which reads as
    # a thin one-pager; more to the point, this is the section a policy staffer
    # looks for before citing anything, and stating the bounds ourselves is the
    # same posture as disclosing the withdrawal above.
    meth_y = ask_y - 13 - len(lines) * 11 - 24
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 10.5)
    c.drawString(m, meth_y, "Method and limits")
    c.setFont("Helvetica", 8.5)
    c.setFillColor(SOFT)
    method = [
        "Travel times are MODELED, not observed: one representative point per census tract (Census internal "
        "point) routed to the",
        "easiest facility to reach: NEAREST on foot or by car, BEST-CONNECTED by bus, which is not always the "
        "nearest. Someone",
        "already established at a particular site travels further, so these are a floor on travel burden rather "
        "than a typical trip.",
        "Walking and driving run on the real road network (OSRM), transit on Greenlink's published "
        "GTFS timetable",
        "(≤1 transfer, ≤30-minute wait, median over departures sampled across each hour). Facility locations come "
        "from HRSA, CMS,",
        "and NPPES. Modeled times will differ from any individual trip; they are for comparing places, not for "
        "planning a journey.",
        "Small-area counts are shown as points, never as rates. Reproductive health, HIV care, and substance-use "
        "treatment are",
        "deliberately withheld from the public tool until every address is verified by phone. A wrong address "
        "there is a safety issue.",
    ]
    for j, ln in enumerate(method):
        c.drawString(m, meth_y - 13 - j * 10, ln)

    # Footer
    c.setStrokeColor(LINE)
    c.setLineWidth(0.7)
    c.line(m, m + 26, W - m, m + 26)
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(ACCENT)
    c.drawString(m, m + 12, url)
    c.setFillColor(SOFT)
    c.setFont("Helvetica", 8)
    c.drawString(m, m + 1,
                 f"Contact: {email} · Modeled estimates from public data; methods and code are open at the "
                 "link above. Counts shown as points, never rates.")
    c.save()
    print(f"wrote {out.relative_to(REPO)}")


def main():
    ap = argparse.ArgumentParser()
    # Real values by default. These shipped as "[SITE URL]" and "[EMAIL]" —
    # literal placeholders in the footer of the PDFs that attach to the partner
    # and elected-official letters. A brief whose contact line reads "[EMAIL]"
    # is worse than no brief; defaults must be sendable.
    ap.add_argument("--url", default="https://upstateph.github.io/upstate-access-project/")
    ap.add_argument("--email", default="nikhilajain@gmail.com")
    args = ap.parse_args()
    outdir = REPO / "advocacy" / "briefs"
    outdir.mkdir(exist_ok=True)
    build("officials", args.url, args.email, outdir / "brief-officials.pdf")
    build("partners", args.url, args.email, outdir / "brief-partners.pdf")


if __name__ == "__main__":
    main()
