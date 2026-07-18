"""Top-level scoring: address + category -> access result.

Orchestrates geocode -> nearest facility by walk -> (optional) transit time ->
(optional) equity comparison. Transit and equity are pluggable: if the Greenlink
GTFS feed or the ACS data hasn't been loaded yet, those fields come back as None
with a reason, and the walk-based result still works end to end.

Privacy: the address is used transiently to geocode and is not persisted here.
"""
from __future__ import annotations

from .facilities import load_facilities
from .geocode import geocode
from .walk import rank_by_walk


def score(address: str, category: str = "fqhc", *, candidates: int = 5) -> dict:
    """Compute access from an address to the nearest facility of a category.

    Returns a JSON-serializable dict. Raises FileNotFoundError if the category's
    facility data hasn't been pulled yet.
    """
    geo = geocode(address)
    if geo is None:
        return {"ok": False, "error": "address_not_found", "address": address}

    facilities = load_facilities(category)
    ranked = rank_by_walk(geo.lat, geo.lon, facilities, k=candidates)
    if not ranked:
        return {"ok": False, "error": "no_facilities_with_coordinates", "category": category}

    nearest = ranked[0]

    # Transit is optional — only computed if the GTFS feed has been loaded.
    transit = _try_transit(geo, ranked)

    result = {
        "ok": True,
        "category": category,
        "origin": geo.as_dict(),
        "nearest": {
            "facility": nearest.facility,
            "walk_minutes": nearest.minutes,
            "walk_network_km": nearest.network_km,
        },
        "transit": transit,
        "alternatives": [
            {"facility": r.facility, "walk_minutes": r.minutes} for r in ranked[1:]
        ],
        "equity": _try_equity(geo),
    }
    return result


def _try_transit(geo, ranked) -> dict | None:
    """Compute Greenlink transit time to the nearest reachable facility, if the
    GTFS feed is available. Returns None-with-reason otherwise."""
    try:
        from .transit import transit_to_facilities  # lazy: needs GTFS loaded
    except Exception:
        return {"available": False, "reason": "transit module not available"}
    try:
        return transit_to_facilities(geo.lat, geo.lon, [r.facility for r in ranked])
    except FileNotFoundError:
        return {"available": False, "reason": "Greenlink GTFS feed not loaded (run fetch_greenlink_gtfs.py)"}


def _try_equity(geo) -> dict | None:
    """Compare the origin tract to its county using ACS data, if loaded."""
    try:
        from .equity import compare_tract_to_county  # lazy: needs ACS loaded
    except Exception:
        return None
    try:
        return compare_tract_to_county(geo.tract_fips, geo.county_fips)
    except FileNotFoundError:
        return {"available": False, "reason": "ACS data not loaded (run fetch_census_acs.py)"}


if __name__ == "__main__":
    import json
    import sys

    addr = " ".join(sys.argv[1:]) or "206 S Main St, Greenville, SC 29601"
    print(json.dumps(score(addr), indent=2))
