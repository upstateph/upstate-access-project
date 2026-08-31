#!/usr/bin/env python3
"""Score a location for car-free access to the four things a housing placement needs.

The access tool normally answers "how far is this person from care". This asks the
same engine a different question with a different origin: **can someone placed at
this address reach the things that keep a placement from failing, without a car?**

The four destinations, and why these four:
  fqhc       primary care, the thing the project already models
  dss        SNAP / Medicaid / TANF enrollment. ONE office serves the whole county.
  workforce  SC Works / DEW, three sites
  grocery    SNAP-accepting supermarket / super store / grocery store, 106 sites
             (not the 443 SNAP retailers; a gas station is not a grocery shop)

CAR-FREE, NOT TRANSIT-ONLY. A unit a ten-minute walk from a supermarket does not
need the bus, and scoring it as unreachable because no route serves it would be
plainly wrong. A destination counts as reachable if it is within WALK_CAP_MIN on
foot OR reachable by Greenlink on the existing <=1-transfer, <=30-min-wait,
median-over-the-hour model. Both components are reported separately so the
transit-only picture is still visible.

The walk cap is 20 minutes, about a mile at the model's 3 mph. It is a judgment
call, stated here rather than buried: far enough to be a normal errand, close
enough to do while carrying groceries. `--walk-cap` changes it, and the output
records which value produced the numbers.

WHAT THIS DELIBERATELY DOES NOT DO. It returns four travel times, not a score and
not a pass/fail recommendation on a unit. A composite number would hide which of
the four failed, which is the only actionable part, and a single verdict attached
to a housing unit is a placement decision that belongs to a human who knows the
household.

Usage:
    python build_housing_access.py                    # all 123 tracts
    python build_housing_access.py --addresses FILE   # plus a list of addresses
    python build_housing_access.py --walk-cap 15
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from statistics import median

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR))
sys.path.insert(0, str(REPO_DIR / "data-pipeline"))

from common import DASHBOARD_DATA_DIR, PROCESSED_DIR, ensure_dirs, read_json, write_json  # noqa: E402
from engine.facilities import load_facilities  # noqa: E402
from engine.geocode import geocode  # noqa: E402
from engine.housing import NEED_LABELS, NEEDS, WALK_CAP_MIN, score_point  # noqa: E402

COUNTY_FIPS = "45045"
# NEEDS, NEED_LABELS and the walk cap live in engine/housing.py so the batch run
# here and the live /api/housing endpoint cannot drift apart.
DEFAULT_WALK_CAP_MIN = WALK_CAP_MIN


def summarize(units: list[dict], pop_key: str = "population") -> dict:
    n = len(units)
    pop_total = sum(u.get(pop_key) or 0 for u in units)

    def pct(sel):
        return round(100.0 * sum(1 for u in units if sel(u)) / n, 1) if n else 0.0

    def pop_pct(sel):
        if not pop_total:
            return None
        got = sum(u.get(pop_key) or 0 for u in units if sel(u))
        return round(100.0 * got / pop_total, 1)

    s = {
        "n_units": n,
        "population_total": pop_total or None,
        "pct_units_all_four": pct(lambda u: u["access"]["all_four"]),
        "pct_population_all_four": pop_pct(lambda u: u["access"]["all_four"]),
        "pct_units_all_four_transit_only": pct(lambda u: u["access"]["all_four_transit_only"]),
        "pct_units_none_of_four": pct(lambda u: u["access"]["n_reachable"] == 0),
        "per_need": {},
        "n_reachable_histogram": {str(k): sum(1 for u in units
                                              if u["access"]["n_reachable"] == k)
                                  for k in range(len(NEEDS) + 1)},
    }
    for need in NEEDS:
        mins = [u["access"]["needs"][need]["best_min"] for u in units
                if u["access"]["needs"][need]["best_min"] is not None]
        s["per_need"][need] = {
            "label": NEED_LABELS[need],
            "pct_units_reachable": pct(lambda u, nd=need: u["access"]["needs"][nd]["reachable"]),
            "pct_population_reachable": pop_pct(lambda u, nd=need: u["access"]["needs"][nd]["reachable"]),
            "pct_units_transit_reachable": pct(lambda u, nd=need: u["access"]["needs"][nd]["transit_reachable"]),
            "pct_units_walkable": pct(lambda u, nd=need: u["access"]["needs"][nd]["walk_within_cap"]),
            "median_min_when_reachable": round(median(mins), 1) if mins else None,
        }
    return s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--walk-cap", type=float, default=DEFAULT_WALK_CAP_MIN,
                    help="minutes on foot that count as reachable without a bus")
    ap.add_argument("--addresses", type=Path, default=None,
                    help="text file, one address per line, scored alongside the tracts")
    args = ap.parse_args()
    ensure_dirs()

    facs = {}
    for need in NEEDS:
        facs[need] = load_facilities(need)
        print(f"  {need:10s} {len(facs[need]):4d} destinations")

    geo_path = DASHBOARD_DATA_DIR / f"tracts_{COUNTY_FIPS}.geojson"
    feats = read_json(geo_path)["features"]
    acs_path = PROCESSED_DIR / f"census_acs_tracts_{COUNTY_FIPS}.json"
    acs = {}
    if acs_path.exists():
        acs = {a["tract_fips"]: a for a in read_json(acs_path)["tracts"]}

    print(f"\nScoring {len(feats)} tracts (walk cap {args.walk_cap:g} min) ...")
    units = []
    for i, f in enumerate(feats, 1):
        p = f["properties"]
        gid = p["GEOID"]
        lat, lon = float(p["INTPTLAT"]), float(p["INTPTLON"])
        rec = {"id": gid, "name": p.get("BASENAME", gid),
               "access": score_point(lat, lon, walk_cap=args.walk_cap,
                                     prefer_osrm=False, facilities=facs)}
        a = acs.get(gid) or {}
        rec["population"] = a.get("total_population")
        rec["median_household_income"] = a.get("median_household_income")
        rec["pct_no_vehicle"] = a.get("pct_no_vehicle")
        units.append(rec)
        if i % 25 == 0:
            print(f"  ... {i}/{len(feats)}")

    summary = summarize(units)
    out = {
        "county_fips": COUNTY_FIPS, "county": "Greenville County",
        "geography": "tract",
        "needs": NEEDS, "need_labels": NEED_LABELS,
        "walk_cap_min": args.walk_cap,
        "source": "MODELED, engine access from each tract's Census internal point",
        "model_notes": (
            "Car-free reachability: a destination counts if it is within the walk cap "
            "on foot (3 mph straight-line with a 1.3x detour factor) OR reachable by "
            "Greenlink on the standard model (<=1 transfer, <=30 min wait, median over "
            "departures sampled every 10 minutes across the weekday-midday hour, and a "
            "trip must exist from most sampled departures). One representative point "
            "per tract, so this is a modeled surface and not an observed trip. "
            "Grocery counts SNAP supermarket / super store / grocery store only."),
        "summary": summary,
        "units": units,
    }
    write_json(PROCESSED_DIR / f"housing_access_tract_{COUNTY_FIPS}.json", out,
               label=f"housing access ({len(units)} tracts)")

    if args.addresses and args.addresses.exists():
        lines = [l.strip() for l in args.addresses.read_text().splitlines() if l.strip()]
        print(f"\nScoring {len(lines)} addresses ...")
        rows = []
        for addr in lines:
            g = geocode(addr)
            if g is None:
                print(f"  SKIP  address not found:            {addr}")
                rows.append({"address": addr, "ok": False, "reason": "not_found"})
                continue
            if g.county_fips != COUNTY_FIPS:
                # Greer and Fountain Inn straddle county lines. This is the
                # coverage guard doing its job, not a failure to look one up.
                print(f"  SKIP  outside county (fips {g.county_fips}): {addr}")
                rows.append({"address": addr, "ok": False, "reason": "outside_county",
                             "resolved_county_fips": g.county_fips,
                             "matched": g.matched_address})
                continue
            rows.append({"address": addr, "ok": True,
                         "matched": g.matched_address,
                         "access": score_point(g.lat, g.lon, walk_cap=args.walk_cap,
                                              prefer_osrm=False, facilities=facs)})
            a = rows[-1]["access"]
            got = "".join("Y" if a["needs"][n]["reachable"] else "." for n in NEEDS)
            print(f"  {got}  {addr}")
        write_json(PROCESSED_DIR / "housing_access_addresses.json",
                   {"walk_cap_min": args.walk_cap, "needs": NEEDS,
                    "need_labels": NEED_LABELS, "addresses": rows},
                   label=f"housing access ({len(rows)} addresses)")

    print("\n=== Pass rate, all four needs, car-free ===")
    print(f"  tracts:     {summary['pct_units_all_four']}%")
    pp = summary["pct_population_all_four"]
    print(f"  population: {pp}%" if pp is not None else
          "  population: not computed (no ACS join)")
    print(f"  transit only, no walking allowed: {summary['pct_units_all_four_transit_only']}% of tracts")
    print(f"  reaches none of the four:         {summary['pct_units_none_of_four']}% of tracts")
    print("\n  per need (car-free / transit-only / walkable):")
    for need in NEEDS:
        d = summary["per_need"][need]
        print(f"    {d['label']:32s} {d['pct_units_reachable']:5.1f}% "
              f"/ {d['pct_units_transit_reachable']:5.1f}% / {d['pct_units_walkable']:5.1f}%")


if __name__ == "__main__":
    main()
