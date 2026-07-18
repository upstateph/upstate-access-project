#!/usr/bin/env python3
"""Phase 4 — build a MODELED tract-level access rollup for Greenville County.

For each Census tract, samples the tract's internal point and computes access to the
nearest FQHC by walk and by Greenlink transit (via the engine). Writes a per-tract
dataset that feeds the dashboard's Greenville access panel.

This is a **modeled** surface (one representative point per tract), NOT observed user
lookups — so it's labeled as such and is not subject to k-anonymity suppression (there
are no individuals here). The k-anonymity machinery in engine/aggregate.py is for real
usage aggregation; this script demonstrates the same tract-level output shape from a
privacy-safe modeled source.

If tract-level ACS has been pulled (census_acs_tracts_45045.json — needs a Census key),
the rollup also joins income so the dashboard can show access-vs-equity.

Usage:
    python build_access_rollup.py            # Greenville County (45045)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import median

# Make the engine importable when running this script directly.
REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR))

from common import DASHBOARD_DATA_DIR, PROCESSED_DIR, ensure_dirs, read_json, write_json  # noqa: E402
from engine.facilities import load_facilities  # noqa: E402
from engine.transit import transit_to_facilities  # noqa: E402
from engine.walk import rank_by_walk  # noqa: E402

COUNTY_FIPS = "45045"


def main() -> None:
    ensure_dirs()
    tracts_geo = DASHBOARD_DATA_DIR / f"tracts_{COUNTY_FIPS}.geojson"
    if not tracts_geo.exists():
        sys.exit(f"ERROR: {tracts_geo} missing. Run fetch_tract_geojson.py first.")
    feats = read_json(tracts_geo)["features"]
    facilities = load_facilities("fqhc")

    # Optional ACS tract join (income), if the key-gated pull has been run.
    acs_path = PROCESSED_DIR / f"census_acs_tracts_{COUNTY_FIPS}.json"
    acs_by_tract = {}
    if acs_path.exists():
        acs_by_tract = {t["tract_fips"]: t for t in read_json(acs_path)["tracts"]}
        print(f"  joining ACS income for {len(acs_by_tract)} tracts")

    print(f"Modeling access for {len(feats)} Greenville tracts "
          f"to {len(facilities)} FQHCs (walk + transit) ...")
    records = []
    for i, f in enumerate(feats, 1):
        p = f["properties"]
        geoid = p["GEOID"]
        lat, lon = float(p["INTPTLAT"]), float(p["INTPTLON"])
        walk = rank_by_walk(lat, lon, facilities, k=1)
        walk_min = walk[0].minutes if walk else None
        nearest_name = walk[0].facility["name"] if walk else None

        transit = transit_to_facilities(lat, lon, facilities)
        reachable = bool(transit.get("reachable"))
        transit_min = transit["itinerary"]["total_minutes"] if reachable else None

        rec = {
            "tract_fips": geoid,
            "name": p.get("BASENAME", geoid),
            "walk_min": walk_min,
            "transit_min": transit_min,
            "transit_reachable": reachable,
            "nearest_fqhc": nearest_name,
        }
        acs = acs_by_tract.get(geoid)
        if acs:
            rec["median_household_income"] = acs.get("median_household_income")
            rec["pct_black"] = acs.get("pct_black")
        records.append(rec)
        if i % 25 == 0:
            print(f"  {i}/{len(feats)} tracts")

    walks = [r["walk_min"] for r in records if r["walk_min"] is not None]
    n_reach = sum(1 for r in records if r["transit_reachable"])
    transits = [r["transit_min"] for r in records if r["transit_min"] is not None]

    out = {
        "county_fips": COUNTY_FIPS,
        "county": "Greenville County",
        "category": "fqhc",
        "source": "MODELED — engine access from each tract's Census internal point",
        "model_notes": (
            "One representative point per tract (Census internal point). Walk = 3 mph, "
            "1.3x detour. Transit = RAPTOR-style <=1-transfer Greenlink, weekday midday. "
            "Modeled surface, not observed usage; no k-anonymity suppression needed."
        ),
        "acs_income_joined": bool(acs_by_tract),
        "summary": {
            "n_tracts": len(records),
            "walk_min_median": round(median(walks), 1) if walks else None,
            "pct_tracts_transit_reachable": round(100 * n_reach / len(records), 1),
            "transit_min_median": round(median(transits), 1) if transits else None,
            "n_tracts_no_transit": len(records) - n_reach,
        },
        "tracts": records,
    }
    write_json(PROCESSED_DIR / f"access_rollup_{COUNTY_FIPS}.json", out, label="access rollup (processed)")
    write_json(DASHBOARD_DATA_DIR / f"access_rollup_{COUNTY_FIPS}.json", out, label="access rollup (site)")

    s = out["summary"]
    print(f"Done: {s['n_tracts']} tracts. Median walk {s['walk_min_median']} min; "
          f"{s['pct_tracts_transit_reachable']}% transit-reachable "
          f"({s['n_tracts_no_transit']} tracts with no ≤1-transfer FQHC trip).")


if __name__ == "__main__":
    main()
