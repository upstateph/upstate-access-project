#!/usr/bin/env python3
"""Cache one canonical address-lookup result for use in advocacy copy.

The downtown example ("a 14-minute walk, but an hour by bus, 36 minutes of it
waiting") is the project's most quotable finding, but it comes from a live engine
run rather than a rollup file — so the policy brief, the PDF briefs, and the
outreach draft were each carrying hand-typed copies that drift when the data or
the Greenlink schedule changes.

This caches the engine's answer to data/processed/lookup_example_downtown.json so
those documents can read it like any other published figure. Re-run it whenever
the GTFS feed or facility data is refreshed.

Uses a PUBLIC landmark address (a downtown commercial block), never a person's
address, and stores only what the documents quote.

    python build_lookup_example.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR))

from common import PROCESSED_DIR, ensure_dirs, write_json  # noqa: E402
from engine.score import score  # noqa: E402

# Public downtown landmark block — Greenville's Main Street commercial corridor.
EXAMPLE_ADDRESS = "206 S Main St, Greenville, SC 29601"
CATEGORY = "fqhc"


def main() -> None:
    ensure_dirs()
    result = score(EXAMPLE_ADDRESS, CATEGORY)
    if not result.get("ok"):
        sys.exit(f"ERROR: example lookup failed: {result.get('error')}")

    near = result["nearest"]
    fac = near["facility"]
    transit = result.get("transit") or {}
    it = transit.get("itinerary") if transit.get("reachable") else None

    out = {
        "address": EXAMPLE_ADDRESS,
        "category": CATEGORY,
        "note": ("Cached live engine result for a public downtown landmark address, so "
                 "advocacy copy can quote it without hand-typing figures. Re-run "
                 "build_lookup_example.py after any GTFS/facility refresh."),
        "facility_name": fac.get("name"),
        "facility_type": fac.get("health_center_type"),
        "walk_minutes": near.get("walk_minutes"),
        "walk_network_mi": near.get("walk_network_mi"),
        "routing_method": near.get("routing_method"),
        "drive_minutes": (result.get("drive") or {}).get("drive_minutes"),
        "transit_reachable": bool(it),
        "transit_total_minutes": it.get("total_minutes") if it else None,
        "transit_wait_minutes": it.get("wait_min") if it else None,
        "transit_in_vehicle_minutes": it.get("in_vehicle_min") if it else None,
        "transit_transfers": it.get("transfers") if it else None,
        "transit_model": transit.get("model"),
    }
    write_json(PROCESSED_DIR / "lookup_example_downtown.json", out,
               label="downtown lookup example")
    if it:
        print(f"Done: {out['walk_minutes']:.0f} min walk vs "
              f"{out['transit_total_minutes']:.0f} min transit "
              f"({out['transit_wait_minutes']:.0f} min waiting) to {out['facility_name']}.")


if __name__ == "__main__":
    main()
