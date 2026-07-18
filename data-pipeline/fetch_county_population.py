#!/usr/bin/env python3
"""Fetch SC county population (keyless) for per-capita pedestrian-fatality rates.

Uses the Census Population Estimates Program (PEP) county totals flat file — a static
CSV download, NOT the Census Data API, so it needs no API key. This lets the statewide
dashboard show fatalities per capita without the ACS key.

Source (verified July 2026, no key):
  https://www2.census.gov/programs-surveys/popest/datasets/2020-2024/counties/totals/co-est2024-alldata.csv

Writes data/processed/county_population_sc.json: {county_fips: population}.

Usage:
    python fetch_county_population.py
"""
from __future__ import annotations

import pandas as pd

from common import PROCESSED_DIR, SC_STATE_FIPS, ensure_dirs, write_json

CSV_URL = ("https://www2.census.gov/programs-surveys/popest/datasets/"
           "2020-2024/counties/totals/co-est2024-alldata.csv")
POP_COLUMN = "POPESTIMATE2024"  # latest vintage in this file


def main() -> None:
    ensure_dirs()
    print(f"Fetching county population from {CSV_URL} ...")
    # PEP files are latin-1 encoded; keep FIPS parts as strings.
    df = pd.read_csv(CSV_URL, encoding="latin-1", dtype={"STATE": str, "COUNTY": str})
    df.columns = [c.strip().upper() for c in df.columns]

    sc = df[(df["STATE"].str.zfill(2) == SC_STATE_FIPS) & (df["COUNTY"].str.zfill(3) != "000")]
    counties = {}
    for _, r in sc.iterrows():
        fips = SC_STATE_FIPS + str(r["COUNTY"]).zfill(3)
        try:
            counties[fips] = int(r[POP_COLUMN])
        except (TypeError, ValueError):
            continue

    out = {
        "source": "US Census Bureau, Population Estimates Program (PEP)",
        "estimate_year": 2024,
        "state_fips": SC_STATE_FIPS,
        "population_by_county": counties,
    }
    write_json(PROCESSED_DIR / "county_population_sc.json", out,
               label=f"SC county population ({len(counties)} counties)")
    print(f"Done: {len(counties)} counties.")


if __name__ == "__main__":
    main()
