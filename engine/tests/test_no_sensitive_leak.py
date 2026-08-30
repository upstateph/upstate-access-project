"""No withheld sensitive facility may appear in a PUBLIC category.

Found the hard way: METRO TREATMENT OF SOUTH CAROLINA — an opioid treatment
program already sitting on the substance_use verification worksheet — was
published live in the `pharmacy` category. Its NPPES taxonomy reads
"Clinic/Center, Methadone Clinic", which contained none of the words the
sensitive-term list was checking for.

The category-name gate cannot catch this: it asks "is THIS category withheld?",
and pharmacy is not. So the check has to run on the facilities themselves, by
address, against the list of places we already know are sensitive.
"""
from __future__ import annotations

import csv
import re
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CANDIDATES = REPO / "data-pipeline" / "seeds" / "substance_use_candidates.csv"
PROCESSED = REPO / "data" / "processed"

# Categories the public can actually select. substance_use is withheld by design.
# Kept in sync with the manifest deliberately, not derived from it: this test
# exists to catch a category shipping sensitive addresses, and deriving the list
# from the same manifest it is checking would let a new category be added and
# silently exempt itself from the check.
PUBLIC = ["fqhc", "fqhc_dental", "fqhc_behavioral", "hospital", "urgent_care",
          "pharmacy", "gov_social", "food", "dental_private", "dialysis",
          "vision", "hearing", "mental_health"]


def _norm(s: str) -> str:
    return " ".join((s or "").upper().replace(".", "").split())


def _sensitive_addresses() -> set[str]:
    """SAMHSA-sourced rows only — state-licensed treatment facilities.

    Deliberately NOT every candidate. The worksheet also carries NPPES
    addiction-COUNSELLOR listings, and counsellors share office suites with
    ordinary therapists: matching on those flagged eleven mental_health
    practices, including two different tenants of 301 Halton Rd Ste J. A guard
    with eleven false alarms is a guard someone switches off, and then the real
    leak walks through. SAMHSA rows are licensed facilities at their own
    premises, so an exact address match there means something.

    The trade-off is stated rather than hidden: an unlicensed SUD practice
    appearing in a public category would not be caught here. The taxonomy filter
    in fetch_nppes.py is the defense for that; this is the backstop for the case
    that filter provably missed."""
    if not CANDIDATES.exists():
        pytest.skip("substance_use candidate worksheet not generated")
    with CANDIDATES.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(l for l in fh if not l.startswith("#")))
    return {_norm(r["address"]) for r in rows
            if (r.get("address") or "").strip()
            and "SAMHSA" in (r.get("_source") or "")}


def test_the_guard_would_have_caught_the_leak_it_was_written_for():
    """A guard that cannot fail is not a guard. 602 Airport Road is Greenville
    Metro Treatment Center, which was live in the pharmacy category."""
    assert _norm("602 Airport Road") in _sensitive_addresses()


@pytest.mark.parametrize("category", PUBLIC)
def test_public_category_contains_no_known_sensitive_site(category):
    path = PROCESSED / f"facilities_{category}.json"
    if not path.exists():
        pytest.skip(f"{category} not fetched")
    payload = json.loads(path.read_text())
    facs = payload["facilities"] if isinstance(payload, dict) else payload
    sensitive = _sensitive_addresses()

    leaks = [f"{f.get('name')} @ {f.get('address')}"
             for f in facs if _norm(f.get("address", "")) in sensitive]
    assert not leaks, (
        f"{category} publishes {len(leaks)} address(es) that are on the "
        f"substance_use verification worksheet: {leaks}")


def test_nppes_fetch_honors_the_shared_exclusion_list():
    """Both ingest paths must read the same exclusion file.

    seed_facilities.py honored it from the start; fetch_nppes.py did not, so an
    organization deliberately kept out of a category by manual seeding could
    still arrive through a taxonomy query. That is not hypothetical: six
    in-house health-center pharmacies were live in the public pharmacy category,
    and from one address the tool reported the nearest pharmacy at a 0.0-minute
    walk when the nearest usable one was 57 minutes away.

    Asserts the wiring, not the contents. The list itself is gitignored, so a
    content test would pass vacuously on a fresh checkout.
    """
    src = (REPO / "data-pipeline" / "fetch_nppes.py").read_text()
    assert "exclusions.csv" in src, "fetch_nppes.py no longer reads the exclusion list"
    assert "load_exclusions(" in src, "fetch_nppes.py defines no exclusion loader"
    assert re.search(r"exclusions\s*=\s*load_exclusions\(", src), \
        "the exclusion list is loaded but never applied in the fetch loop"
