#!/usr/bin/env python3
"""Fetch SC county boundaries as GeoJSON for the dashboard choropleth.

Downloads the public US-counties GeoJSON (keyed by 5-digit FIPS), keeps only South
Carolina (FIPS starting "45"), and writes dashboard/data/sc_counties.geojson. Feature
`id` is the 5-digit county GEOID, which matches county_fips throughout this project.

Usage:
    python fetch_geojson.py
"""
from __future__ import annotations

import json

import requests

from common import DASHBOARD_DATA_DIR, SC_STATE_FIPS, ensure_dirs

SRC_URL = "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json"


def main() -> None:
    ensure_dirs()
    print(f"Downloading US county GeoJSON from {SRC_URL} ...")
    resp = requests.get(SRC_URL, timeout=120)
    resp.raise_for_status()
    gj = resp.json()

    sc = [f for f in gj["features"] if str(f.get("id", "")).startswith(SC_STATE_FIPS)]
    out = {"type": "FeatureCollection", "features": sc}

    dest = DASHBOARD_DATA_DIR / "sc_counties.geojson"
    dest.write_text(json.dumps(out))
    print(f"  wrote {len(sc)} SC counties -> {dest.relative_to(DASHBOARD_DATA_DIR.parent.parent)}")


if __name__ == "__main__":
    main()
