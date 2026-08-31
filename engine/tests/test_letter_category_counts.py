"""The letters must not keep asserting a live-category count the site outgrew.

This one exists because it already happened. On 31 Aug 2026 seven categories
went live in a single day, taking the count from 11 to 18, and the send packet
went on saying "Eleven service types are live" in a letter that had already been
emailed. Nothing caught it: outreach/ is a separate private repo, so it is
excluded from the published-numbers sweep and from every other check in
tools/weekly_debug.py by design.

The check is deliberately narrow, and the narrowing is what needs guarding, so
these tests run the matcher over synthetic sentences rather than over the real
letters. outreach/ is gitignored and absent on a fresh checkout, and no test
should depend on private content or reproduce it.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

import weekly_debug as wd                                      # noqa: E402


def claimed(text: str) -> list[int]:
    """Every live-category count the checker would read out of `text`."""
    flat = wd._QUOTED.sub(lambda m: " " * len(m.group()), text).replace("\n", " ")
    found = []
    for m in wd.COUNT_CLAIM.finditer(flat):
        if not (m.group(2) or wd.LIVE_CUE.match(flat[m.end():])):
            continue
        raw = m.group(1).lower()
        found.append(int(raw) if raw.isdigit() else wd.WORD_NUMBERS[raw])
    return found


def test_reads_a_spelled_out_count():
    """The register letters actually use. Digits alone would miss most claims."""
    assert claimed("Eighteen service types are live.") == [18]


def test_reads_a_digit_count_and_an_adjective_form():
    assert claimed("18 categories are live.") == [18]
    assert claimed("The tool now has 18 live categories.") == [18]


def test_reads_a_claim_split_across_a_hard_wrap():
    """The packet is hard-wrapped, so the number and the proof of liveness
    routinely sit on different lines. This is the case the first draft missed."""
    assert claimed("letters now name the 18 categories\nthat ARE live, verified"
                   " against dist/data/categories.json.") == [18]


def test_ignores_the_withheld_category_count():
    """The withheld three (HIV care, reproductive health, substance use) are a
    true and entirely different claim. Flagging them would train Nikhil to
    ignore this check, and the withheld count must never be 'corrected' upward
    to match the live one."""
    assert claimed("There are three categories I've built and won't publish. "
                   "HIV care, reproductive health, substance use.") == []


def test_ignores_a_quoted_record_of_what_an_old_letter_said():
    """The packet quotes already-sent wording so the send record survives a
    correction. A quote is a record, not a live claim."""
    assert claimed('ACOG went out on 30 Aug reading "Eleven service types are '
                   'live" and cannot be corrected retroactively.') == []


def test_ignores_a_bare_count_with_no_liveness_cue():
    assert claimed("he lands somewhere with 11 categories. If he ever clicks") == []
    assert claimed("taking the live count from 11 to 18. ACOG went out") == []


def test_a_stale_count_is_reported_with_its_line_number(tmp_path, monkeypatch):
    """End to end: a letter that fell behind the site is named, with a line
    number, and without any of its prose in the message."""
    outreach = tmp_path / "outreach" / "letters"
    outreach.mkdir(parents=True)
    (outreach / "packet.md").write_text(
        "Dear team,\n\nfiller line\nEleven service types are live.\n")
    monkeypatch.setattr(wd, "REPO", tmp_path)
    monkeypatch.setattr(wd, "live_category_count", lambda: 18)
    monkeypatch.setattr(wd, "results", [])

    wd.check_letter_category_counts()
    status, _, detail = wd.results[0]

    assert status == wd.WARN
    assert "outreach/letters/packet.md:4 says 11" in detail
    assert "18 categories are live" in detail
    assert "service types" not in detail          # no letter prose in the report


def test_absent_outreach_clone_is_not_a_failure(tmp_path, monkeypatch):
    """outreach/ is gitignored, so a fresh checkout simply has nothing to check."""
    monkeypatch.setattr(wd, "REPO", tmp_path)
    monkeypatch.setattr(wd, "results", [])

    wd.check_letter_category_counts()

    assert wd.results[0][0] == wd.OK
