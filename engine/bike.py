"""Cycling time from an origin to facilities.

Added after an FQHC clinician (SS) pointed out that patients arrive at her
health center by bicycle. Without a bike mode the tool reported the WALK time
for those trips, which overstates the burden by roughly a factor of three — and
overstating burden for the population the project is about is not a harmless
error in the safe direction. It makes access look worse than it is, which is
exactly the kind of flattering-to-the-thesis mistake that gets a finding
withdrawn later.

Same shape as walk.py and drive.py: straight-line distance x a detour factor
divided by an effective speed. This is the OFFLINE FALLBACK; when OSRM is
reachable the real routed time is used instead (FOSSGIS runs a `bike` profile
alongside car and foot).

The speed is deliberately conservative. 13 km/h is roughly 8 mph — well below
what a fit cyclist on a greenway does, and chosen to represent an ordinary
person on an ordinary bicycle, possibly carrying something, on streets that
mostly lack bike infrastructure. Erring fast here would understate burden.
"""
from __future__ import annotations

from dataclasses import dataclass

from .geo_utils import MILES_PER_KM, haversine_km

BIKE_SPEED_KMH = 13.0         # ~8 mph effective door-to-door, ordinary rider
NETWORK_DETOUR_FACTOR = 1.25  # cyclists can use some paths cars cannot


@dataclass
class BikeResult:
    facility: dict
    straight_mi: float
    network_mi: float
    minutes: float


def bike_minutes(distance_km: float,
                 speed_kmh: float = BIKE_SPEED_KMH,
                 detour: float = NETWORK_DETOUR_FACTOR) -> float:
    return (distance_km * detour) / speed_kmh * 60.0


def rank_by_bike(origin_lat: float, origin_lon: float, facilities: list[dict],
                 *, k: int | None = None,
                 speed_kmh: float = BIKE_SPEED_KMH,
                 detour: float = NETWORK_DETOUR_FACTOR) -> list[BikeResult]:
    out: list[BikeResult] = []
    for f in facilities:
        if f.get("lat") is None or f.get("lon") is None:
            continue
        straight = haversine_km(origin_lat, origin_lon, f["lat"], f["lon"])
        out.append(BikeResult(
            facility=f,
            straight_mi=round(straight * MILES_PER_KM, 2),
            network_mi=round(straight * detour * MILES_PER_KM, 2),
            minutes=round(bike_minutes(straight, speed_kmh, detour), 1),
        ))
    out.sort(key=lambda r: r.minutes)
    return out[:k] if k else out
