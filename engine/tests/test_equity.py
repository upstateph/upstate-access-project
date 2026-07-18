"""Offline tests for equity comparison. Run: python -m engine.tests.test_equity

Uses synthetic ACS fixtures written to a temp dir — no Census key or network needed.
"""
import json
import tempfile
from pathlib import Path

from engine.equity import compare_tract_to_county

COUNTY_FIPS = "45045"
TRACT_FIPS = "45045000200"


def _fixtures(tmp: Path):
    counties = {
        "vintage": "2024",
        "counties": [{
            "county_fips": COUNTY_FIPS, "name": "Greenville County, South Carolina",
            "median_household_income": 70000, "total_population": 500000,
            "pct_white": 70.0, "pct_black": 18.0, "pct_hispanic": 9.0,
        }],
    }
    tracts = {
        "vintage": "2024", "geography": "tract", "county_fips": COUNTY_FIPS,
        "tracts": [
            {"tract_fips": TRACT_FIPS, "median_household_income": 35000,
             "total_population": 4000, "pct_white": 40.0, "pct_black": 45.0, "pct_hispanic": 12.0},
            {"tract_fips": "45045000300", "median_household_income": 90000,
             "total_population": 5000, "pct_white": 85.0, "pct_black": 8.0, "pct_hispanic": 4.0},
            {"tract_fips": "45045000400", "median_household_income": 55000,
             "total_population": 4500, "pct_white": 60.0, "pct_black": 30.0, "pct_hispanic": 7.0},
        ],
    }
    cf = tmp / "counties.json"; tf = tmp / "tracts.json"
    cf.write_text(json.dumps(counties)); tf.write_text(json.dumps(tracts))
    return cf, tf


def test_low_income_tract_vs_county():
    with tempfile.TemporaryDirectory() as d:
        cf, tf = _fixtures(Path(d))
        r = compare_tract_to_county(TRACT_FIPS, COUNTY_FIPS, counties_file=cf, tracts_file=tf)
    assert r["available"] is True
    inc = r["median_household_income"]
    assert inc["tract"] == 35000 and inc["county"] == 70000
    assert inc["ratio_to_county"] == 0.5                       # 35k / 70k
    assert inc["pct_of_county_tracts_below"] == 0.0            # lowest of the 3 tracts
    assert r["race_ethnicity_pct"]["tract"]["black"] == 45.0
    assert r["race_ethnicity_pct"]["county"]["black"] == 18.0


def test_missing_fips_returns_unavailable():
    with tempfile.TemporaryDirectory() as d:
        cf, tf = _fixtures(Path(d))
        r = compare_tract_to_county(None, COUNTY_FIPS, counties_file=cf, tracts_file=tf)
    assert r["available"] is False


def _run():
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}"); passed += 1
    print(f"{passed} tests passed.")


if __name__ == "__main__":
    _run()
