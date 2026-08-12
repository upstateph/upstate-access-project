#!/usr/bin/env python3
"""Route-level delay attribution + frequency scenarios — the operational layer.

"40.7% of tracts are transit-reachable" is diagnostic: a planner cannot act on it.
This answers the operational question instead — *which route, what change, worth how
many minutes to how many places* — by (1) attributing each tract's trip time to the
routes it actually rides, and (2) re-running the router against a modified timetable
to measure what a frequency improvement would buy.

Every itinerary here is the median over a sampled departure window (engine default),
so nothing depends on where a single arbitrary instant lands in a headway.

    python build_route_diagnostics.py                 # top 3 routes, 2x frequency
    python build_route_diagnostics.py --routes 5 --factor 2
    python build_route_diagnostics.py --limit 15      # quick smoke run
"""
from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR))

from common import DASHBOARD_DATA_DIR, PROCESSED_DIR, ensure_dirs, read_json, write_json  # noqa: E402
from engine.facilities import load_facilities  # noqa: E402
from engine.scenario import densified_feed, observed_headways  # noqa: E402
from engine.transit import (  # noqa: E402
    DEFAULT_DEPART, MAX_TOTAL_MIN, WINDOW_MINUTES, WINDOW_STEP_MINUTES,
    _feed, _fmt_time, parse_gtfs_time, transit_to_facilities,
)

COUNTY_FIPS = "45045"
CATEGORY = "fqhc"
GOOD_TRIP_MIN = 45.0          # "a trip someone would actually make" threshold
MIDDAY = (11 * 3600, 14 * 3600)
# Unreachable departures are CENSORED at the router's cap rather than dropped.
# Dropping them breaks the scenario comparison: adding service makes previously
# unreachable (and therefore slower) departures viable, which pulls a
# reachable-only median UPWARD and makes a genuine improvement look like a
# regression. Censoring keeps the comparison monotone — more service can only
# lower or hold each departure's time — which is the property a counterfactual needs.
CENSOR_MIN = MAX_TOTAL_MIN


def med(xs):
    return round(statistics.median(xs), 1) if xs else None


def departures():
    t0 = parse_gtfs_time(DEFAULT_DEPART)
    return [_fmt_time(t0 + m * 60) for m in range(0, WINDOW_MINUTES, WINDOW_STEP_MINUTES)]


def run_all(points, facilities, feed=None):
    """Per-tract departure profile.

    {tract_id: {"times": [censored minutes per departure], "n_reachable": int,
                "best": representative itinerary result or None}}
    """
    deps = departures()
    out = {}
    for i, (tid, lat, lon) in enumerate(points):
        times, good = [], []
        for dep in deps:
            r = transit_to_facilities(lat, lon, facilities, depart=dep, feed=feed)
            if r.get("reachable"):
                times.append(r["itinerary"]["total_minutes"])
                good.append(r)
            else:
                times.append(CENSOR_MIN)
        good.sort(key=lambda r: r["itinerary"]["total_minutes"])
        out[tid] = {
            "times": times,
            "n_reachable": len(good),
            "n_departures": len(deps),
            # Representative (median among reachable) — used only for route attribution.
            "best": good[len(good) // 2] if good else None,
        }
        if (i + 1) % 25 == 0:
            print(f"    {i + 1}/{len(points)} tracts ...", flush=True)
    return out


def dependable(prof):
    """Engine convention: a trip from a majority of sampled departures."""
    return prof["n_reachable"] * 2 >= prof["n_departures"]


def summarize(results):
    meds = {t: statistics.median(p["times"]) for t, p in results.items()}
    reach = [t for t, p in results.items() if dependable(p)]
    return {
        "n_reachable": len(reach),
        "n_total": len(results),
        "pct_reachable": round(100 * len(reach) / len(results), 1) if results else None,
        "median_total_min": med([meds[t] for t in reach]),
        "n_under_threshold": sum(1 for t in reach if meds[t] <= GOOD_TRIP_MIN),
        "note": f"Unreachable departures censored at {int(CENSOR_MIN)} min.",
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Route-level delay attribution + scenarios.")
    ap.add_argument("--routes", type=int, default=3, help="how many routes to test (default 3)")
    ap.add_argument("--factor", type=int, default=2, help="frequency multiplier (default 2)")
    ap.add_argument("--limit", type=int, help="only model the first N tracts (smoke test)")
    args = ap.parse_args()

    ensure_dirs()
    geo = DASHBOARD_DATA_DIR / f"tracts_{COUNTY_FIPS}.geojson"
    if not geo.exists():
        sys.exit(f"ERROR: {geo.name} missing — run fetch_tract_geojson.py first.")
    feats = read_json(geo)["features"]
    if args.limit:
        feats = feats[:args.limit]
    points = [(f["properties"]["GEOID"],
               float(f["properties"]["INTPTLAT"]),
               float(f["properties"]["INTPTLON"])) for f in feats]
    facilities = load_facilities(CATEGORY)
    feed = _feed()

    print(f"Baseline: {len(points)} tracts -> nearest of {len(facilities)} FQHCs ...")
    base = run_all(points, facilities)
    base_summary = summarize(base)

    # ── attribute each tract's trip to the routes it rides ───────────────────
    routes: dict[str, dict] = {}
    for tid, prof in base.items():
        r = prof["best"]
        if not r or not dependable(prof):
            continue
        it = r["itinerary"]
        legs = it.get("legs") or []
        if not legs:
            continue
        boarding = legs[0]["route_id"]
        for pos, leg in enumerate(legs):
            rec = routes.setdefault(leg["route_id"], {
                "route_id": leg["route_id"], "tracts_using": [], "tracts_boarding": [],
                "totals": [], "waits": [], "in_vehicle": [],
            })
            if tid not in rec["tracts_using"]:
                rec["tracts_using"].append(tid)
                rec["totals"].append(it["total_minutes"])
                rec["waits"].append(it["wait_min"])
                rec["in_vehicle"].append(it["in_vehicle_min"])
            if pos == 0 and tid not in rec["tracts_boarding"]:
                rec["tracts_boarding"].append(tid)
        del boarding

    for rid, rec in routes.items():
        gaps = observed_headways(feed, rid, *MIDDAY)
        rec["median_headway_min"] = round(statistics.median(gaps) / 60, 0) if gaps else None
        rec["n_tracts_using"] = len(rec["tracts_using"])
        rec["n_tracts_boarding"] = len(rec["tracts_boarding"])
        rec["median_total_min"] = med(rec["totals"])
        rec["median_wait_min"] = med(rec["waits"])
        rec["median_in_vehicle_min"] = med(rec["in_vehicle"])
        # What a frequency fix could plausibly touch: riders who BOARD this route,
        # times the wait they currently absorb.
        rec["wait_burden_min"] = round((rec["median_wait_min"] or 0) * rec["n_tracts_boarding"], 1)
        for k in ("totals", "waits", "in_vehicle"):
            rec.pop(k)

    ranked = sorted(routes.values(), key=lambda r: -r["wait_burden_min"])

    # ── scenarios: actually re-run the router on a denser timetable ──────────
    scenarios = []
    for rec in ranked[:args.routes]:
        rid = rec["route_id"]
        print(f"Scenario: route {rid} at {args.factor}x frequency ...", flush=True)
        scen_feed = densified_feed(rid, args.factor)
        scen = run_all(points, facilities, feed=scen_feed)
        s = summarize(scen)
        base_med = {t: statistics.median(p["times"]) for t, p in base.items()}
        scen_med = {t: statistics.median(p["times"]) for t, p in scen.items()}
        improved = [base_med[t] - scen_med[t] for t in base_med]
        scenarios.append({
            "route_id": rid,
            "factor": args.factor,
            "trips_added": scen_feed.scenario["trips_added"],
            "headway_before_min": rec["median_headway_min"],
            "headway_after_min": round(statistics.median(
                observed_headways(scen_feed, rid, *MIDDAY)) / 60, 0) if observed_headways(scen_feed, rid, *MIDDAY) else None,
            "before": base_summary,
            "after": s,
            "delta_median_total_min": (round(s["median_total_min"] - base_summary["median_total_min"], 1)
                                       if s["median_total_min"] is not None and base_summary["median_total_min"] is not None else None),
            "delta_tracts_reachable": s["n_reachable"] - base_summary["n_reachable"],
            "delta_tracts_under_threshold": s["n_under_threshold"] - base_summary["n_under_threshold"],
            "median_minutes_saved_per_improved_tract": med([d for d in improved if d > 0]),
            "n_tracts_improved": sum(1 for d in improved if d > 0),
        })
        print(f"    {rid}: median {base_summary['median_total_min']} -> {s['median_total_min']} min, "
              f"{s['n_under_threshold'] - base_summary['n_under_threshold']:+d} tracts under "
              f"{int(GOOD_TRIP_MIN)} min, {s['n_reachable'] - base_summary['n_reachable']:+d} newly reachable",
              flush=True)

    out = {
        "county_fips": COUNTY_FIPS, "county": "Greenville County", "category": CATEGORY,
        "source": "MODELED — engine itineraries per tract, attributed to the routes ridden",
        "threshold_min": GOOD_TRIP_MIN,
        "model_notes": (
            "Each tract's trip is the MEDIAN over a sampled departure window, so no "
            "figure depends on a single arbitrary departure instant. Scenarios re-run "
            "the router against a timetable with the named route's trips interleaved "
            "to raise frequency — they assume the same stop pattern and running times "
            "and ignore vehicle/operator cost, which is the first question a planner "
            "will ask. One representative point per tract; modeled, not observed."
        ),
        "baseline": base_summary,
        "routes": ranked,
        "scenarios": scenarios,
    }
    fname = f"route_diagnostics_{COUNTY_FIPS}.json"
    write_json(PROCESSED_DIR / fname, out, label=f"{fname} (processed)")
    write_json(DASHBOARD_DATA_DIR / fname, out, label=f"{fname} (site)")


if __name__ == "__main__":
    main()
