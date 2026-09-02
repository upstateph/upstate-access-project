"""A withheld-category address must not sit in tracked source unreviewed.

`check_sensitive_not_shipped` guards `dist/`, which is what the public site
serves. Source is public too, so an address written into a script, a doc or a
comment is disclosed just as thoroughly, past a check that by construction never
looks there. `check_sensitive_addresses_in_source` closes that.

Everything here runs against a fabricated repo in tmp_path. The real seed CSVs
hold candidate addresses for HIV care, reproductive health and substance-use
treatment; no test may read them or reproduce one.

Two design choices these tests pin, both of which are easy to "simplify" away:

- It matches EXACT seed addresses, not keywords. Category words miss the case
  that prompted it, since that file names neither HIV nor Ryan White, and an
  early draft matched `hiv` inside the word `archive`. Address-shaped regex is
  worse: the same building routinely hosts a published FQHC, so 46 of 46 naive
  hits were co-location.
- The allowlist stores a hash of "path|address", never the address. It is a
  public file; listing the addresses would be the leak it prevents.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import weekly_debug as wd                                      # noqa: E402

ADDR = "742 Evergreen Terrace"
NORM = "742 evergreen terrace"
HEADER = ("name,address,city,state,zip,phone,verified_on,verified_by,"
          "verification_method,source_url,date_found,notes\n")


def fake_repo(tmp_path: Path, tracked: dict[str, str], allow: str = "") -> Path:
    """A repo with one candidate address and the given tracked files."""
    seeds = tmp_path / "data-pipeline" / "seeds"
    seeds.mkdir(parents=True)
    (seeds / "candidates-hiv_ryan_white.csv").write_text(
        HEADER + f"A Site,{ADDR},Greenville,SC,29601,,2026-08-01,,,,,\n")
    for rel, text in tracked.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    tools = tmp_path / "tools"
    tools.mkdir(parents=True, exist_ok=True)
    (tools / "allowed_address_exposures.txt").write_text(allow)
    return tmp_path


def run(monkeypatch, repo: Path, tracked: list[str]):
    monkeypatch.setattr(wd, "REPO", repo)
    monkeypatch.setattr(wd, "results", [])
    monkeypatch.setattr(wd, "run", lambda *a, **k: (0, "\n".join(tracked)))
    wd.check_sensitive_addresses_in_source()
    return wd.results[0]


def ident(rel: str) -> str:
    return hashlib.sha256(f"{rel}|{NORM}".encode()).hexdigest()[:12]


def test_an_address_in_a_tracked_script_fails(tmp_path, monkeypatch):
    """The case this exists for: a worked example in a tool, explaining a real
    row, in a public repo."""
    repo = fake_repo(tmp_path, {"tools/drift.py": f'"""Example: {ADDR}."""\n'})
    status, _, detail = run(monkeypatch, repo, ["tools/drift.py"])
    assert status == wd.FAIL
    assert "tools/drift.py:1" in detail


def test_the_report_never_prints_the_address(tmp_path, monkeypatch):
    """Check output reaches terminals, logs and notifications. Naming the
    address in the failure would be the disclosure the check exists to stop."""
    repo = fake_repo(tmp_path, {"tools/drift.py": f"# {ADDR}\n"})
    _, _, detail = run(monkeypatch, repo, ["tools/drift.py"])
    for leak in (ADDR, "Evergreen", "evergreen"):
        assert leak not in detail


def test_an_allowlisted_pair_passes(tmp_path, monkeypatch):
    """Co-location is real and cannot be told from disclosure automatically, so
    a reviewed pair is recorded once and stays quiet after that."""
    rel = "deploy/lite/index.html"
    repo = fake_repo(tmp_path, {rel: f"<p>{ADDR}</p>\n"},
                     allow=f"{ident(rel)}  # published FQHC, same building\n")
    status, _, detail = run(monkeypatch, repo, [rel])
    assert status == wd.OK
    assert "1 known co-locations allowed" in detail


def test_the_allowlist_is_per_file_not_per_address(tmp_path, monkeypatch):
    """Allowing an address in one file must not allow it everywhere. The hash
    covers path and address together for exactly this reason."""
    repo = fake_repo(tmp_path,
                     {"deploy/lite/index.html": ADDR, "tools/drift.py": ADDR},
                     allow=f"{ident('deploy/lite/index.html')}  # reviewed\n")
    status, _, detail = run(monkeypatch, repo,
                            ["deploy/lite/index.html", "tools/drift.py"])
    assert status == wd.FAIL
    assert "tools/drift.py" in detail
    assert "deploy/lite" not in detail


def test_data_directories_are_not_scanned(tmp_path, monkeypatch):
    """Published facility data for LIVE categories legitimately carries these
    addresses; the same building hosts both. Scanning there is all noise."""
    repo = fake_repo(tmp_path, {"data/processed/facilities_fqhc.json": ADDR})
    status, _, _ = run(monkeypatch, repo, ["data/processed/facilities_fqhc.json"])
    assert status == wd.OK


def test_absent_seed_csvs_are_not_a_failure(tmp_path, monkeypatch):
    """seeds/ is gitignored, so a fresh checkout and CI have nothing to match."""
    (tmp_path / "tools").mkdir(parents=True)
    status, _, detail = run(monkeypatch, tmp_path, [])
    assert status == wd.OK
    assert "not present" in detail
