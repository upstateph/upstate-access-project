#!/usr/bin/env python3
"""Build the free_clinic category for Greenville County.

Sources, in order of authority:
  1. **The operators' own sites**, which is what these records are built from:
     greenvillefreeclinic.org/locations and taylorsfmc.org (read 31 Aug 2026).
  2. The SC Free Clinic Association directory, used only to discover that the
     clinics exist.

**The association directory was wrong in four ways**, which is why the operator
pages win. It named three sites "Greenville Free Medical Clinic (satellite)"
when each has its own name; it listed an 843 Lowcountry area code for two of
them when every satellite is the parent number plus an extension; it had one
wrong ZIP; and its hours predate a service expansion the clinic announces on its
own front page ("JUST ADDED, additional days of service at each of the satellite
clinic sites"). A statewide association directory is a discovery tool, not a
source of truth about hours.

NPPES was checked before either and rejected: its "Voluntary or Charitable"
taxonomy returns 12 county organizations, of which one is a free clinic and the
rest are churches, home-care agencies and a children's charity.

WHY THIS CATEGORY MATTERS. Calls in late August established that acceptance, not
distance, decides where people go. Free clinics are the other half of the "will
see you regardless" destination set; until now the tool knew only the FQHC half.

HOURS ARE THE POINT HERE, NOT A DETAIL. Four of the five sites are open only on
named days, and two of them gate entry on a registration window rather than
closing time:
  - the three GFMC satellites run primary care on two or three days a week, each
    with a registration time that is the real deadline;
  - Taylors takes NEW patients on Wednesdays from 9:00 to 11:30am, 2.5 hours a
    week, and everything else is by appointment.
A travel-time answer that omits that sends someone on an hour-long bus trip to a
locked door, so every record carries its published hours and the category ships
with a coverage_note.

Usage:
    python fetch_free_clinics.py
"""
from __future__ import annotations

from common import ensure_dirs, PROCESSED_DIR, write_json
from facility_common import build_facility

SOURCE = ("Clinic operators' own published locations pages: greenvillefreeclinic.org "
          "and taylorsfmc.org, read 2026-08-31")

PARENT_PHONE = "864-232-1470"

# name, address, city, zip, phone, hours, is_satellite, note
CLINICS = [
    ("Greenville Free Medical Clinic", "600 Arlington Avenue", "Greenville", "29601",
     PARENT_PHONE,
     "Mon 8:45am-5pm; Tue 9:45am-7pm; Wed 8:45am-5pm; Thu 9:45am-7pm; Fri 8:45am-1pm. "
     "In-house pharmacy opens 45 minutes later each day and closes with the clinic.",
     False,
     "Main site. General and specialty medical, limited dental, behavioral health "
     "and counseling, health education, in-house pharmacy. Closed New Year's Eve "
     "and Day, Memorial Day, Independence Day, Labor Day, Thanksgiving and the day "
     "after, Christmas Eve and Day."),

    ("Northwest Crescent Free Clinic", "925 North Franklin Road", "Greenville", "29617",
     "", "Primary care Tuesdays and Thursdays. Registration begins 9:00am Tuesday "
         "and 1:00pm Thursday.",
     True,
     "Satellite of Greenville Free Medical Clinic, in Building A of the Northwest "
     "Crescent Child and Family Center, far left of campus with its own driveway. "
     "Phone is voice messages only, on the parent line at extension 160."),

    ("Greer Free Clinic", "113-C Berry Avenue", "Greer", "29650",
     "", "Primary care Tuesdays and Thursdays. Registration begins 1:00pm Tuesday "
         "and 9:00am Thursday.",
     True,
     "Satellite of Greenville Free Medical Clinic, co-located with Greer Relief at "
     "the Neighborhood Impact Center, which is already in the food category at the "
     "same address. Phone is voice messages only, parent line extension 165."),

    ("Golden Strip Free Clinic", "1102 Howard Drive", "Simpsonville", "29681",
     "", "Primary care Mondays, Tuesdays and Wednesdays. Registration begins 9:00am "
         "Monday, 12:00pm Tuesday, 9:00am Wednesday. Monday and Wednesday take "
         "scheduled visits plus limited walk-ins.",
     True,
     "Satellite of Greenville Free Medical Clinic, in Building 3 of the Center for "
     "Community Services. Phone is voice messages only, parent line extension 155."),

    ("Taylors Free Medical Clinic", "400 West Main Street", "Taylors", "29687",
     "864-244-1134",
     "NEW PATIENT REGISTRATION: Wednesdays 9:00am to 11:30am only, no appointment "
     "needed. All provider visits are by appointment.",
     False,
     "Independent faith-based clinic, not a Greenville Free Medical Clinic site. "
     "Eligibility: household income at or below 165% of the federal poverty level, "
     "Greenville County resident, and no other health coverage including Medicare, "
     "Medicaid and VA benefits. Services include primary care, pharmacy, "
     "counseling, gynecology, cardiology, dermatology, orthopedics and chiropractic."),
]

# Satellites answer on the parent line at an extension; none has a direct number.
EXTENSIONS = {
    "Northwest Crescent Free Clinic": "160",
    "Greer Free Clinic": "165",
    "Golden Strip Free Clinic": "155",
}


def main() -> None:
    ensure_dirs()
    print(f"Geocoding {len(CLINICS)} free clinic sites in Greenville County ...")
    facilities = []
    for name, addr, city, zc, phone, hours, satellite, note in CLINICS:
        extra = {"hours": hours, "is_satellite": satellite, "notes": note}
        if not phone:
            extra["phone_parent"] = PARENT_PHONE
            extra["phone_extension"] = EXTENSIONS.get(name)
            extra["phone_voicemail_only"] = True
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
                    f"All {len(facilities)} free clinics known in the county. Four of them "
                    f"open only on named days, and two gate entry on a registration window "
                    f"rather than closing time, so check the hours before travelling. "
                    f"The {n_sat} satellites take voice messages only, on the main clinic's "
                    f"line at an extension."),
                "facilities": facilities},
               label=f"free clinics ({len(facilities)})")
    print(f"Done: {len(facilities)} free clinics, {n_sat} of them satellites.")


if __name__ == "__main__":
    main()
