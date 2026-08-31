"""Tests for the housing-unit scorer.

These pin three things that are easy to break and expensive to break:
  1. car-free means walk OR transit, so a walkable destination is never scored
     as unreachable just because no bus serves it;
  2. the result carries no composite score and no verdict on the unit, because a
     single number would hide which need failed and a pass/fail on a housing unit
     is a placement decision belonging to a human;
  3. the privacy contract, which is `score()`'s: never echo the address back.
"""
import pytest

from engine import housing as H


@pytest.fixture
def fake_facs():
    """Four one-facility pools at controlled distances from a fixed origin.

    The near pair sits a few hundred metres off rather than exactly on the origin:
    a facility at distance zero has a zero-minute walk, which passes even a
    zero-minute cap and would make the walk-cap test vacuous.
    """
    def at(cat, lat, lon, name):
        return [{"id": name, "name": name, "category": cat,
                 "lat": lat, "lon": lon, "address": "x", "city": "Greenville",
                 "state": "SC", "zip": "29601", "county_fips": "45045"}]
    return {
        "fqhc": at("fqhc", 34.8556, -82.3940, "Near FQHC"),
        "dss": at("dss", 34.8556, -82.3940, "Near DSS"),
        "workforce": at("workforce", 35.20, -82.70, "Far SC Works"),
        "grocery": at("grocery", 35.20, -82.70, "Far grocery"),
    }


def test_walkable_counts_as_reachable_without_transit(monkeypatch, fake_facs):
    """A destination across the street is reachable even with no bus at all."""
    monkeypatch.setattr(H, "transit_to_facilities_window",
                        lambda *a, **k: {"available": True, "reachable": False})
    r = H.score_point(34.8526, -82.3940, facilities=fake_facs, prefer_osrm=False)
    assert r["needs"]["fqhc"]["reachable"] is True
    assert r["needs"]["fqhc"]["by"] == "walk"
    assert r["needs"]["fqhc"]["transit_reachable"] is False
    # ... and the far ones are not reachable, so this is not a vacuous pass.
    assert r["needs"]["grocery"]["reachable"] is False
    assert r["all_four"] is False
    assert r["n_reachable"] == 2


def test_transit_rescues_a_destination_too_far_to_walk(monkeypatch, fake_facs):
    monkeypatch.setattr(H, "transit_to_facilities_window",
                        lambda *a, **k: {"available": True, "reachable": True,
                                         "itinerary": {"total_minutes": 41.0}})
    r = H.score_point(34.8526, -82.3940, facilities=fake_facs, prefer_osrm=False)
    assert r["needs"]["grocery"]["reachable"] is True
    assert r["needs"]["grocery"]["by"] == "transit"
    assert r["needs"]["grocery"]["walk_within_cap"] is False
    assert r["all_four"] is True


def test_walk_cap_is_the_thing_that_decides(monkeypatch, fake_facs):
    """Same geometry, different cap, different answer. Guards a silent default change."""
    monkeypatch.setattr(H, "transit_to_facilities_window",
                        lambda *a, **k: {"available": True, "reachable": False})
    generous = H.score_point(34.8526, -82.3940, walk_cap=10_000,
                             facilities=fake_facs, prefer_osrm=False)
    strict = H.score_point(34.8526, -82.3940, walk_cap=0.0,
                           facilities=fake_facs, prefer_osrm=False)
    assert generous["all_four"] is True
    assert strict["n_reachable"] == 0
    assert strict["walk_cap_min"] == 0.0


def test_reports_which_needs_failed_and_offers_no_composite(monkeypatch, fake_facs):
    """The design decision, pinned: facts per need, no score, no verdict."""
    monkeypatch.setattr(H, "transit_to_facilities_window",
                        lambda *a, **k: {"available": True, "reachable": False})
    r = H.score_point(34.8526, -82.3940, facilities=fake_facs, prefer_osrm=False)
    assert set(r["unreachable"]) == {"Workforce services (SC Works)", "Grocery store"}
    for banned in ("score", "rating", "grade", "recommended", "verdict", "suitable"):
        assert banned not in r, f"{banned!r} implies a judgment this tool must not make"


def test_out_of_county_is_named_not_just_refused(monkeypatch):
    """Greer straddles the county line; a worker needs a boundary, not a failure."""
    class G:
        lat, lon = 34.94, -82.22
        county_fips = "45083"
        matched_address = "601 MAIN ST, GREER, SC, 29651"
    monkeypatch.setattr(H, "geocode", lambda a: G())
    r = H.housing_score("601 N Main St, Greer, SC 29651")
    assert r["ok"] is False
    assert r["error"] == "outside_coverage_area"
    assert r["resolved_county"] == "Spartanburg County"


def test_errors_never_echo_the_address(monkeypatch):
    secret = "742 Evergreen Terrace, Greenville, SC 29601"
    monkeypatch.setattr(H, "geocode", lambda a: None)
    r = H.housing_score(secret)
    assert r == {"ok": False, "error": "address_not_found"}
    assert secret not in repr(r)


def test_needs_list_is_the_four_a_placement_actually_requires():
    assert H.NEEDS == ("fqhc", "dss", "workforce", "grocery")
    assert set(H.NEED_LABELS) == set(H.NEEDS)


def test_coverage_guard_is_shared_with_score(monkeypatch):
    """Both entry points must refuse identically.

    housing_score() once had its own thinner copy of this guard that lost the
    address_needs_city branch, so a bare street address off a rental listing came
    back as "outside the county". That reads as "this unit fails" rather than
    "you did not say which city", which is the wrong message entirely.
    """
    from engine import score as S

    class Far:
        lat, lon = 47.60, -122.33          # Seattle, where "206 S Main St" lands
        county_fips = "53033"
        matched_address = "206 S MAIN ST, SEATTLE, WA"

    monkeypatch.setattr(H, "geocode", lambda a: Far())
    monkeypatch.setattr(S, "geocode", lambda a: Far())

    bare = H.housing_score("206 S Main St")
    assert bare["error"] == "address_needs_city"
    assert S.score("206 S Main St", "fqhc")["error"] == "address_needs_city"

    named = H.housing_score("206 S Main St, Greer, SC")
    assert named["error"] == "outside_coverage_area"
    assert S.score("206 S Main St, Greer, SC", "fqhc")["error"] == "outside_coverage_area"
