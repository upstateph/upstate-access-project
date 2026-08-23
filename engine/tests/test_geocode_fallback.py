"""The fallback geocoder, and the county boundary it must not blur.

The Census geocoder returned no match for 6 of 30 real Greenville County
addresses — rural routes and unincorporated places like Slater-Marietta. Each
failure is a dead end that reads as the tool being broken. OpenStreetMap
rescues some of them, but it returns no census geography, so the tract is
recovered by point-in-polygon against the county boundaries already shipped for
the map. That is also what enforces coverage: a point in no Greenville tract
gets no county, and score() refuses it.
"""
from __future__ import annotations

from unittest.mock import patch

from engine import geocode as G
from engine import score as S


def test_point_in_polygon_places_downtown_in_a_tract():
    assert G.tract_for_point(34.8484, -82.4001) is not None


def test_point_in_polygon_rejects_a_point_far_outside_the_county():
    assert G.tract_for_point(38.8977, -77.0365) is None      # White House


def test_fallback_is_only_consulted_when_census_has_no_match():
    with patch.object(G, "_nominatim") as nomi:
        with patch.object(G.requests, "get") as get:
            get.return_value.status_code = 200
            get.return_value.raise_for_status = lambda: None
            get.return_value.json = lambda: {"result": {"addressMatches": [{
                "coordinates": {"x": -82.4001, "y": 34.8484},
                "matchedAddress": "206 S MAIN ST",
                "geographies": {"Census Tracts": [{"GEOID": "45045000200"}]},
            }]}}
            r = G.geocode("206 S Main St, Greenville, SC 29601")
    assert r is not None and r.source == "census"
    nomi.assert_not_called()


class _Geo:
    """A fallback hit that landed outside every county tract."""
    lat, lon = 35.9, -82.9
    tract_fips = None
    county_fips = None
    matched_address = "somewhere else"
    source = "nominatim"


def test_unknown_county_is_refused_rather_than_assumed():
    """Fail closed. A fallback hit outside the tracts has no county, and
    'unknown' must not be treated as 'probably fine' — that is how an
    out-of-county address gets a confident in-county answer."""
    with patch.object(S, "geocode", return_value=_Geo()):
        r = S.score("anywhere at all")
    assert r["ok"] is False and r["error"] == "outside_coverage_area"


def test_refusal_names_a_neighbouring_county_when_it_can():
    """Greer, Piedmont and Fountain Inn straddle county lines, so a resident can
    type a real local address and be refused. Naming the county turns an
    apparent malfunction into a visible boundary."""
    class Spartanburg(_Geo):
        county_fips = "45083"
        tract_fips = "45083000100"
    with patch.object(S, "geocode", return_value=Spartanburg()):
        r = S.score("101 N Main St, Greer, SC 29651")
    assert r["resolved_county"] == "Spartanburg County"
