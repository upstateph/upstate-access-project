"""Score one location for car-free access to what a housing placement needs.

Same engine, different question. `score()` asks "how far is this person from one
category of care". This asks "can someone placed at this address reach the four
things that keep a placement from failing, without a car".

The four, and why:
  fqhc       primary care
  dss        SNAP / Medicaid / TANF enrollment. ONE office serves the whole county.
  workforce  SC Works / DEW, three sites
  grocery    SNAP supermarket / super store / grocery store, 106 sites. Not the
             443 SNAP-authorized retailers: a gas station is not a grocery shop,
             and counting one would make food access look about four times better
             than it is, in exactly the neighborhoods that have no supermarket.

CAR-FREE, NOT TRANSIT-ONLY. A unit a ten-minute walk from a supermarket does not
need the bus. A destination counts as reachable if it is within `walk_cap` minutes
on foot OR reachable by Greenlink on the standard model. Both are reported
separately so the transit-only picture stays visible.

WHAT THIS RETURNS AND WHAT IT REFUSES TO RETURN. Four travel times and four
booleans. No composite score, and no verdict on the unit. A single number would
hide which of the four failed, which is the only part anyone can act on, and a
pass/fail stamped on a housing unit is a placement decision belonging to a person
who knows the household. The caller gets facts; the judgment stays human.

Privacy: identical contract to `score()`. The address is used transiently to
geocode, is never persisted here, and is never echoed back in an error.
"""
from __future__ import annotations

from .facilities import load_facilities
from .geocode import geocode
from .routing import nearest as route_nearest
from .score import COUNTY_FIPS, COUNTY_NAME, NEIGHBOR_COUNTIES
from .transit import transit_to_facilities_window

NEEDS = ("fqhc", "dss", "workforce", "grocery")

NEED_LABELS = {
    "fqhc": "Primary care (FQHC)",
    "dss": "DSS benefits office",
    "workforce": "Workforce services (SC Works)",
    "grocery": "Grocery store",
}

# Minutes on foot that count as "you do not need the bus for this".
# About a mile at the model's 3 mph. A judgment call, stated rather than buried:
# far enough to be a normal errand, close enough to do carrying groceries.
WALK_CAP_MIN = 20.0


def score_point(lat: float, lon: float, *, walk_cap: float = WALK_CAP_MIN,
                prefer_osrm: bool = True,
                facilities: dict[str, list[dict]] | None = None) -> dict:
    """Car-free reachability from a coordinate to each of the four needs.

    `facilities` lets a batch caller load each category once instead of per point.
    """
    facs = facilities or {n: load_facilities(n) for n in NEEDS}
    needs: dict[str, dict] = {}

    for need in NEEDS:
        pool = facs[need]
        walk = route_nearest(lat, lon, pool, "walk", k=1, prefer_osrm=prefer_osrm)
        wr = walk["results"][0] if walk["results"] else None
        walk_min = wr["minutes"] if wr else None

        transit = transit_to_facilities_window(lat, lon, pool)
        t_ok = bool(transit.get("reachable"))
        transit_min = transit["itinerary"]["total_minutes"] if t_ok else None

        walk_ok = walk_min is not None and walk_min <= walk_cap
        if walk_ok and transit_min is not None:
            best, by = (walk_min, "walk") if walk_min <= transit_min else (transit_min, "transit")
        elif walk_ok:
            best, by = walk_min, "walk"
        elif transit_min is not None:
            best, by = transit_min, "transit"
        else:
            best, by = None, None

        needs[need] = {
            "label": NEED_LABELS[need],
            "reachable": bool(walk_ok or t_ok),
            "by": by,
            "best_min": round(best, 1) if best is not None else None,
            "walk_min": round(walk_min, 1) if walk_min is not None else None,
            "walk_within_cap": walk_ok,
            "transit_min": transit_min,
            "transit_reachable": t_ok,
            "nearest": wr["facility"]["name"] if wr else None,
            "walk_method": walk["method"],
        }

    return {
        "needs": needs,
        "n_reachable": sum(1 for n in NEEDS if needs[n]["reachable"]),
        "n_needs": len(NEEDS),
        "all_four": all(needs[n]["reachable"] for n in NEEDS),
        "all_four_transit_only": all(needs[n]["transit_reachable"] for n in NEEDS),
        "unreachable": [NEED_LABELS[n] for n in NEEDS if not needs[n]["reachable"]],
        "walk_cap_min": walk_cap,
    }


def housing_score(address: str, *, walk_cap: float = WALK_CAP_MIN,
                  prefer_osrm: bool = True) -> dict:
    """Score one address. Mirrors `score()`'s error contract exactly."""
    geo = geocode(address)
    if geo is None:
        # Deliberately does not echo the address back.
        return {"ok": False, "error": "address_not_found"}

    if geo.county_fips != COUNTY_FIPS:
        # Greer, Piedmont and Fountain Inn straddle county lines, so a real local
        # address can land outside the modeled county. Name the county when we
        # can: a boundary reads as a boundary, an unexplained refusal reads as a
        # bug. This matters more here than in `score()`, because a placement
        # worker checking a Greer unit needs to know the tool cannot answer
        # rather than assume the unit failed.
        return {"ok": False, "error": "outside_coverage_area",
                "coverage": COUNTY_NAME,
                "resolved_county": NEIGHBOR_COUNTIES.get(geo.county_fips)}

    result = score_point(geo.lat, geo.lon, walk_cap=walk_cap, prefer_osrm=prefer_osrm)
    result["ok"] = True
    result["tract_fips"] = geo.tract_fips if hasattr(geo, "tract_fips") else None
    result["model"] = (
        "Car-free access: reachable means within the walk cap on foot OR a "
        "Greenlink trip with at most one transfer and at most a 30-minute wait, "
        "taken as the median over departures sampled every 10 minutes across the "
        "weekday-midday hour. Modeled from public data, not an observed trip.")
    return result
