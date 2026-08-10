"""Equity comparison: how does an origin's Census tract compare to its county?

Given a geocoded tract + county FIPS, benchmarks the tract's median household income
and race/ethnicity against the county — the "compared to other people in the county
by income and race" part of the spec. Reads ACS data pulled by the data pipeline:

    data/processed/census_acs_sc_counties.json           (county-level, all SC)
    data/processed/census_acs_tracts_<county_fips>.json  (tract-level, one county)

Both require a Census API key to pull (see fetch_census_acs.py). This module is pure
computation over already-pulled files, so it's unit-testable offline with fixtures.
"""
from __future__ import annotations

import json
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent
PROCESSED_DIR = ENGINE_DIR.parent / "data" / "processed"

COUNTIES_FILE = PROCESSED_DIR / "census_acs_sc_counties.json"


def _load(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"ACS file not found: {path}. Run fetch_census_acs.py.")
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _percentile(value: float, population: list[float]) -> float | None:
    """Percentile rank of `value` within `population` (0–100)."""
    vals = [v for v in population if v is not None]
    if not vals or value is None:
        return None
    below = sum(1 for v in vals if v < value)
    return round(100 * below / len(vals), 1)


def compare_tract_to_county(tract_fips: str | None, county_fips: str | None,
                            *, counties_file: Path = COUNTIES_FILE,
                            tracts_file: Path | None = None) -> dict:
    """Benchmark a tract against its county. Raises FileNotFoundError if ACS data
    for the county's tracts hasn't been pulled."""
    if not tract_fips or not county_fips:
        return {"available": False, "reason": "origin has no tract/county FIPS"}

    counties = _load(counties_file)
    county = next((c for c in counties["counties"] if c["county_fips"] == county_fips), None)

    if tracts_file is None:
        tracts_file = PROCESSED_DIR / f"census_acs_tracts_{county_fips}.json"
    tracts_doc = _load(tracts_file)
    tracts = tracts_doc["tracts"]
    tract = next((t for t in tracts if t.get("tract_fips") == tract_fips), None)
    if tract is None:
        return {"available": False, "reason": f"tract {tract_fips} not in ACS pull"}

    inc = tract.get("median_household_income")
    county_inc = county.get("median_household_income") if county else None
    tract_incomes = [t.get("median_household_income") for t in tracts]

    return {
        "available": True,
        "acs_vintage": tracts_doc.get("vintage"),
        "tract_fips": tract_fips,
        "county_fips": county_fips,
        "median_household_income": {
            "tract": inc,
            "county": county_inc,
            "ratio_to_county": round(inc / county_inc, 2) if inc and county_inc else None,
            "pct_of_county_tracts_below": _percentile(inc, tract_incomes),
        },
        "race_ethnicity_pct": {
            "tract": {
                "white": tract.get("pct_white"),
                "black": tract.get("pct_black"),
                "hispanic": tract.get("pct_hispanic"),
            },
            "county": {
                "white": county.get("pct_white") if county else None,
                "black": county.get("pct_black") if county else None,
                "hispanic": county.get("pct_hispanic") if county else None,
            },
        },
        "households_no_vehicle_pct": {
            "tract": tract.get("pct_no_vehicle"),
            "county": county.get("pct_no_vehicle") if county else None,
        },
        "population": {"tract": tract.get("total_population"),
                       "county": county.get("total_population") if county else None},
    }
