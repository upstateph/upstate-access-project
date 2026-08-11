"""Offline tests for the k-anonymity rollup. Run: python -m engine.tests.test_aggregate"""
from engine.aggregate import AccessRecord, aggregate, anonymize_result


def _recs(tract, n, walk=10.0, reachable=True, transit=30.0):
    return [AccessRecord(tract, walk, transit if reachable else None, reachable) for _ in range(n)]


def test_suppresses_below_threshold():
    # 24 in tract A (< 25 -> suppressed), 25 in tract B (>= 25 -> visible).
    recs = _recs("45045000100", 24) + _recs("45045000200", 25)
    out = aggregate(recs, k=25)
    assert out["n_tracts_visible"] == 1
    assert out["n_tracts_suppressed"] == 1
    assert out["n_observations_suppressed"] == 24
    assert out["tracts"][0]["tract_fips"] == "45045000200"
    assert out["tracts"][0]["n"] == 25


def test_visible_stats_are_computed():
    recs = _recs("45045000200", 30, walk=12.0, transit=40.0)
    t = aggregate(recs, k=25)["tracts"][0]
    assert t["walk_min_mean"] == 12.0
    assert t["transit_min_median"] == 40.0
    assert t["pct_transit_reachable"] == 100.0


def test_partial_reachability_suppresses_sub_k_median():
    """A tract passing k is not enough — each statistic needs its own k observations.

    Here 20 of 25 lookups are transit-reachable, so a transit median would rest on
    only 20 observations. Policy (docs/privacy-design.md) is to suppress ANY
    tract-level statistic computed from fewer than k lookups, so the median is
    withheld while the share (denominator 25) is still published."""
    recs = _recs("45045000200", 20, reachable=True) + _recs("45045000200", 5, reachable=False)
    t = aggregate(recs, k=25)["tracts"][0]
    assert t["n"] == 25
    assert t["pct_transit_reachable"] == 80.0          # 20 of 25 — denominator is n
    assert t["transit_min_median"] is None             # only 20 observations < k
    assert t["walk_min_median"] == 10.0                # all 25 have a walk time


def test_statistic_published_when_subset_meets_k():
    recs = _recs("45045000200", 25, reachable=True) + _recs("45045000200", 3, reachable=False)
    t = aggregate(recs, k=25)["tracts"][0]
    assert t["n"] == 28
    assert t["transit_min_median"] == 30.0             # 25 reachable observations >= k


def test_fail_closed_drops_unattributable():
    recs = _recs("45045000200", 25) + [AccessRecord("", 10.0, 30.0, True)]
    out = aggregate(recs, k=25)
    assert out["tracts"][0]["n"] == 25                 # the empty-tract record dropped


def test_anonymize_strips_identifying_fields():
    result = {
        "ok": True,
        "origin": {"matched_address": "206 S MAIN ST", "lat": 34.8, "lon": -82.4,
                   "tract_fips": "45045000200", "county_fips": "45045"},
        "nearest": {"facility": {"name": "Some Clinic"}, "walk_minutes": 17.5},
        "transit": {"available": True, "reachable": True, "itinerary": {"total_minutes": 32.3}},
    }
    rec = anonymize_result(result)
    assert rec.tract_fips == "45045000200"
    assert rec.walk_minutes == 17.5
    assert rec.transit_minutes == 32.3 and rec.transit_reachable is True
    # No address/coords/facility survive on the record.
    assert not hasattr(rec, "lat") and not hasattr(rec, "matched_address")


def test_anonymize_returns_none_without_tract():
    assert anonymize_result({"ok": True, "origin": {"tract_fips": None}}) is None
    assert anonymize_result({"ok": False}) is None


def _run():
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}"); passed += 1
    print(f"{passed} tests passed.")


if __name__ == "__main__":
    _run()
