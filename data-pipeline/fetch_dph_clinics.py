#!/usr/bin/env python3
"""Build the wic and health_department categories from SC DPH's own clinic list.

Source: https://dph.sc.gov/public/public-health-clinics, Greenville County
section, read 31 Aug 2026. This is the operating agency's own directory, which
outranks every aggregator: a third-party listing still described the Slater
office as "temporarily closed as of January 2024" while DPH publishes current
Tuesday and Wednesday hours for it.

TWO CATEGORIES FROM ONE SOURCE, because the page describes five sites and only
one of them is a health department. The other four are WIC offices that do
nothing else. Publishing all five as "county health department" would tell
someone they can get immunizations at a WIC office.

  health_department  1 site   the county health department itself
  wic                5 sites  every site offering WIC, including the health
                              department, which offers it alongside everything else

DAYS MATTER MORE THAN HOURS HERE. Two of the five WIC offices open on named days
only: Simpsonville on Mondays and Thursdays, Slater on Tuesdays and Wednesdays.
WIC requires in-person visits and its participants are disproportionately
without a car, so a travel-time answer that omits the day is worse than useless.

CO-LOCATION WORTH KNOWING. Three addresses in this file already appear elsewhere
in the project's data:
  113C Berry Ave, Greer        Greer WIC + Greer Free Clinic + Greer Relief (food)
  1102 Howard Dr, Simpsonville Simpsonville WIC + Golden Strip Free Clinic
  352 Halton Rd, Greenville    Health Department + SC DSS (gov_social)
Those are the county's real safety-net hubs, and a housing unit that reaches one
reaches several services in a single trip.

Usage:
    python fetch_dph_clinics.py
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
    "hours_source_url": "https://dph.sc.gov/public/public-health-clinics",
    "hours_read_on": "2026-08-31",
}

SOURCE = "SC DPH public health clinic directory (dph.sc.gov), read 2026-08-31"
APPOINTMENTS = "Appointments statewide: (855) 472-3432. Ask about extended or weekend hours."

# name, address, city, zip, phone, hours, services, is_health_dept
SITES = [
    ("Greenville County Health Department", "352 Halton Road", "Greenville", "29607",
     "864-372-3270", "Monday to Friday, 8:30am to 5pm",
     "Family planning, immunizations, STD/HIV/Hep C, WIC, opioid overdose kits, "
     "PrEP, STI PEP (doxyPEP), TB", True),

    ("Prisma Center for Pediatric Medicine WIC Office", "1 Doctor's Drive", "Greenville", "29605",
     "864-522-5220", "Monday to Friday, 8:30am to 5pm", "WIC only", False),

    ("Greer WIC Office", "113C Berry Ave", "Greer", "29651",
     "864-334-3498", "Monday to Friday, 8:30am to 5pm", "WIC only", False),

    ("Simpsonville WIC Office", "1102 Howard Drive", "Simpsonville", "29681",
     "864-688-2221", "MONDAYS AND THURSDAYS ONLY, 9am to 4:30pm", "WIC only", False),

    ("Slater WIC Office", "3 S. Main St.", "Slater", "29683",
     "864-836-1100", "TUESDAYS AND WEDNESDAYS ONLY, 8:30am to 5pm", "WIC only", False),
]


def main() -> None:
    ensure_dirs()
    print(f"Geocoding {len(SITES)} SC DPH sites in Greenville County ...")
    wic, hd = [], []
    for name, addr, city, zc, phone, hours, services, is_hd in SITES:
        extra = {"open_hours": hours, "services": services, "appointments": APPOINTMENTS,
                 **HOURS_PROVENANCE}
        fac = build_facility("wic", name=name, address=addr, city=city, state="SC",
                             zip_code=zc, phone=phone, source=SOURCE,
                             keep_county_fips="45045", extra=extra)
        if not fac:
            print(f"  WARN: did not geocode inside Greenville County: {name} ({addr}, {city})")
            continue
        wic.append(fac)
        print(f"  + {name}{'  [health department]' if is_hd else ''}")
        if is_hd:
            h = dict(fac)
            h["category"] = "health_department"
            hd.append(h)

    n_limited = sum(1 for f in wic if "ONLY" in (f.get("hours") or ""))
    write_json(PROCESSED_DIR / "facilities_wic.json",
               {"category": "wic", "county": "Greenville County", "source": SOURCE,
                "coverage_note": (
                    f"All {len(wic)} SC DPH sites in the county offering WIC. "
                    f"{n_limited} of them open on named days only: Simpsonville on "
                    f"Mondays and Thursdays, Slater on Tuesdays and Wednesdays. "
                    f"{APPOINTMENTS}"),
                "facilities": wic},
               label=f"WIC ({len(wic)})")
    write_json(PROCESSED_DIR / "facilities_health_department.json",
               {"category": "health_department", "county": "Greenville County", "source": SOURCE,
                "coverage_note": (
                    "One county health department, at 352 Halton Road. The other SC DPH "
                    "sites in the county are WIC offices and provide nothing else, so "
                    "they are in the wic category instead. " + APPOINTMENTS),
                "facilities": hd},
               label=f"health department ({len(hd)})")
    print(f"Done: {len(wic)} WIC sites, {len(hd)} health department.")


if __name__ == "__main__":
    main()
