#!/usr/bin/env python3
"""Build the government & social-services facilities for Greenville County.

These are a small, fixed set of offices verified against official .gov sources (SC DSS,
SC Works / SCDEW, Social Security Administration), geocoded via the Census Geocoder.
Curated in-code so the set is reproducible and reviewable.

Usage:
    python fetch_gov_offices.py
"""
from __future__ import annotations

from common import ensure_dirs, PROCESSED_DIR, write_json
from facility_common import build_facility

# name, address, city, zip, phone, agency  (all verified from official sources, 2026)
OFFICES = [
    ("SC DSS — Greenville County", "352 Halton Rd Suite 100", "Greenville", "29607", "864-467-7700", "DSS"),
    ("SC Works Greenville (McAlister Square)", "225 South Pleasantburg Dr Suite E-1", "Greenville", "29607", "864-467-8080", "DEW"),
    ("Social Security Administration — Greenville", "319 Pelham Rd", "Greenville", "29615", "877-274-5423", "SSA"),
    ("SC Works Connection — Hughes Main Library", "25 Heritage Green Pl", "Greenville", "29601", "", "DEW"),
    ("SC Works Connection — Anderson Rd Library", "2625 Anderson Rd", "Greenville", "29611", "", "DEW"),
    ("SC Works Connection — Augusta Rd Library", "100 Lydia St", "Greenville", "29605", "", "DEW"),
]


def main() -> None:
    ensure_dirs()
    print(f"Geocoding {len(OFFICES)} verified government/social-services offices ...")
    facilities = []
    for name, addr, city, zc, phone, agency in OFFICES:
        fac = build_facility("gov_social", name=name, address=addr, city=city, state="SC",
                             zip_code=zc, phone=phone,
                             source="Verified official .gov office directory",
                             extra={"agency": agency})
        if fac:
            facilities.append(fac)
            print(f"  + {name}")
        else:
            print(f"  WARN: could not geocode {name} ({addr})")

    write_json(PROCESSED_DIR / "facilities_gov_social.json",
               {"category": "gov_social", "county": "Greenville County",
                "source": "Verified official .gov office directory", "facilities": facilities},
               label=f"gov/social services ({len(facilities)})")
    print(f"Done: {len(facilities)} offices.")


if __name__ == "__main__":
    main()
