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
  - Coordinates: X = longitude, Y = latitude

SERVICE LINES. A health center site is not automatically a primary care
destination. HRSA publishes no per-site service line in any machine-readable feed
(see overrides/fqhc_service_lines.csv for what was checked and ruled out), so
sites default to primary care — defensible, since providing it is a condition of
Section 330 scope — and specialty sites are recorded as exceptions in that file.
Without this, a dental-only site is counted as a primary care destination and the
travel-time numbers report a clinic that cannot give you a physical.

MOBILE UNITS are included but NOT routable. Every mobile van in Greenville County
lists 130 Mallard St — New Horizon's administrative office. That is the dispatch
base, not where the van parks to see patients, and HRSA publishes no route or
schedule. Routing someone to the base would produce a confident, precise, wrong
answer, so mobile sites are carried with mobile=True / routable=False and
reported separately. Their real service locations have to come from the operator.

Usage:
    python fetch_hrsa_fqhc.py                        # Greenville County, incl. Look-Alikes
    python fetch_hrsa_fqhc.py --county "Richland County"
    python fetch_hrsa_fqhc.py --exclude-lookalikes
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import pandas as pd
import requests

from common import PROCESSED_DIR, RAW_DIR, ensure_dirs, write_json

SERVICE_LINES_CSV = Path(__file__).resolve().parent / "overrides" / "fqhc_service_lines.csv"
DEFAULT_SERVICE_LINES = ("primary_care",)

CSV_URL = (
    "https://data.hrsa.gov/DataDownload/DD_Files/"
    "Health_Center_Service_Delivery_and_LookAlike_Sites.csv"
)
RAW_CSV = RAW_DIR / "hrsa" / "health_center_sites.csv"

COL = {
    "bphc": "BPHC Assigned Number",
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
    "hours": "Operating Hours per Week",
    "lon": "Geocoding Artifact Address Primary X Coordinate",
    "lat": "Geocoding Artifact Address Primary Y Coordinate",
}
KEEP_TYPE_DESC = {"Service Delivery Site", "Administrative/Service Delivery Site"}
# Location types that have no fixed address a person can travel to. Kept in the
# output, flagged, and excluded from routing rather than dropped: a mobile unit is
# real access, and silently omitting it understates a health center's reach.
NON_ROUTABLE_LOC_TYPES = {"Mobile Van", "Seasonal"}


def load_service_lines() -> dict[str, dict]:
    """bphc_number -> {service_lines, verified_on, verification_method}."""
    if not SERVICE_LINES_CSV.exists():
        print(f"  WARNING: {SERVICE_LINES_CSV.name} missing — every site will be "
              "treated as primary care, including specialty sites.")
        return {}
    out = {}
    with SERVICE_LINES_CSV.open(encoding="utf-8") as fh:
        rows = csv.DictReader(line for line in fh if not line.startswith("#"))
        for r in rows:
            key = (r.get("bphc_number") or "").strip()
            if not key:
                continue
            lines = [s.strip() for s in (r.get("service_lines") or "").split("|") if s.strip()]
            hours = (r.get("open_hours") or "").strip()
            # A row may carry hours but no service line — someone asked one
            # question and not the other. Skipping it would silently discard a
            # real answer, so only skip rows that say nothing at all.
            if not lines and not hours:
                continue
            out[key] = {
                "service_lines": lines,
                "open_hours": (r.get("open_hours") or "").strip() or None,
                "verified_on": (r.get("verified_on") or "").strip() or None,
                "verification_method": (r.get("verification_method") or "").strip() or None,
            }
    return out


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
    )
    if not include_lookalikes:
        m &= df[COL["hc_type"]].str.contains("FQHC", case=False, na=False) & \
             ~df[COL["hc_type"]].str.contains("Look", case=False, na=False)

    overrides = load_service_lines()
    sub = df[m].copy()
    # An override keyed on a BPHC number that no site carries does nothing, and
    # does it silently — the site keeps the primary-care default and looks
    # confirmed because someone clearly went and recorded an answer. Since these
    # rows are filled in by hand from phone calls, a mistyped identifier is the
    # likely failure, so say it rather than let a verified fact go unapplied.
    known = set(sub[COL["bphc"]].astype(str).str.strip())
    for key in overrides:
        if key not in known:
            print(f"  WARNING: override for {key} matches no active site in "
                  f"{county} — check the BPHC number; this override is not applied.")
    facilities = []
    for _, r in sub.iterrows():
        try:
            lat = float(r[COL["lat"]]); lon = float(r[COL["lon"]])
        except (TypeError, ValueError):
            lat = lon = None  # keep the record but flag missing coords
        fips = (r.get(COL["county_fips"]) or "").strip() or None
        bphc = (r.get(COL["bphc"]) or "").strip()
        loc_type = (r.get(COL["loc_type"]) or "").strip()
        mobile = loc_type in NON_ROUTABLE_LOC_TYPES

        ov = overrides.get(bphc)
        facilities.append({
            "id": bphc or (r.get(COL["site_name"]) or "").strip()[:60] or f"site-{len(facilities)}",
            "bphc_number": bphc,
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
            "location_type": loc_type,
            # INSURANCE ACCEPTANCE — the critique a reviewing physician made:
            # "a clinic you can reach that will not take your insurance is not
            # accessible." Travel time alone is an UPPER BOUND on real access.
            #
            # This can be asserted for health centers and almost nowhere else.
            # Section 330 requires them to serve all patients regardless of
            # ability to pay and to accept Medicaid, so it is a condition of the
            # program rather than an inference from a directory. Every other
            # category stays null — unknown, and labelled as unknown, because a
            # blank that renders as "no" would be worse than saying nothing.
            "accepts_medicaid": True,
            "accepts_medicaid_basis": (
                "Section 330 program requirement — health centers serve all "
                "patients regardless of ability to pay and accept Medicaid"),
            "operating_hours_per_week": (r.get(COL["hours"]) or "").strip() or None,
            # Services offered, and on what evidence. `assumed` means nobody has
            # confirmed it — the site is treated as primary care because Section
            # 330 scope requires it, not because a source said so.
            "service_lines": (list(ov["service_lines"]) if ov and ov.get("service_lines")
                              else list(DEFAULT_SERVICE_LINES)),
            # Verbatim as the site said it. None means nobody has asked yet —
            # distinct from "open hours unknown to exist".
            "open_hours": ov.get("open_hours") if ov else None,
            "service_lines_source": "override file" if ov else "assumed (Section 330 scope)",
            "service_lines_verified_on": ov["verified_on"] if ov else None,
            "service_lines_method": ov["verification_method"] if ov else None,
            # A mobile unit's listed address is its dispatch base. Routing to it
            # would answer a question the data cannot answer.
            "mobile": mobile,
            "routable": not mobile,
            "address_is_dispatch_base": mobile,
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
    primary = [f for f in facilities if "primary_care" in f["service_lines"] and f["routable"]]
    mobile = [f for f in facilities if f["mobile"]]
    specialty = [f for f in facilities if "primary_care" not in f["service_lines"]]
    assumed = [f for f in facilities if f["service_lines_source"].startswith("assumed")]

    out = {
        "category": "fqhc",
        "county": args.county,
        "source": "HRSA Health Center Service Delivery and Look-Alike Sites",
        "source_url": CSV_URL,
        "filters": {
            "status": "Active",
            "type_description": sorted(KEEP_TYPE_DESC),
            "location_type": "all (mobile/seasonal flagged routable=false)",
            "include_lookalikes": not args.exclude_lookalikes,
        },
        # Consumers must filter; the file no longer pretends every row is a
        # primary care destination you can walk to.
        "counts": {
            "sites": len(facilities),
            "routable_primary_care": len(primary),
            "mobile_non_routable": len(mobile),
            "specialty_no_primary_care": len(specialty),
            "service_lines_assumed": len(assumed),
        },
        "caveats": [
            "Sites without an entry in overrides/fqhc_service_lines.csv are assumed "
            "to provide primary care (a condition of Section 330 scope). HRSA "
            "publishes no per-site service line.",
            "Mobile units are listed at their dispatch base, not their service "
            "locations, and are excluded from travel-time routing.",
        ],
        "facilities": facilities,
    }
    write_json(PROCESSED_DIR / "facilities_fqhc.json", out,
               label=f"FQHC facilities ({len(facilities)} sites, {with_coords} geocoded)")

    # Specialty sites are excluded from the FQHC (primary care) category, but they
    # are real destinations and must not disappear from the tool — a safety-net
    # dental clinic is exactly the kind of place this project exists to locate.
    # They are written to their own file and joined into the `dental` category as
    # a composite member. NPPES does not list them (it enumerates the health
    # center under a generic FQHC taxonomy), so without this they would be lost.
    dental = [dict(f, category="fqhc_dental") for f in facilities
              if "dental" in f["service_lines"]]
    if dental:
        write_json(PROCESSED_DIR / "facilities_fqhc_dental.json", {
            "category": "fqhc_dental",
            "county": args.county,
            "source": "HRSA Health Center Service Delivery and Look-Alike Sites",
            "source_url": CSV_URL,
            "note": ("Health center sites whose scope is dental rather than primary "
                     "care. Service line recorded in overrides/fqhc_service_lines.csv."),
            "facilities": dental,
        }, label=f"FQHC dental sites ({len(dental)})")

    # Behavioural health, same reasoning as dental and confirmed by phone on
    # 24 Aug: New Horizon offers it at every fixed site. NPPES does not list any
    # of them — the health centre enumerates under a generic FQHC taxonomy, so a
    # search of behavioural-health taxonomies returns 260 sites in this county
    # and NONE of them are health centres. Without this the category silently
    # excludes the most reachable behavioural health there is for the population
    # this project is about: a site that must serve you regardless of ability to
    # pay. Unlike dental, these sites keep their primary-care role too, so they
    # appear in BOTH categories — that is correct, not a duplicate.
    behavioral = [dict(f, category="fqhc_behavioral") for f in facilities
                  if "behavioral" in f["service_lines"] and f["routable"]]
    if behavioral:
        write_json(PROCESSED_DIR / "facilities_fqhc_behavioral.json", {
            "category": "fqhc_behavioral",
            "county": args.county,
            "source": "HRSA Health Center Service Delivery and Look-Alike Sites",
            "source_url": CSV_URL,
            "note": ("Health center sites confirmed by phone to provide behavioral "
                     "health alongside primary care. Recorded in "
                     "overrides/fqhc_service_lines.csv; NPPES lists none of them."),
            "facilities": behavioral,
        }, label=f"FQHC behavioral health sites ({len(behavioral)})")

    print(f"Done: {len(facilities)} active sites ({with_coords} with coordinates).")
    print(f"  routable primary care: {len(primary)}")
    for f in facilities:
        tags = []
        if f["mobile"]:
            tags.append(f"MOBILE — base address, not routable, {f['operating_hours_per_week']} hrs/wk")
        if "primary_care" not in f["service_lines"]:
            tags.append("no primary care: " + "/".join(f["service_lines"]))
        if f["service_lines_source"].startswith("assumed"):
            tags.append("services assumed")
        suffix = ("  [" + "; ".join(tags) + "]") if tags else ""
        print(f"  - {f['name']}  ({f['city']}){suffix}")
    if assumed:
        print(f"\n{len(assumed)} site(s) have UNCONFIRMED service lines. Confirm with the "
              "health center and record it in overrides/fqhc_service_lines.csv.")


if __name__ == "__main__":
    main()
