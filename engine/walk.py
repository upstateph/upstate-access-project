"""Walking time from an origin to facilities.

MVP fidelity: straight-line (haversine) distance × a detour factor to approximate
real street-network length, divided by a walking speed. This is intentionally
dependency-light and is the documented first approximation; a later upgrade can swap
in true pedestrian-network routing (e.g. OSM via a routing engine) behind the same
interface without changing callers. See engine/README.md.
"""
from __future__ import annotations

from dataclasses import dataclass

from .geo_utils import haversine_km

# Tunable assumptions (kept explicit so they can be justified/adjusted).
WALK_SPEED_KMH = 4.8        # ~3.0 mph, a standard pedestrian planning speed
NETWORK_DETOUR_FACTOR = 1.3  # street network is ~30% longer than straight line


@dataclass
class WalkResult:
    facility: dict
    straight_km: float
    network_km: float
    minutes: float


def walk_minutes(distance_km: float,
                 speed_kmh: float = WALK_SPEED_KMH,
                 detour: float = NETWORK_DETOUR_FACTOR) -> float:
    """Convert a straight-line distance (km) to estimated walk minutes."""
    return (distance_km * detour) / speed_kmh * 60.0


def rank_by_walk(origin_lat: float, origin_lon: float, facilities: list[dict],
                 *, k: int | None = None,
                 speed_kmh: float = WALK_SPEED_KMH,
                 detour: float = NETWORK_DETOUR_FACTOR) -> list[WalkResult]:
    """Rank facilities by estimated walking time from the origin (nearest first).

    Each facility must have numeric 'lat' and 'lon'. Facilities missing coordinates
    are skipped. Returns the top k (or all, if k is None).
    """
    results: list[WalkResult] = []
    for f in facilities:
        lat, lon = f.get("lat"), f.get("lon")
        if lat is None or lon is None:
            continue
        straight = haversine_km(origin_lat, origin_lon, float(lat), float(lon))
        network = straight * detour
        results.append(WalkResult(
            facility=f,
            straight_km=round(straight, 3),
            network_km=round(network, 3),
            minutes=round(walk_minutes(straight, speed_kmh, detour), 1),
        ))
    results.sort(key=lambda r: r.minutes)
    return results if k is None else results[:k]
