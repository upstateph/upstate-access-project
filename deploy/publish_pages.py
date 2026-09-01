#!/usr/bin/env python3
"""Publish dist/ to the gh-pages branch, which is what upstateph.github.io serves.

    .venv/bin/python deploy/publish_pages.py            # build, publish, verify
    .venv/bin/python deploy/publish_pages.py --dry-run  # everything except push

WHY THIS EXISTS. Pages publishes from the gh-pages branch, so pushing main does
not touch it. Every publish before 2026-09-01 was done by hand, and the site
drifted behind main twice:

  - 14 Aug to 27 Aug. The URL served a build with no address box. A practitioner
    reported the link as broken, two reviewers reviewed the wrong tool, and it
    cost an apology email (outreach letters/practitioner-link-correction.md) and
    the rule that anyone asked to TRY the tool gets the beta link instead.
  - 29 Aug to 1 Sep. The URL served a build with no quick-exit control and no
    Referrer-Policy, while both were live on the beta. Nothing noticed until
    check_live_matches_local was added to tools/weekly_debug.py.

The URL is printed on the community flyer and cited in letters already sent, so
it cannot be retired. The remaining option is to make republishing cost nothing
and to make a bad publish fail loudly instead of silently.

HOW IT WORKS. The working tree is never touched: no checkout, no branch switch,
no stash. dist/ is indexed into a throwaway index file, written as a tree, and
committed with git commit-tree onto origin/gh-pages. That matters because this
repo regularly has more than one session editing it at once, and a publish that
switched branches underneath one of them would be its own kind of incident.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DIST = REPO / "dist"
BRANCH = "gh-pages"
LIVE_URL = "https://upstateph.github.io/upstate-access-project/"

# Markers that are invisible when missing: the page still returns 200 and still
# looks like the tool. Both drift incidents were exactly this. Checked in dist/
# before pushing, then again on the live URL afterwards.
REQUIRED_MARKERS = {
    "quick-exit.js": 'the quick exit control ("quick-exit.js")',
    'content="no-referrer"': "the no-referrer policy",
    'class="skip-link"': "the skip link",
}
SENSITIVE = ("abortion", "reproductive_health", "hiv_ryan_white", "substance_use")


def git(*args: str, env: dict | None = None, check: bool = True) -> str:
    r = subprocess.run(["git", *args], cwd=REPO, env=env, check=False,
                       capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed:\n{r.stderr.strip()}")
    return r.stdout.strip()


def require_clean_source() -> None:
    """What is live must be traceable to a commit.

    publish() stamps the current HEAD sha into the gh-pages commit message. If
    the tree is dirty that sha is a lie: the published bytes correspond to no
    commit anyone can check out. Cheap to enforce, and it is the only thing
    that makes "which build is live?" answerable later.
    """
    dirty = [ln for ln in git("status", "--porcelain").splitlines()
             if ln[3:].startswith(("dashboard/", "deploy/"))]
    if dirty:
        raise SystemExit("REFUSING TO PUBLISH: uncommitted changes in the source "
                         "of dist/:\n  " + "\n  ".join(dirty[:5])
                         + "\n\nCommit them first, so the live site maps to a commit.")


def gate_on_weekly_checks() -> None:
    """Run the real checks against the built bytes, imported rather than restated.

    REQUIRED_MARKERS below is deliberately small because it also has to run
    against a page fetched over HTTP. It is not sufficient as a pre-publish
    gate: every marker it knows lives in the HTML, so it would cheerfully
    publish a build whose live regions had regressed to `hidden`, whose results
    no longer moved focus, or whose .visually-hidden had become display:none.
    None of those appear in the HTML and all of them are silent failures.

    Importing the checks rather than copying them is the point: when a check
    tightens in weekly_debug, publishing tightens with it. A restated copy is
    how the guard and the thing it guards drift apart.
    """
    sys.path.insert(0, str(REPO / "tools"))
    import weekly_debug as wd

    wd.results.clear()
    for fn in (wd.check_sensitive_not_shipped,
               wd.check_protective_infrastructure,
               wd.check_accessibility):
        try:
            fn()
        except Exception as e:                                # noqa: BLE001
            wd.record(wd.FAIL, fn.__name__, f"check crashed: {e}")

    for status, name, detail in wd.results:
        print(f"  [{status:4s}] {name:28s} {detail}")

    fails = [r for r in wd.results if r[0] == wd.FAIL]
    if fails:
        raise SystemExit("REFUSING TO PUBLISH:\n  "
                         + "\n  ".join(f"{n}: {d}" for _, n, d in fails))


def build() -> None:
    """Always rebuild. Publishing a dist/ someone else left on disk is how the
    site drifts, and the two-command version of this script is the version that
    gets half-run."""
    sys.path.insert(0, str(REPO / "deploy"))
    import build_site
    build_site.main()


def check_publishable() -> None:
    """Refuse to publish rather than publish something wrong. build_site.py runs
    the sensitive-data check too; it is repeated here because this is the step
    that makes files public, and a guard on the outward-facing action is worth
    more than a guard on the local one."""
    if not DIST.is_dir():
        raise SystemExit("REFUSING TO PUBLISH: dist/ does not exist.")

    leaked = [p.relative_to(DIST) for p in DIST.rglob("facilities_*.json")
              if any(k in p.name for k in SENSITIVE)]
    if leaked:
        raise SystemExit(f"REFUSING TO PUBLISH: sensitive facility data in dist/: {leaked}")

    pages = sorted(DIST.glob("*.html"))
    if not pages:
        raise SystemExit("REFUSING TO PUBLISH: no HTML in dist/.")
    problems = []
    for page in pages:
        text = page.read_text(encoding="utf-8", errors="replace")
        for marker, why in REQUIRED_MARKERS.items():
            if marker not in text:
                problems.append(f"{page.name} is missing {why}")
    if problems:
        raise SystemExit("REFUSING TO PUBLISH:\n  " + "\n  ".join(problems))
    print(f"  pre-publish check: {len(pages)} pages carry all "
          f"{len(REQUIRED_MARKERS)} protective markers")

    # GitHub Pages runs Jekyll unless told not to, and Jekyll drops files and
    # directories beginning with an underscore. Nothing in dist/ starts with one
    # today; .nojekyll costs one empty file and removes the question.
    (DIST / ".nojekyll").touch()


def write_tree() -> str:
    """Index dist/ into a throwaway index and return the tree sha. dist/ is
    gitignored, hence --force; GIT_WORK_TREE makes the paths land at the root of
    the tree rather than under dist/."""
    with tempfile.TemporaryDirectory() as tmp:
        env = os.environ.copy()
        env["GIT_INDEX_FILE"] = str(Path(tmp) / "index")
        env["GIT_WORK_TREE"] = str(DIST)
        git("read-tree", "--empty", env=env)
        subprocess.run(["git", "add", "--all", "--force", "."],
                       cwd=DIST, env=env, check=True, capture_output=True)
        return git("write-tree", env=env)


def publish(dry_run: bool) -> str | None:
    head = git("rev-parse", "--short", "HEAD")
    subject = git("log", "-1", "--format=%s")
    git("fetch", "--quiet", "origin", BRANCH)
    parent = git("rev-parse", f"origin/{BRANCH}")

    tree = write_tree()
    if tree == git("rev-parse", f"{parent}^{{tree}}"):
        print(f"  nothing to publish: {BRANCH} already serves this exact tree")
        return None

    changed = git("diff", "--stat", f"{parent}^{{tree}}", tree)
    print("  changes vs the published site:")
    for line in changed.splitlines():
        print(f"    {line}")

    if dry_run:
        print(f"  --dry-run: would commit tree {tree[:9]} onto {BRANCH} and push")
        return None

    commit = git("commit-tree", tree, "-p", parent,
                 "-m", f"Publish: {subject} ({head})")
    git("update-ref", f"refs/heads/{BRANCH}", commit)
    git("push", "origin", f"{commit}:refs/heads/{BRANCH}")
    print(f"  pushed {commit[:9]} to {BRANCH}")
    return commit


def verify_live(attempts: int = 10, delay: int = 20) -> bool:
    """Pages takes a minute or so to serve a new commit. A publish that is not
    verified is the same as the two that drifted: it looked done."""
    print(f"  verifying {LIVE_URL} (Pages needs a moment to deploy)")
    for i in range(1, attempts + 1):
        try:
            req = urllib.request.Request(LIVE_URL, headers={"User-Agent": "uap-publish"})
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read().decode("utf-8", "replace")
            missing = [why for marker, why in REQUIRED_MARKERS.items() if marker not in body]
            if not missing:
                print(f"  live and correct: all {len(REQUIRED_MARKERS)} markers present")
                return True
            print(f"    attempt {i}/{attempts}: still missing {', '.join(missing)}")
        except urllib.error.URLError as e:
            print(f"    attempt {i}/{attempts}: {type(e).__name__}")
        if i < attempts:
            time.sleep(delay)
    print("  NOT VERIFIED: the push succeeded but the live URL does not show the "
          "markers yet. Check the repository's Pages settings, then re-run "
          "tools/weekly_debug.py --live.")
    return False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="build and check, show what would change, but do not push")
    ap.add_argument("--no-verify", action="store_true",
                    help="skip the post-push check of the live URL")
    args = ap.parse_args()

    print(f"Publishing dist/ to {BRANCH} ({LIVE_URL})")
    require_clean_source()
    build()
    check_publishable()
    gate_on_weekly_checks()
    commit = publish(args.dry_run)
    if commit and not args.no_verify:
        if not verify_live():
            raise SystemExit(1)


if __name__ == "__main__":
    main()
