#!/usr/bin/env python3
"""Phase 5 — generate the policy brief + Greenlink outreach draft from real data.

Pulls from the Phase 1 dashboard data (FARS fatalities + Dangerous by Design context)
and the Phase 4 Greenville access rollup, and writes two Markdown deliverables:

  advocacy/policy-brief.md            — a short, cited policy brief
  advocacy/greenlink-outreach-draft.md — a DRAFT message for the Greenlink conversation

Both are regenerated from data so the numbers never drift. The outreach file is a
TEMPLATE ONLY — nothing is sent; a human reviews and sends it.

Usage:
    python advocacy/generate_brief.py
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
PROCESSED = REPO_DIR / "data" / "processed"
ADVOCACY = REPO_DIR / "advocacy"
GREENVILLE_FIPS = "45045"
GREENLINK_CONTACT = "GreenlinkTDP@greenvillesc.gov"


def load(name: str) -> dict:
    path = PROCESSED / name
    if not path.exists():
        raise SystemExit(f"Missing {path}. Run the Phase 1 and Phase 4 pipelines first.")
    return json.loads(path.read_text())


def main() -> None:
    dash = load("dashboard.json")
    access = load(f"access_rollup_{GREENVILLE_FIPS}.json")

    ctx = dash.get("context") or {}
    years = dash["years"]
    y0, y1 = years[0], years[-1]
    state_total = dash["state_total"]
    first_val = dash["state_totals_by_year"][str(y0)]
    last_val = dash["state_totals_by_year"][str(y1)]
    change_pct = round((last_val - first_val) / first_val * 100) if first_val else None
    gv = next((c for c in dash["counties"] if c["county_fips"] == GREENVILLE_FIPS), None)
    gv_total = gv["ped_total"] if gv else None

    s = access["summary"]
    acs_note = "" if access.get("acs_income_joined") else \
        " *(Income overlay pending a Census ACS pull — the access-by-income comparison " \
        "activates once tract demographics are added.)*"

    sources = ctx.get("sources", [])
    src_lines = "\n".join(f"{i+1}. {x['title']} — {x['url']}" for i, x in enumerate(sources))

    brief = f"""# Pedestrian safety & health-center access in Upstate South Carolina
### A data brief from the Upstate Access Project

*Generated from NHTSA FARS, Census/HRSA/Greenlink data, and Smart Growth America's
Dangerous by Design. Figures regenerate from the pipeline; see `docs/data-sources.md`.*

---

## The problem, in numbers

- **South Carolina is the #{ctx.get('state_rank', '—')} most dangerous state in the nation for people
  walking** ({ctx.get('report', 'Dangerous by Design')}, {ctx.get('publisher', '')}),
  at {ctx.get('state_annual_deaths_per_100k', '—')} pedestrian deaths per 100,000 residents per year.
- **{state_total:,} people were killed while walking in South Carolina from {y0}–{y1}** (NHTSA FARS),
  {"up " + str(change_pct) + "% over the period" if change_pct and change_pct > 0 else "a persistent toll"}.
- The Charleston and Columbia metros rank {", ".join("#" + str(m['national_rank']) for m in ctx.get('metros', []))
      if ctx.get('metros') else "among the worst"} nationally; the Upstate is not spared.
- **Greenville County alone recorded {gv_total} pedestrian fatalities** over {y0}–{y1}.

Pedestrian risk and health-care access are two sides of the same coin: the residents
least able to drive are the most exposed on foot **and** the most dependent on transit
to reach care.

## What our access analysis found (Greenville County)

Modeling travel time from every census tract to the nearest Federally Qualified Health
Center (FQHC){acs_note}:

- **Median walking time to the nearest FQHC is {s['walk_min_median']} minutes** — far beyond a
  reasonable walk for most residents.
- **Only {s['pct_tracts_transit_reachable']}% of tracts can reach an FQHC by Greenlink within a single
  transfer** (weekday midday). **{s['n_tracts_no_transit']} of {s['n_tracts']} tracts have no such trip at all.**
- Where transit does reach an FQHC, it takes a median of **{s['transit_min_median']} minutes** one way.

FQHCs are concentrated in the urban core; large parts of the county are effectively
cut off from them without a car.

## Why this matters

FQHCs exist specifically to serve low-income and uninsured patients. If reaching one
requires a car, the safety-net is out of reach for exactly the people it was built for —
the same people most exposed to pedestrian danger on Upstate roads.

## Recommendations

1. **Transit frequency and coverage where the safety-net is.** Prioritize Greenlink
   service improvements on corridors connecting underserved tracts to FQHC locations.
   The {ctx.get('edition_year', '')} Greenlink Transit Development Plan is the natural vehicle.
2. **Pedestrian-safety investment on the deadliest corridors,** aligned with the city's
   Pedestrian Safety Action Plan, focused where fatalities and low car-access overlap.
3. **Co-locate or extend clinic access** (mobile/satellite FQHC sites, or siting new
   service-delivery sites) in transit-reachable, currently-underserved tracts.
4. **Publish access as a standing metric.** Track "share of residents who can reach an
   FQHC within 30 minutes by transit" over time as service and siting change.

## Method & caveats

Travel times are **modeled** estimates (walking at 3 mph with a 1.3× street detour;
transit via a RAPTOR-style ≤1-transfer search of the Greenlink GTFS feed, weekday
midday) from one representative point per tract — not observed individual trips. They
are directionally reliable for identifying gaps, not exact door-to-door times. FQHC
locations are HRSA service-delivery sites. This is a pilot; verify specifics with
providers and the agency before acting.

## Sources

{src_lines}
5. NHTSA FARS (Fatality Analysis Reporting System), {y0}–{y1}
6. HRSA Health Center Service Delivery Sites; Greenlink GTFS feed
"""

    outreach = f"""# DRAFT — Greenlink outreach note (NOT SENT)

> **This is a template.** Review, edit, and send it yourself. Nothing here is
> transmitted automatically. Suggested recipient: `{GREENLINK_CONTACT}`.

---

**Subject:** Transit access to community health centers — a data offer for the TDP

Hello Greenlink Transit Development Plan team,

I'm Nikhil Jain, DO, MPH. I've built an open analysis of how reachable Greenville
County's Federally Qualified Health Centers (FQHCs) are by walking and by Greenlink
transit, tract by tract, using your public GTFS feed and HRSA facility data.

A few findings that may be useful for the TDP:

- Only **{s['pct_tracts_transit_reachable']}% of county census tracts** can reach an FQHC within a
  single Greenlink transfer (weekday midday); **{s['n_tracts_no_transit']} of {s['n_tracts']} tracts** have no
  such trip at all.
- Where transit does connect, the median trip is about **{s['transit_min_median']} minutes** one way.
- This lands on a population already at high pedestrian risk — South Carolina ranks
  #{ctx.get('state_rank', '—')} nationally for pedestrian danger, with {gv_total} pedestrian
  fatalities in Greenville County alone from {y0}–{y1}.

I'd welcome a conversation about which corridors would most improve safety-net access,
and I'm happy to share the underlying analysis (methods and data are fully documented
and reproducible). The intent is to be useful to your planning, not to critique.

Thank you for the work you do,
Nikhil Jain, DO, MPH
Upstate Access Project

---
*Figures above are modeled estimates from public data; see the project's data-source
and method notes. Verify against operational data before publication.*
"""

    (ADVOCACY / "policy-brief.md").write_text(brief)
    (ADVOCACY / "greenlink-outreach-draft.md").write_text(outreach)
    print("Wrote:")
    print("  advocacy/policy-brief.md")
    print("  advocacy/greenlink-outreach-draft.md  (DRAFT — not sent)")


if __name__ == "__main__":
    main()
