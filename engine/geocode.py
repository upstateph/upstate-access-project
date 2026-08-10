"""Address geocoding via the US Census Geocoder (free, no API key).

Turns a street address into a lat/lon plus its Census tract and county FIPS, which
the equity comparison later joins against ACS demographics.

Endpoint (verified July 2026):
  https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress
    ?address=...&benchmark=Public_AR_Current&vintage=Current_Current&format=json

Privacy: the address is sent only to the Census geocoder to resolve coordinates and
is never written to disk or logs by this module.
"""
from __future__ import annotations

from dataclasses import dataclass

import requests

GEOCODER_URL = "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
BENCHMARK = "Public_AR_Current"
VINTAGE = "Current_Current"


class GeocoderUnavailable(RuntimeError):
    """The geocoding service could not be reached.

    Deliberately carries a FIXED message: requests' own exceptions embed the full
    request URL — including the URL-encoded home address — in str(e), and server
    error handlers echo str(e) to clients/logs. This wrapper is the privacy boundary."""

    def __init__(self):
        super().__init__("geocoding service unreachable")


@dataclass
class GeocodeResult:
    matched_address: str
    lat: float
    lon: float
    tract_fips: str | None   # 11-digit: state(2)+county(3)+tract(6)
    county_fips: str | None  # 5-digit: state(2)+county(3)

    def as_dict(self) -> dict:
        return {
            "matched_address": self.matched_address,
            "lat": self.lat,
            "lon": self.lon,
            "tract_fips": self.tract_fips,
            "county_fips": self.county_fips,
        }


def geocode(address: str, *, timeout: int = 30) -> GeocodeResult | None:
    """Geocode a one-line address. Returns None if no match is found."""
    params = {
        "address": address,
        "benchmark": BENCHMARK,
        "vintage": VINTAGE,
        "format": "json",
    }
    try:
        resp = requests.get(GEOCODER_URL, params=params, timeout=timeout)
        resp.raise_for_status()
        matches = resp.json().get("result", {}).get("addressMatches", [])
    except requests.RequestException:
        raise GeocoderUnavailable() from None  # never propagate the address-bearing URL
    if not matches:
        return None

    m = matches[0]
    coords = m["coordinates"]  # x = lon, y = lat
    geos = m.get("geographies", {})

    tract_fips = _first_geoid(geos, ("Census Tracts", "2020 Census Tracts"))
    county_fips = _first_geoid(geos, ("Counties", "2020 Census Counties"))
    # County FIPS is the first 5 digits of the tract GEOID if not returned directly.
    if not county_fips and tract_fips and len(tract_fips) >= 5:
        county_fips = tract_fips[:5]

    return GeocodeResult(
        matched_address=m.get("matchedAddress", address),
        lat=float(coords["y"]),
        lon=float(coords["x"]),
        tract_fips=tract_fips,
        county_fips=county_fips,
    )


def _first_geoid(geographies: dict, layer_names: tuple[str, ...]) -> str | None:
    for name in layer_names:
        layer = geographies.get(name)
        if layer:
            geoid = layer[0].get("GEOID")
            if geoid:
                return geoid
    return None


if __name__ == "__main__":
    import sys

    addr = " ".join(sys.argv[1:]) or "206 S Main St, Greenville, SC 29601"
    r = geocode(addr)
    if r is None:
        print(f"No match for: {addr}")
    else:
        print(f"Matched: {r.matched_address}")
        print(f"  lat/lon: {r.lat}, {r.lon}")
        print(f"  tract:   {r.tract_fips}")
        print(f"  county:  {r.county_fips}")
