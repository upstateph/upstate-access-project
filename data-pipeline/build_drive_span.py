#!/usr/bin/env python3
"""Drive time by time of day, the car counterpart to build_service_span.py.

    python build_drive_span.py

Free-flow drive minutes from each tract's Census internal point to its nearest
FQHC, multiplied by that tract's typical-traffic congestion factor for each of
the four windows service_span already uses. Same windows, same geography, same
destination choice, so the two artifacts can sit in one UI without the car and
the bus disagreeing about what "5pm" means.

WHAT IS OURS AND WHAT IS BORROWED, because the distinction is the point. The
free-flow minutes are computed here by the project's own routing. The only
thing that comes from outside is the RATIO between typical and free-flow
conditions, sampled per tract by fetch_drive_congestion.py. Publishing a ratio
rather than a provider's absolute ETA also keeps the number ours to explain.

⚠️ NO CONGESTION FILE MEANS NO WINDOWS, NOT FOUR IDENTICAL ONES. If
fetch_drive_congestion.py has not run (it needs a key and writes nothing
without one), this still builds, but every window is null and
congestion_available is false. Emitting free-flow four times over would render
as four equal numbers and read as "traffic makes no difference here", which is
a claim nobody measured. An empty column that says why is honest; a filled one
that quietly means nothing is not.
"""
from __future__ import annotations

import sys
from pathlib import Path
from statistics import median

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR))

from common import DASHBOARD_DATA_DIR, PROCESSED_DIR, ensure_dirs, read_json, write_json  # noqa: E402
from engine.facilities import load_facilities  # noqa: E402
from engine.routing import nearest  # noqa: E402

COUNTY_FIPS = "45045"
CATEGORY = "fqhc"
CONGESTION = f"drive_congestion_{COUNTY_FIPS}.json"
OUT_NAME = f"drive_span_tract_{COUNTY_FIPS}.json"
WINDOWS = [
    {"key": "wk_08", "label": "Weekday 8:00 am"},
    {"key": "wk_12", "label": "Weekday midday"},
    {"key": "wk_17", "label": "Weekday 5:00 pm"},
    {"key": "sat_12", "label": "Saturday midday"},
]
BASELINE = "wk_12"


def main() -> None:
    ensure_dirs()
    geojson = DASHBOARD_DATA_DIR / f"tracts_{COUNTY_FIPS}.geojson"
    if not geojson.exists():
        sys.exit(f"ERROR: {geojson} missing — run fetch_tract_geojson.py first.")
    feats = read_json(geojson)["features"]
    facilities = load_facilities(CATEGORY)

    cpath = PROCESSED_DIR / CONGESTION
    cong, is_mock, provider, sampled_on = {}, False, None, None
    if cpath.exists():
        c = read_json(cpath)
        is_mock = bool(c.get("is_mock"))
        provider, sampled_on = c.get("provider"), c.get("sampled_on")
        cong = {u["id"]: u for u in c.get("units", [])}
    available = bool(cong) and not is_mock
    if is_mock:
        # A mock file is for exercising the pipeline, never for producing a
        # published surface. Refusing here as well as in the fetcher means one
        # stray artifact on somebody's laptop cannot become a live claim.
        print(f"  {CONGESTION} is a MOCK sample. Building free-flow only; "
              f"windows will be null.")

    units = []
    for f in feats:
        p = f["properties"]
        lat, lon = float(p["INTPTLAT"]), float(p["INTPTLON"])
        ranked = nearest(lat, lon, facilities, "drive", k=1, prefer_osrm=False)
        if not ranked["results"]:
            continue
        r = ranked["results"][0]
        free = r["minutes"]
        rec = {"id": p["GEOID"], "name": p.get("BASENAME", p["GEOID"]),
               "free_flow_min": round(free, 1),
               "nearest_fqhc": r["facility"].get("name")}
        cu = cong.get(rec["id"], {}) if available else {}
        for w in WINDOWS:
            fac = cu.get(w["key"])
            rec[w["key"]] = round(free * fac, 1) if (available and fac) else None
        units.append(rec)

    summary = {}
    for w in WINDOWS:
        vals = [u[w["key"]] for u in units if u[w["key"]] is not None]
        summary[w["key"]] = {
            "label": w["label"],
            "n_modeled": len(vals),
            "drive_min_median": round(median(vals), 1) if vals else None,
        }
    ff = [u["free_flow_min"] for u in units if u["free_flow_min"] is not None]

    out = {
        "county_fips": COUNTY_FIPS,
        "county": "Greenville County",
        "category": CATEGORY,
        "geography": "tract",
        "baseline_window": BASELINE,
        "congestion_available": available,
        "congestion_provider": provider if available else None,
        "congestion_sampled_on": sampled_on if available else None,
        "source": "MODELED — free-flow drive time x typical-traffic congestion factor",
        "model_notes": (
            "Free-flow minutes are computed by this project's own routing from each "
            "tract's Census internal point to its nearest FQHC. The congestion factor "
            "is typical-traffic divided by free-flow for that same pair, sampled once "
            "per tract centroid by fetch_drive_congestion.py. No address searched on "
            "the site is ever sent to a routing provider. TYPICAL conditions, not live "
            "traffic, so the number is stable enough to compare against annual ACS data."
            + ("" if available else
               " NO CONGESTION SAMPLE IS PRESENT, so every window is null and only "
               "free_flow_min is meaningful. Do not render nulls as 'no delay'.")
        ),
        "free_flow_min_median": round(median(ff), 1) if ff else None,
        "windows": [{**w} for w in WINDOWS],
        "summary": summary,
        "units": units,
    }
    write_json(PROCESSED_DIR / OUT_NAME, out, label=f"{OUT_NAME} (processed)")
    write_json(DASHBOARD_DATA_DIR / OUT_NAME, out, label=f"{OUT_NAME} (site)")
    print(f"  free-flow median {out['free_flow_min_median']} min over {len(units)} tracts")
    if available:
        for w in WINDOWS:
            s = summary[w["key"]]
            print(f"  {s['label']:>18}: median {s['drive_min_median']} min "
                  f"over {s['n_modeled']} tracts")
    else:
        print("  congestion_available=false: windows are null, free-flow only.")
        print("  Set DRIVE_TRAFFIC_KEY and run fetch_drive_congestion.py to populate.")


if __name__ == "__main__":
    main()
