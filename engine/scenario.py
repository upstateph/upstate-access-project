"""Service-change scenarios: route the real network, and a modified one.

A county-level statistic ("40.7% of tracts are transit-reachable") tells a planner
nothing they can act on. What they need is *which route, which change, worth how
many minutes*. That requires answering counterfactuals, and the only honest way to
answer one is to modify the timetable and re-run the router over it.

`densified_feed("506", factor=2)` returns a feed in which route 506 runs twice as
often — synthetic trips inserted midway between each consecutive pair of real trips
on the same stop pattern and service day. It copies the trip tables rather than
mutating the cached feed, so the real network is never disturbed.

Bounds worth stating when quoting a scenario result:
  - It assumes the added trips follow an existing pattern's stop sequence and
    running times, i.e. "run the same trip more often", not a re-route.
  - It ignores operational feasibility entirely — vehicles, operators, layover.
    A doubled headway implies roughly doubled peak vehicles on that route, which
    is the cost side a planner will immediately ask about.
  - It changes no other route, so transfer opportunities elsewhere are unchanged.
"""
from __future__ import annotations

import copy

from .transit import GreenlinkGTFS, _feed


def route_trip_groups(feed: GreenlinkGTFS, route_id: str) -> dict:
    """Trips of a route grouped by (service_id, stop pattern).

    Grouping by the stop-id sequence keeps directions and branches separate, so a
    synthetic trip is always interleaved with trips it actually resembles.
    """
    groups: dict[tuple, list[str]] = {}
    for tid, route in feed.trip_route.items():
        if route != route_id:
            continue
        seq = feed.trip_stops.get(tid)
        if not seq:
            continue
        key = (feed.trip_service.get(tid), tuple(s for _, s, _, _ in seq))
        groups.setdefault(key, []).append(tid)
    return groups


def first_departure(feed: GreenlinkGTFS, trip_id: str) -> int | None:
    for _seq, _sid, dep, arr in feed.trip_stops[trip_id]:
        t = dep if dep is not None else arr
        if t is not None:
            return t
    return None


def observed_headways(feed: GreenlinkGTFS, route_id: str,
                      start_sec: int, end_sec: int) -> list[int]:
    """Gaps (seconds) between consecutive departures on each pattern in a window."""
    gaps: list[int] = []
    for tids in route_trip_groups(feed, route_id).values():
        times = sorted(t for t in (first_departure(feed, x) for x in tids)
                       if t is not None and start_sec <= t <= end_sec)
        gaps.extend(b - a for a, b in zip(times, times[1:]))
    return gaps


def densified_feed(route_id: str, factor: int = 2) -> GreenlinkGTFS:
    """A copy of the cached feed with `route_id` running `factor`x as often."""
    if factor < 2:
        raise ValueError("factor must be >= 2")
    base = _feed()
    scen = copy.copy(base)                       # shallow: stops/coords shared (read-only)
    scen.trip_stops = dict(base.trip_stops)      # copy the tables we mutate
    scen.trip_route = dict(base.trip_route)
    scen.trip_service = dict(base.trip_service)

    added = 0
    for (service_id, _pattern), tids in route_trip_groups(base, route_id).items():
        timed = sorted(((first_departure(base, t), t) for t in tids
                        if first_departure(base, t) is not None))
        for (t_now, tid), (t_next, _) in zip(timed, timed[1:]):
            gap = t_next - t_now
            if gap <= 0:
                continue
            for k in range(1, factor):
                shift = int(gap * k / factor)
                new_id = f"{tid}__x{factor}_{k}"
                scen.trip_stops[new_id] = [
                    (seq, sid,
                     None if dep is None else dep + shift,
                     None if arr is None else arr + shift)
                    for seq, sid, dep, arr in base.trip_stops[tid]
                ]
                scen.trip_route[new_id] = route_id
                scen.trip_service[new_id] = service_id
                added += 1
    scen.scenario = {"route_id": route_id, "factor": factor, "trips_added": added}
    return scen
