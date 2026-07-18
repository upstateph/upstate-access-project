#!/usr/bin/env python3
"""Join processed FARS + ACS + context into the JSON the Tier 1 dashboard reads.

Reads from data/processed/ and writes a single consolidated dashboard.json into
both data/processed/ and dashboard/data/ (the static site reads the latter).

The ACS join is optional: if census_acs_sc_counties.json is missing (e.g. no Census
API key yet), the dashboard still renders FARS trends and counts, with equity fields
marked unavailable. Run fetch_fars.py, context.py, and (ideally) fetch_census_acs.py
first.

Usage:
    python build_dashboard_data.py
"""
from __future__ import annotations

import sys

from common import (
    DASHBOARD_DATA_DIR,
    PROCESSED_DIR,
    SC_COUNTIES,
    ensure_dirs,
    read_json,
    write_json,
)

UNKNOWN_FIPS = "45999"


def load_fars() -> dict:
    path = PROCESSED_DIR / "fars_sc_pedestrian.json"
    if not path.exists():
        sys.exit("ERROR: run fetch_fars.py first (missing fars_sc_pedestrian.json).")
    return read_json(path)


def load_acs() -> dict | None:
    path = PROCESSED_DIR / "census_acs_sc_counties.json"
    if not path.exists():
        print("  note: ACS data not found — building without the equity overlay.")
        print("        run fetch_census_acs.py (needs CENSUS_API_KEY) to add it.")
        return None
    return read_json(path)


def load_population() -> dict:
    """Keyless PEP county population (fetch_county_population.py). {} if absent."""
    path = PROCESSED_DIR / "county_population_sc.json"
    if not path.exists():
        print("  note: county population not found — per-capita metric omitted.")
        print("        run fetch_county_population.py (no key needed) to add it.")
        return {}
    return read_json(path)["population_by_county"]


def load_context() -> dict | None:
    path = PROCESSED_DIR / "context.json"
    return read_json(path) if path.exists() else None


def main() -> None:
    ensure_dirs()
    fars = load_fars()
    acs = load_acs()
    context = load_context()

    years = fars["years"]
    n_years = len(years)

    acs_by_fips = {}
    if acs:
        acs_by_fips = {c["county_fips"]: c for c in acs["counties"]}
    population = load_population()

    counties = []
    unknown_county_total = 0
    for row in fars["counties"]:
        fips = row["county_fips"]
        if fips == UNKNOWN_FIPS:
            unknown_county_total = row["total"]
            continue

        rec = {
            "county_fips": fips,
            "name": SC_COUNTIES.get(fips, f"County {fips}"),
            "ped_total": row["total"],
            "ped_by_year": row["by_year"],
            "avg_annual_ped": round(row["total"] / n_years, 2) if n_years else None,
        }

        # Keyless per-capita rate: total pedestrian deaths per 100k residents.
        pop_est = population.get(fips)
        rec["population_est"] = pop_est
        rec["ped_per_100k_pop"] = (
            round(row["total"] / pop_est * 100_000, 1) if pop_est else None
        )

        a = acs_by_fips.get(fips)
        if a:
            pop = a.get("total_population")
            rec["population"] = pop
            rec["median_household_income"] = a.get("median_household_income")
            rec["pct_white"] = a.get("pct_white")
            rec["pct_black"] = a.get("pct_black")
            rec["pct_hispanic"] = a.get("pct_hispanic")
            if pop:
                annual = row["total"] / n_years
                rec["ped_rate_per_100k_annual"] = round(annual / pop * 100_000, 2)
            else:
                rec["ped_rate_per_100k_annual"] = None
        else:
            rec.update({
                "population": None,
                "median_household_income": None,
                "pct_white": None,
                "pct_black": None,
                "pct_hispanic": None,
                "ped_rate_per_100k_annual": None,
            })
        counties.append(rec)

    counties.sort(key=lambda r: r["ped_total"], reverse=True)

    dashboard = {
        "generated_note": (
            "Tier 1 statewide tracker data. FARS pedestrian fatalities joined with "
            "Census ACS county demographics. See docs/data-sources.md."
        ),
        "state": "South Carolina",
        "years": years,
        "state_totals_by_year": fars["state_totals_by_year"],
        "state_total": sum(fars["state_totals_by_year"].values()),
        "fars_source": fars["source"],
        "acs_available": acs is not None,
        "acs_vintage": acs["vintage"] if acs else None,
        "acs_source": acs["source"] if acs else None,
        "population_available": bool(population),
        "population_source": "Census PEP 2024 county estimates" if population else None,
        "unknown_county_total": unknown_county_total,
        "counties": counties,
        "context": context,
    }

    write_json(PROCESSED_DIR / "dashboard.json", dashboard, label="dashboard.json (processed)")
    write_json(DASHBOARD_DATA_DIR / "dashboard.json", dashboard, label="dashboard.json (site)")

    equity = "with equity overlay" if acs else "WITHOUT equity overlay (no ACS yet)"
    print(f"Done: {len(counties)} counties, {dashboard['state_total']} fatalities, {equity}.")


if __name__ == "__main__":
    main()
