#!/usr/bin/env python3
"""Build the free_clinic category for Greenville County.

Source: South Carolina Free Clinic Association member directory,
https://www.scfreeclinics.org/clinics/ (62 clinics statewide, read 31 Aug 2026).
NPPES was checked first and rejected: its "Voluntary or Charitable" taxonomy
returns 12 county organizations of which one is a free clinic, the rest being
churches, home-care agencies and a children's charity. That is a candidate
source, not a category.

WHY THIS CATEGORY MATTERS. Calls in late August established that acceptance, not
distance, decides where people go. Free clinics are the other half of the "will
see you regardless" destination set, and until now the tool only knew the FQHC
half.

HOURS ARE NOT A NICE-TO-HAVE HERE. Three of the five county sites are satellites
open a single afternoon a week. A travel-time tool that lists a Thursday-only
clinic as simply "nearby" will send someone on a 60-minute bus trip on a Tuesday
to a locked door, which is worse than not listing it. Every record therefore
carries its published hours, and the satellites are flagged.

⚠️ TWO THINGS TO VERIFY BY PHONE BEFORE ANYONE RELIES ON THIS:
  1. The association lists the Greer and Simpsonville satellites with a **843**
     area code. 843 is the SC Lowcountry; the parent clinic is 864-232-1470.
     Almost certainly a typo on their site. Those two phone numbers are stored
     BLANK rather than wrong, with the parent number in `phone_parent`.
  2. Membership is voluntary, so a free clinic that never joined the association
     will not appear here. The category ships with a coverage_note saying so.

Usage:
    python fetch_free_clinics.py
"""
from __future__ import annotations

from common import ensure_dirs, PROCESSED_DIR, write_json
from facility_common import build_facility

SOURCE = "SC Free Clinic Association member directory (scfreeclinics.org), read 2026-08-31"

# name, address, city, zip, phone, hours, is_satellite, note
CLINICS = [
    ("Greenville Free Medical Clinic", "600 Arlington Avenue", "Greenville", "29601",
     "864-232-1470", "", False,
     "Main site. Free medical and dental care, health education and prescriptions "
     "for eligible uninsured residents."),
    ("Greenville Free Medical Clinic (Franklin Road satellite)", "925 N Franklin Rd", "Greenville", "",
     "864-232-1470", "Thursday 12pm to 6pm", True,
     "Satellite, one afternoon a week."),
    ("Greenville Free Medical Clinic (Greer satellite)", "113C Berry Avenue", "Greer", "29651",
     "", "Tuesday 12pm to 6pm", True,
     "Satellite inside the Neighborhood Impact Center, one afternoon a week. Shares "
     "an address with Greer Relief & Resources Agency, already in the food category. "
     "Phone withheld: the association lists 843-232-1470, a Lowcountry area code, "
     "against a parent clinic on 864."),
    ("Greenville Free Medical Clinic (Simpsonville satellite)", "1102 Howard Dr", "Simpsonville", "",
     "", "Tuesday 12pm to 6pm; Wednesday 9am to 4pm", True,
     "Satellite. Phone withheld: association lists an 843 area code against an 864 "
     "parent clinic."),
    ("Taylors Free Medical Clinic", "400 West Main Street", "Taylors", "29687",
     "864-244-1134", "", False,
     "Independent member clinic, not a Greenville Free Medical Clinic site."),
]

PARENT_PHONE = "864-232-1470"


def main() -> None:
    ensure_dirs()
    print(f"Geocoding {len(CLINICS)} SC Free Clinic Association sites in Greenville County ...")
    facilities = []
    for name, addr, city, zc, phone, hours, satellite, note in CLINICS:
        extra = {"hours": hours, "is_satellite": satellite, "notes": note}
        if not phone:
            extra["phone_parent"] = PARENT_PHONE
            extra["phone_unverified"] = True
        fac = build_facility("free_clinic", name=name, address=addr, city=city, state="SC",
                             zip_code=zc, phone=phone, source=SOURCE,
                             keep_county_fips="45045", extra=extra)
        if fac:
            facilities.append(fac)
            flag = " [satellite]" if satellite else ""
            print(f"  + {name}{flag}")
        else:
            print(f"  WARN: did not geocode inside Greenville County: {name} ({addr}, {city})")

    n_sat = sum(1 for f in facilities if f.get("is_satellite"))
    write_json(PROCESSED_DIR / "facilities_free_clinic.json",
               {"category": "free_clinic", "county": "Greenville County", "source": SOURCE,
                "coverage_note": (
                    f"All {len(facilities)} SC Free Clinic Association member sites in the "
                    f"county. {n_sat} of them are satellites open one afternoon a week, so "
                    f"check the hours before travelling. Association membership is "
                    f"voluntary, so a free clinic that never joined would not appear here."),
                "facilities": facilities},
               label=f"free clinics ({len(facilities)})")
    print(f"Done: {len(facilities)} free clinics, {n_sat} of them limited-hours satellites.")


if __name__ == "__main__":
    main()
