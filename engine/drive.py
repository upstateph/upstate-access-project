"""Driving time from an origin to facilities.

MVP fidelity, mirroring walk.py: straight-line (haversine) distance × a road detour
factor ÷ an effective driving speed. The effective speed is deliberately below the
posted-limit free-flow speed to absorb signals, stops, and typical congestion on a
mixed urban/suburban network. Like the walk model, this is a documented approximation;
the upgrade path is a real road-network router (OSRM / a routing engine) behind the
same interface. See engine/README.md.
"""
from __future__ import annotations

from dataclasses import dataclass

from .geo_utils import MILES_PER_KM, haversine_km

# Tunable assumptions (kept explicit so they can be justified/adjusted).
DRIVE_SPEED_KMH = 40.0        # ~25 mph effective door-to-door on a mixed network
NETWORK_DETOUR_FACTOR = 1.3   # road network is ~30% longer than straight line


@dataclass
class DriveResult:
    facility: dict
    straight_mi: float
    network_mi: float   # estimated on-network distance, in miles
    minutes: float


def drive_minutes(distance_km: float,
                  speed_kmh: float = DRIVE_SPEED_KMH,
                  detour: float = NETWORK_DETOUR_FACTOR) -> float:
    """Convert a straight-line distance (km) to estimated driving minutes."""
    return (distance_km * detour) / speed_kmh * 60.0


def rank_by_drive(origin_lat: float, origin_lon: float, facilities: list[dict],
                  *, k: int | None = None,
                  speed_kmh: float = DRIVE_SPEED_KMH,
                  detour: float = NETWORK_DETOUR_FACTOR) -> list[DriveResult]:
    """Rank facilities by estimated driving time from the origin (nearest first)."""
    results: list[DriveResult] = []
    for f in facilities:
        lat, lon = f.get("lat"), f.get("lon")
        if lat is None or lon is None:
            continue
        straight = haversine_km(origin_lat, origin_lon, float(lat), float(lon))
        results.append(DriveResult(
            facility=f,
            straight_mi=round(straight * MILES_PER_KM, 2),
            network_mi=round(straight * detour * MILES_PER_KM, 2),
            minutes=round(drive_minutes(straight, speed_kmh, detour), 1),
        ))
    results.sort(key=lambda r: r.minutes)
    return results if k is None else results[:k]
