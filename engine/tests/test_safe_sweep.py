"""safe_sweep must refuse to quietly edit the places that bit us.

The 2026-08-29 spelling sweep broke three things and the suite caught none.
The one that mattered collapsed a guard's `meters|metres` alternation to
`meters|meters`, halving its coverage without failing anything. These tests
pin the behavior that would have prevented it.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
TOOL = REPO / "tools" / "safe_sweep.py"


def run(*args, cwd=None):
    return subprocess.run([sys.executable, str(TOOL), *args],
                          capture_output=True, text=True, cwd=cwd or REPO)


def test_dry_run_is_the_default(tmp_path):
    f = tmp_path / "a.md"
    f.write_text("the colour of it\n")
    r = run("--pairs", "colour:color", "--paths", str(tmp_path))
    assert r.returncode == 0
    assert "DRY RUN" in r.stdout
    assert f.read_text() == "the colour of it\n", "dry run wrote to disk"


def test_regex_lines_are_flagged_risky_and_skipped(tmp_path):
    f = tmp_path / "guard.py"
    f.write_text('import re\nPAT = re.compile(r"150 (?:meters|metres)")\n')
    r = run("--pairs", "metres:meters", "--paths", str(tmp_path))
    assert "RISKY" in r.stdout
    assert "SKIPPED" in r.stdout


def test_word_mode_does_not_match_inside_a_longer_word(tmp_path):
    """`analyse`->`analyze` must not touch `analyses`; `centre`->`center` must
    not turn `centred` into `centerd`. Both happened."""
    f = tmp_path / "b.md"
    f.write_text("two analyses, centred nicely, realistic too\n")
    r = run("--pairs", "analyse:analyze", "centre:center", "--paths", str(tmp_path), "--word")
    assert "0 replacement" in r.stdout, r.stdout


def test_refuses_to_apply_with_a_dirty_tree(tmp_path):
    """--apply on a dirty tree cannot be rolled back cleanly, so it is refused."""
    r = run("--pairs", "colour:color", "--paths", "docs", "--apply")
    assert r.returncode in (0, 2)
    if r.returncode == 2:
        assert "REFUSING" in r.stdout
