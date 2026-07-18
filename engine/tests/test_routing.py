"""Offline tests for the routing layer + OSRM fallback.
Run: python -m engine.tests.test_routing

Forces OSRM off (OSRM_DISABLE) so no network is touched — this exercises the
straight-line fallback path and the common result shape.
"""
import os

os.environ["OSRM_DISABLE"] = "1"  # must be set before osrm reads it

from engine import osrm  # noqa: E402
from engine.routing import nearest  # noqa: E402

FACS = [
    {"id": "far", "name": "Far", "lat": 34.8750, "lon": -82.4200},
    {"id": "near", "name": "Near", "lat": 34.8555, "lon": -82.4005},
]
ORIGIN = (34.8484, -82.4001)


def test_osrm_disabled_flag():
    assert osrm.osrm_disabled() is True
    assert osrm.rank_by_osrm(*ORIGIN, FACS, "drive") is None  # disabled -> None


def test_nearest_falls_back_to_estimate():
    r = nearest(*ORIGIN, FACS, "walk")
    assert r["method"] == "estimate"
    assert [x["facility"]["id"] for x in r["results"]] == ["near", "far"]
    assert r["results"][0]["minutes"] < r["results"][1]["minutes"]


def test_drive_mode_and_common_shape():
    r = nearest(*ORIGIN, FACS, "drive", k=1)
    assert r["method"] == "estimate"
    assert len(r["results"]) == 1
    row = r["results"][0]
    assert {"facility", "minutes", "network_mi"} <= set(row)


def test_invalid_mode_raises():
    try:
        nearest(*ORIGIN, FACS, "teleport")
    except ValueError:
        return
    raise AssertionError("expected ValueError for invalid mode")


def _run():
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}"); passed += 1
    print(f"{passed} tests passed.")


if __name__ == "__main__":
    _run()
