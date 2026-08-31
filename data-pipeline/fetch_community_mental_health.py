#!/usr/bin/env python3
"""Build community_mental_health from the state's own clinic list.

Source: Greater Greenville Mental Health Center locations, published by the SC
Department of Behavioral Health and Developmental Disabilities,
https://bhdd.sc.gov/office-mental-health/providers/mental-health-centers/
greater-greenville-mental-health-center-ggmhc/ggmhc-locations, read 31 Aug 2026.

**The agency renamed.** What older sources and this repo's notes call SCDMH is
now BHDD; scdmh.org still resolves and redirects. Cite BHDD.

WHY THIS IS A SEPARATE CATEGORY FROM behavioral_health. The existing
behavioral-health count is dominated by private practices enumerated in NPPES,
which take the insurance they choose to take. A community mental health center
is the public system: it takes everyone, including Medicaid and the uninsured.
For someone without coverage those are not substitutes, and merging them would
hide the distinction that decides whether a trip is worth making.

NPPES could not produce this. Its "Community Mental Health Center" taxonomy
exists and 58 records carry it, but the exact query string returns zero for the
county. The state publishes the real list, so this is a curated list rather than
a fetch, which is why the record count is small and correct instead of large and
approximate.

Usage:
    python fetch_community_mental_health.py
"""
from __future__ import annotations

from common import ensure_dirs, PROCESSED_DIR, write_json
from facility_common import build_facility

# Hours come from the operator's own published page, which is a distinct trust
# tier: stronger than an aggregator listing, weaker than a phone call. The SC
# Free Clinic Association directory was stale on names, phones, one ZIP and
# every satellite's hours while the clinic's own site was current, which is
# exactly why the distinction is worth carrying to the reader.
HOURS_PROVENANCE = {
    "hours_provenance": "published_by_operator",
    "hours_source_url": "https://bhdd.sc.gov/office-mental-health/providers/mental-health-centers/greater-greenville-mental-health-center-ggmhc/ggmhc-locations",
    "hours_read_on": "2026-08-31",
}

SOURCE = ("SC Dept. of Behavioral Health and Developmental Disabilities (BHDD), "
          "Greater Greenville Mental Health Center locations, read 2026-08-31")

HOURS = "Monday to Friday, 8:30am to 5pm"

# name, address, city, zip, phone
CLINICS = [
    ("Greater Greenville Mental Health Center, Greenville Clinic",
     "124 Mallard Street", "Greenville", "29601", "864-241-1040"),
    ("Greater Greenville Mental Health Center, Simpsonville Clinic",
     "20 Powderhorn Road", "Simpsonville", "29681", "864-963-3421"),
    ("Greater Greenville Mental Health Center, Greer Clinic",
     "220 Executive Drive", "Greer", "29651", "864-879-2111"),
]


def main() -> None:
    ensure_dirs()
    print(f"Geocoding {len(CLINICS)} GGMHC clinics ...")
    facilities = []
    for name, addr, city, zc, phone in CLINICS:
        fac = build_facility("community_mental_health", name=name, address=addr,
                             city=city, state="SC", zip_code=zc, phone=phone,
                             source=SOURCE, keep_county_fips="45045",
                             extra={"open_hours": HOURS,
                                    "notes": ("Public outpatient mental health for children, "
                                              "adolescents, adults and families. Takes "
                                              "Medicaid and the uninsured, unlike most "
                                              "private practices in the behavioral_health "
                                              "count."),
                                    **HOURS_PROVENANCE})
        if fac:
            facilities.append(fac)
            print(f"  + {name}")
        else:
            print(f"  WARN: did not geocode inside Greenville County: {name}")

    write_json(PROCESSED_DIR / "facilities_community_mental_health.json",
               {"category": "community_mental_health", "county": "Greenville County",
                "source": SOURCE,
                "coverage_note": (
                    "The three Greater Greenville Mental Health Center clinics, which are "
                    "the public system for the county and take Medicaid and the uninsured. "
                    "Private practices are counted separately under mental health."),
                "facilities": facilities},
               label=f"community mental health ({len(facilities)})")
    print(f"Done: {len(facilities)} community mental health clinics.")


if __name__ == "__main__":
    main()
