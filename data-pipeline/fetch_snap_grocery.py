#!/usr/bin/env python3
"""Build the grocery category for Greenville County from USDA SNAP retailer data.

Source: USDA FNS "SNAP Retailer Location data" (ArcGIS FeatureServer, ~252k records
nationally, no API key). Authoritative, since a store cannot accept SNAP without
being in it, and it is the only open national dataset of food retail with
coordinates.

WHY THIS FILTERS HARD. The county has 443 SNAP-authorized retailers and only 106
of them are places a household can do a grocery shop. The rest are convenience
stores, dollar stores, gas stations and specialty shops, which accept SNAP but do
not sell a week of food. Counting them would make food access look roughly four
times better than it is, and would do it in exactly the neighborhoods that have a
gas station and no supermarket. This mirrors the FQHC category's
`require_service_line` rule: the funding designation is not the service.

Kept:    Supermarket, Super Store, Grocery Store
Dropped: Convenience Store, Other, Specialty Store, Farmers and Markets,
         Restaurant Meals Program

Farmers markets are dropped despite being real food, because they are seasonal and
open a few hours a week; a travel-time answer that treats one as equivalent to a
supermarket would be wrong in the direction that matters.

Coordinates come from USDA and are used as-is rather than re-geocoded: they are
already the authoritative locations, and 106 Census Geocoder calls would add
nothing but load. Records are bbox-checked against the county's own tract geometry
so a mislabeled county field cannot smuggle in an out-of-area store.

Usage:
    python fetch_snap_grocery.py
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR / "data-pipeline"))

from common import ensure_dirs, PROCESSED_DIR, write_json  # noqa: E402

SERVICE = ("https://services1.arcgis.com/RLQu0rK7h4kbsBq5/arcgis/rest/services/"
           "snap_retailer_location_data/FeatureServer/0/query")
COUNTY_FIPS = "45045"
COUNTY = "GREENVILLE"
STATE = "SC"

# Store types that mean "you can buy a week of groceries here".
GROCERY_TYPES = {"Supermarket", "Super Store", "Grocery Store"}

TRACTS_GEOJSON = REPO_DIR / "dashboard" / "data" / f"tracts_{COUNTY_FIPS}.geojson"


def county_bbox() -> tuple[float, float, float, float] | None:
    """(min_lat, min_lon, max_lat, max_lon) from the county's own tract geometry."""
    if not TRACTS_GEOJSON.exists():
        return None
    lats: list[float] = []
    lons: list[float] = []

    def walk(coords):
        if (isinstance(coords, list) and len(coords) == 2
                and all(isinstance(c, (int, float)) for c in coords)):
            lons.append(float(coords[0]))
            lats.append(float(coords[1]))
            return
        for c in coords:
            if isinstance(c, list):
                walk(c)

    for f in json.loads(TRACTS_GEOJSON.read_text())["features"]:
        walk(f["geometry"]["coordinates"])
    if not lats:
        return None
    # A small pad, so a store on the county line is not dropped by rounding.
    return (min(lats) - 0.02, min(lons) - 0.02, max(lats) + 0.02, max(lons) + 0.02)


def fetch_raw() -> list[dict]:
    params = {
        "where": f"State='{STATE}' AND County='{COUNTY}'",
        "outFields": "*",
        "returnGeometry": "false",
        "resultRecordCount": "2000",
        "f": "json",
    }
    url = SERVICE + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=90) as r:
        payload = json.loads(r.read().decode("utf-8"))
    if "error" in payload:
        raise SystemExit(f"USDA service error: {payload['error']}")
    return [f["attributes"] for f in payload.get("features", [])]


def main() -> None:
    ensure_dirs()
    print(f"Fetching SNAP retailers for {COUNTY} County, {STATE} ...")
    rows = fetch_raw()
    print(f"  {len(rows)} SNAP-authorized retailers in the county")

    bbox = county_bbox()
    if bbox:
        print(f"  county bbox from tract geometry: "
              f"lat {bbox[0]:.3f}..{bbox[2]:.3f}, lon {bbox[1]:.3f}..{bbox[3]:.3f}")
    else:
        print("  WARN: no tract geometry, skipping the bbox check")

    kept: list[dict] = []
    dropped_type: dict[str, int] = {}
    dropped_bbox = 0
    for a in rows:
        stype = (a.get("Store_Type") or "").strip()
        if stype not in GROCERY_TYPES:
            dropped_type[stype] = dropped_type.get(stype, 0) + 1
            continue
        try:
            lat = float(a["Latitude"])
            lon = float(a["Longitude"])
        except (TypeError, ValueError, KeyError):
            dropped_bbox += 1
            continue
        if bbox and not (bbox[0] <= lat <= bbox[2] and bbox[1] <= lon <= bbox[3]):
            dropped_bbox += 1
            continue
        name = (a.get("Store_Name") or "").strip()
        addr = (a.get("Store_Street_Address") or "").strip()
        if not name or not addr:
            continue
        kept.append({
            "id": f"snap-{a.get('Record_ID')}",
            "name": name,
            "category": "grocery",
            "address": addr,
            "city": (a.get("City") or "").strip().title(),
            "state": STATE,
            "zip": str(a.get("Zip_Code") or "").strip(),
            "phone": "",
            "county_fips": COUNTY_FIPS,
            "lat": lat,
            "lon": lon,
            "store_type": stype,
            "source": "USDA FNS SNAP Retailer Location data",
        })

    print(f"  kept {len(kept)} grocery destinations")
    for t, n in sorted(dropped_type.items(), key=lambda kv: -kv[1]):
        print(f"    dropped {n:4d}  {t or '(blank type)'}")
    if dropped_bbox:
        print(f"    dropped {dropped_bbox:4d}  outside county bbox / no coordinates")

    write_json(PROCESSED_DIR / "facilities_grocery.json",
               {"category": "grocery", "county": "Greenville County",
                "source": "USDA FNS SNAP Retailer Location data",
                "filter": ("SNAP retailers of type " + ", ".join(sorted(GROCERY_TYPES))
                           + " only; convenience/dollar/specialty stores and farmers "
                             "markets excluded because they do not sell a week of food"),
                "facilities": kept},
               label=f"grocery ({len(kept)})")
    print(f"Done: {len(kept)} grocery destinations.")


if __name__ == "__main__":
    main()
