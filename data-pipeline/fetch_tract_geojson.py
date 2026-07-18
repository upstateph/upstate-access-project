#!/usr/bin/env python3
"""Fetch Census tract boundaries (+ internal points) for a county, for Phase 4.

Writes dashboard/data/tracts_<county_fips>.geojson. Each feature carries GEOID (the
11-digit tract FIPS) and INTPTLAT/INTPTLON (the Census "internal point" — a
representative point guaranteed to fall inside the tract), which the access rollup
samples. Geometry powers the Greenville access choropleth.

Source (verified July 2026, no key): Census TIGERweb REST, current Tracts layer.

Usage:
    python fetch_tract_geojson.py                 # Greenville County (45045)
    python fetch_tract_geojson.py 45079           # another SC county
"""
from __future__ import annotations

import json
import sys

import requests

from common import DASHBOARD_DATA_DIR, SC_STATE_FIPS, ensure_dirs

TIGERWEB = ("https://tigerweb.geo.census.gov/arcgis/rest/services/"
            "TIGERweb/Tracts_Blocks/MapServer/0/query")


def main() -> None:
    county_fips = sys.argv[1] if len(sys.argv) > 1 else "45045"
    county3 = county_fips[-3:]
    ensure_dirs()

    params = {
        "where": f"STATE='{SC_STATE_FIPS}' AND COUNTY='{county3}'",
        "outFields": "GEOID,INTPTLAT,INTPTLON,BASENAME",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "geojson",
    }
    print(f"Fetching tracts for county {county_fips} from TIGERweb ...")
    resp = requests.get(TIGERWEB, params=params, timeout=90)
    resp.raise_for_status()
    gj = resp.json()
    feats = gj.get("features", [])
    if not feats:
        sys.exit("ERROR: no tract features returned.")

    dest = DASHBOARD_DATA_DIR / f"tracts_{county_fips}.geojson"
    dest.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    print(f"  wrote {len(feats)} tracts -> {dest.relative_to(DASHBOARD_DATA_DIR.parent.parent)}")


if __name__ == "__main__":
    main()
