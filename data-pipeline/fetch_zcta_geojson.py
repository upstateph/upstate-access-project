#!/usr/bin/env python3
"""Fetch ZIP Code Tabulation Area (ZCTA) boundaries for a county, for Phase 4.

ZCTAs approximate USPS ZIP codes and do NOT nest inside counties, so we query the
Census TIGERweb ZCTA layer over the county's bounding box, then keep only the ZCTAs
whose Census internal point falls **inside the county polygon** — i.e. ZIP areas
centered in the county. Writes dashboard/data/zcta_<county_fips>.geojson with GEOID
(the 5-digit ZIP) and INTPTLAT/INTPTLON.

Source (verified July 2026, no key): Census TIGERweb, 2020 ZCTA layer.

Usage:
    python fetch_zcta_geojson.py                 # Greenville County (45045)
"""
from __future__ import annotations

import json
import sys

import requests

from common import DASHBOARD_DATA_DIR, ensure_dirs, read_json

ZCTA_LAYER = ("https://tigerweb.geo.census.gov/arcgis/rest/services/"
              "TIGERweb/PUMA_TAD_TAZ_UGA_ZCTA/MapServer/1/query")


def _iter_coords(geom):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    for poly in polys:
        yield poly  # poly = [outer_ring, hole1, ...]


def _point_in_ring(lon, lat, ring) -> bool:
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if (y1 > lat) != (y2 > lat):
            xint = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if lon < xint:
                inside = not inside
    return inside


def point_in_geometry(lon, lat, geom) -> bool:
    """Point-in-polygon for GeoJSON Polygon/MultiPolygon (outer minus holes)."""
    for poly in _iter_coords(geom):
        if _point_in_ring(lon, lat, poly[0]) and not any(
                _point_in_ring(lon, lat, hole) for hole in poly[1:]):
            return True
    return False


def county_polygon(county_fips: str):
    gj = read_json(DASHBOARD_DATA_DIR / "sc_counties.geojson")
    feat = next((f for f in gj["features"] if str(f["id"]) == county_fips), None)
    if not feat:
        sys.exit(f"County {county_fips} not in sc_counties.geojson (run fetch_geojson.py).")
    return feat["geometry"]


def bbox(geom):
    xs, ys = [], []
    for poly in _iter_coords(geom):
        for ring in poly:
            for lon, lat in ring:
                xs.append(lon); ys.append(lat)
    return min(xs), min(ys), max(xs), max(ys)


def main() -> None:
    county_fips = sys.argv[1] if len(sys.argv) > 1 else "45045"
    ensure_dirs()
    geom = county_polygon(county_fips)
    xmin, ymin, xmax, ymax = bbox(geom)

    params = {
        "where": "1=1",
        "geometry": json.dumps({"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax,
                                "spatialReference": {"wkid": 4326}}),
        "geometryType": "esriGeometryEnvelope",
        "spatialRel": "esriSpatialRelIntersects",
        "inSR": "4326", "outSR": "4326",
        "outFields": "GEOID,BASENAME,INTPTLAT,INTPTLON",
        "returnGeometry": "true", "f": "geojson",
    }
    print(f"Fetching ZCTAs near county {county_fips} from TIGERweb ...")
    resp = requests.get(ZCTA_LAYER, params=params, timeout=90)
    resp.raise_for_status()
    feats = resp.json().get("features", [])

    kept = []
    for f in feats:
        p = f["properties"]
        try:
            lat, lon = float(p["INTPTLAT"]), float(p["INTPTLON"])
        except (TypeError, ValueError, KeyError):
            continue
        if point_in_geometry(lon, lat, geom):
            kept.append(f)

    dest = DASHBOARD_DATA_DIR / f"zcta_{county_fips}.geojson"
    dest.write_text(json.dumps({"type": "FeatureCollection", "features": kept}))
    print(f"  {len(feats)} ZCTAs intersected the bbox; kept {len(kept)} centered in the county")
    print(f"  wrote -> {dest.relative_to(DASHBOARD_DATA_DIR.parent.parent)}")


if __name__ == "__main__":
    main()
