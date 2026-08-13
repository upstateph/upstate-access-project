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


# ── Composite categories ──────────────────────────────────────────────────────
# "Mental & behavioral health" is one menu option backed by two files: an ungated
# mental_health list and the gated substance_use list. The point of the split is
# that a person never has to pick a stigmatizing label off a dropdown, WITHOUT
# that convenience becoming a way for unverified sensitive addresses to ship.

def write_composite_manifest(path, entries):
    """entries: list of dicts already shaped like manifest rows."""
    path.write_text(json.dumps({"categories": entries}))


COMPOSITE = {"key": "behavioral_health", "sensitive": False, "public_ready": True,
             "members": ["mental_health", "substance_use"]}


def test_composite_serves_only_cleared_members(sandbox):
    """The whole reason the files stay separate: a withheld member must not ride
    along on a cleared one."""
    processed, manifest = sandbox
    write_composite_manifest(manifest, [
        COMPOSITE,
        {"key": "mental_health", "sensitive": False, "public_ready": True},
        {"key": "substance_use", "sensitive": True, "public_ready": False},
    ])
    write_facilities(processed, "mental_health", None)
    write_facilities(processed, "substance_use", None)

    got = F.load_facilities("behavioral_health")
    assert len(got) == 1                      # mental_health only
    assert all(f["name"] == "Site 0" for f in got)
    with pytest.raises(F.CategoryWithheld):   # and not reachable directly either
        F.load_facilities("substance_use")


def test_composite_includes_member_once_verified(sandbox):
    processed, manifest = sandbox
    write_composite_manifest(manifest, [
        COMPOSITE,
        {"key": "mental_health", "sensitive": False, "public_ready": True},
        {"key": "substance_use", "sensitive": True, "public_ready": True},
    ])
    write_facilities(processed, "mental_health", None)
    write_facilities(processed, "substance_use", _dt.date.today().isoformat())
    assert len(F.load_facilities("behavioral_health")) == 2


def test_composite_drops_member_whose_verification_went_stale(sandbox):
    """Expiry has to reach through the composite. Otherwise wrapping a sensitive
    category in a composite would quietly buy it an indefinite exemption."""
    processed, manifest = sandbox
    write_composite_manifest(manifest, [
        COMPOSITE,
        {"key": "mental_health", "sensitive": False, "public_ready": True},
        {"key": "substance_use", "sensitive": True, "public_ready": True},
    ])
    write_facilities(processed, "mental_health", None)
    old = (_dt.date.today() - _dt.timedelta(days=F.VERIFICATION_MAX_AGE_DAYS + 1)).isoformat()
    write_facilities(processed, "substance_use", old)
    assert len(F.load_facilities("behavioral_health")) == 1


def test_composite_with_no_cleared_members_is_withheld(sandbox):
    processed, manifest = sandbox
    write_composite_manifest(manifest, [
        COMPOSITE,
        {"key": "mental_health", "sensitive": False, "public_ready": False},
        {"key": "substance_use", "sensitive": True, "public_ready": False},
    ])
    write_facilities(processed, "substance_use", None)
    assert F.is_public_ready("behavioral_health") is False
    with pytest.raises(F.CategoryWithheld):
        F.load_facilities("behavioral_health")


# ── Servable destinations ─────────────────────────────────────────────────────
# A record can be real and still be a wrong answer to "how long to get there".

def write_sites(processed, key, sites):
    processed.joinpath(f"facilities_{key}.json").write_text(
        json.dumps({"category": key, "facilities": sites}))


def test_non_routable_sites_are_never_destinations(sandbox):
    """HRSA lists every mobile unit at its dispatch base, so routing to one
    reports travel time to an administrative office."""
    processed, manifest = sandbox
    write_manifest(manifest, "fqhc", sensitive=False, public_ready=True)
    write_sites(processed, "fqhc", [
        {"name": "Clinic", "routable": True, "service_lines": ["primary_care"]},
        {"name": "Mobile Van", "routable": False, "mobile": True,
         "service_lines": ["primary_care"]},
    ])
    got = F.load_facilities("fqhc")
    assert [f["name"] for f in got] == ["Clinic"]


def test_service_line_requirement_excludes_specialty_sites(sandbox):
    """A dental-only site must not answer "nearest community health center"."""
    processed, manifest = sandbox
    manifest.write_text(json.dumps({"categories": [
        {"key": "fqhc", "sensitive": False, "public_ready": True,
         "require_service_line": "primary_care"}]}))
    write_sites(processed, "fqhc", [
        {"name": "Medical", "service_lines": ["primary_care"]},
        {"name": "Dental only", "service_lines": ["dental"]},
    ])
    assert [f["name"] for f in F.load_facilities("fqhc")] == ["Medical"]


def test_records_without_service_lines_are_kept(sandbox):
    """Older files predate the field; a schema change must not empty a category."""
    processed, manifest = sandbox
    manifest.write_text(json.dumps({"categories": [
        {"key": "fqhc", "sensitive": False, "public_ready": True,
         "require_service_line": "primary_care"}]}))
    write_sites(processed, "fqhc", [{"name": "Legacy site"}])
    assert [f["name"] for f in F.load_facilities("fqhc")] == ["Legacy site"]
