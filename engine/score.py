"""Top-level scoring: address + category -> access result.

Orchestrates geocode -> nearest facility by walk -> (optional) transit time ->
(optional) equity comparison. Transit and equity are pluggable: if the Greenlink
GTFS feed or the ACS data hasn't been loaded yet, those fields come back as None
with a reason, and the walk-based result still works end to end.

Privacy: the address is used transiently to geocode and is not persisted here.
"""
from __future__ import annotations

import re

from .facilities import load_facilities
from .geocode import geocode
from .routing import nearest as route_nearest


# The only county modeled. Facility data, the GTFS feed and the equity
# benchmark are all Greenville County; an origin outside it cannot be scored.
COUNTY_FIPS = "45045"
COUNTY_NAME = "Greenville County, South Carolina"

# Neighboring counties, so a refusal can say WHERE an address landed rather than
# only that it was outside. Several Upstate towns straddle a county line —
# Greer (Greenville/Spartanburg), Piedmont (Greenville/Anderson), Fountain Inn
# (Greenville/Laurens) — so a resident of one of them can type a perfectly real
# local address and be refused. "Outside the pilot area" reads as a bug in that
# situation; "this address is in Spartanburg County" reads as a boundary, which
# is what it is.
NEIGHBOR_COUNTIES = {
    "45083": "Spartanburg County",
    "45007": "Anderson County",
    "45059": "Laurens County",
    "45077": "Pickens County",
    "45021": "Cherokee County",
    "45087": "Union County",
}


def score(address: str, category: str = "fqhc", *,
          candidates: int = 5, prefer_osrm: bool = True) -> dict:
    """Compute access from an address to the nearest facility of a category.

    Walk and drive times use OSRM road-network routing when reachable, falling back to
    the straight-line estimate (each result carries a `routing_method`). Returns a
    JSON-serializable dict. Raises FileNotFoundError if the category's facility data
    hasn't been pulled yet.
    """
    geo = geocode(address)
    if geo is None:
        # Deliberately does NOT echo the address back — keeps it out of any
        # client-side logging/reporting of error responses.
        return {"ok": False, "error": "address_not_found"}

    # Refuse addresses outside the modeled county.
    #
    # Without this the tool answers anyway, and answers absurdly: the White
    # House returned "nearest: GREER, 10,509 minutes" — a 7.3-day walk — and a
    # Chicago address returned 11 days, both with ok=true. That is worse than an
    # error, because it looks like a working answer. Every remote reviewer sent
    # this link will try their own address first; a confident nonsense number is
    # how a tool loses a reader in one click.
    #
    # The coverage limit is real, not a bug to route around: facility data,
    # GTFS and the equity benchmark are all Greenville County only.
    # Fail CLOSED: refuse unless the county is positively established as ours.
    # The fallback geocoder returns no county when a point falls outside the
    # modeled tracts, and "unknown" must not be treated as "probably fine" —
    # that is how a Spartanburg address gets a confident Greenville answer.
    if geo.county_fips != COUNTY_FIPS:
        # Distinguish "you are outside the county" from "you did not say WHICH
        # Greenville". A bare street with no city resolves somewhere plausible
        # and far away: "206 S Main St" geocodes to Seattle. Refusing that as
        # out-of-coverage is technically right and diagnostically useless, since
        # the reader's actual mistake was leaving the city off. A reviewer raised
        # this from the other direction, reporting that a ZIP appeared to be
        # required; it never was, but the input clearly does not explain itself.
        said_where = bool(re.search(r",\s*[A-Za-z][A-Za-z .'-]{2,}", address or "")
                          or re.search(r"\b(SC|South Carolina)\b", address or "", re.I))
        if not said_where:
            return {"ok": False, "error": "address_needs_city",
                    "coverage": COUNTY_NAME,
                    "matched_far_away": geo.matched_address}
        return {"ok": False, "error": "outside_coverage_area",
                "coverage": COUNTY_NAME,
                # Named where possible so a county-line resident sees a boundary
                # rather than a malfunction. None when the geocoder could not
                # place it at all.
                "resolved_county": NEIGHBOR_COUNTIES.get(geo.county_fips)}

    facilities = load_facilities(category)

    # Walk, drive and bike run in SEQUENCE, deliberately.
    #
    # Each is one OSRM /table request, and they dominate the lookup: profiling
    # put 20.85 s of a 21.64 s call inside these three. Measured on the live
    # beta, a warm lookup takes 21.5-27 s. Running the three concurrently is the
    # obvious fix and is NOT taken, because FOSSGIS's published policy for the
    # demo server is "you should not exceed 1 request per second"
    # (https://github.com/Project-OSRM/osrm-backend/wiki/API-Usage-Policy).
    # Three simultaneous requests per lookup breaks that, and the penalty for
    # ignoring it is being blocked — which costs every user real routing, to
    # save fifteen seconds.
    #
    # Honest note on the evidence: a concurrent build did show one address
    # degrading from method=osrm to method=estimate, but that test could not be
    # repeated — the sandbox lost outbound access to routing.openstreetmap.de
    # entirely (the live beta was reaching it fine at the same moment), so the
    # degradation cannot be pinned on rate limiting. The policy is the reason
    # this stays sequential; the observation is not load-bearing.
    #
    # So the ~25 s is accepted and DISCLOSED in the UI rather than engineered
    # around. The real fix is self-hosted OSRM (docs/roadmap.md Phase A), which
    # removes the limit because the server is ours; it is gated on a VPS.
    walk = route_nearest(geo.lat, geo.lon, facilities, "walk",
                         k=candidates, prefer_osrm=prefer_osrm)
    drive = route_nearest(geo.lat, geo.lon, facilities, "drive", k=1,
                          prefer_osrm=prefer_osrm)
    bike = route_nearest(geo.lat, geo.lon, facilities, "bike", k=1,
                         prefer_osrm=prefer_osrm)

    if not walk["results"]:
        return {"ok": False, "error": "no_facilities_with_coordinates", "category": category}

    nearest = walk["results"][0]

    # Drive time to the nearest-by-drive facility (may differ from nearest-by-walk).
    drive_block = None
    if drive["results"]:
        d = drive["results"][0]
        drive_block = {
            "facility": d["facility"],
            "drive_minutes": d["minutes"],
            "drive_network_mi": d["network_mi"],
            "routing_method": drive["method"],
        }

    # Bike. Added after an FQHC clinician reported patients arriving by bicycle:
    # without it those trips were reported at WALK time, roughly three times the
    # real burden. Ranked independently because the nearest facility by bike is
    # not always the nearest on foot.
    bike_block = None
    if bike["results"]:
        b = bike["results"][0]
        bike_block = {
            "facility": b["facility"],
            "bike_minutes": b["minutes"],
            "bike_network_mi": b["network_mi"],
            "routing_method": bike["method"],
        }

    # Transit is optional — only computed if the GTFS feed has been loaded.
    # Evaluated over the FULL facility list, not the top-k by walk: the facility
    # best reached by bus is often not among the closest by foot (audit finding —
    # top-5 flipped a pharmacy tract to "unreachable"). Labels are computed once
    # per origin, so the per-facility cost is small.
    transit = _try_transit(geo, facilities)

    result = {
        "ok": True,
        "category": category,
        "origin": geo.as_dict(),
        "nearest": {
            "facility": nearest["facility"],
            "walk_minutes": nearest["minutes"],
            "walk_network_mi": nearest["network_mi"],
            "routing_method": walk["method"],
        },
        "bike": bike_block,
        "drive": drive_block,
        "transit": transit,
        "alternatives": [
            {"facility": r["facility"], "walk_minutes": r["minutes"]}
            for r in walk["results"][1:]
        ],
        "equity": _try_equity(geo),
    }
    return result


def _try_transit(geo, facilities) -> dict | None:
    """Compute Greenlink transit time to the nearest reachable facility, if the
    GTFS feed is available. Returns None-with-reason otherwise.

    Degrades on ANY feed-layer failure — a corrupt/truncated zip or a feed missing
    an expected file must not take down the walk/drive result too (the module
    contract above promises the walk-based result still works end to end)."""
    try:
        # Windowed: a single departure instant is a coin flip on the headway, so we
        # sample a window and report the median. Same model the published rollups use.
        from .transit import transit_to_facilities_window  # lazy: needs GTFS loaded
    except Exception:
        return {"available": False, "reason": "transit module not available"}
    try:
        return transit_to_facilities_window(geo.lat, geo.lon, facilities)
    except FileNotFoundError:
        return {"available": False, "reason": "Greenlink GTFS feed not loaded (run fetch_greenlink_gtfs.py)"}
    except Exception:  # noqa: BLE001 — corrupt zip, unexpected feed schema, etc.
        return {"available": False, "reason": "Greenlink GTFS feed could not be read"}


def _try_equity(geo) -> dict | None:
    """Compare the origin tract to its county using ACS data, if loaded."""
    try:
        from .equity import compare_tract_to_county  # lazy: needs ACS loaded
    except Exception:
        return None
    try:
        return compare_tract_to_county(geo.tract_fips, geo.county_fips)
    except FileNotFoundError:
        return {"available": False, "reason": "ACS data not loaded (run fetch_census_acs.py)"}
    except Exception:  # noqa: BLE001 — malformed/truncated ACS JSON must not 500 the lookup
        return {"available": False, "reason": "ACS data could not be read"}


if __name__ == "__main__":
    import json
    import sys

    addr = " ".join(sys.argv[1:]) or "206 S Main St, Greenville, SC 29601"
    print(json.dumps(score(addr), indent=2))
