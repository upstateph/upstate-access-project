#!/usr/bin/env python3
"""Phase 4 — build MODELED access rollups for Greenville County, by geography.

For each area (census tract OR ZIP code / ZCTA), samples the area's internal point and
computes access to the nearest FQHC by walk, drive, and Greenlink transit (via the
engine). Writes one rollup per geography that feeds the dashboard's Greenville access
page (which lets the viewer switch between tract and ZIP, and between walk/drive/transit).

Modeled surface (one representative point per area), NOT observed usage — labeled as
such, not subject to k-anonymity suppression (no individuals). The k-anonymity machinery
in engine/aggregate.py is for real usage aggregation.

Tract geography also joins tract-level ACS income when available (needs a Census key);
ZCTA does not (ZIP-level ACS is a separate pull).

Usage:
    python build_access_rollup.py             # both tract and zcta
    python build_access_rollup.py tract       # one geography
"""
from __future__ import annotations

import sys
from pathlib import Path
from statistics import median

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR))

from common import DASHBOARD_DATA_DIR, PROCESSED_DIR, ensure_dirs, read_json, write_json  # noqa: E402
from engine.drive import rank_by_drive  # noqa: E402
from engine.facilities import load_facilities  # noqa: E402
from engine.transit import transit_to_facilities  # noqa: E402
from engine.walk import rank_by_walk  # noqa: E402

COUNTY_FIPS = "45045"
GEOGRAPHIES = {
    "tract": {"geojson": f"tracts_{COUNTY_FIPS}.geojson", "unit_label": "tract", "acs": True},
    "zcta": {"geojson": f"zcta_{COUNTY_FIPS}.geojson", "unit_label": "ZIP", "acs": False},
}


def build_one(geo: str, facilities: list[dict]) -> None:
    cfg = GEOGRAPHIES[geo]
    geojson_path = DASHBOARD_DATA_DIR / cfg["geojson"]
    if not geojson_path.exists():
        print(f"  [{geo}] SKIP — {geojson_path.name} missing "
              f"(run fetch_{'tract' if geo == 'tract' else 'zcta'}_geojson.py)")
        return
    feats = read_json(geojson_path)["features"]

    acs_by_id = {}
    if cfg["acs"]:
        acs_path = PROCESSED_DIR / f"census_acs_tracts_{COUNTY_FIPS}.json"
        if acs_path.exists():
            acs_by_id = {t["tract_fips"]: t for t in read_json(acs_path)["tracts"]}
            print(f"  [{geo}] joining ACS income for {len(acs_by_id)} tracts")

    print(f"  [{geo}] modeling access for {len(feats)} {cfg['unit_label']}s "
          f"to {len(facilities)} FQHCs (walk + drive + transit) ...")
    records = []
    for f in feats:
        p = f["properties"]
        gid = p["GEOID"]
        lat, lon = float(p["INTPTLAT"]), float(p["INTPTLON"])
        walk = rank_by_walk(lat, lon, facilities, k=1)
        drive = rank_by_drive(lat, lon, facilities, k=1)
        transit = transit_to_facilities(lat, lon, facilities)
        reachable = bool(transit.get("reachable"))

        rec = {
            "id": gid,
            "name": p.get("BASENAME", gid),
            "walk_min": walk[0].minutes if walk else None,
            "drive_min": drive[0].minutes if drive else None,
            "transit_min": transit["itinerary"]["total_minutes"] if reachable else None,
            "transit_reachable": reachable,
            "nearest_fqhc": walk[0].facility["name"] if walk else None,
        }
        acs = acs_by_id.get(gid)
        if acs:
            rec["median_household_income"] = acs.get("median_household_income")
            rec["pct_black"] = acs.get("pct_black")
        records.append(rec)

    walks = [r["walk_min"] for r in records if r["walk_min"] is not None]
    drives = [r["drive_min"] for r in records if r["drive_min"] is not None]
    transits = [r["transit_min"] for r in records if r["transit_min"] is not None]
    n_reach = sum(1 for r in records if r["transit_reachable"])

    out = {
        "county_fips": COUNTY_FIPS,
        "county": "Greenville County",
        "geography": geo,
        "unit_label": cfg["unit_label"],
        "category": "fqhc",
        "source": f"MODELED — engine access from each {cfg['unit_label']}'s internal point",
        "model_notes": (
            f"One representative point per {cfg['unit_label']} (Census internal point). "
            "Walk = 3 mph, drive = 25 mph effective, both 1.3x detour. Transit = "
            "RAPTOR-style <=1-transfer Greenlink, weekday midday. Modeled surface, not "
            "observed usage; no k-anonymity suppression needed."
        ),
        "acs_income_joined": bool(acs_by_id),
        "summary": {
            "n_units": len(records),
            "walk_min_median": round(median(walks), 1) if walks else None,
            "drive_min_median": round(median(drives), 1) if drives else None,
            "pct_units_transit_reachable": round(100 * n_reach / len(records), 1) if records else None,
            "transit_min_median": round(median(transits), 1) if transits else None,
            "n_units_no_transit": len(records) - n_reach,
        },
        "units": records,
    }
    fname = f"access_rollup_{geo}_{COUNTY_FIPS}.json"
    write_json(PROCESSED_DIR / fname, out, label=f"{fname} (processed)")
    write_json(DASHBOARD_DATA_DIR / fname, out, label=f"{fname} (site)")
    s = out["summary"]
    print(f"  [{geo}] done: {s['n_units']} {cfg['unit_label']}s; median walk "
          f"{s['walk_min_median']} / drive {s['drive_min_median']} min; "
          f"{s['pct_units_transit_reachable']}% transit-reachable.")


def main() -> None:
    ensure_dirs()
    which = [sys.argv[1]] if len(sys.argv) > 1 else list(GEOGRAPHIES)
    facilities = load_facilities("fqhc")
    for geo in which:
        if geo not in GEOGRAPHIES:
            sys.exit(f"Unknown geography '{geo}'. Options: {', '.join(GEOGRAPHIES)}")
        build_one(geo, facilities)


if __name__ == "__main__":
    main()
