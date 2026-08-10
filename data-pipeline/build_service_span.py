#!/usr/bin/env python3
"""Build the time-of-day / service-span transit access rollup for Greenville County.

For each census tract's internal point, computes ≤1-transfer Greenlink access to the
nearest FQHC at several representative departure windows (weekday morning, midday,
evening peak, and Saturday midday). The point: a tract that is "transit-reachable"
at noon may have no usable trip at 8am, 5pm, or on the weekend — service span and
frequency, not just coverage, decide whether transit actually connects people to care.

MODELED surface (one representative point per tract), not observed usage — same
caveats as build_access_rollup.py; no k-anonymity needed.

Usage:
    python build_service_span.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from statistics import median

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR))

from common import DASHBOARD_DATA_DIR, PROCESSED_DIR, ensure_dirs, read_json, write_json  # noqa: E402
from engine.facilities import load_facilities  # noqa: E402
from engine.transit import transit_to_facilities  # noqa: E402

COUNTY_FIPS = "45045"
CATEGORY = "fqhc"

WINDOWS = [
    {"key": "wk_08", "label": "Weekday 8:00 am", "day": "weekday", "depart": "08:00:00"},
    {"key": "wk_12", "label": "Weekday midday", "day": "weekday", "depart": "12:00:00"},
    {"key": "wk_17", "label": "Weekday 5:00 pm", "day": "weekday", "depart": "17:00:00"},
    {"key": "sat_12", "label": "Saturday midday", "day": "saturday", "depart": "12:00:00"},
]
BASELINE = "wk_12"  # the window the main access rollup models


def main() -> None:
    ensure_dirs()
    geojson_path = DASHBOARD_DATA_DIR / f"tracts_{COUNTY_FIPS}.geojson"
    if not geojson_path.exists():
        sys.exit(f"ERROR: {geojson_path} missing — run fetch_tract_geojson.py first.")
    feats = read_json(geojson_path)["features"]
    facilities = load_facilities(CATEGORY)

    print(f"Modeling {len(WINDOWS)} departure windows x {len(feats)} tracts "
          f"to {len(facilities)} FQHCs ...")
    units = []
    for i, f in enumerate(feats):
        p = f["properties"]
        lat, lon = float(p["INTPTLAT"]), float(p["INTPTLON"])
        rec = {"id": p["GEOID"], "name": p.get("BASENAME", p["GEOID"])}
        for w in WINDOWS:
            t = transit_to_facilities(lat, lon, facilities,
                                      depart=w["depart"], day=w["day"])
            reachable = bool(t.get("reachable"))
            rec[w["key"]] = t["itinerary"]["total_minutes"] if reachable else None
        units.append(rec)
        if (i + 1) % 25 == 0:
            print(f"  {i + 1}/{len(feats)} tracts ...")

    summary = {}
    for w in WINDOWS:
        vals = [u[w["key"]] for u in units if u[w["key"]] is not None]
        lost_vs_baseline = sum(
            1 for u in units if u[BASELINE] is not None and u[w["key"]] is None)
        summary[w["key"]] = {
            "label": w["label"],
            "n_reachable": len(vals),
            "pct_reachable": round(100 * len(vals) / len(units), 1) if units else None,
            "transit_min_median": round(median(vals), 1) if vals else None,
            "n_lost_vs_midday": lost_vs_baseline if w["key"] != BASELINE else 0,
        }

    out = {
        "county_fips": COUNTY_FIPS,
        "county": "Greenville County",
        "category": CATEGORY,
        "geography": "tract",
        "baseline_window": BASELINE,
        "source": "MODELED — engine transit access from each tract's internal point",
        "model_notes": (
            "One representative point per tract (Census internal point). Transit = "
            "RAPTOR-style <=1-transfer Greenlink at each departure window, from the "
            "GTFS static schedule. Modeled surface, not observed usage."
        ),
        "windows": [{**w} for w in WINDOWS],
        "summary": summary,
        "units": units,
    }
    fname = f"service_span_tract_{COUNTY_FIPS}.json"
    write_json(PROCESSED_DIR / fname, out, label=f"{fname} (processed)")
    write_json(DASHBOARD_DATA_DIR / fname, out, label=f"{fname} (site)")
    for w in WINDOWS:
        s = summary[w["key"]]
        print(f"  {s['label']:>18}: {s['pct_reachable']}% reachable, "
              f"median {s['transit_min_median']} min"
              + (f", {s['n_lost_vs_midday']} tracts lose access vs midday"
                 if w["key"] != BASELINE else ""))


if __name__ == "__main__":
    main()
