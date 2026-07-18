#!/usr/bin/env python3
"""Fetch organization facilities from the NPPES NPI Registry (keyless), by taxonomy.

Used for categories the live directories cover as provider taxonomies — pharmacies and
urgent care. NPPES filters by city (not county), so we loop the county's cities, then
geocode and keep only facilities that land inside Greenville County.

Usage:
    python fetch_nppes.py pharmacy "Pharmacy"
    python fetch_nppes.py urgent_care "Urgent Care"
"""
from __future__ import annotations

import sys

import requests

from common import ensure_dirs, PROCESSED_DIR, write_json
from facility_common import build_facility

GREENVILLE_FIPS = "45045"
NPPES_URL = "https://npiregistry.cms.hhs.gov/api/"
# Cities in / around Greenville County (county filter is enforced by geocoding).
CITIES = ["Greenville", "Greer", "Simpsonville", "Mauldin", "Travelers Rest",
          "Fountain Inn", "Taylors", "Piedmont"]


def fetch_orgs(taxonomy_desc: str) -> list[dict]:
    seen, raw = set(), []
    for city in CITIES:
        params = {"version": "2.1", "enumeration_type": "NPI-2", "state": "SC",
                  "city": city, "taxonomy_description": taxonomy_desc, "limit": 200}
        results = requests.get(NPPES_URL, params=params, timeout=60).json().get("results", [])
        for res in results:
            npi = res.get("number")
            if npi in seen:
                continue
            seen.add(npi)
            loc = next((a for a in res.get("addresses", []) if a.get("address_purpose") == "LOCATION"), None)
            if not loc:
                continue
            raw.append({
                "name": (res.get("basic", {}) or {}).get("organization_name", ""),
                "address": loc.get("address_1", ""), "city": loc.get("city", ""),
                "state": loc.get("state", "SC"), "zip": (loc.get("postal_code", "") or "")[:5],
                "phone": loc.get("telephone_number", ""),
            })
    return raw


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit('Usage: python fetch_nppes.py <category> "<taxonomy_description>"')
    category, taxonomy = sys.argv[1], sys.argv[2]
    ensure_dirs()

    print(f"Fetching NPPES '{taxonomy}' orgs across {len(CITIES)} cities ...")
    raw = fetch_orgs(taxonomy)
    print(f"  {len(raw)} unique orgs; geocoding + filtering to Greenville County ...")

    facilities = []
    for r in raw:
        fac = build_facility(category, name=r["name"], address=r["address"], city=r["city"],
                             state=r["state"], zip_code=r["zip"], phone=r["phone"],
                             source="NPPES NPI Registry", keep_county_fips=GREENVILLE_FIPS)
        if fac:
            facilities.append(fac)

    # Dedupe by (name, address) after geocoding.
    uniq = {(f["name"].lower(), f["address"].lower()): f for f in facilities}
    facilities = sorted(uniq.values(), key=lambda f: f["name"])
    write_json(PROCESSED_DIR / f"facilities_{category}.json",
               {"category": category, "county": "Greenville County",
                "source": "NPPES NPI Registry", "taxonomy": taxonomy, "facilities": facilities},
               label=f"{category} ({len(facilities)})")
    print(f"Done: {len(facilities)} {category} facilities in Greenville County.")


if __name__ == "__main__":
    main()
