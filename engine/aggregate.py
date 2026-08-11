"""Phase 4 — aggregate access results by tract with k-anonymity suppression.

Two related jobs:
  1. `anonymize_result` strips a per-lookup engine.score() output down to a record
     that carries NO re-identifying information — only the tract FIPS and the travel
     times. The searched address, matched address, coordinates, and chosen facility
     are all dropped. This is what may be retained/rolled up; the raw address never is.
  2. `aggregate` rolls those records up to tract level and **suppresses any tract with
     fewer than K observations** (default K = 25, spec §6). Suppression is
     **fail-closed**: if a count can't be established, the tract is suppressed.

The same aggregation works whether the records come from real (anonymized) usage or
from a modeled sampling of tract points — the caller labels the source.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, median

K_ANONYMITY_THRESHOLD = 25  # placeholder to tune once real usage volume is known (spec §10)


@dataclass
class AccessRecord:
    """A single de-identified access observation. No address, no coordinates."""
    tract_fips: str
    walk_minutes: float | None
    transit_minutes: float | None      # None if transit unreachable
    transit_reachable: bool


def anonymize_result(result: dict) -> AccessRecord | None:
    """Reduce an engine.score() result to a de-identified AccessRecord.

    Returns None if the result has no tract (can't be aggregated) or failed. Only the
    tract FIPS and travel times survive — never the address or facility identity."""
    if not result.get("ok"):
        return None
    tract = (result.get("origin") or {}).get("tract_fips")
    if not tract:
        return None
    walk = (result.get("nearest") or {}).get("walk_minutes")
    transit = result.get("transit") or {}
    reachable = bool(transit.get("reachable"))
    tmin = transit.get("itinerary", {}).get("total_minutes") if reachable else None
    return AccessRecord(tract_fips=tract, walk_minutes=walk,
                        transit_minutes=tmin, transit_reachable=reachable)


def aggregate(records: list[AccessRecord], *, k: int = K_ANONYMITY_THRESHOLD) -> dict:
    """Roll records up to tract level, suppressing tracts with < k observations.

    Returns {threshold, tracts: [...visible...], suppressed_tracts, suppressed_observations}.
    Suppressed tracts expose NO statistics and not even their exact small count."""
    by_tract: dict[str, list[AccessRecord]] = {}
    for r in records:
        if not r or not r.tract_fips:
            continue  # fail-closed: unattributable observation is dropped
        by_tract.setdefault(r.tract_fips, []).append(r)

    visible, suppressed_tracts, suppressed_obs = [], 0, 0
    for tract, recs in sorted(by_tract.items()):
        n = len(recs)
        if n < k:
            suppressed_tracts += 1
            suppressed_obs += n
            continue
        walks = [x.walk_minutes for x in recs if x.walk_minutes is not None]
        transits = [x.transit_minutes for x in recs if x.transit_minutes is not None]
        # A tract passing the k check is NOT enough: each derived statistic must
        # itself rest on >= k observations. Otherwise a tract with 30 lookups but
        # only 2 reachable-by-transit publishes a median of those 2 individuals'
        # exact trip times. Sub-k statistics are suppressed individually.
        def _stat(values, fn):
            return round(fn(values), 1) if len(values) >= k else None

        visible.append({
            "tract_fips": tract,
            "n": n,
            "walk_min_mean": _stat(walks, mean),
            "walk_min_median": _stat(walks, median),
            "transit_min_median": _stat(transits, median),
            # A share over all n observations is safe (denominator >= k) and is
            # what makes "no transit route here" reportable at all.
            "pct_transit_reachable": round(
                100 * sum(1 for x in recs if x.transit_reachable) / n, 1),
        })

    return {
        "k_anonymity_threshold": k,
        "n_tracts_visible": len(visible),
        "n_tracts_suppressed": suppressed_tracts,
        "n_observations_suppressed": suppressed_obs,
        "tracts": visible,
    }
