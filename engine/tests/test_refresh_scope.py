"""The nightly refresh must never re-run a fetcher that erases phone calls.

Several facility files carry fields that no fetcher produces. They are written by
hand after somebody rang the place and asked: hours_provenance,
hours_verified_on, verified_by, verification_note, service_lines_verified_on.
Re-running the fetcher rebuilds the file from the upstream registry and those
fields are gone, with no error and no diff anybody would notice in a green run.

Demonstrated 5 Sep 2026 by doing it. Re-running fetch_hrsa_fqhc.py returned the
same 11 FQHC sites, nothing added and nothing removed, and dropped phone_verified
hours from five of them, all verified 2026-08-24. Reverted immediately.

This is the part of the project no other tool has. An automated refresh that
quietly erased it would look exactly like a clean night, which is why it gets a
test rather than a comment.

If you need one of these refreshed: run it by hand and re-apply the verified
fields, or teach the fetcher to preserve them, and only then change this list.
"""
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "refresh-data.yml"
PROCESSED = REPO / "data" / "processed"

VERIFICATION_FIELDS = {
    "hours_provenance", "hours_verified_on", "verified_by", "verified_on",
    "verification_method", "verification_note", "service_lines_verified_on",
}

pytestmark = pytest.mark.skipif(not WORKFLOW.exists(), reason="workflow not present")


def _files_carrying_verification():
    out = {}
    for f in sorted(PROCESSED.glob("facilities_*.json")):
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        found = {k for row in d.get("facilities", []) for k in row
                 if k in VERIFICATION_FIELDS}
        if found:
            out[f.stem[len("facilities_"):]] = sorted(found)
    return out


# The fetcher that rebuilds each protected category from upstream.
PROTECTED_FETCHERS = {
    "fqhc": "fetch_hrsa_fqhc.py",
    "fqhc_dental": "fetch_hrsa_fqhc.py",
    "fqhc_behavioral": "fetch_hrsa_fqhc.py",
    "free_clinic": "fetch_free_clinics.py",
    "wic": "fetch_dph_clinics.py",
    "health_department": "fetch_dph_clinics.py",
    "community_mental_health": "fetch_community_mental_health.py",
}


def test_verification_carrying_fetchers_are_not_automated():
    wf = WORKFLOW.read_text()
    runs = set(re.findall(r"python data-pipeline/(fetch_[a-z_]+\.py)", wf))
    offenders = sorted({s for cat, s in PROTECTED_FETCHERS.items() if s in runs})
    assert not offenders, (
        "the nightly refresh runs " + ", ".join(offenders) + ", which rebuilds a "
        "facility file from upstream and erases the phone-verified fields on it. "
        "See this module's docstring; it was measured, not theorised."
    )


def test_the_protected_list_still_matches_the_data():
    """If a new category starts carrying verified fields, protect it too."""
    carrying = _files_carrying_verification()
    # address_contested is computed by the fetcher, so it survives a refetch.
    unlisted = sorted(set(carrying) - set(PROTECTED_FETCHERS))
    assert not unlisted, (
        "these categories now carry hand-verified fields but are not in "
        f"PROTECTED_FETCHERS: {unlisted}. Add them, with the fetcher that would "
        "overwrite them, or the nightly job may start erasing phone calls."
    )
