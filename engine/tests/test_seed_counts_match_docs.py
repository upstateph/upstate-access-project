"""Documents must not assert a withheld-category count the seed CSVs contradict.

This guards `check_seed_counts_match_docs` in tools/weekly_debug.py, which
exists for a class of defect that produced seven bugs on this project in two
days and never once failed anything: a number written into prose that stopped
tracking the thing it counted.

The one it is named for: NEXT-STEPS.md claimed "2 of 20+" seed rows verified
when docs/sensitive-categories-status.md had it at 2 of 50, and both files were
internally consistent. That is why the check compares documents against the CSVs
rather than against each other. Two documents can agree and both be wrong.

Everything here runs against a fabricated repo in tmp_path. The real seed CSVs
hold candidate addresses for HIV care, reproductive health and substance-use
treatment; they are gitignored, and no test may read them, reproduce them, or
depend on their contents.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import weekly_debug as wd                                      # noqa: E402

HEADER = ("name,address,city,state,zip,phone,verified_on,verified_by,"
          "verification_method,source_url,date_found,notes\n")


def fake_repo(tmp_path: Path, seeds: dict[str, list[bool]], doc: str) -> Path:
    """A repo whose seed CSVs say `seeds` and whose status doc says `doc`.

    seeds maps category to a list of rows, each True if that row is verified.
    Row content is filler: the check counts rows and reads verified_on only.
    """
    names = {"hiv_ryan_white": "candidates-hiv_ryan_white.csv",
             "reproductive_health": "candidates-reproductive_health.csv",
             "substance_use": "substance_use_candidates.csv"}
    d = tmp_path / "data-pipeline" / "seeds"
    d.mkdir(parents=True)
    for cat, rows in seeds.items():
        lines = [HEADER]
        for i, verified in enumerate(rows):
            on = "2026-08-01" if verified else ""
            lines.append(f"row{i},1 Test St,Greenville,SC,29601,,{on},,,,,\n")
        (d / names[cat]).write_text("".join(lines))
    docs = tmp_path / "docs"
    docs.mkdir(parents=True)
    (docs / "sensitive-categories-status.md").write_text(doc)
    return tmp_path


def table(rows: dict[str, tuple[int, int]], sentence: str = "") -> str:
    body = "\n".join(f"| `{k}` | {c} | {v} | no |" for k, (c, v) in rows.items())
    return f"| Category | Candidates | Verified | Live? |\n|---|---|---|---|\n{body}\n\n{sentence}\n"


def run(monkeypatch, repo: Path):
    monkeypatch.setattr(wd, "REPO", repo)
    monkeypatch.setattr(wd, "results", [])
    wd.check_seed_counts_match_docs()
    return wd.results[0]


def test_agreeing_counts_pass(tmp_path, monkeypatch):
    repo = fake_repo(
        tmp_path,
        {"hiv_ryan_white": [True, True, False], "reproductive_health": [False] * 6,
         "substance_use": [False] * 41},
        table({"hiv_ryan_white": (3, 2), "reproductive_health": (6, 0),
               "substance_use": (41, 0), "abortion": (0, 0)}),
    )
    status, _, detail = run(monkeypatch, repo)
    assert status == wd.OK
    assert "48 of 50" in detail


def test_a_verified_count_that_drifted_fails(tmp_path, monkeypatch):
    """The doc claims a human checked an address that no CSV row records."""
    repo = fake_repo(
        tmp_path,
        {"hiv_ryan_white": [True, False, False], "reproductive_health": [],
         "substance_use": []},
        table({"hiv_ryan_white": (3, 2), "reproductive_health": (0, 0),
               "substance_use": (0, 0), "abortion": (0, 0)}),
    )
    status, _, detail = run(monkeypatch, repo)
    assert status == wd.FAIL
    assert "doc says 3/2, seeds have 3/1" in detail


def test_the_next_steps_bug_is_caught(tmp_path, monkeypatch):
    """The exact historical defect: a derived sentence far below the real total.

    The table is right and only the prose sentence is wrong, which is what makes
    this one survive a reading: the numbers above it check out.
    """
    repo = fake_repo(
        tmp_path,
        {"hiv_ryan_white": [True, True, False], "reproductive_health": [False] * 6,
         "substance_use": [False] * 41},
        table({"hiv_ryan_white": (3, 2), "reproductive_health": (6, 0),
               "substance_use": (41, 0), "abortion": (0, 0)},
              "**2 of 20 candidate addresses have never been checked by a person.**"),
    )
    status, _, detail = run(monkeypatch, repo)
    assert status == wd.FAIL
    assert "says 2 of 20 unverified, seeds have 48 of 50" in detail


def test_a_missing_category_row_fails(tmp_path, monkeypatch):
    """A category dropped from the table reads as "not a concern" rather than
    "nobody wrote it down", which is the more dangerous of the two."""
    repo = fake_repo(
        tmp_path,
        {"hiv_ryan_white": [], "reproductive_health": [], "substance_use": []},
        table({"hiv_ryan_white": (0, 0), "reproductive_health": (0, 0),
               "substance_use": (0, 0)}),
    )
    status, _, detail = run(monkeypatch, repo)
    assert status == wd.FAIL
    assert "abortion has no row" in detail


def test_absent_seed_csvs_are_not_a_failure(tmp_path, monkeypatch):
    """seeds/ is gitignored, so a fresh checkout and CI have nothing to compare.
    Same choice the letter-count check makes for an absent outreach/ clone."""
    docs = tmp_path / "docs"
    docs.mkdir(parents=True)
    (docs / "sensitive-categories-status.md").write_text(table({"abortion": (0, 0)}))
    status, _, detail = run(monkeypatch, tmp_path)
    assert status == wd.OK
    assert "not present" in detail


def test_the_report_never_carries_a_row_or_an_address(tmp_path, monkeypatch):
    """Check output reaches terminals, logs and notifications. The seed CSVs hold
    candidate addresses for three stigma-sensitive categories, so a failure
    message that quoted one would be the leak the categories are withheld to
    prevent."""
    repo = fake_repo(
        tmp_path,
        {"hiv_ryan_white": [True], "reproductive_health": [], "substance_use": []},
        table({"hiv_ryan_white": (9, 9), "reproductive_health": (0, 0),
               "substance_use": (0, 0), "abortion": (0, 0)}),
    )
    status, name, detail = run(monkeypatch, repo)
    assert status == wd.FAIL
    for leak in ("1 Test St", "Greenville", "29601", "row0"):
        assert leak not in detail, f"check output leaked {leak!r}"
    assert name == "seed counts vs docs"
