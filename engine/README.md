# engine/: Scoring engine core (Phase 2)

**Status: in progress.** Geocoding + walk-based access work end to end; Greenlink
transit routing and the equity join are being wired in.

The hardest technical piece: geocode an address, then compute time to the nearest
facility of a chosen category via **walk** and via **Greenlink transit** (walk + wait
+ ride + transfer). Isolated here so it can be tested independently before it's wired
into any UI (spec §7, Phase 2).

## Modules

| Module | Does | Status |
|---|---|---|
| `geocode.py` | Address → lat/lon + tract/county FIPS (Census Geocoder, no key) | ✅ works |
| `geo_utils.py` | Haversine distance | ✅ works |
| `walk.py` | Rank facilities by walking time (straight-line estimate) | ✅ works |
| `drive.py` | Rank facilities by driving time (straight-line estimate) | ✅ works |
| `osrm.py` | Real road-network walk/drive times via OSRM (table service) | ✅ works |
| `routing.py` | Unify OSRM + estimate: `nearest(origin, facs, mode)` | ✅ works |
| `facilities.py` | Load a category's facility list from processed data | ✅ works |
| `score.py` | Orchestrate geocode → nearest → transit → equity | ✅ walk path works |
| `transit.py` | Greenlink GTFS transit time (RAPTOR-style, walk + ride + transfer + ride) | ✅ works (≤1 transfer) |
| `equity.py` | Compare origin tract vs county (ACS) | ⬜ needs ACS pull |

## Interface

```python
from engine.score import score
score("206 S Main St, Greenville, SC 29601", category="fqhc")
```

Returns a JSON-serializable dict: geocoded origin, nearest facility with `walk_minutes`,
walk alternatives, a `transit` block (None-with-reason until GTFS is loaded), and an
`equity` block (None-with-reason until ACS is loaded). Transit and equity are pluggable
so the walk result works before they exist.

## Walk / drive routing: estimate + OSRM

Two backends behind one call, `routing.nearest(origin, facilities, mode)`:

- **Estimate (offline, default for bulk):** straight-line (haversine) distance ×
  **1.3 detour** ÷ speed: **4.8 km/h** (~3 mph) walking, **40 km/h** (~25 mph
  effective) driving. Dependency-light, reproducible, always available. Constants live
  in `walk.py` / `drive.py`.
- **OSRM (real road-network):** `osrm.py` calls a public OSRM server's *table* service
  (one origin → all facilities in one request) for true routed times. Used by the
  interactive lookup and `score()` by default; falls back to the estimate whenever OSRM
  is unreachable, and each result carries `routing_method: "osrm" | "estimate"`.

Config: `OSRM_CAR_URL` / `OSRM_FOOT_URL` to point at your own OSRM (recommended beyond a
pilot, since the public FOSSGIS demo asks for light use); `OSRM_DISABLE=1` forces the
estimate. Transport prefers `requests` and falls back to a `curl` subprocess when the
local TLS stack can't reach the host (e.g. old LibreSSL).

## Transit model (built: MVP fidelity)

A **RAPTOR-style earliest-arrival** search allowing up to `MAX_ROUNDS` rides
(currently 2 → **0 or 1 transfer**) on a representative weekday midday departure:
walk to a nearby stop (≤20 min) + wait + ride + optional transfer (≥3 min buffer) +
ride + walk from the alighting stop. Labels are computed once from the origin, then
each facility is checked against them. Returns a leg-by-leg breakdown, or
`reachable: false` with a reason when nothing qualifies within the caps.

Allowing one transfer matters for Greenlink specifically: it's hub-and-spoke through
the downtown transit center, so suburban origin→destination pairs (e.g. Woodruff Rd →
an FQHC) are typically only reachable by transferring downtown, which the model now
finds.

**Bounds / upgrade path:** raise `MAX_ROUNDS` for more transfers, or swap in a full
router (r5py / OpenTripPlanner) behind `transit_to_facilities()`; callers don't
change. For destinations within walking distance of the origin, the walk result is
reported alongside and will (correctly) beat transit.

## Privacy

Nothing here logs or persists the input address (see `docs/privacy-design.md`). The
address is sent only to the Census geocoder to resolve coordinates.
