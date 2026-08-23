"""An origin outside the modelled county must be refused, not answered.

Before this guard the tool returned ok=true with a 10,509-minute walk (7.3 days)
from the White House to a Greenville clinic, and 11 days from Chicago. A
confident nonsense number is worse than an error: it looks like a working
answer, and every remote reviewer tries their own address first.
"""
from unittest.mock import patch

from engine import score as S


class _Geo:
    def __init__(self, county):
        self.lat, self.lon = 34.85, -82.40
        self.tract_fips, self.county_fips = county + "000200", county
        self.matched_address = "somewhere"


def test_out_of_county_origin_is_refused():
    with patch.object(S, "geocode", return_value=_Geo("11001")):        # DC
        r = S.score("1600 Pennsylvania Ave NW, Washington, DC 20500")
    assert r["ok"] is False
    assert r["error"] == "outside_coverage_area"


def test_out_of_state_origin_is_refused():
    with patch.object(S, "geocode", return_value=_Geo("17031")):        # Cook County, IL
        r = S.score("233 S Wacker Dr, Chicago, IL 60606")
    assert r["ok"] is False and r["error"] == "outside_coverage_area"


def test_refusal_names_the_coverage_area_so_the_user_can_act():
    with patch.object(S, "geocode", return_value=_Geo("11001")):
        r = S.score("anywhere")
    assert "Greenville" in r.get("coverage", "")


def test_in_county_origin_is_not_refused_by_the_guard():
    """The guard must not fire on a valid address — verified by getting past it
    to the facility-loading stage rather than by asserting a full result."""
    with patch.object(S, "geocode", return_value=_Geo("45045")):
        with patch.object(S, "load_facilities", side_effect=FileNotFoundError):
            try:
                r = S.score("206 S Main St, Greenville, SC 29601")
            except FileNotFoundError:
                return  # reached load_facilities => guard did not fire
    assert r.get("error") != "outside_coverage_area"
