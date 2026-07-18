"""Unified nearest-facility routing for walk & drive.

`nearest()` prefers real OSRM road-network times and falls back to the straight-line
estimate, returning a common shape plus which method was used. This lets score() and
the access rollup ask for "walk"/"drive" times without caring about the backend.

Transit is separate (GTFS) — see transit.py.
"""
from __future__ import annotations

from . import osrm
from .drive import rank_by_drive
from .walk import rank_by_walk

_ESTIMATORS = {"walk": rank_by_walk, "drive": rank_by_drive}


def nearest(origin_lat: float, origin_lon: float, facilities: list[dict], mode: str,
            *, k: int | None = None, prefer_osrm: bool = True) -> dict:
    """Rank facilities by travel time for a mode ('walk' | 'drive').

    Returns {"method": "osrm"|"estimate", "results": [{facility, minutes, network_km}]}.
    """
    if mode not in _ESTIMATORS:
        raise ValueError(f"mode must be 'walk' or 'drive', got {mode!r}")

    if prefer_osrm:
        osrm_ranked = osrm.rank_by_osrm(origin_lat, origin_lon, facilities, mode, k=k)
        if osrm_ranked is not None:
            return {
                "method": "osrm",
                "results": [
                    {"facility": r.facility, "minutes": r.minutes, "network_mi": r.network_mi}
                    for r in osrm_ranked
                ],
            }

    est = _ESTIMATORS[mode](origin_lat, origin_lon, facilities, k=k)
    return {
        "method": "estimate",
        "results": [
            {"facility": r.facility, "minutes": r.minutes, "network_mi": r.network_mi}
            for r in est
        ],
    }
