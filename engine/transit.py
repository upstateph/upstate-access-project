"""Greenlink transit travel-time estimation from the GTFS static feed.

Model (MVP fidelity — documented, honest about its bounds):
  A RAPTOR-style earliest-arrival search allowing up to MAX_ROUNDS rides
  (currently 2 -> **0 or 1 transfer**):
      walk to a nearby stop -> ride -> (optional transfer + wait) -> ride
      -> walk to the destination.
  We evaluate a representative weekday midday departure and return the fastest
  itinerary, with a full leg-by-leg breakdown.

  Allowing one transfer matters for Greenlink specifically: it's a hub-and-spoke
  system radiating from the downtown transit center, so many suburban
  origin->destination pairs are only reachable by transferring downtown.

  Upgrade path (unchanged interface): raise MAX_ROUNDS for more transfers, or swap
  in a full router (r5py / OpenTripPlanner) behind transit_to_facilities().

Reads the cached feed at data/raw/gtfs/greenlink_gtfs.zip (run fetch_greenlink_gtfs.py).
Nothing here persists the origin.
"""
from __future__ import annotations

import csv
import datetime as _dt
import io
import zipfile
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from .geo_utils import haversine_km
from .walk import walk_minutes

ENGINE_DIR = Path(__file__).resolve().parent
GTFS_ZIP = ENGINE_DIR.parent / "data" / "raw" / "gtfs" / "greenlink_gtfs.zip"

# Tunables (explicit so they can be justified/adjusted).
MAX_ACCESS_WALK_MIN = 20.0    # farthest we'll walk to/from a bus stop
DEFAULT_DEPART = "12:00:00"   # representative midday weekday departure
MAX_TOTAL_MIN = 180.0         # ignore itineraries longer than this
MAX_ROUNDS = 2                # rides allowed (2 => up to 1 transfer)
MIN_TRANSFER_SEC = 180        # buffer required to make a connecting ride


# ── GTFS loading ─────────────────────────────────────────────────────────────
def _read(zf: zipfile.ZipFile, name: str) -> list[dict]:
    with zf.open(name) as fh:
        return list(csv.DictReader(io.TextIOWrapper(fh, "utf-8-sig")))


def parse_gtfs_time(t: str) -> int | None:
    """GTFS 'HH:MM:SS' -> seconds after midnight. Hours may exceed 24."""
    t = (t or "").strip()
    if not t:
        return None
    h, m, s = (int(x) for x in t.split(":"))
    return h * 3600 + m * 60 + s


class GreenlinkGTFS:
    """Lazily-parsed view of the feed needed for routing."""

    def __init__(self, zip_path: Path = GTFS_ZIP):
        if not zip_path.exists():
            raise FileNotFoundError(
                f"Greenlink GTFS feed not found at {zip_path}. Run fetch_greenlink_gtfs.py."
            )
        with zipfile.ZipFile(zip_path) as zf:
            stops = _read(zf, "stops.txt")
            trips = _read(zf, "trips.txt")
            stop_times = _read(zf, "stop_times.txt")
            cal_dates = _read(zf, "calendar_dates.txt")

        self.stop_coord: dict[str, tuple[float, float]] = {}
        self.stop_name: dict[str, str] = {}
        for s in stops:
            try:
                self.stop_coord[s["stop_id"]] = (float(s["stop_lat"]), float(s["stop_lon"]))
            except (TypeError, ValueError):
                continue
            self.stop_name[s["stop_id"]] = s.get("stop_name", "")

        self.service_dates: dict[str, set[str]] = defaultdict(set)
        for r in cal_dates:
            if r.get("exception_type") == "1":  # 1 = service added on this date
                self.service_dates[r["service_id"]].add(r["date"])

        self.trip_service = {t["trip_id"]: t["service_id"] for t in trips}
        self.trip_route = {t["trip_id"]: t.get("route_id", "") for t in trips}

        tt: dict[str, list] = defaultdict(list)
        for st in stop_times:
            dep = parse_gtfs_time(st.get("departure_time"))
            arr = parse_gtfs_time(st.get("arrival_time"))
            if dep is None and arr is None:
                continue
            tt[st["trip_id"]].append((int(st["stop_sequence"]), st["stop_id"], dep, arr))
        for tid in tt:
            tt[tid].sort(key=lambda r: r[0])
        self.trip_stops = tt

    def representative_service(self, day: str = "weekday") -> set[str]:
        """Service IDs active on the earliest date of the requested day type.

        day: "weekday" (Mon–Fri), "saturday", or "sunday"."""
        wanted = {"weekday": (0, 1, 2, 3, 4), "saturday": (5,), "sunday": (6,)}[day]
        all_dates = sorted({d for dates in self.service_dates.values() for d in dates})
        target = None
        for d in all_dates:
            dt = _dt.date(int(d[:4]), int(d[4:6]), int(d[6:8]))
            if dt.weekday() in wanted:
                target = d
                break
        if target is None and all_dates:
            target = all_dates[0]
        return {sid for sid, dates in self.service_dates.items() if target in dates}

    # Backwards-compatible alias for the original weekday-only API.
    def representative_weekday_service(self) -> set[str]:
        return self.representative_service("weekday")

    def name(self, sid: str) -> str:
        return self.stop_name.get(sid, sid)


@lru_cache(maxsize=1)
def _feed() -> GreenlinkGTFS:
    return GreenlinkGTFS()


# ── Routing ──────────────────────────────────────────────────────────────────
def _nearby_stops(lat: float, lon: float, feed: GreenlinkGTFS) -> dict[str, float]:
    """Stops within MAX_ACCESS_WALK_MIN, mapped to walk minutes."""
    out: dict[str, float] = {}
    for sid, (slat, slon) in feed.stop_coord.items():
        wm = walk_minutes(haversine_km(lat, lon, slat, slon))
        if wm <= MAX_ACCESS_WALK_MIN:
            out[sid] = round(wm, 1)
    return out


def _compute_labels(origin_lat: float, origin_lon: float, depart: str,
                    feed: GreenlinkGTFS, day: str = "weekday") -> tuple[dict, dict, int]:
    """RAPTOR-style earliest-arrival labels for every reachable stop.

    Returns (labels, access_stops, t0). Each label:
      {arrival, rides, access_walk, legs:[{board/alight stop+time, route_id}]}.
    """
    t0 = parse_gtfs_time(depart)
    access = _nearby_stops(origin_lat, origin_lon, feed)
    services = feed.representative_service(day)
    active_trips = [(tid, seq) for tid, seq in feed.trip_stops.items()
                    if feed.trip_service.get(tid) in services]

    # Round 0: standing at each access stop, ready to board.
    labels: dict[str, dict] = {}
    for sid, wm in access.items():
        labels[sid] = {"arrival": t0 + wm * 60, "rides": 0, "access_walk": wm, "legs": []}

    for _ in range(MAX_ROUNDS):
        updated: dict[str, dict] = {}
        for tid, seq in active_trips:
            board = None  # (label_snapshot, board_sid, board_dep)
            for _s, sid, dep, arr in seq:
                cur = labels.get(sid)  # previous-round labels only
                if cur is not None and dep is not None:
                    buffer = MIN_TRANSFER_SEC if cur["rides"] > 0 else 0
                    if dep >= cur["arrival"] + buffer:
                        # Board at the earliest boardable stop; switch to a boarding
                        # with fewer prior rides when we find one (fewer transfers,
                        # same downstream arrival times).
                        if board is None or cur["rides"] < board[0]["rides"]:
                            board = (cur, sid, dep)
                if board is not None and arr is not None and board[1] != sid:
                    bcur, bsid, bdep = board
                    prev = updated.get(sid) or labels.get(sid)
                    if prev is None or arr < prev["arrival"]:
                        leg = {
                            "board_stop": feed.name(bsid), "board_time": bdep,
                            "alight_stop": feed.name(sid), "alight_time": arr,
                            "route_id": feed.trip_route.get(tid, ""),
                        }
                        updated[sid] = {
                            "arrival": arr,
                            "rides": bcur["rides"] + 1,
                            "access_walk": bcur["access_walk"],
                            "legs": bcur["legs"] + [leg],
                        }
        for sid, lab in updated.items():
            cur = labels.get(sid)
            if (cur is None or lab["arrival"] < cur["arrival"]
                    or (lab["arrival"] == cur["arrival"] and lab["rides"] < cur["rides"])):
                labels[sid] = lab

    return labels, access, t0


def _best_to(dest_lat: float, dest_lon: float, labels: dict, t0: int,
             feed: GreenlinkGTFS) -> dict | None:
    """Best itinerary from the precomputed labels to a destination, or None."""
    egress = _nearby_stops(dest_lat, dest_lon, feed)
    best = None
    for sid, wm in egress.items():
        lab = labels.get(sid)
        if lab is None or not lab["legs"]:
            continue
        total_arrival = lab["arrival"] + wm * 60
        total_min = (total_arrival - t0) / 60.0
        if total_min <= 0 or total_min > MAX_TOTAL_MIN:
            continue
        if best is None or total_min < best["total_minutes"]:
            legs = lab["legs"]
            board_ready = t0 + lab["access_walk"] * 60
            first_wait = (legs[0]["board_time"] - board_ready) / 60.0
            transfer_wait = sum(
                legs[i]["board_time"] - legs[i - 1]["alight_time"]
                for i in range(1, len(legs))
            ) / 60.0
            in_vehicle = sum(l["alight_time"] - l["board_time"] for l in legs) / 60.0
            best = {
                "total_minutes": round(total_min, 1),
                "walk_to_stop_min": lab["access_walk"],
                "wait_min": round(first_wait + transfer_wait, 1),
                "in_vehicle_min": round(in_vehicle, 1),
                "walk_from_stop_min": wm,
                "transfers": len(legs) - 1,
                "legs": [
                    {
                        "route_id": l["route_id"],
                        "board_stop": l["board_stop"],
                        "alight_stop": l["alight_stop"],
                        "board_time": _fmt_time(l["board_time"]),
                        "alight_time": _fmt_time(l["alight_time"]),
                    }
                    for l in legs
                ],
                "depart_query": _fmt_time(t0),
            }
    return best


def _fmt_time(sec: int) -> str:
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h % 24:02d}:{m:02d}:{s:02d}"


def transit_time(origin_lat: float, origin_lon: float,
                 dest_lat: float, dest_lon: float,
                 *, depart: str = DEFAULT_DEPART, day: str = "weekday") -> dict | None:
    """Fastest ≤1-transfer transit itinerary origin→dest, or None if unreachable."""
    feed = _feed()
    labels, _access, t0 = _compute_labels(origin_lat, origin_lon, depart, feed, day)
    return _best_to(dest_lat, dest_lon, labels, t0, feed)


def transit_to_facilities(origin_lat: float, origin_lon: float,
                          facilities: list[dict], *, depart: str = DEFAULT_DEPART,
                          day: str = "weekday") -> dict:
    """Best ≤1-transfer transit itinerary from origin to any of the facilities.

    Labels are computed once from the origin, then each facility is checked against
    them. `reachable` is False when no itinerary exists within the caps."""
    feed = _feed()
    labels, _access, t0 = _compute_labels(origin_lat, origin_lon, depart, feed, day)

    best_fac, best_it = None, None
    for f in facilities:
        lat, lon = f.get("lat"), f.get("lon")
        if lat is None or lon is None:
            continue
        it = _best_to(float(lat), float(lon), labels, t0, feed)
        if it and (best_it is None or it["total_minutes"] < best_it["total_minutes"]):
            best_it, best_fac = it, f

    model = f"≤{MAX_ROUNDS - 1}-transfer {day} {depart[:5]}"
    if best_it is None:
        return {
            "available": True,
            "reachable": False,
            "reason": f"No Greenlink itinerary within caps (≤{int(MAX_ACCESS_WALK_MIN)} min "
                      f"walk to/from a stop, ≤{MAX_ROUNDS - 1} transfer, "
                      f"≤{int(MAX_TOTAL_MIN)} min total).",
            "model": model,
        }
    return {
        "available": True,
        "reachable": True,
        "model": model,
        "facility": best_fac,
        "itinerary": best_it,
    }


if __name__ == "__main__":
    import json
    import sys
    olat, olon = 34.8484, -82.4001
    dlat, dlon = (float(sys.argv[1]), float(sys.argv[2])) if len(sys.argv) >= 3 else (34.8163, -82.4143)
    print(json.dumps(transit_time(olat, olon, dlat, dlon), indent=2))
