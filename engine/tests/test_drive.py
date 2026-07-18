"""Offline tests for the drive model. Run: python -m engine.tests.test_drive"""
from engine.drive import drive_minutes, rank_by_drive


def test_drive_minutes_scaled():
    # 40 km/h with 1.3 detour: 1 km straight -> 1.3 km -> 1.95 min
    assert abs(drive_minutes(1.0) - 1.95) < 0.01, drive_minutes(1.0)


def test_drive_faster_than_walk_for_same_distance():
    from engine.walk import walk_minutes
    assert drive_minutes(5.0) < walk_minutes(5.0)


def test_rank_orders_nearest_first():
    origin = (34.8484, -82.4001)
    facs = [
        {"id": "far", "lat": 34.8750, "lon": -82.4200},
        {"id": "near", "lat": 34.8555, "lon": -82.4005},
    ]
    ranked = rank_by_drive(*origin, facs)
    assert [r.facility["id"] for r in ranked] == ["near", "far"]


def _run():
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}"); passed += 1
    print(f"{passed} tests passed.")


if __name__ == "__main__":
    _run()
