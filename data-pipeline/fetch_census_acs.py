#!/usr/bin/env python3
"""Fetch Census ACS 5-year income + race/ethnicity data for every SC county.

Tier 1 equity overlay. Pulls from the Census Data API and caches a tidy per-county
table to data/processed/census_acs_sc_counties.json.

API notes (verified July 2026):
  - Latest vintage: ACS 2024 5-year -> base https://api.census.gov/data/2024/acs/acs5
  - An API key is now REQUIRED for every request (keyless calls 302 to a
    missing-key page). Get a free key at https://api.census.gov/data/key_signup.html
    and set CENSUS_API_KEY in the environment.
  - Response is an array-of-arrays: row 0 is column headers, rest are data rows.
  - All values are strings; sentinels like -666666666 mean "not available".

Usage:
    export CENSUS_API_KEY=your_key_here
    python fetch_census_acs.py
"""
from __future__ import annotations

import argparse
import os
import sys

import requests

from common import (
    PROCESSED_DIR,
    SC_STATE_FIPS,
    clean_census_value,
    ensure_dirs,
    write_json,
)

ACS_VINTAGE = "2024"  # ACS 2020-2024 5-year, released Jan 2026
ACS_BASE = f"https://api.census.gov/data/{ACS_VINTAGE}/acs/acs5"

# Variable code -> friendly key. Verified against the live 2024 variable list.
VARIABLES = {
    "B19013_001E": "median_household_income",
    "B01003_001E": "total_population",
    "B02001_001E": "race_total",
    "B02001_002E": "white_alone",
    "B02001_003E": "black_alone",
    "B03003_003E": "hispanic_latino",
}


def get_api_key() -> str:
    key = os.environ.get("CENSUS_API_KEY", "").strip()
    if not key:
        sys.exit(
            "ERROR: Census API key required (as of May 2026 the Census API rejects\n"
            "keyless requests). Get a free key at\n"
            "  https://api.census.gov/data/key_signup.html\n"
            "then run:  export CENSUS_API_KEY=your_key_here"
        )
    return key


def fetch_rows(key: str, *, geography: str = "county",
               county_fips: str | None = None) -> list[list[str]]:
    var_codes = list(VARIABLES.keys())
    params = {"get": "NAME," + ",".join(var_codes), "key": key}
    if geography == "county":
        params["for"] = "county:*"
        params["in"] = f"state:{SC_STATE_FIPS}"
        what = "SC counties"
    elif geography == "tract":
        if not county_fips:
            sys.exit("ERROR: tract geography requires a 5-digit county_fips.")
        county3 = county_fips[-3:]
        params["for"] = "tract:*"
        params["in"] = f"state:{SC_STATE_FIPS} county:{county3}"
        what = f"tracts in county {county_fips}"
    else:
        sys.exit(f"ERROR: unknown geography '{geography}'.")

    print(f"Fetching ACS {ACS_VINTAGE} 5-year for {what} ...")
    resp = requests.get(ACS_BASE, params=params, timeout=60)
    if resp.status_code != 200:
        sys.exit(
            f"ERROR: Census API returned HTTP {resp.status_code}.\n"
            f"URL: {resp.url}\n"
            "If this is a 302/redirect, the API key is missing or invalid."
        )
    return resp.json()


def to_records(rows: list[list[str]], geography: str) -> list[dict]:
    header = rows[0]
    idx = {name: header.index(name) for name in header}
    records = []
    for row in rows[1:]:
        county_fips = SC_STATE_FIPS + row[idx["county"]]  # full 5-digit FIPS
        rec = {"county_fips": county_fips, "name": row[idx["NAME"]]}
        if geography == "tract":
            rec["tract_fips"] = county_fips + row[idx["tract"]]  # 11-digit GEOID
        for code, friendly in VARIABLES.items():
            rec[friendly] = clean_census_value(row[idx[code]])
        total = rec.get("race_total")
        if total:
            rec["pct_white"] = round(100 * (rec["white_alone"] or 0) / total, 1)
            rec["pct_black"] = round(100 * (rec["black_alone"] or 0) / total, 1)
            rec["pct_hispanic"] = round(100 * (rec["hispanic_latino"] or 0) / total, 1)
        else:
            rec["pct_white"] = rec["pct_black"] = rec["pct_hispanic"] = None
        records.append(rec)
    key = "tract_fips" if geography == "tract" else "name"
    records.sort(key=lambda r: r.get(key) or "")
    return records


NOTE = ("median_household_income is in inflation-adjusted dollars for the vintage "
        "year. Sentinel values (e.g. -666666666) are stored as null.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch ACS 5-year data for SC.")
    ap.add_argument("--tracts", metavar="COUNTY_FIPS",
                    help="Pull tract-level data for a 5-digit county FIPS "
                         "(e.g. 45045 for Greenville) instead of all SC counties.")
    args = ap.parse_args()

    ensure_dirs()
    key = get_api_key()

    if args.tracts:
        rows = fetch_rows(key, geography="tract", county_fips=args.tracts)
        records = to_records(rows, "tract")
        out = {
            "source": "US Census Bureau, ACS 5-Year", "vintage": ACS_VINTAGE,
            "geography": "tract", "state_fips": SC_STATE_FIPS,
            "county_fips": args.tracts, "variables": VARIABLES, "note": NOTE,
            "tracts": records,
        }
        write_json(PROCESSED_DIR / f"census_acs_tracts_{args.tracts}.json", out,
                   label=f"ACS {ACS_VINTAGE} ({len(records)} tracts in {args.tracts})")
        print(f"Done: {len(records)} tracts in county {args.tracts}.")
    else:
        rows = fetch_rows(key, geography="county")
        records = to_records(rows, "county")
        out = {
            "source": "US Census Bureau, ACS 5-Year", "vintage": ACS_VINTAGE,
            "geography": "county", "state_fips": SC_STATE_FIPS,
            "variables": VARIABLES, "note": NOTE, "counties": records,
        }
        write_json(PROCESSED_DIR / "census_acs_sc_counties.json", out,
                   label=f"ACS {ACS_VINTAGE} ({len(records)} SC counties)")
        print(f"Done: {len(records)} counties.")


if __name__ == "__main__":
    main()
