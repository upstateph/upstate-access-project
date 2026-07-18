#!/usr/bin/env python3
"""Fetch HRSA FQHC service-delivery sites for Greenville County, SC.

Tier 2 facility data (launch category = FQHC). Downloads HRSA's national
"Health Center Service Delivery and Look-Alike Sites" CSV, caches it, filters to
real brick-and-mortar sites in the target county, and writes
data/processed/facilities_fqhc.json in the engine's facility format.

Source (verified July 2026, no API key):
  https://data.hrsa.gov/DataDownload/DD_Files/Health_Center_Service_Delivery_and_LookAlike_Sites.csv
  (national, ~18.9k site rows, refreshed regularly)

Filtering (see docs/data-sources.md):
  - Complete County Name == target county (NOT 'County Description', which is junk)
  - Site Status Description == Active
  - Health Center Type Description in {Service Delivery Site,
    Administrative/Service Delivery Site}  (drop pure Administrative back-office)
  - Health Center Location Type Description == Permanent
    (drop Mobile Van / Seasonal — no fixed public destination)
  - Coordinates: X = longitude, Y = latitude

Usage:
    python fetch_hrsa_fqhc.py                        # Greenville County, incl. Look-Alikes
    python fetch_hrsa_fqhc.py --county "Richland County"
    python fetch_hrsa_fqhc.py --exclude-lookalikes
"""
from __future__ import annotations

import argparse

import pandas as pd
import requests

from common import PROCESSED_DIR, RAW_DIR, ensure_dirs, write_json

CSV_URL = (
    "https://data.hrsa.gov/DataDownload/DD_Files/"
    "Health_Center_Service_Delivery_and_LookAlike_Sites.csv"
)
RAW_CSV = RAW_DIR / "hrsa" / "health_center_sites.csv"

COL = {
    "site_name": "Site Name",
    "hc_name": "Health Center Name",
    "hc_type": "Health Center Type",                      # FQHC vs Look-Alike
    "type_desc": "Health Center Type Description",        # Service Delivery vs Administrative
    "loc_type": "Health Center Location Type Description",  # Permanent / Seasonal / Mobile Van
    "status": "Site Status Description",
    "address": "Site Address",
    "city": "Site City",
    "state": "Site State Abbreviation",
    "zip": "Site Postal Code",
    "phone": "Site Telephone Number",
    "county_name": "Complete County Name",
    "county_fips": "State and County Federal Information Processing Standard Code",
    "lon": "Geocoding Artifact Address Primary X Coordinate",
    "lat": "Geocoding Artifact Address Primary Y Coordinate",
}
KEEP_TYPE_DESC = {"Service Delivery Site", "Administrative/Service Delivery Site"}


def download_csv() -> None:
    RAW_CSV.parent.mkdir(parents=True, exist_ok=True)
    if RAW_CSV.exists() and RAW_CSV.stat().st_size > 0:
        print(f"  using cached {RAW_CSV.name}")
        return
    print(f"  downloading {CSV_URL} (~14 MB) ...")
    resp = requests.get(CSV_URL, timeout=180)
    resp.raise_for_status()
    RAW_CSV.write_bytes(resp.content)


def build(county: str, include_lookalikes: bool) -> list[dict]:
    df = pd.read_csv(RAW_CSV, dtype=str, low_memory=False)
    df.columns = [c.strip() for c in df.columns]

    m = (
        (df[COL["county_name"]].str.strip().str.casefold() == county.casefold())
        & (df[COL["status"]].str.strip() == "Active")
        & (df[COL["type_desc"]].str.strip().isin(KEEP_TYPE_DESC))
        & (df[COL["loc_type"]].str.strip() == "Permanent")
    )
    if not include_lookalikes:
        m &= df[COL["hc_type"]].str.contains("FQHC", case=False, na=False) & \
             ~df[COL["hc_type"]].str.contains("Look", case=False, na=False)

    sub = df[m].copy()
    facilities = []
    for _, r in sub.iterrows():
        try:
            lat = float(r[COL["lat"]]); lon = float(r[COL["lon"]])
        except (TypeError, ValueError):
            lat = lon = None  # keep the record but flag missing coords
        fips = (r.get(COL["county_fips"]) or "").strip() or None
        facilities.append({
            "id": (r.get(COL["site_name"]) or "").strip()[:60] or f"site-{len(facilities)}",
            "name": (r.get(COL["site_name"]) or "").strip(),
            "category": "fqhc",
            "health_center": (r.get(COL["hc_name"]) or "").strip(),
            "health_center_type": (r.get(COL["hc_type"]) or "").strip(),
            "address": (r.get(COL["address"]) or "").strip(),
            "city": (r.get(COL["city"]) or "").strip(),
            "state": (r.get(COL["state"]) or "").strip(),
            "zip": (r.get(COL["zip"]) or "").strip(),
            "phone": (r.get(COL["phone"]) or "").strip(),
            "county_name": (r.get(COL["county_name"]) or "").strip(),
            "county_fips": fips,
            "lat": lat,
            "lon": lon,
            "source": "HRSA Health Center Service Delivery Sites",
        })
    facilities.sort(key=lambda f: f["name"])
    return facilities


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--county", default="Greenville County")
    ap.add_argument("--exclude-lookalikes", action="store_true")
    args = ap.parse_args()

    ensure_dirs()
    print(f"HRSA FQHC sites for {args.county}:")
    download_csv()
    facilities = build(args.county, include_lookalikes=not args.exclude_lookalikes)

    with_coords = sum(1 for f in facilities if f["lat"] is not None)
    out = {
        "category": "fqhc",
        "county": args.county,
        "source": "HRSA Health Center Service Delivery and Look-Alike Sites",
        "source_url": CSV_URL,
        "filters": {
            "status": "Active",
            "type_description": sorted(KEEP_TYPE_DESC),
            "location_type": "Permanent",
            "include_lookalikes": not args.exclude_lookalikes,
        },
        "facilities": facilities,
    }
    write_json(PROCESSED_DIR / "facilities_fqhc.json", out,
               label=f"FQHC facilities ({len(facilities)} sites, {with_coords} geocoded)")
    print(f"Done: {len(facilities)} sites ({with_coords} with coordinates).")
    for f in facilities:
        print(f"  - {f['name']}  [{f['health_center_type']}]  {f['city']}")


if __name__ == "__main__":
    main()
