"""Guards on the drive-time congestion factor.

The dangerous failure here is not a crash, it is a plausible number nobody
measured. Drive times feed a public health tool that people cite, so every path
that could produce a congestion figure without a real sample behind it gets a
test: no key, a mock sample, an implausible ratio, and a missing file.

The positive path (a real provider populating the windows) is exercised with a
synthetic non-mock artifact, because this checkout has no key and CI never will.
"""
import contextlib
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PROCESSED = REPO / "data" / "processed"
CONGESTION = PROCESSED / "drive_congestion_45045.json"
SPAN = PROCESSED / "drive_span_tract_45045.json"


def _load(name, path):
    """Import a data-pipeline script as a module.

    Its own directory has to go on sys.path first: these scripts do
    `from common import ...`, and common.py sits beside them in data-pipeline/,
    which is only importable because sys.path[0] is the script's directory when
    it is run directly. Importing one from elsewhere loses that.
    """
    d = str(Path(path).parent)
    if d not in sys.path:
        sys.path.insert(0, d)
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


fetch = _load("_fetch_drive_congestion",
              REPO / "data-pipeline" / "fetch_drive_congestion.py")


# ── the windows must not drift away from the transit ones ────────────────────

def test_windows_match_service_span():
    """One UI shows both. If the keys diverge, the car and the bus stop lining up."""
    span = _load("_build_service_span", REPO / "data-pipeline" / "build_service_span.py")
    assert [w["key"] for w in fetch.WINDOWS] == [w["key"] for w in span.WINDOWS]
    assert [w["depart"] for w in fetch.WINDOWS] == [w["depart"] for w in span.WINDOWS]
    assert fetch.BASELINE == span.BASELINE


# ── departure resolution ─────────────────────────────────────────────────────

def test_next_occurrence_is_future_and_right_day():
    for day, weekday in (("weekday", 1), ("saturday", 5)):
        d = fetch.next_occurrence(day, "08:00:00")
        assert d > datetime.now(), "providers reject departures in the past"
        assert d.weekday() == weekday
        assert (d.hour, d.minute) == (8, 0)


# ── no key means no file, and no invented multiplier ─────────────────────────

def test_no_key_writes_nothing(tmp_path):
    existed = CONGESTION.exists()
    before = CONGESTION.read_bytes() if existed else None
    env = {k: v for k, v in os.environ.items() if k != "DRIVE_TRAFFIC_KEY"}
    r = subprocess.run([sys.executable, "data-pipeline/fetch_drive_congestion.py"],
                       cwd=REPO, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "Writing NOTHING" in r.stdout
    assert CONGESTION.exists() == existed
    if existed:
        assert CONGESTION.read_bytes() == before


# ── implausible ratios are dropped, never clamped into looking real ──────────

def test_plausibility_bounds_are_a_closed_interval():
    assert fetch.MIN_PLAUSIBLE == 1.0, "a congested trip is never faster than free-flow"
    assert fetch.MAX_PLAUSIBLE > fetch.MIN_PLAUSIBLE


# ── the builder must not turn a missing sample into "no delay" ───────────────

SPAN_SITE = REPO / "dashboard" / "data" / "drive_span_tract_45045.json"


def _run_builder():
    return subprocess.run([sys.executable, "data-pipeline/build_drive_span.py"],
                          cwd=REPO, capture_output=True, text=True)


@contextlib.contextmanager
def _tree_restored(*paths):
    """Put every touched file back byte for byte AND mtime for mtime.

    The first version of these tests re-ran the builder in a finally block and
    called that "leaving the tree as we found it". It was not: rebuilding
    rewrites data/processed/ and dashboard/data/ with fresh timestamps, so
    running the suite left dashboard/ newer than dist/ and weekly_debug then
    reported "dist/ freshness: dashboard/ is newer" every single time. That WARN
    also fired in CI, where a check that cries wolf nightly is how a real stale
    deploy gets ignored. A test must not move a published artifact.
    """
    saved = {p: (p.read_bytes(), p.stat().st_mtime_ns) if p.exists() else None
             for p in paths}
    try:
        yield
    finally:
        for p, prev in saved.items():
            if prev is None:
                p.unlink(missing_ok=True)
            else:
                data, mtime = prev
                p.write_bytes(data)
                os.utime(p, ns=(mtime, mtime))


def test_mock_sample_never_populates_windows(tmp_path):
    """A mock artifact on a laptop must not be able to become a published claim."""
    with _tree_restored(CONGESTION, SPAN, SPAN_SITE):
        CONGESTION.write_text(json.dumps({
            "is_mock": True, "provider": "mock", "sampled_on": "2026-09-04",
            "units": [{"id": "45045003701", "wk_08": 1.9, "wk_12": 1.9,
                       "wk_17": 1.9, "sat_12": 1.9}],
        }))
        assert _run_builder().returncode == 0
        out = json.loads(SPAN.read_text())
        assert out["congestion_available"] is False
        assert all(u["wk_17"] is None for u in out["units"])
        assert "NO CONGESTION SAMPLE" in out["model_notes"]


def test_real_sample_populates_windows_from_free_flow():
    """The published minute is free-flow x factor, and must be reproducible."""
    with _tree_restored(CONGESTION, SPAN, SPAN_SITE):
        CONGESTION.write_text(json.dumps({
            "is_mock": False, "provider": "tomtom", "sampled_on": "2026-09-04",
            "units": [{"id": "45045003701", "wk_08": 1.5, "wk_12": 1.0,
                       "wk_17": 2.0, "sat_12": 1.1}],
        }))
        assert _run_builder().returncode == 0
        out = json.loads(SPAN.read_text())
        assert out["congestion_available"] is True
        assert out["congestion_provider"] == "tomtom"
        u = next(x for x in out["units"] if x["id"] == "45045003701")
        assert u["wk_17"] == pytest.approx(round(u["free_flow_min"] * 2.0, 1), abs=0.11)
        assert u["wk_12"] == pytest.approx(u["free_flow_min"], abs=0.11)
        # A tract with no sample stays null rather than borrowing another's factor.
        others = [x for x in out["units"] if x["id"] != "45045003701"]
        assert others and all(x["wk_17"] is None for x in others)


def test_span_never_claims_a_provider_it_did_not_use():
    if not SPAN.exists():
        pytest.skip("drive span not built; run data-pipeline/build_drive_span.py")
    out = json.loads(SPAN.read_text())
    if not out["congestion_available"]:
        assert out["congestion_provider"] is None
        assert out["congestion_sampled_on"] is None
