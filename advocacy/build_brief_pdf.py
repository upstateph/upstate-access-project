#!/usr/bin/env python3
"""Generate one-page PDF policy briefs from the project's published data.

Two audience variants (positioning per project rules — CLAUDE.md):
  officials — access-to-care framing (pedestrian safety left the project
              2026-08-27 and must not be used as a hook)
  partners  — full framing including equity detail, for agencies/nonprofits

The transit-reachability map is drawn as VECTOR graphics straight from the data
files (no image conversion). Every number, including the downtown walk/transit
example, which is cached by data-pipeline/build_lookup_example.py, is read from
published JSON rather than hard-coded, so re-running after a data refresh keeps
the brief honest.

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
    tracts = json.loads((DATA / "tracts_45045.geojson").read_text())
    example_path = REPO / "data" / "processed" / "lookup_example_downtown.json"
    example = json.loads(example_path.read_text()) if example_path.exists() else None
    return rollup, span, tracts, example


def draw_map(c, rollup, tracts, x0, y0, w, h):
    """Vector transit-reachability map into the given box (page points).

    One fact per tract: does a <=1-transfer Greenlink trip to a community health
    center exist from most sampled departures? Filled = no such trip. This is
    the map form of the lead stat, nothing more."""
    reach = {u["id"]: u.get("transit_reachable") for u in rollup["units"]}
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

    NO_TRANSIT = HexColor("#f3c9cb")
    for f in tracts["features"]:
        props = f.get("properties", {})
        geoid = props.get("GEOID") or props.get("geoid") or props.get("id")
        reachable = reach.get(geoid)
        geom = f["geometry"]
        polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        c.setLineWidth(0.4)
        c.setStrokeColor(LINE)
        fill = reachable is False
        if fill:
            c.setFillColor(NO_TRANSIT)
        for poly in polys:
            for ring in poly:
                p = c.beginPath()
                for i, (lo, la) in enumerate(ring):
                    xx, yy = P(lo, la)
                    (p.moveTo if i == 0 else p.lineTo)(xx, yy)
                p.close()
                c.drawPath(p, stroke=1, fill=1 if fill else 0)


def build(variant: str, url: str, email: str, out: Path) -> None:
    rollup, span, tracts, example = load()
    s = rollup["summary"]
    sp = span["summary"]
    W, H = letter
    m = 0.75 * inch
    c = canvas.Canvas(str(out), pagesize=letter)

    officials = variant == "officials"

    # Header
    c.setFillColor(ACCENT)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(m, H - m + 14, "UPSTATE ACCESS PROJECT  ·  GREENVILLE COUNTY DATA BRIEF")
    c.setFillColor(INK)
    title = ("Access to everyday health services in Greenville County"
             if officials else
             "Can Greenville County residents actually reach care? Transit, walking, and equity")
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
    c.drawString(m, H - m - 22,
                 "Nikhil Jain, DO, MPH · modeled from public data (Greenlink GTFS, OSRM road-network "
                 "routing, HRSA, Census ACS 2024)")

    # Three stat callouts. (History: the lead callout was once a pedestrian-
    # deaths figure; the corridor interpretation was withdrawn, and the whole
    # pedestrian-safety analysis left the project on 2026-08-27. Do not
    # reintroduce it here: these PDFs are the attachments on the letters.)
    pct_pop_no_transit = round(100 - s["pct_population_transit_reachable"])
    stats = [
        (f"{s['n_units_no_transit']} of {s['n_units']}",
         "census tracts have no Greenlink trip to a community health center "
         "within one transfer and a reasonable wait"),
        (f"{pct_pop_no_transit}%",
         "of county residents live in those tracts, where reaching care "
         "without a car means someone driving you"),
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
    draw_map(c, rollup, tracts, m, map_top - map_h, W - 2 * m - 2.1 * inch, map_h)

    # Map legend + reading
    lx = W - m - 1.95 * inch
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(lx, map_top - 12, "Transit access to a")
    c.drawString(lx, map_top - 23, "community health center")
    items = [
        (HexColor("#f3c9cb"), "no Greenlink trip within one transfer"),
        (HexColor("#ffffff"), "reachable within one transfer"),
    ]
    ly = map_top - 40
    for color, label in items:
        c.setStrokeColor(LINE)
        c.setLineWidth(0.8)
        c.setFillColor(color)
        c.rect(lx, ly - 1, 10, 8, stroke=1, fill=1)
        c.setFillColor(SOFT)
        c.setFont("Helvetica", 8)
        c.drawString(lx + 15, ly, label)
        ly -= 12
    c.setFillColor(SOFT)
    c.setFont("Helvetica", 8)
    reading = (["Reachable means a trip exists from",
                "most sampled departures, with at most",
                "one transfer and a 30-minute cap on",
                "any single wait.",
                "", f"Median trips run {sp['wk_08']['transit_min_median']:.0f} min at 8 am and",
                f"{sp['sat_12']['transit_min_median']:.0f} min Saturday vs "
                f"{sp['wk_12']['transit_min_median']:.0f} min midday:",
                "same coverage, thinner frequency.",
                "Frequency, not coverage, is the gap."])
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
        "Free, open, tract-level data on how long it takes residents to reach everyday health services, "
        "structured to plug into Greenlink's Transit Development Plan and the county's transportation "
        "planning. I'd welcome the chance to share the analysis with your office."
        if officials else
        "Open data and methods for aligning safety-net access with transit planning, available for joint "
        "analysis, data collection partnerships, and community validation."
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
