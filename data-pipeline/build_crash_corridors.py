#!/usr/bin/env python3
"""Build the crash-corridor overlay: FARS fatality points × walking routes to care.

For each Greenville County tract, fetches the actual OSRM walking-route geometry from
the tract's internal point to its nearest FQHC, then measures which FARS pedestrian
fatality points (fetch_fars_points.py) lie within PROXIMITY_M of a route. The output
lets the access page show, corridor by corridor, that the roads people must walk to
reach care overlap the roads where pedestrians die.

Honest bounds, stated in the output:
  - Routes are modeled (one internal point per tract, nearest-FQHC-by-walk), not
    observed foot traffic.
  - Counts are POINTS NEAR A LINE, never rates — n is far too small per corridor
    for statistical claims. The overlay is evidence of overlap, not of causation.

Uses the public OSRM demo server politely (one route call per tract, rate-limited).

Usage:
    python build_crash_corridors.py
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR))

from common import DASHBOARD_DATA_DIR, PROCESSED_DIR, ensure_dirs, read_json, write_json  # noqa: E402
from engine.facilities import load_facilities  # noqa: E402
from engine.osrm import SERVERS, _get_json  # noqa: E402
from engine.routing import nearest as route_nearest  # noqa: E402

COUNTY_FIPS = "45045"
PROXIMITY_M = 150.0        # a point within this distance of a route "lies on" it
POLITE_DELAY_S = 0.4       # between OSRM route calls (public demo server)
POINTS_FILE = PROCESSED_DIR / f"fars_ped_points_{COUNTY_FIPS}.json"


def fetch_walk_route(olat: float, olon: float, dlat: float, dlon: float) -> list | None:
    """Full walking-route geometry [(lat, lon), ...] via OSRM, or None."""
    base, seg = SERVERS["foot"]
    url = (f"{base}/route/v1/{seg}/{olon},{olat};{dlon},{dlat}"
           f"?overview=full&geometries=geojson")
    data = _get_json(url)
    if not data or data.get("code") != "Ok" or not data.get("routes"):
        return None
    coords = data["routes"][0]["geometry"]["coordinates"]  # [lon, lat] pairs
    return [(lat, lon) for lon, lat in coords]


def point_segment_m(plat: float, plon: float, a: tuple, b: tuple) -> float:
    """Distance in meters from point to segment a-b (local flat-earth approx —
    fine at county scale for a 150 m threshold)."""
    ky = 111_320.0                                   # m per degree latitude
    kx = ky * math.cos(math.radians(plat))           # m per degree longitude here
    ax, ay = (a[1] - plon) * kx, (a[0] - plat) * ky
    bx, by = (b[1] - plon) * kx, (b[0] - plat) * ky
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(ax, ay)
    t = max(0.0, min(1.0, -(ax * dx + ay * dy) / (dx * dx + dy * dy)))
    return math.hypot(ax + t * dx, ay + t * dy)


def min_dist_to_route_m(plat: float, plon: float, route: list) -> float:
    return min(point_segment_m(plat, plon, route[i], route[i + 1])
               for i in range(len(route) - 1))


def thin(route: list) -> list:
    """Round + de-duplicate coordinates for the published file (display fidelity)."""
    out = []
    for lat, lon in route:
        pt = [round(lat, 5), round(lon, 5)]
        if not out or out[-1] != pt:
            out.append(pt)
    return out


def main() -> None:
    ensure_dirs()
    if not POINTS_FILE.exists():
        sys.exit(f"ERROR: {POINTS_FILE.name} missing — run fetch_fars_points.py first.")
    points_doc = read_json(POINTS_FILE)
    points = points_doc["points"]

    geojson_path = DASHBOARD_DATA_DIR / f"tracts_{COUNTY_FIPS}.geojson"
    if not geojson_path.exists():
        sys.exit(f"ERROR: {geojson_path.name} missing — run fetch_tract_geojson.py first.")
    feats = read_json(geojson_path)["features"]
    facilities = load_facilities("fqhc")

    print(f"Routing {len(feats)} tracts to their nearest FQHC (OSRM foot, full geometry) ...")
    routes, n_estimate_only = [], 0
    for i, f in enumerate(feats):
        p = f["properties"]
        lat, lon = float(p["INTPTLAT"]), float(p["INTPTLON"])
        near = route_nearest(lat, lon, facilities, "walk", k=1)
        if not near["results"]:
            continue
        fac = near["results"][0]["facility"]
        geom = fetch_walk_route(lat, lon, float(fac["lat"]), float(fac["lon"]))
        if geom is None or len(geom) < 2:
            n_estimate_only += 1   # no routed geometry -> excluded from the overlay
            continue
        routes.append({
            "tract_id": p["GEOID"],
            "tract_name": p.get("BASENAME", p["GEOID"]),
            "fqhc_name": fac["name"],
            "walk_minutes": near["results"][0]["minutes"],
            "geometry": geom,      # full fidelity for proximity; thinned on write
        })
        if (i + 1) % 25 == 0:
            print(f"  {i + 1}/{len(feats)} tracts routed ...")
        time.sleep(POLITE_DELAY_S)

    if not routes:
        sys.exit("ERROR: no OSRM route geometries could be fetched (server unreachable?).")

    print(f"Measuring {len(points)} crash points against {len(routes)} corridors "
          f"(threshold {int(PROXIMITY_M)} m) ...")
    near_any = set()
    for r in routes:
        n_deaths, n_dark, crash_idx = 0, 0, []
        for j, pt in enumerate(points):
            if min_dist_to_route_m(pt["lat"], pt["lon"], r["geometry"]) <= PROXIMITY_M:
                n_deaths += pt["n_ped_deaths"]
                n_dark += pt["n_ped_deaths"] if pt["dark"] else 0
                crash_idx.append(j)
                near_any.add(j)
        r["n_deaths_near"] = n_deaths
        r["n_deaths_near_dark"] = n_dark
        r["crash_indices"] = crash_idx
        r["geometry"] = thin(r["geometry"])

    routes.sort(key=lambda r: r["n_deaths_near"], reverse=True)
    deaths_near_any = sum(points[j]["n_ped_deaths"] for j in near_any)
    total_deaths = sum(p["n_ped_deaths"] for p in points)

    out = {
        "county_fips": COUNTY_FIPS,
        "county": "Greenville County",
        "category": "fqhc",
        "source": ("FARS crash points (NHTSA) x modeled OSRM walking routes "
                   "from each tract's internal point to its nearest FQHC"),
        "proximity_m": PROXIMITY_M,
        "years": points_doc.get("years"),
        # The interpretation this file once supported is WITHDRAWN, and the
        # withdrawal has to travel WITH the data. Prose gets regenerated from
        # these numbers — the PDF briefs built their lead statistic straight out
        # of `deaths_near_any_corridor` — so a clean-looking statistic sitting in
        # JSON with encouraging framing is how a retracted claim comes back.
        # The old note ended "Evidence of overlap, not causation", which reads as
        # a caveat on a real finding rather than a retraction of it.
        "withdrawn_interpretation": {
            "claim": ("N of M pedestrian deaths occurred within "
                      f"{int(PROXIMITY_M)} m of a modeled walking route to care, "
                      "therefore routes to care are the dangerous ones"),
            "status": "WITHDRAWN — do not publish or quote",
            "why": ("A null model refutes it: re-routing every tract to a RANDOMLY "
                    "CHOSEN health center captures MORE deaths (~59%) than routing "
                    "to the real nearest one (38.5%). At matched route length an "
                    "arbitrary destination always overlaps more, so the statistic "
                    "measures how much arterial road a route covers, not risk. The "
                    "companion darkness claim is also withdrawn: 84.1% of all county "
                    "pedestrian deaths occur in darkness versus 85.7% near these "
                    "corridors, a 1.6-point difference that is not a signal."),
            "what_would_be_needed": ("road-network exposure as the denominator, not "
                                     "raw counts of points near a line"),
        },
        "model_notes": (
            "Routes are MODELED walking paths (one Census internal point per tract, "
            "nearest FQHC by walk), not observed foot traffic. A crash 'on' a corridor "
            "means within "
            f"{int(PROXIMITY_M)} m of the routed line. Counts are points near a line, "
            "never rates — per-corridor numbers are far too small for statistical "
            "claims. THE OVERLAP INTERPRETATION IS WITHDRAWN: see "
            "withdrawn_interpretation in this file. These counts are kept as "
            "descriptive geography only."
        ),
        "summary": {
            "n_corridors": len(routes),
            "n_corridors_unrouted": n_estimate_only,
            "n_crash_points": len(points),
            "total_deaths_located": total_deaths,
            "deaths_near_any_corridor": deaths_near_any,
            "pct_deaths_near_any_corridor": round(100 * deaths_near_any / total_deaths, 1)
                                            if total_deaths else None,
        },
        "corridors": routes,
        "points": points,
    }
    fname = f"crash_corridors_{COUNTY_FIPS}.json"
    write_json(PROCESSED_DIR / fname, out, label=f"{fname} (processed)")
    write_json(DASHBOARD_DATA_DIR / fname, out, label=f"{fname} (site)")

    s = out["summary"]
    print(f"Done: {s['deaths_near_any_corridor']} of {s['total_deaths_located']} located "
          f"pedestrian deaths ({s['pct_deaths_near_any_corridor']}%) lie within "
          f"{int(PROXIMITY_M)} m of a modeled walk-to-FQHC route.")
    for r in routes[:5]:
        if r["n_deaths_near"]:
            print(f"  tract {r['tract_name']} -> {r['fqhc_name']}: "
                  f"{r['n_deaths_near']} deaths near route ({r['n_deaths_near_dark']} in darkness)")


if __name__ == "__main__":
    main()
