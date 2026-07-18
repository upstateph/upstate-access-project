"""Offline tests for the geo/walk math. Run: python -m engine.tests.test_walk

No network required. Kept as plain asserts so it runs with or without pytest.
"""
from engine.geo_utils import haversine_km
from engine.walk import rank_by_walk, walk_minutes


def test_haversine_known_distance():
    # ~1 deg latitude ≈ 111 km
    d = haversine_km(34.0, -82.0, 35.0, -82.0)
    assert 110 < d < 112, d


def test_haversine_zero():
    assert haversine_km(34.85, -82.40, 34.85, -82.40) == 0.0


def test_walk_minutes_monotonic_and_scaled():
    # 4.8 km/h with 1.3 detour: 1 km straight -> 1.3 km -> 16.25 min
    m = walk_minutes(1.0)
    assert abs(m - 16.25) < 0.01, m
    assert walk_minutes(2.0) > walk_minutes(1.0)


def test_rank_orders_nearest_first_and_skips_missing_coords():
    origin = (34.8484, -82.4001)
    facs = [
        {"id": "far", "name": "Far", "lat": 34.8750, "lon": -82.4200},
        {"id": "near", "name": "Near", "lat": 34.8555, "lon": -82.4005},
        {"id": "nocoord", "name": "No Coords", "lat": None, "lon": None},
    ]
    ranked = rank_by_walk(*origin, facs)
    assert [r.facility["id"] for r in ranked] == ["near", "far"]  # nocoord skipped
    assert ranked[0].minutes < ranked[1].minutes


def _run():
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ok  {name}")
            passed += 1
    print(f"{passed} tests passed.")


if __name__ == "__main__":
    _run()
