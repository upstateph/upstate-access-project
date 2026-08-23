"""Real road-network travel times via OSRM (Open Source Routing Machine).

Upgrades the straight-line walk/drive estimates to actual routed times when an OSRM
server is reachable, using the **table service** (one origin → many facilities in a
single request). Falls back cleanly to None so callers can use the offline estimate.

Servers (public FOSSGIS demo instances, no key; car, foot and bike profiles):
    car:  https://routing.openstreetmap.de/routed-car
    foot: https://routing.openstreetmap.de/routed-foot
    bike: https://routing.openstreetmap.de/routed-bike
Set OSRM_CAR_URL / OSRM_FOOT_URL to point at your own OSRM (recommended for anything
beyond a pilot — the public demo asks for light, non-bulk use). Set OSRM_DISABLE=1 to
force the offline estimate everywhere.

Transport: prefers `requests`; if the local TLS stack can't negotiate with the host
(seen with old LibreSSL), it transparently falls back to a `curl` subprocess. Either
way a failure returns None and the caller uses the estimate — OSRM is never required.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass

import requests

from .geo_utils import MILES_PER_KM

# Profile -> (server base URL, OSRM url profile segment).
SERVERS = {
    "car": (os.environ.get("OSRM_CAR_URL", "https://routing.openstreetmap.de/routed-car"), "driving"),
    "foot": (os.environ.get("OSRM_FOOT_URL", "https://routing.openstreetmap.de/routed-foot"), "foot"),
    # FOSSGIS runs a bike profile alongside car and foot. Verified distinct on a
    # 0.97-mile downtown pair: car 2.6 min, bike 7.2, foot 21.1.
    "bike": (os.environ.get("OSRM_BIKE_URL", "https://routing.openstreetmap.de/routed-bike"), "bike"),
}
# Engine travel mode -> OSRM profile.
MODE_TO_PROFILE = {"walk": "foot", "drive": "car", "bike": "bike"}
_UA = "UpstateAccessProject/pilot (public-health access tool)"
_TIMEOUT = 25


@dataclass
class OsrmResult:
    facility: dict
    minutes: float
    network_mi: float   # real routed distance, in miles


def osrm_disabled() -> bool:
    return os.environ.get("OSRM_DISABLE", "").strip() in ("1", "true", "yes")


def _get_json(url: str) -> dict | None:
    """GET JSON, preferring requests and falling back to curl on transport errors."""
    try:
        r = requests.get(url, timeout=_TIMEOUT, headers={"User-Agent": _UA})
        if r.status_code == 200:
            return r.json()
        return None
    except Exception:
        # Transport failure (e.g. TLS handshake on old LibreSSL) — try curl.
        return _curl_json(url)


def _curl_json(url: str) -> dict | None:
    if not shutil.which("curl"):
        return None
    try:
        out = subprocess.run(
            ["curl", "-s", "--max-time", str(_TIMEOUT), "-A", _UA, url],
            capture_output=True, text=True, timeout=_TIMEOUT + 5,
        )
        if out.returncode != 0 or not out.stdout:
            return None
        return json.loads(out.stdout)
    except Exception:
        return None


def _matrix(origin: tuple[float, float], dests: list[tuple[float, float]], profile: str):
    """Return [(duration_min, distance_km)] origin→each dest, or None on failure."""
    base, seg = SERVERS[profile]
    pts = [origin] + dests
    coord_str = ";".join(f"{lon},{lat}" for lat, lon in pts)  # OSRM is lon,lat
    url = (f"{base}/table/v1/{seg}/{coord_str}"
           f"?sources=0&annotations=duration,distance")
    data = _get_json(url)
    if not data or data.get("code") != "Ok":
        return None
    durs = data.get("durations", [[]])[0]
    dists = data.get("distances", [[]])[0]
    if len(durs) < len(pts) or len(dists) < len(pts):
        return None
    out = []
    for i in range(1, len(pts)):  # skip index 0 (origin→origin)
        d, m = durs[i], dists[i]
        if d is None or m is None:
            out.append(None)  # unroutable destination
        else:
            out.append((round(d / 60.0, 1), round(m / 1000.0, 3)))
    return out


def rank_by_osrm(origin_lat: float, origin_lon: float, facilities: list[dict],
                 mode: str, *, k: int | None = None) -> list[OsrmResult] | None:
    """Rank facilities by real OSRM travel time for a mode ('walk' | 'drive').

    Returns None if OSRM is disabled/unreachable so the caller can fall back to the
    straight-line estimate."""
    if osrm_disabled():
        return None
    profile = MODE_TO_PROFILE[mode]
    with_coords = [f for f in facilities if f.get("lat") is not None and f.get("lon") is not None]
    if not with_coords:
        return None
    dests = [(float(f["lat"]), float(f["lon"])) for f in with_coords]
    matrix = _matrix((origin_lat, origin_lon), dests, profile)
    if matrix is None:
        return None
    results = []
    for f, cell in zip(with_coords, matrix):
        if cell is None:
            continue
        minutes, km = cell
        results.append(OsrmResult(facility=f, minutes=minutes,
                                  network_mi=round(km * MILES_PER_KM, 2)))
    if not results:
        return None
    results.sort(key=lambda r: r.minutes)
    return results if k is None else results[:k]


def available(mode: str = "drive") -> bool:
    """Quick reachability check for one profile (used for status/labeling)."""
    if osrm_disabled():
        return False
    profile = MODE_TO_PROFILE[mode]
    base, seg = SERVERS[profile]
    data = _get_json(f"{base}/table/v1/{seg}/-82.4,34.85;-82.39,34.86?sources=0&annotations=duration")
    return bool(data and data.get("code") == "Ok")
