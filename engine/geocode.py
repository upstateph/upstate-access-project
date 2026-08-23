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

import json
import time
from dataclasses import dataclass
from pathlib import Path

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
    source: str = "census"   # which geocoder answered

    def as_dict(self) -> dict:
        return {
            "matched_address": self.matched_address,
            "lat": self.lat,
            "lon": self.lon,
            "tract_fips": self.tract_fips,
            "county_fips": self.county_fips,
            "source": self.source,
        }


def geocode(address: str, *, timeout: int = 30, retries: int = 2,
            backoff: float = 2.0) -> GeocodeResult | None:
    """Geocode a one-line address. Returns None if no match is found."""
    params = {
        "address": address,
        "benchmark": BENCHMARK,
        "vintage": VINTAGE,
        "format": "json",
    }
    # Retry with backoff. The Census geocoder throttles sustained bulk use, and a
    # single refusal used to abort an entire pipeline run partway through — a
    # 700-address category fetch died on one transient 5xx and wrote nothing.
    matches = None
    for attempt in range(retries + 1):
        try:
            resp = requests.get(GEOCODER_URL, params=params, timeout=timeout)
            resp.raise_for_status()
            matches = resp.json().get("result", {}).get("addressMatches", [])
            break
        except (requests.RequestException, ValueError):
            if attempt == retries:
                # Never propagate the original exception: it embeds the request URL,
                # which contains the address.
                raise GeocoderUnavailable() from None
            time.sleep(backoff * (2 ** attempt))
    if not matches:
        # Census has no match. Try OpenStreetMap before giving up — it covers
        # rural routes and unincorporated places that Census misses.
        return _nominatim(address, timeout=timeout)

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


# ── Fallback geocoder ─────────────────────────────────────────────────────────
# The Census geocoder failed on 6 of 30 real Greenville County addresses (20%):
# rural routes, small unincorporated places (Tigerville, Slater-Marietta), and
# some ordinary suburban streets. Each failure is a dead end for the person
# typing it, and "no match for that address" reads as the tool being broken
# rather than one federal API having patchy coverage.
#
# OpenStreetMap's Nominatim is the fallback. It returns coordinates but NOT
# census geography, which this project needs for the equity join — so the tract
# is recovered by point-in-polygon against the county tract boundaries already
# shipped for the map. That has a useful side effect: a point outside every
# Greenville tract yields no county, and the caller refuses it. The coverage
# boundary is enforced by the same step that assigns the tract.
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
# Nominatim's usage policy requires an identifying User-Agent and at most one
# request per second. This is an interactive, one-address-at-a-time path, but
# the interval is enforced rather than assumed.
_NOMINATIM_UA = "UpstateAccessProject/pilot (public-health access tool; nikhilajain@gmail.com)"
_NOMINATIM_MIN_INTERVAL = 1.1
_last_nominatim_call = 0.0

_TRACTS_PATH = Path(__file__).resolve().parent.parent / "dashboard" / "data" / "tracts_45045.geojson"
_tracts_cache: list[tuple[str, list]] | None = None


def _load_tracts() -> list[tuple[str, list]]:
    """(GEOID, list-of-rings) per tract. Cached; empty if the file is absent."""
    global _tracts_cache
    if _tracts_cache is not None:
        return _tracts_cache
    out: list[tuple[str, list]] = []
    try:
        with _TRACTS_PATH.open(encoding="utf-8") as fh:
            data = json.load(fh)
        for feat in data.get("features", []):
            geoid = (feat.get("properties") or {}).get("GEOID")
            geom = feat.get("geometry") or {}
            if not geoid or not geom.get("coordinates"):
                continue
            polys = ([geom["coordinates"]] if geom.get("type") == "Polygon"
                     else geom["coordinates"])
            rings = [ring for poly in polys for ring in poly]
            out.append((str(geoid), rings))
    except (OSError, ValueError, KeyError):
        out = []
    _tracts_cache = out
    return out


def _point_in_ring(lat: float, lon: float, ring: list) -> bool:
    """Ray casting. Ring coordinates are [lon, lat] per GeoJSON."""
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (y1 > lat) != (y2 > lat):
            if y2 != y1 and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
                inside = not inside
    return inside


def tract_for_point(lat: float, lon: float) -> str | None:
    """GEOID of the county tract containing this point, or None if outside."""
    for geoid, rings in _load_tracts():
        if rings and _point_in_ring(lat, lon, rings[0]):
            # Subsequent rings are holes; a point in a hole is not in the tract.
            if not any(_point_in_ring(lat, lon, hole) for hole in rings[1:]):
                return geoid
    return None


def _nominatim(address: str, *, timeout: int) -> GeocodeResult | None:
    """Second-chance geocode via OpenStreetMap. Returns None if it also fails."""
    global _last_nominatim_call
    wait = _NOMINATIM_MIN_INTERVAL - (time.monotonic() - _last_nominatim_call)
    if wait > 0:
        time.sleep(wait)
    params = {"q": address, "format": "jsonv2", "limit": 1,
              "countrycodes": "us", "addressdetails": 0}
    try:
        resp = requests.get(NOMINATIM_URL, params=params, timeout=timeout,
                            headers={"User-Agent": _NOMINATIM_UA})
        _last_nominatim_call = time.monotonic()
        resp.raise_for_status()
        hits = resp.json()
    except (requests.RequestException, ValueError):
        _last_nominatim_call = time.monotonic()
        return None
    if not hits:
        return None

    hit = hits[0]
    try:
        lat, lon = float(hit["lat"]), float(hit["lon"])
    except (KeyError, TypeError, ValueError):
        return None

    tract = tract_for_point(lat, lon)
    # No tract means the point is outside Greenville County. Return it with no
    # county rather than guessing: score() refuses anything that is not 45045,
    # so an out-of-area fallback hit is declined instead of silently answered.
    return GeocodeResult(
        matched_address=hit.get("display_name", address),
        lat=lat, lon=lon,
        tract_fips=tract,
        county_fips=tract[:5] if tract else None,
        source="nominatim",
    )
