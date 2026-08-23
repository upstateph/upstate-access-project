"""Cycling is a distinct mode, not a proxy for walking.

Added after an FQHC clinician reported patients arriving by bicycle. Before
this, those trips were reported at WALK time — roughly three times the real
burden. Overstating burden is not a harmless error in the safe direction: it
makes access look worse than it is, which flatters the project's own thesis.
"""
from __future__ import annotations

import pytest

from engine import routing
from engine.bike import BIKE_SPEED_KMH, bike_minutes, rank_by_bike
from engine.walk import WALK_SPEED_KMH

FACILITIES = [
    {"name": "Near", "lat": 34.8525, "lon": -82.3981},
    {"name": "Far", "lat": 34.9000, "lon": -82.4500},
    {"name": "No coords", "lat": None, "lon": None},
]
ORIGIN = (34.8484, -82.4001)


def test_bike_is_faster_than_walking_over_the_same_distance():
    assert bike_minutes(5.0) < bike_minutes(5.0) * 2
    assert BIKE_SPEED_KMH > WALK_SPEED_KMH


def test_bike_ranks_nearest_first_and_skips_missing_coordinates():
    out = rank_by_bike(*ORIGIN, FACILITIES)
    assert [r.facility["name"] for r in out] == ["Near", "Far"]
    assert all(r.minutes > 0 for r in out)


def test_routing_accepts_bike_as_a_mode():
    r = routing.nearest(*ORIGIN, FACILITIES, "bike", k=1, prefer_osrm=False)
    assert r["method"] == "estimate"
    assert r["results"][0]["facility"]["name"] == "Near"


def test_unknown_mode_still_rejected_and_names_the_valid_ones():
    with pytest.raises(ValueError) as e:
        routing.nearest(*ORIGIN, FACILITIES, "teleport", prefer_osrm=False)
    assert "bike" in str(e.value)


def test_bike_speed_is_conservative():
    """A fast assumption would understate burden for the population this is
    about. 13 km/h is an ordinary rider on streets without bike infrastructure."""
    assert 10.0 <= BIKE_SPEED_KMH <= 16.0
