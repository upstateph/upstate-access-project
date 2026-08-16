"""The withdrawn crash-corridor claim must not reappear in published copy.

This is a content test rather than a code test, and it earns its place in the
suite: the claim has come back twice, both times because a document was
regenerated wholesale from a stale base, and both times into the email whose
entire purpose is asking physicians to trust the work. A check that depends on
someone remembering to run it had already failed twice by the time this was
written.

`tools/check_withdrawn_claims.py` holds the patterns and the reasoning.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CHECKER = REPO / "tools" / "check_withdrawn_claims.py"


def run_checker(*targets: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CHECKER), *targets],
                          capture_output=True, text=True, cwd=REPO)


def test_public_copy_asserts_no_withdrawn_claim():
    result = run_checker("docs", "dashboard", "README.md")
    assert result.returncode == 0, (
        "A withdrawn claim is asserted in published copy:\n" + result.stdout)


def test_generated_attachments_assert_no_withdrawn_claim():
    """advocacy/ holds the PDF briefs that get attached to partner letters.

    This is separated from the prose check because it is the case that actually
    went wrong: both briefs asserted the withdrawn claim as their lead statistic
    while every markdown scan came back clean, since the claim was generated
    into a binary from the corridor JSON rather than written into any document.
    """
    if not (REPO / "advocacy").is_dir():
        pytest.skip("advocacy/ not present")
    result = run_checker("advocacy")
    assert result.returncode == 0, (
        "A withdrawn claim is asserted in a generated attachment:\n" + result.stdout)


def test_outreach_copy_asserts_no_withdrawn_claim():
    """outreach/ is a separate private repo cloned in place, and is where both
    regressions actually happened — so it is checked even though it is not
    tracked here. Skipped on a fresh checkout that has not cloned it."""
    if not (REPO / "outreach").is_dir():
        pytest.skip("outreach/ not cloned (it is a separate private repo)")
    result = run_checker("outreach")
    assert result.returncode == 0, (
        "A withdrawn claim is asserted in outreach copy:\n" + result.stdout)


def test_checker_catches_the_claim_it_is_meant_to_catch(tmp_path):
    """A guard that cannot fail is not a guard. This replays the exact sentence
    that regressed twice."""
    bad = tmp_path / "draft.md"
    bad.write_text(
        "Some preamble about the project.\n\n"
        "My most quotable claim: 70 of Greenville County's 182 pedestrian deaths\n"
        "since 2014 happened within 150 meters of a modeled walking route to a\n"
        "health center. Which part of that would you challenge first?\n")
    result = run_checker(str(bad))
    assert result.returncode == 1
    assert "70-of-182" in result.stdout


def test_checker_does_not_flag_the_retraction_itself(tmp_path):
    """The retraction has to quote the claim to retract it. Flagging that would
    make the check noisy, and a noisy check gets switched off — which is how the
    claim would come back a third time."""
    ok = tmp_path / "writeup.md"
    ok.write_text(
        "3. **Walking routes to care overlap with where pedestrians die.** 70 of the\n"
        "   county's 182 pedestrian deaths (38.5%) occurred within 150 meters of a\n"
        "   modeled walking route. **This claim has been withdrawn.** A null model\n"
        "   refutes it: a randomly chosen destination captures more deaths (~59%).\n")
    result = run_checker(str(ok))
    assert result.returncode == 0, result.stdout


def test_checker_does_not_flag_pipeline_documentation(tmp_path):
    """"150 m proximity" in a build script's docs describes what the code
    computes; it asserts nothing about the world."""
    ok = tmp_path / "README.md"
    ok.write_text("python build_crash_corridors.py   # walk-route geometries + 150 m proximity\n")
    assert run_checker(str(ok)).returncode == 0
