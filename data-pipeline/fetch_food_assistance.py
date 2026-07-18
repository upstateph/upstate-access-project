#!/usr/bin/env python3
"""Build food-assistance facilities for Greenville County.

No clean programmatic feed exists for food pantries (HIFLD is gone; 211 has no open
API), so this is a curated, verified starter list geocoded via the Census Geocoder.
Expand it from the county 211 / Harvest Hope partner directory as needed.

Usage:
    python fetch_food_assistance.py
"""
from __future__ import annotations

from common import ensure_dirs, PROCESSED_DIR, write_json
from facility_common import build_facility

# name, address, city, zip, phone  (verified starter list — expand from 211/Harvest Hope)
PANTRIES = [
    ("Harvest Hope Food Bank — Greenville", "2818 White Horse Rd", "Greenville", "29611", "864-281-3995"),
    ("Salvation Army of Greenville", "417 Rutherford St", "Greenville", "29609", "864-235-4803"),
    ("Greer Relief & Resources Agency", "113C Berry Ave", "Greer", "29651", "864-848-5355"),
    ("First Christian Fellowship Outreach", "110 Montana St", "Greenville", "29611", ""),
]


def main() -> None:
    ensure_dirs()
    print(f"Geocoding {len(PANTRIES)} verified food-assistance sites ...")
    facilities = []
    for name, addr, city, zc, phone in PANTRIES:
        fac = build_facility("food", name=name, address=addr, city=city, state="SC",
                             zip_code=zc, phone=phone,
                             source="Curated verified list (211 / Harvest Hope)")
        if fac:
            facilities.append(fac)
            print(f"  + {name}")
        else:
            print(f"  WARN: could not geocode {name} ({addr})")

    write_json(PROCESSED_DIR / "facilities_food.json",
               {"category": "food", "county": "Greenville County",
                "source": "Curated verified list (211 / Harvest Hope)", "facilities": facilities},
               label=f"food assistance ({len(facilities)})")
    print(f"Done: {len(facilities)} food-assistance sites.")


if __name__ == "__main__":
    main()
