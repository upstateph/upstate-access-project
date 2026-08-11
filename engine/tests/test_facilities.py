"""Tests for the sensitive-category gate and verification freshness.

These pin the safety-critical behavior: a stigma-sensitive category must never be
servable unless it is explicitly cleared AND its manual verification is current,
and every ambiguous case must fail closed (withhold rather than serve).
"""
import datetime as _dt
import json

import pytest

from engine import facilities as F


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Point the module at a temp processed dir + manifest."""
    processed = tmp_path / "processed"
    processed.mkdir()
    manifest = tmp_path / "categories.json"
    monkeypatch.setattr(F, "PROCESSED_DIR", processed)
    monkeypatch.setattr(F, "MANIFEST", manifest)
    return processed, manifest


def write_manifest(path, key, *, sensitive, public_ready):
    path.write_text(json.dumps({"categories": [
        {"key": key, "sensitive": sensitive, "public_ready": public_ready}]}))


def write_facilities(processed, key, verified_on):
    """verified_on: iso string, None (missing), or a list per facility."""
    dates = verified_on if isinstance(verified_on, list) else [verified_on]
    processed.joinpath(f"facilities_{key}.json").write_text(json.dumps({
        "category": key,
        "facilities": [{"name": f"Site {i}", "lat": 34.8, "lon": -82.4,
                        "verified_on": d} for i, d in enumerate(dates)],
    }))


def days_ago(n):
    return (_dt.date.today() - _dt.timedelta(days=n)).isoformat()


# ── the gate ────────────────────────────────────────────────────────────────
def test_sensitive_category_withheld_even_when_data_exists(sandbox):
    processed, manifest = sandbox
    write_manifest(manifest, "hiv_ryan_white", sensitive=True, public_ready=False)
    write_facilities(processed, "hiv_ryan_white", days_ago(1))
    with pytest.raises(F.CategoryWithheld):
        F.load_facilities("hiv_ryan_white")


def test_withheld_is_raised_before_file_check(sandbox):
    """The response must not reveal whether a seed file exists on disk."""
    _, manifest = sandbox
    write_manifest(manifest, "abortion", sensitive=True, public_ready=False)
    with pytest.raises(F.CategoryWithheld):     # no facilities file at all
        F.load_facilities("abortion")


def test_missing_manifest_still_blocks_sensitive_keys(sandbox):
    """Fail-closed: an unreadable manifest must not open the gate."""
    processed, _ = sandbox                       # manifest never written
    write_facilities(processed, "substance_use", days_ago(1))
    assert F.is_public_ready("substance_use") is False
    assert F.is_public_ready("fqhc") is True     # non-sensitive still works


def test_allow_withheld_permits_local_verification_work(sandbox):
    processed, manifest = sandbox
    write_manifest(manifest, "abortion", sensitive=True, public_ready=False)
    write_facilities(processed, "abortion", days_ago(1))
    assert len(F.load_facilities("abortion", allow_withheld=True)) == 1


# ── verification freshness ──────────────────────────────────────────────────
def test_cleared_and_fresh_category_is_servable(sandbox):
    processed, manifest = sandbox
    write_manifest(manifest, "abortion", sensitive=True, public_ready=True)
    write_facilities(processed, "abortion", days_ago(10))
    assert F.is_public_ready("abortion") is True
    assert len(F.load_facilities("abortion")) == 1


def test_stale_verification_withdraws_a_cleared_category(sandbox):
    processed, manifest = sandbox
    write_manifest(manifest, "abortion", sensitive=True, public_ready=True)
    write_facilities(processed, "abortion", days_ago(F.VERIFICATION_MAX_AGE_DAYS + 1))
    assert F.verification_status("abortion")["stale"] is True
    assert F.is_public_ready("abortion") is False
    with pytest.raises(F.CategoryWithheld):
        F.load_facilities("abortion")


def test_oldest_facility_governs_freshness(sandbox):
    processed, manifest = sandbox
    write_manifest(manifest, "abortion", sensitive=True, public_ready=True)
    write_facilities(processed, "abortion",
                     [days_ago(1), days_ago(F.VERIFICATION_MAX_AGE_DAYS + 5)])
    assert F.is_public_ready("abortion") is False   # one rotten entry withdraws all


@pytest.mark.parametrize("bad", [None, "", "not-a-date", "2026/01/01"])
def test_unusable_dates_count_as_unverified(sandbox, bad):
    processed, manifest = sandbox
    write_manifest(manifest, "abortion", sensitive=True, public_ready=True)
    write_facilities(processed, "abortion", bad)
    st = F.verification_status("abortion")
    assert st["stale"] is True and st["n_verified"] == 0
    assert F.is_public_ready("abortion") is False


def test_future_date_is_not_a_verification(sandbox):
    processed, manifest = sandbox
    write_manifest(manifest, "abortion", sensitive=True, public_ready=True)
    write_facilities(processed, "abortion",
                     (_dt.date.today() + _dt.timedelta(days=3)).isoformat())
    assert F.is_public_ready("abortion") is False


def test_non_sensitive_category_needs_no_verification_dates(sandbox):
    processed, manifest = sandbox
    write_manifest(manifest, "pharmacy", sensitive=False, public_ready=True)
    write_facilities(processed, "pharmacy", None)
    assert F.is_public_ready("pharmacy") is True


def test_no_data_is_not_stale(sandbox):
    processed, _ = sandbox
    st = F.verification_status("abortion")
    assert st["has_data"] is False and st["stale"] is False
