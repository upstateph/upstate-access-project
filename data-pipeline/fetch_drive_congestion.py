#!/usr/bin/env python3
"""Sample typical drive-time congestion once per tract centroid, per window.

    python fetch_drive_congestion.py            # needs DRIVE_TRAFFIC_KEY
    python fetch_drive_congestion.py --provider mock   # offline, for tests only

WHY THIS EXISTS. Drive time in this project has no time of day. Transit does:
build_service_span.py models weekday 8am, midday, 5pm and Saturday midday, and
the spread is large. The car number is identical at 8am and 5pm, which is the
one thing every driver in Greenville County knows is false.

WHY TRACT CENTROIDS AND NOT THE USER'S ADDRESS. This is the whole design, not
an optimisation. A traffic-aware ETA for a real lookup would mean sending that
person's home address to a commercial routing API on every search, which is
exactly what docs/privacy-design.md exists to prevent: no accounts, no logging
of searched addresses, addresses only in POST bodies. Sampling 123 Census tract
internal points instead means the only coordinates that ever leave this project
are published Census geography. The factor is precomputed on that grid, the
site multiplies a locally computed free-flow time by it, and no user address
touches a third party at any point. A tract centroid is not a person.

WHAT A FACTOR IS. congested / free-flow for the same origin-destination pair,
at a representative departure time. 1.00 means the trip is unaffected; 1.30
means it takes 30% longer than it would on empty roads. Applying a ratio rather
than publishing the provider's absolute minutes also keeps this honest about
what is ours: the free-flow time is computed here, and only the *shape* of the
congestion comes from outside.

TYPICAL, NOT LIVE. The provider is asked for historical/typical traffic at that
time of day, not for conditions right now. A number that moves every five
minutes cannot be benchmarked against annual ACS income data, gives two people
different answers to the same question, and cannot be cited in a letter. The
question this project answers is whether a neighbourhood is structurally far
from care, and "structurally" is the operative word.

⚠️ NO KEY MEANS NO FILE. If DRIVE_TRAFFIC_KEY is unset this writes NOTHING and
exits 0. It does not fall back to an assumed multiplier, and nothing downstream
invents one either. A made-up congestion factor on a public health tool is
worse than admitting the car number is free-flow: the first is wrong and
confident, the second is merely incomplete and says so.

⚠️ PROVIDER TERMS ARE YOUR PROBLEM BEFORE YOU SET A KEY. Routing providers
differ on whether you may store derived values and republish them. Google Maps
Platform terms are the restrictive end and would likely forbid this use;
TomTom and Mapbox are more permissive but still have terms. Read them for the
provider you choose. This script does not and cannot check that for you.

⚠️ THE TOMTOM ADAPTER IS UNVERIFIED AGAINST THE LIVE API. It was written from
the documented response shape and has only ever run against --provider mock,
because this checkout has no key. It parses defensively and fails loudly with
the keys it actually received rather than guessing. Treat the first real run as
the verification, and delete this paragraph once it has passed one.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR))

from common import DASHBOARD_DATA_DIR, PROCESSED_DIR, ensure_dirs, read_json, write_json  # noqa: E402
from engine.facilities import load_facilities  # noqa: E402
from engine.routing import nearest  # noqa: E402

COUNTY_FIPS = "45045"
CATEGORY = "fqhc"
OUT_NAME = f"drive_congestion_{COUNTY_FIPS}.json"

# The same four windows build_service_span.py uses, so the two artifacts can sit
# side by side in one UI without explaining why the car and the bus disagree
# about what "5pm" means. Keep them in step.
WINDOWS = [
    {"key": "wk_08", "label": "Weekday 8:00 am", "day": "weekday", "depart": "08:00:00"},
    {"key": "wk_12", "label": "Weekday midday", "day": "weekday", "depart": "12:00:00"},
    {"key": "wk_17", "label": "Weekday 5:00 pm", "day": "weekday", "depart": "17:00:00"},
    {"key": "sat_12", "label": "Saturday midday", "day": "saturday", "depart": "12:00:00"},
]
BASELINE = "wk_12"

# A factor below 1 means the "congested" trip was faster than free-flow, which is
# not a thing traffic does. It means the provider disagreed with itself, and the
# honest response is to drop the sample rather than publish a speed-up.
MIN_PLAUSIBLE = 1.0
# Above this, assume something is wrong with the pair rather than that the drive
# genuinely takes four times as long. Recorded, not silently clamped.
MAX_PLAUSIBLE = 4.0

POLITE_DELAY_S = 0.25


def next_occurrence(day: str, hhmmss: str) -> datetime:
    """The next future datetime matching this window, which is what providers want.

    Traffic APIs take an absolute departure timestamp and reject times in the
    past. "Next Tuesday 8am" and "next Saturday noon" are the representative
    weekday and weekend instants; the provider resolves them against its
    historical profile for that time of day, so which future week it lands in
    does not matter as long as it is the right day type.
    """
    h, m, s = (int(x) for x in hhmmss.split(":"))
    now = datetime.now()
    d = now.replace(hour=h, minute=m, second=s, microsecond=0)
    # Tuesday for weekdays: Monday and Friday both have atypical traffic.
    want = 1 if day == "weekday" else (5 if day == "saturday" else 6)
    ahead = (want - d.weekday()) % 7
    if ahead == 0 and d <= now:
        ahead = 7
    return d + timedelta(days=ahead)


def tomtom(o_lat, o_lon, d_lat, d_lon, depart: datetime, key: str) -> tuple[float, float]:
    """(typical_seconds, free_flow_seconds) for one pair at one departure time.

    computeTravelTimeFor=all makes a single call return both numbers, which
    matters: computing free-flow ourselves from a different engine would make
    the ratio a comparison between two providers rather than a measurement of
    congestion.
    """
    url = ("https://api.tomtom.com/routing/1/calculateRoute/"
           f"{o_lat},{o_lon}:{d_lat},{d_lon}/json?" + urllib.parse.urlencode({
               "key": key,
               "routeType": "fastest",
               "traffic": "true",
               "travelMode": "car",
               "computeTravelTimeFor": "all",
               "departAt": depart.strftime("%Y-%m-%dT%H:%M:%S"),
           }))
    with urllib.request.urlopen(url, timeout=30) as r:
        body = json.loads(r.read().decode())
    try:
        s = body["routes"][0]["summary"]
    except (KeyError, IndexError):
        raise SystemExit(f"TomTom response had no routes[0].summary. Top-level "
                         f"keys were: {sorted(body)}. Nothing written.")
    typical = s.get("historicTrafficTravelTimeInSeconds")
    free = s.get("noTrafficTravelTimeInSeconds")
    if typical is None or free is None:
        raise SystemExit(
            "TomTom summary lacked historicTrafficTravelTimeInSeconds or "
            f"noTrafficTravelTimeInSeconds. Summary keys were: {sorted(s)}. "
            "Nothing written; fix the adapter rather than substituting a guess.")
    return float(typical), float(free)


def mock(o_lat, o_lon, d_lat, d_lon, depart: datetime, key: str) -> tuple[float, float]:
    """Deterministic stand-in so the pipeline is testable without a key or network.

    NOT a congestion model and never written to a published file: main() refuses
    to write the site copy for a mock run, and stamps the artifact as mock so a
    reader cannot mistake it for a measurement.
    """
    free = 600.0
    bump = {8: 1.35, 12: 1.05, 17: 1.45}.get(depart.hour, 1.02)
    if depart.weekday() >= 5:
        bump = 1.03
    return free * bump, free


PROVIDERS = {"tomtom": tomtom, "mock": mock}


def read_key() -> str:
    """The provider key, from the environment or from a gitignored .env.

    Two sources because there are two callers with different habits. GitHub
    Actions injects DRIVE_TRAFFIC_KEY from a repository secret; a person at a
    laptop should not have to remember an export before every run. .env is
    already in .gitignore, same discipline as outreach/phone.txt: the secret
    lives only in files git never sees.

    Never printed, never logged, never written into the artifact. The output
    records the provider NAME and the sample date, which is what a reader needs
    to judge the number, and nothing that would let them make the calls.
    """
    k = os.environ.get("DRIVE_TRAFFIC_KEY", "").strip()
    if k:
        return k
    env = REPO_DIR / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DRIVE_TRAFFIC_KEY"):
                _, _, v = line.partition("=")
                return v.strip().strip("'\"")
    return ""


def check_key(provider: str, key: str) -> int:
    """ONE call, to prove the key and the adapter work, before spending 492.

    The TomTom adapter was written from the documented response shape and had
    never run against the live API, because this checkout had no key. Finding out
    it was wrong on request 1 of 492 is very different from finding out on
    request 492, and different again from finding out from a file full of nulls.

    Prints the parsed numbers so a person can sanity-check them: a typical trip
    that is slower than free-flow, by a plausible margin, at a plausible duration.
    """
    fn = PROVIDERS[provider]
    # Downtown Greenville to Berea, a real pair this project routes every day.
    o_lat, o_lon, d_lat, d_lon = 34.8526, -82.3940, 34.8871, -82.4479
    when = next_occurrence("weekday", "17:00:00")
    print(f"Checking {provider} with one request, departing {when:%a %d %b %H:%M} ...")
    try:
        typical, free = fn(o_lat, o_lon, d_lat, d_lon, when, key)
    except SystemExit as e:
        print(f"  FAILED: {e}")
        return 1
    except Exception as e:                                     # noqa: BLE001
        print(f"  FAILED: {type(e).__name__}: {e}")
        return 1
    factor = typical / free if free else 0
    print(f"  free flow      {free/60:6.1f} min")
    print(f"  typical 5pm    {typical/60:6.1f} min")
    print(f"  factor         {factor:6.3f}")
    if not (MIN_PLAUSIBLE <= factor <= MAX_PLAUSIBLE):
        print(f"  ⚠️  outside the plausible band {MIN_PLAUSIBLE}-{MAX_PLAUSIBLE}. "
              "The adapter may be reading the wrong fields.")
        return 1
    print("  OK. The key works and the adapter parses. Safe to run the full sample.")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Sample drive congestion per tract centroid.")
    ap.add_argument("--provider", default=os.environ.get("DRIVE_TRAFFIC_PROVIDER", "tomtom"),
                    choices=sorted(PROVIDERS))
    ap.add_argument("--limit", type=int, help="sample only the first N tracts (smoke run)")
    ap.add_argument("--check", action="store_true",
                    help="make ONE request to prove the key and adapter work, then stop")
    args = ap.parse_args()

    key = read_key()
    if args.check:
        raise SystemExit(check_key(args.provider, key))
    if args.provider != "mock" and not key:
        print("DRIVE_TRAFFIC_KEY is not set, so no congestion sample was taken.")
        print("Writing NOTHING. Drive times stay free-flow and are labeled as such.")
        print("This is the designed outcome, not a failure: a guessed multiplier")
        print("on a public health tool is worse than an honest absence.")
        return

    ensure_dirs()
    geojson = DASHBOARD_DATA_DIR / f"tracts_{COUNTY_FIPS}.geojson"
    if not geojson.exists():
        sys.exit(f"ERROR: {geojson} missing — run fetch_tract_geojson.py first.")
    feats = read_json(geojson)["features"]
    if args.limit:
        feats = feats[:args.limit]
    facilities = load_facilities(CATEGORY)
    fn = PROVIDERS[args.provider]

    print(f"Sampling {len(WINDOWS)} windows x {len(feats)} tract centroids "
          f"via {args.provider} ...")
    units, dropped = [], []
    for i, f in enumerate(feats):
        p = f["properties"]
        lat, lon = float(p["INTPTLAT"]), float(p["INTPTLON"])
        # The SAME nearest-facility choice the rollup makes, so the factor
        # describes the trip the site actually reports rather than some other
        # trip that happens to start in the same tract.
        ranked = nearest(lat, lon, facilities, "drive", k=1, prefer_osrm=False)
        if not ranked["results"]:
            continue
        dest = ranked["results"][0]["facility"]
        rec = {"id": p["GEOID"], "name": p.get("BASENAME", p["GEOID"]),
               "dest": dest.get("name")}
        for w in WINDOWS:
            when = next_occurrence(w["day"], w["depart"])
            typical, free = fn(lat, lon, float(dest["lat"]), float(dest["lon"]), when, key)
            if free <= 0:
                rec[w["key"]] = None
                continue
            factor = round(typical / free, 3)
            if factor < MIN_PLAUSIBLE or factor > MAX_PLAUSIBLE:
                dropped.append({"id": rec["id"], "window": w["key"], "factor": factor})
                rec[w["key"]] = None
            else:
                rec[w["key"]] = factor
            if args.provider != "mock":
                time.sleep(POLITE_DELAY_S)
        units.append(rec)
        if (i + 1) % 25 == 0:
            print(f"  {i + 1}/{len(feats)} tracts ...")

    summary = {}
    for w in WINDOWS:
        vals = sorted(u[w["key"]] for u in units if u[w["key"]] is not None)
        summary[w["key"]] = {
            "label": w["label"],
            "n_sampled": len(vals),
            "factor_median": round(vals[len(vals) // 2], 3) if vals else None,
            "factor_max": vals[-1] if vals else None,
        }

    out = {
        "county_fips": COUNTY_FIPS,
        "county": "Greenville County",
        "category": CATEGORY,
        "geography": "tract",
        "baseline_window": BASELINE,
        "provider": args.provider,
        "sampled_on": date.today().isoformat(),
        "is_mock": args.provider == "mock",
        "source": ("MODELED — typical-traffic vs free-flow drive time for each tract's "
                   "Census internal point to its nearest FQHC"),
        "model_notes": (
            "A factor is typical-traffic seconds divided by free-flow seconds for the "
            "same origin-destination pair at a representative departure. TYPICAL, not "
            "live: the provider is queried for its historical profile at that time of "
            "day, so the number is stable enough to benchmark against annual ACS data. "
            "Sampled at 123 Census tract internal points, never at a user's address; no "
            "address searched on the site is sent to any routing provider. Factors "
            f"outside {MIN_PLAUSIBLE}-{MAX_PLAUSIBLE} are dropped rather than clamped."
        ),
        "windows": [{**w} for w in WINDOWS],
        "summary": summary,
        "dropped_implausible": dropped,
        "units": units,
    }
    write_json(PROCESSED_DIR / OUT_NAME, out, label=f"{OUT_NAME} (processed)")
    if args.provider == "mock":
        print("  mock run: site copy deliberately NOT written.")
    else:
        write_json(DASHBOARD_DATA_DIR / OUT_NAME, out, label=f"{OUT_NAME} (site)")
    for w in WINDOWS:
        s = summary[w["key"]]
        print(f"  {s['label']:>18}: median factor {s['factor_median']} "
              f"over {s['n_sampled']} tracts")
    if dropped:
        print(f"  dropped {len(dropped)} implausible samples (outside "
              f"{MIN_PLAUSIBLE}-{MAX_PLAUSIBLE}); see dropped_implausible")


if __name__ == "__main__":
    main()
