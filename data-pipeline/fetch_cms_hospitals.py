#!/usr/bin/env python3
"""Fetch hospitals & emergency rooms for Greenville County from CMS (keyless).

Source (verified July 2026): CMS Provider Data Catalog, "Hospital General Information"
(dataset xubh-q36u). Filterable by state + county; includes an emergency-services flag.
Addresses only — geocoded via the Census Geocoder into facilities_hospital.json.

Usage:
    python fetch_cms_hospitals.py
"""
from __future__ import annotations

import requests

from common import ensure_dirs, PROCESSED_DIR, write_json
from facility_common import build_facility

GREENVILLE_FIPS = "45045"
CMS_URL = "https://data.cms.gov/provider-data/api/1/datastore/query/xubh-q36u/0"


def main() -> None:
    ensure_dirs()
    params = {
        "conditions[0][property]": "state", "conditions[0][value]": "SC", "conditions[0][operator]": "=",
        "conditions[1][property]": "countyparish", "conditions[1][value]": "GREENVILLE", "conditions[1][operator]": "=",
    }
    print("Fetching CMS hospitals for Greenville County ...")
    rows = requests.get(CMS_URL, params=params, timeout=60).json().get("results", [])
    print(f"  {len(rows)} hospital records; geocoding ...")

    facilities = []
    for r in rows:
        er = str(r.get("emergency_services", "")).strip().lower() == "yes"
        fac = build_facility(
            "hospital",
            name=r.get("facility_name", ""), address=r.get("address", ""),
            city=r.get("citytown", ""), state=r.get("state", "SC"),
            zip_code=r.get("zip_code", ""), phone=r.get("telephone_number", ""),
            source="CMS Hospital General Information",
            keep_county_fips=GREENVILLE_FIPS,
            extra={"hospital_type": r.get("hospital_type", ""), "emergency_room": er},
        )
        if fac:
            facilities.append(fac)
            print(f"  + {fac['name']}{'  [ER]' if er else ''}")

    facilities.sort(key=lambda f: f["name"])
    write_json(PROCESSED_DIR / "facilities_hospital.json",
               {"category": "hospital", "county": "Greenville County",
                "source": "CMS Hospital General Information", "facilities": facilities},
               label=f"hospitals ({len(facilities)})")
    print(f"Done: {len(facilities)} hospitals ({sum(1 for f in facilities if f.get('emergency_room'))} with ER).")


if __name__ == "__main__":
    main()
