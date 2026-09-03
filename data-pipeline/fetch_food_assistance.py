#!/usr/bin/env python3
"""Build food-assistance facilities for Greenville County from the Vivery API.

THE OLD DOCSTRING SAID NO CLEAN FEED EXISTS. THAT STOPPED BEING TRUE.
It read: "No clean programmatic feed exists for food pantries (HIFLD is gone;
211 has no open API), so this is a curated, verified starter list ... Expand it
from the county 211 / Harvest Hope partner directory as needed." Both halves
were correct when written and the conclusion is now wrong. Harvest Hope's own
"Find a Food Pantry" page runs the Vivery (formerly Food Access / AccessFood)
widget, and that widget reads a public JSON API. So the partner directory this
file was told to expand from IS machine-readable, and has been all along, just
not at the URL anyone thought to look for. Four hand-typed rows became 40-odd
without typing any of them.

The find, recorded so nobody repeats the search: harvesthope.org/get-help mounts
a shadow-DOM widget from cdn.vivery.org, which calls api.accessfood.org. Harvest
Hope is regionId 142, regionMapId 202. No key, no auth.

WHAT THIS DOES NOT DO IS TRUST IT. Vivery is a directory maintained by the food
banks themselves, which makes it the best available source and not a verified
one. Two guards:

  1. Every address is independently geocoded through the Census geocoder, the
     same path every other category uses, and anything that fails to geocode or
     lands outside Greenville County is dropped rather than kept on the strength
     of Vivery's own coordinates.
  2. Vivery's coordinates are then compared against the Census result and the
     distance recorded on the record. A big disagreement means one of the two is
     wrong about where a pantry is, which is worth seeing rather than averaging
     away.

HOURS ARE THE POINT, NOT A BONUS. The schedules endpoint carries weeksOfMonth
and daysOfMonth, which is exactly the "1st and 3rd Monday" pattern that makes a
travel-time answer dangerous: a site treated as open Mon-Fri sends someone on an
hour-long bus trip to a locked door. Those rows are preserved verbatim. Harvest
Hope's own page says "Hours may vary. Please call before visiting", and that
warning is carried into the coverage_note rather than being quietly dropped
because it is inconvenient for a tool that wants to look precise.

Usage:
    python fetch_food_assistance.py
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import urllib.parse
import urllib.request
from collections import defaultdict

from common import ensure_dirs, PROCESSED_DIR, write_json
from facility_common import build_facility

API = "https://api.accessfood.org/api/MapInformation/"
REGION_ID, REGION_MAP_ID = 142, 202          # Harvest Hope Food Bank
GREENVILLE_FIPS = "45045"
# Downtown Greenville. 30 miles covers the whole county with room to spare; the
# county filter below does the real work, so a generous radius costs nothing but
# a few rows that get dropped.
CENTER_LAT, CENTER_LON, RADIUS_MI = 34.8526, -82.3940, 30
DAYS = {1: "Sun", 2: "Mon", 3: "Tue", 4: "Wed", 5: "Thu", 6: "Fri", 7: "Sat"}

# Sites the hand-curated list had and Vivery does not. THIS LIST EXISTS BECAUSE
# THE SWITCH TO VIVERY SILENTLY LOST ONE. The old four rows were checked against
# the new 44 and First Christian Fellowship Outreach was simply absent from the
# directory, which is a fair reminder that a bigger source is not a superset of a
# smaller one. Anything dropped from here should be dropped because it was
# checked and found wrong, not because a feed stopped mentioning it.
SUPPLEMENT = [
    # name, address, city, zip, phone, why it is here
    ("First Christian Fellowship Outreach", "110 Montana St", "Greenville", "29611", "",
     "Carried over from the curated list that predated the Vivery source; not in "
     "the Harvest Hope partner directory as of the fetch date."),
]

# Above this, the two sources disagree enough that one of them is wrong about
# where a pantry is, rather than rounding differently. Seen on the first run:
# Vivery said "3710 Augusta Road" and the Census geocoder matched "3710 OLD
# AUGUSTA RD", a different street about a mile away.
DISAGREEMENT_LIMIT_M = 250


def _get(endpoint: str, params: dict) -> object:
    url = API + endpoint + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def fetch_locations() -> list[dict]:
    """Every Vivery location within RADIUS_MI, paged out. 20 per page."""
    base = {"radius": RADIUS_MI, "lat": CENTER_LAT, "lng": CENTER_LON,
            "dayAv": "", "foodProgramAv": "", "serviceTypeAv": "", "foodOfferingAv": "",
            "dietRestrictionAv": "", "locationFeatureAv": "", "languagesAv": "",
            "serviceCategoriesAv": "", "regionId": REGION_ID, "regionMapId": REGION_MAP_ID,
            "showOutOfNetwork": 1, "includeLocationOperatingHours": "true", "isMapV2": "true"}
    out, seen = [], set()
    for page in range(40):                      # generous cap; the loop breaks on empty
        rows = (_get("LocationSearch", {**base, "page": page}) or {}).get("item1") or []
        new = [r for r in rows if r["locationId"] not in seen]
        seen.update(r["locationId"] for r in new)
        out += new
        if not rows or not new:
            break
    return out


def fetch_schedules(location_ids: list[int]) -> dict[int, list[dict]]:
    if not location_ids:
        return {}
    rows = _get("LocationSchedules", {"LocationIds": ",".join(map(str, location_ids))}) or []
    by_loc = defaultdict(list)
    for s in rows:
        by_loc[s["locationId"]].append(s)
    return by_loc


def describe_hours(rows: list[dict]) -> tuple[str, bool]:
    """One human-readable hours string, plus whether it is a partial-month schedule.

    The flag is the important half. A pantry open the 1st and 3rd Monday is open
    about 9% of weekdays, and a tool that says "12 minutes away" without saying
    that has told the truth and misled the reader in the same breath.
    """
    if not rows:
        return "", False
    parts, partial = [], False
    for s in sorted(rows, key=lambda r: (r.get("dayOfWeek") or 0)):
        day = DAYS.get(s.get("dayOfWeek"), "?")
        when = f"{s.get('startTimeDescr','').strip()}-{s.get('endTimeDescr','').strip()}".strip("-")
        qualifier = (s.get("weeksOfMonth") or s.get("daysOfMonth") or "").strip()
        if qualifier:
            partial = True
            parts.append(f"{day} {when} (weeks/days of month: {qualifier})")
        else:
            parts.append(f"{day} {when}")
    return "; ".join(p for p in parts if p.strip()), partial


def haversine_m(a_lat, a_lon, b_lat, b_lon) -> float:
    R = 6371000.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = math.radians(b_lat - a_lat), math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def main() -> None:
    ensure_dirs()
    today = _dt.date.today().isoformat()
    print(f"Querying Vivery (Harvest Hope region {REGION_ID}) ...")
    locs = fetch_locations()
    print(f"  {len(locs)} locations within {RADIUS_MI} mi of downtown Greenville")

    scheds = fetch_schedules([l["locationId"] for l in locs])
    print(f"  schedules for {len(scheds)} of them")

    facilities, dropped, far = [], [], []
    for l in locs:
        name = (l.get("locationName") or "").strip()
        addr = (l.get("address1") or "").strip()
        hours, partial = describe_hours(scheds.get(l["locationId"], []))
        extra = {
            "vivery_location_id": l["locationId"],
            "in_harvest_hope_network": bool(l.get("inNetWorkInd")),
            "food_programs": (l.get("foodPrograms") or "").strip(", "),
            "food_service_types": (l.get("foodServiceTypes") or "").strip(", "),
            "open_hours": hours,
            # See describe_hours: this is the locked-door flag, not a detail.
            "partial_month_schedule": partial,
            "hours_source": "Vivery LocationSchedules",
            "fetched_on": today,
        }
        fac = build_facility(
            "food", name=name, address=addr, city=(l.get("city") or "").strip(),
            state=(l.get("state") or "SC").strip(), zip_code=(l.get("zipCode") or "").strip(),
            phone=(l.get("phone") or "").strip(),
            source=f"Vivery / Harvest Hope partner directory (api.accessfood.org, fetched {today})",
            keep_county_fips=GREENVILLE_FIPS, extra=extra)
        if fac is None:
            dropped.append(f"{name} ({addr}, {l.get('city')})")
            continue
        # Cross-check: two independent opinions about where this pantry is.
        if l.get("latitude") and l.get("longitude"):
            d = haversine_m(fac["lat"], fac["lon"], l["latitude"], l["longitude"])
            fac["geocode_disagreement_m"] = round(d)
            if d > DISAGREEMENT_LIMIT_M:
                # PUBLISH THE OPERATOR'S POINT, NOT THE INTERPOLATED ONE. The
                # Census geocoder interpolates along a street segment and will
                # happily match a similarly-named street; Vivery's coordinate
                # comes from the food bank's own listing. Neither is authoritative,
                # so both are kept on the record and the disagreement is stated,
                # but the one more likely to put somebody at the right door wins.
                fac["census_lat"], fac["census_lon"] = fac["lat"], fac["lon"]
                fac["lat"], fac["lon"] = l["latitude"], l["longitude"]
                fac["coordinate_source"] = "Vivery (operator listing)"
                fac["address_contested"] = True
                far.append(f"{name}: {round(d)} m apart; Census matched "
                           f"'{fac.get('matched_address')}' for '{addr}'")
        facilities.append(fac)
        print(f"  + {name}" + ("  [partial-month hours]" if partial else ""))

    for name, addr, city, zc, phone, why in SUPPLEMENT:
        if any(name.lower() == f["name"].lower() for f in facilities):
            continue                       # the directory caught up; no duplicate
        fac = build_facility("food", name=name, address=addr, city=city, state="SC",
                             zip_code=zc, phone=phone,
                             source="Curated list carried forward (not in Vivery)",
                             keep_county_fips=GREENVILLE_FIPS,
                             extra={"supplement_reason": why, "fetched_on": today})
        if fac:
            facilities.append(fac)
            print(f"  + {name}  [supplement, not in Vivery]")
        else:
            dropped.append(f"{name} ({addr}) — SUPPLEMENT FAILED TO GEOCODE")

    if dropped:
        print(f"\nDROPPED {len(dropped)} (outside Greenville County or not geocodable):")
        for d in dropped:
            print(f"  - {d}")
    if far:
        print(f"\nGEOCODE DISAGREEMENT over 250 m on {len(far)}:")
        for f in far:
            print(f"  ! {f}")

    n_partial = sum(1 for f in facilities if f.get("partial_month_schedule"))
    n_hours = sum(1 for f in facilities if f.get("open_hours"))
    note = ("Sourced from the Harvest Hope partner directory via Vivery. Harvest Hope's "
            "own page says hours may vary and to call before visiting, which is the right "
            "advice: this directory is maintained by the food banks, not verified by us. "
            f"{n_hours} of {len(facilities)} sites publish hours at all"
            + (f", and {n_partial} of those open only in certain weeks of the month, "
               "so a weekday travel time overstates when they can actually be reached."
               if n_partial else "."))

    write_json(PROCESSED_DIR / "facilities_food.json",
               {"category": "food", "county": "Greenville County",
                "source": f"Vivery / Harvest Hope partner directory (api.accessfood.org, fetched {today})",
                "coverage_note": note, "facilities": facilities},
               label=f"food assistance ({len(facilities)})")
    print(f"\nDone: {len(facilities)} food-assistance sites in Greenville County "
          f"({n_hours} with hours, {n_partial} partial-month).")


if __name__ == "__main__":
    main()
