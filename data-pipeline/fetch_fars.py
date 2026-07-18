#!/usr/bin/env python3
"""Fetch NHTSA FARS pedestrian fatalities for South Carolina, by county and year.

Tier 1 core dataset. Downloads the annual FARS "National CSV" zip for each year,
caches it under data/raw/fars/, filters to South Carolina pedestrian fatalities,
and writes a tidy per-county / per-year table to
data/processed/fars_sc_pedestrian.json.

FARS structure (verified July 2026):
  - Bulk download, no API key needed. Per-year National CSV zip at:
      https://static.nhtsa.gov/nhtsa/downloads/FARS/{year}/National/FARS{year}NationalCSV.zip
    (Latest year available = 2024; 2025 is 404.)
  - person.csv : one row per person, and it already carries STATE and COUNTY, so no
                 join to accident.csv is needed. PER_TYP = 5 -> pedestrian;
                 INJ_SEV = 4 -> fatal; STATE = 45 -> South Carolina.
  - COUNTY is the 3-digit county FIPS as an unpadded integer (e.g. 19). Full 5-digit
    GEOID = "45" + zero-padded 3-digit COUNTY (19 -> "45019"). Codes 0 and 997-999
    are unknown/not-reported sentinels.
  - Column names are uppercase in the CSVs; select by header NAME (positions shift
    across years). File name casing varies by year, so match case-insensitively.
    Files are latin-1 / cp1252 encoded. (Cross-checked: 2023 -> 187 SC pedestrian
    fatalities across 37 counties.)

Usage:
    python fetch_fars.py                 # default year range
    python fetch_fars.py 2018 2023       # custom inclusive range
"""
from __future__ import annotations

import io
import sys
import zipfile
from collections import defaultdict

import pandas as pd
import requests

from common import (
    PROCESSED_DIR,
    RAW_DIR,
    SC_STATE_FIPS,
    ensure_dirs,
    write_json,
)

DEFAULT_START, DEFAULT_END = 2014, 2024  # inclusive; years past availability 404 & skip
SC_STATE_CODE = 45  # numeric STATE code for South Carolina
PED_PER_TYP = 5     # PER_TYP code for Pedestrian
FATAL_INJ_SEV = 4   # INJ_SEV code for Fatal (killed)

URL_TMPL = (
    "https://static.nhtsa.gov/nhtsa/downloads/FARS/"
    "{year}/National/FARS{year}NationalCSV.zip"
)

FARS_RAW_DIR = RAW_DIR / "fars"


def download_year(year: int) -> bytes | None:
    """Return the raw zip bytes for a year, using a local cache. None if 404."""
    FARS_RAW_DIR.mkdir(parents=True, exist_ok=True)
    cache = FARS_RAW_DIR / f"FARS{year}NationalCSV.zip"
    if cache.exists() and cache.stat().st_size > 0:
        print(f"  [{year}] using cached {cache.name}")
        return cache.read_bytes()

    url = URL_TMPL.format(year=year)
    print(f"  [{year}] downloading {url}")
    resp = requests.get(url, timeout=180)
    if resp.status_code == 404:
        print(f"  [{year}] not available (404) — skipping")
        return None
    resp.raise_for_status()
    cache.write_bytes(resp.content)
    return resp.content


def _find_member(zf: zipfile.ZipFile, stem: str) -> str | None:
    """Case-insensitive lookup of a CSV member like 'person' or 'accident'."""
    target = f"{stem}.csv"
    for name in zf.namelist():
        base = name.split("/")[-1].lower()
        if base == target:
            return name
    return None


def _read_csv(zf: zipfile.ZipFile, member: str) -> pd.DataFrame:
    with zf.open(member) as fh:
        raw = fh.read()
    # FARS CSVs are latin-1/cp1252; fall back defensively.
    for enc in ("latin-1", "cp1252", "utf-8"):
        try:
            df = pd.read_csv(io.BytesIO(raw), encoding=enc, low_memory=False)
            df.columns = [c.strip().upper() for c in df.columns]
            return df
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    raise RuntimeError(f"Could not decode {member}")


def process_year(year: int, zip_bytes: bytes) -> dict[str, int]:
    """Return {county_fips: fatal_pedestrian_count} for SC in this year.

    person.csv carries STATE and COUNTY directly, so no join to accident.csv is
    needed for county-level pedestrian counts.
    """
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        person_name = _find_member(zf, "person")
        if not person_name:
            print(f"  [{year}] missing person CSV — skipping")
            return {}
        person = _read_csv(zf, person_name)

    # Fatal pedestrians in SC.
    ped = person[
        (person["STATE"] == SC_STATE_CODE)
        & (person["PER_TYP"] == PED_PER_TYP)
        & (person["INJ_SEV"] == FATAL_INJ_SEV)
    ]
    if ped.empty:
        return {}

    counts: dict[str, int] = defaultdict(int)
    for county in ped["COUNTY"]:
        try:
            cnum = int(county)
        except (TypeError, ValueError):
            continue
        # 000 and >=997 are "unknown/not reported" county sentinels in FARS.
        if cnum <= 0 or cnum >= 997:
            county_fips = f"{SC_STATE_FIPS}999"  # unknown bucket
        else:
            county_fips = f"{SC_STATE_FIPS}{cnum:03d}"
        counts[county_fips] += 1
    return dict(counts)


def main(argv: list[str]) -> None:
    if len(argv) == 3:
        start, end = int(argv[1]), int(argv[2])
    else:
        start, end = DEFAULT_START, DEFAULT_END

    ensure_dirs()
    print(f"FARS pedestrian fatalities for SC, {start}-{end}:")

    # {county_fips: {year: count}}
    by_county: dict[str, dict[int, int]] = defaultdict(dict)
    by_year_state: dict[int, int] = {}
    years_available: list[int] = []

    for year in range(start, end + 1):
        zip_bytes = download_year(year)
        if zip_bytes is None:
            continue
        counts = process_year(year, zip_bytes)
        year_total = sum(counts.values())
        by_year_state[year] = year_total
        years_available.append(year)
        for fips, n in counts.items():
            by_county[fips][year] = n
        print(f"  [{year}] {year_total} SC pedestrian fatalities "
              f"across {len(counts)} counties")

    if not years_available:
        sys.exit("ERROR: no FARS years could be downloaded. Check network/URLs.")

    # Tidy per-county records with totals.
    counties = []
    for fips, per_year in sorted(by_county.items()):
        counties.append({
            "county_fips": fips,
            "by_year": {str(y): per_year.get(y, 0) for y in years_available},
            "total": sum(per_year.values()),
        })

    out = {
        "source": "NHTSA FARS (Fatality Analysis Reporting System)",
        "state_fips": SC_STATE_FIPS,
        "metric": "pedestrian_fatalities",
        "definition": "person records with PER_TYP=5 (pedestrian) and INJ_SEV=4 (fatal)",
        "years": years_available,
        "state_totals_by_year": {str(y): by_year_state[y] for y in years_available},
        "counties": counties,
    }
    write_json(
        PROCESSED_DIR / "fars_sc_pedestrian.json",
        out,
        label=f"FARS SC pedestrian ({len(years_available)} yrs, {len(counties)} counties)",
    )
    grand_total = sum(by_year_state.values())
    print(f"Done: {grand_total} SC pedestrian fatalities, {years_available[0]}-{years_available[-1]}.")


if __name__ == "__main__":
    main(sys.argv)
