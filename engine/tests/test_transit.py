"""Offline tests for GTFS time parsing. Run: python -m engine.tests.test_transit

No network or feed file required (only parse_gtfs_time is exercised here).
"""
from engine.transit import parse_gtfs_time


def test_parse_basic():
    assert parse_gtfs_time("12:00:00") == 12 * 3600
    assert parse_gtfs_time("00:00:30") == 30
    assert parse_gtfs_time("08:15:00") == 8 * 3600 + 15 * 60


def test_parse_after_midnight_over_24h():
    # GTFS allows hours >= 24 for trips past midnight.
    assert parse_gtfs_time("25:30:00") == 25 * 3600 + 30 * 60


def test_parse_empty_is_none():
    assert parse_gtfs_time("") is None
    assert parse_gtfs_time(None) is None
    assert parse_gtfs_time("   ") is None


def _run():
    passed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}"); passed += 1
    print(f"{passed} tests passed.")


if __name__ == "__main__":
    _run()
