#!/usr/bin/env python3
"""Fetch incident-level FARS pedestrian fatality POINTS for one county.

Where fetch_fars.py builds county/year counts, this script keeps the crash
coordinates: it joins fatal-pedestrian person records (PER_TYP=5, INJ_SEV=4) to
accident.csv by ST_CASE to get LATITUDE/LONGITUD, light condition, and hour.
Feeds the crash-corridor overlay (build_crash_corridors.py).

These are official public records of fatal crashes — no PII beyond what NHTSA
already publishes. Presented as points, never rates: per-corridor counts are far
too small for statistical claims.

Usage:
    python fetch_fars_points.py               # Greenville County, default years
    python fetch_fars_points.py 2018 2024     # custom inclusive year range
"""
from __future__ import annotations

import io
import sys
import zipfile

from common import PROCESSED_DIR, DASHBOARD_DATA_DIR, ensure_dirs, write_json
from fetch_fars import (
    DEFAULT_END,
    DEFAULT_START,
    FATAL_INJ_SEV,
    PED_PER_TYP,
    SC_STATE_CODE,
    _find_member,
    _read_csv,
    download_year,
)

COUNTY_FIPS = "45045"
COUNTY_CODE = 45  # FARS COUNTY is the unpadded 3-digit county FIPS (Greenville = 045)

# FARS LGT_COND codes -> label. "Dark" groupings matter for countermeasure framing.
LIGHT_LABELS = {
    1: "Daylight", 2: "Dark — not lighted", 3: "Dark — lighted",
    4: "Dawn", 5: "Dusk", 6: "Dark — unknown lighting",
}
DARK_CODES = {2, 3, 6}

# Plausible bounds for Greenville County; FARS uses sentinel coords for unknown
# (e.g. 77.7777/99.9999 lat, 777.7777/999.9999 lon), which these bounds exclude.
LAT_RANGE = (34.4, 35.3)
LON_RANGE = (-82.9, -81.9)


def points_for_year(year: int, zip_bytes: bytes) -> tuple[list[dict], int]:
    """Return ([point records], n_cases_missing_coords) for the county/year."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        person_name = _find_member(zf, "person")
        accident_name = _find_member(zf, "accident")
        if not person_name or not accident_name:
            print(f"  [{year}] missing person/accident CSV — skipping")
            return [], 0
        person = _read_csv(zf, person_name)
        accident = _read_csv(zf, accident_name)

    ped = person[
        (person["STATE"] == SC_STATE_CODE)
        & (person["COUNTY"] == COUNTY_CODE)
        & (person["PER_TYP"] == PED_PER_TYP)
        & (person["INJ_SEV"] == FATAL_INJ_SEV)
    ]
    if ped.empty:
        return [], 0

    # Pedestrian deaths per crash (a single crash can kill more than one).
    deaths_by_case = ped.groupby("ST_CASE").size().to_dict()

    acc = accident[accident["ST_CASE"].isin(deaths_by_case)]
    points, missing = [], 0
    for _, row in acc.iterrows():
        try:
            lat, lon = float(row["LATITUDE"]), float(row["LONGITUD"])
        except (TypeError, ValueError, KeyError):
            missing += 1
            continue
        if not (LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LON_RANGE[0] <= lon <= LON_RANGE[1]):
            missing += 1  # sentinel/unknown coordinates
            continue
        try:
            light_code = int(row.get("LGT_COND"))
        except (TypeError, ValueError):
            light_code = None
        try:
            hour = int(row.get("HOUR"))
            if hour > 23:
                hour = None  # 99 = unknown
        except (TypeError, ValueError):
            hour = None
        points.append({
            "year": year,
            "lat": round(lat, 5),
            "lon": round(lon, 5),
            "n_ped_deaths": int(deaths_by_case[row["ST_CASE"]]),
            "light": LIGHT_LABELS.get(light_code, "Other / unknown"),
            "dark": light_code in DARK_CODES,
            "hour": hour,
        })
    return points, missing


def main(argv: list[str]) -> None:
    if len(argv) == 3:
        start, end = int(argv[1]), int(argv[2])
    else:
        start, end = DEFAULT_START, DEFAULT_END

    ensure_dirs()
    print(f"FARS pedestrian fatality points for county {COUNTY_FIPS}, {start}-{end}:")
    all_points, total_missing, years = [], 0, []
    for year in range(start, end + 1):
        zip_bytes = download_year(year)
        if zip_bytes is None:
            continue
        pts, missing = points_for_year(year, zip_bytes)
        years.append(year)
        total_missing += missing
        all_points.extend(pts)
        print(f"  [{year}] {sum(p['n_ped_deaths'] for p in pts)} deaths at "
              f"{len(pts)} located crashes" + (f" (+{missing} without usable coords)" if missing else ""))

    if not years:
        sys.exit("ERROR: no FARS years could be downloaded. Check network/URLs.")

    n_deaths = sum(p["n_ped_deaths"] for p in all_points)
    out = {
        "source": "NHTSA FARS (accident + person files, joined by ST_CASE)",
        "county_fips": COUNTY_FIPS,
        "county": "Greenville County",
        "metric": "pedestrian_fatality_crash_points",
        "years": years,
        "n_crashes_located": len(all_points),
        "n_deaths_located": n_deaths,
        "n_crashes_missing_coords": total_missing,
        "note": (
            "One point per fatal crash involving >=1 pedestrian death; n_ped_deaths "
            "carries the per-crash toll. Crashes with sentinel/unknown coordinates are "
            "counted in n_crashes_missing_coords and excluded from the map. Points, "
            "not rates — counts are too small for per-corridor statistical claims."
        ),
        "points": sorted(all_points, key=lambda p: (p["year"], p["lat"])),
    }
    fname = f"fars_ped_points_{COUNTY_FIPS}.json"
    write_json(PROCESSED_DIR / fname, out, label=f"{fname} ({len(all_points)} crash points)")
    write_json(DASHBOARD_DATA_DIR / fname, out, label=f"{fname} (site)")
    print(f"Done: {n_deaths} pedestrian deaths at {len(all_points)} located crashes, "
          f"{years[0]}-{years[-1]} ({total_missing} crashes lacked usable coordinates).")


if __name__ == "__main__":
    main(sys.argv)
