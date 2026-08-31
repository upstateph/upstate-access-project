"""Every number printed on the housing page must match the data that produced it.

`dashboard/housing-access.html` and `docs/housing-placement-proposal.md` hardcode
county-wide figures. They are correct today and nothing stops them drifting the
next time the pipeline is re-run against a fresh GTFS feed or ACS vintage. A
stale percentage on a public page is the failure this project already withdrew a
claim over, so it gets a guard rather than a good intention.

If this fails after a legitimate data refresh, the fix is to update the page and
the proposal, not to loosen the test.
"""
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data" / "processed" / "housing_access_tract_45045.json"
PAGE = REPO / "dashboard" / "housing-access.html"
PROPOSAL = REPO / "docs" / "housing-placement-proposal.md"

pytestmark = pytest.mark.skipif(
    not DATA.exists(),
    reason="housing rollup not built; run data-pipeline/build_housing_access.py")


@pytest.fixture(scope="module")
def summary():
    return json.loads(DATA.read_text())["summary"]


@pytest.fixture(scope="module")
def units():
    return json.loads(DATA.read_text())["units"]


def _texts():
    out = []
    if PAGE.exists():
        out.append(("housing-access.html", PAGE.read_text()))
    if PROPOSAL.exists():
        out.append(("housing-placement-proposal.md", PROPOSAL.read_text()))
    return out


@pytest.mark.parametrize("key", ["pct_units_all_four", "pct_population_all_four",
                                 "pct_units_none_of_four"])
def test_headline_percentages_appear_and_match(summary, key):
    value = f"{summary[key]}%"
    for name, text in _texts():
        assert value in text, (
            f"{name} does not contain {key} = {value}. Either the data moved and "
            f"the page is stale, or the figure was dropped.")


def test_histogram_counts_match(summary):
    h = summary["n_reachable_histogram"]
    between = h["1"] + h["2"] + h["3"]
    for name, text in _texts():
        nums = set(re.findall(r"\b\d+\b", text))
        for label, n in (("zero", h["0"]), ("all four", h["4"]), ("in between", between)):
            assert str(n) in nums, f"{name} is missing the {label} count ({n})"


def test_per_need_reachability_matches(summary):
    for need, d in summary["per_need"].items():
        value = f"{d['pct_units_reachable']}%"
        for name, text in _texts():
            assert value in text, f"{name} is missing {need} reachability {value}"


def test_income_and_vehicle_table_matches(units):
    """The proposal's central argument, recomputed from the units."""
    ok4 = [u for u in units if u["access"]["all_four"]]
    no4 = [u for u in units if u["access"]["n_reachable"] == 0]

    def avg(rows, k):
        v = [r[k] for r in rows if r.get(k) is not None]
        return sum(v) / len(v)

    text = PROPOSAL.read_text()
    assert f"${round(avg(ok4, 'median_household_income')):,}" in text
    assert f"${round(avg(no4, 'median_household_income')):,}" in text
    assert f"{round(avg(ok4, 'pct_no_vehicle'), 1)}%" in text
    assert f"{round(avg(no4, 'pct_no_vehicle'), 1)}%" in text


def test_dss_really_is_a_single_office():
    """The proposal's sharpest claim. If a second office opens, the copy is wrong."""
    dss = json.loads((REPO / "data" / "processed" / "facilities_dss.json").read_text())
    n = len(dss["facilities"])
    assert n == 1, (
        f"{n} DSS offices in the data, but the page and proposal both say one "
        f"office serves the county.")
