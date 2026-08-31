#!/usr/bin/env python3
"""One command that answers: is anything about this project broken or stale today?

Written to be run daily and read in ten seconds. Every check is either OK, WARN
(worth knowing, not urgent) or FAIL (something published is wrong right now).

    .venv/bin/python tools/daily_debug.py           # fast, no network
    .venv/bin/python tools/daily_debug.py --live    # also ping the public site

Exit code is 1 if anything FAILs, so it can gate a commit or a cron job.

The checks earn their place from things that have actually gone wrong here:
a withdrawn claim reappearing, a published number drifting from its data, a
spelling sweep silently narrowing a safety guard, a GTFS feed quietly expiring
under a router that keeps answering, and a sensitive category leaking into a
built artifact.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OK, WARN, FAIL = "OK", "WARN", "FAIL"
results: list[tuple[str, str, str]] = []


def record(status: str, name: str, detail: str = "") -> None:
    results.append((status, name, detail))


def run(cmd: list[str], cwd: Path = REPO) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return p.returncode, (p.stdout + p.stderr).strip()


def py() -> str:
    venv = REPO / ".venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable


# ---------------------------------------------------------------- checks

def check_tests() -> None:
    code, out = run([py(), "-m", "pytest", "-q"])
    tail = [l for l in out.splitlines() if "passed" in l or "failed" in l]
    record(OK if code == 0 else FAIL, "test suite", tail[-1] if tail else out[-200:])


def check_claims_guard() -> None:
    code, out = run([py(), "tools/check_withdrawn_claims.py"])
    record(OK if code == 0 else FAIL, "withdrawn-claims guard", out.splitlines()[-1] if out else "")


def check_published_numbers() -> None:
    script = REPO / "tools" / "check_published_numbers.py"
    if not script.exists():
        record(WARN, "published-numbers sweep", "tools/check_published_numbers.py missing")
        return
    code, out = run([py(), str(script)])
    last = [l for l in out.splitlines() if "checks run" in l]
    record(OK if code == 0 else FAIL, "published-numbers sweep",
           last[-1].strip("= ") if last else out[-200:])


def check_gtfs_freshness() -> None:
    """The quiet one. An expired feed does not error; the router just plans trips
    against a dead schedule and keeps answering confidently."""
    try:
        sys.path.insert(0, str(REPO))
        from engine.transit import feed_status
        st = feed_status()
    except Exception as e:                                   # noqa: BLE001
        record(WARN, "GTFS feed", f"could not read feed status: {type(e).__name__}")
        return
    if not st.get("available"):
        record(WARN, "GTFS feed", "no feed on disk; transit answers will be 'not reachable'")
        return
    days = st.get("days_left")
    if st.get("expired"):
        record(FAIL, "GTFS feed", f"EXPIRED: {st.get('reason')}")
    elif days is not None and days < 30:
        record(WARN, "GTFS feed", f"expires in {days} days; refresh soon")
    else:
        record(OK, "GTFS feed", f"{days} days of service left")


def check_sensitive_not_shipped() -> None:
    """No sensitive category may be SERVABLE, and no sensitive facility data may ship.

    Deliberately not a grep for the key names. The `behavioral_health` composite
    publishes `members_withheld: ["substance_use"]` on purpose, so that someone
    searching mental health can see the results exclude substance-use treatment.
    Suppressing that name would make the composite silently incomplete, which is
    a worse failure than naming a category that has no data behind it. The rule
    is about servable categories and facility addresses, not about the word.
    """
    SENS = ["abortion", "reproductive_health", "hiv_ryan_white", "substance_use"]
    dist = REPO / "dist"
    if not dist.exists():
        record(WARN, "sensitive-category leak", "dist/ not built, nothing to check")
        return

    problems = []
    manifest = dist / "data" / "categories.json"
    if manifest.exists():
        cats = json.loads(manifest.read_text())["categories"]
        for c in cats:
            if c.get("key") in SENS:
                problems.append(f"{c['key']} is offered in the menu")
            # A composite must not go live carrying a sensitive member as live.
            for m in c.get("members_live", []):
                if m in SENS:
                    problems.append(f"{c.get('key')} lists {m} as live")

    # No sensitive facility file, and no sensitive facility ADDRESS, in dist/.
    for p in dist.rglob("facilities_*.json"):
        if any(k in p.name for k in SENS):
            problems.append(f"{p.relative_to(dist)} shipped")
    for k in SENS:
        src = REPO / "data" / "processed" / f"facilities_{k}.json"
        if not src.exists():
            continue
        try:
            addrs = {f.get("address", "") for f in json.loads(src.read_text())["facilities"]}
        except Exception:                                     # noqa: BLE001
            continue
        for p in list(dist.rglob("*.json")) + list(dist.rglob("*.js")) + list(dist.rglob("*.html")):
            text = p.read_text(errors="ignore")
            hit = [a for a in addrs if a and len(a) > 8 and a in text]
            if hit:
                problems.append(f"{k} address in {p.relative_to(dist)}")

    record(OK if not problems else FAIL, "sensitive-category leak",
           "no sensitive category servable, no sensitive address shipped"
           if not problems else "; ".join(problems[:3]))


def check_syntax_and_json() -> None:
    code, out = run(["git", "ls-files", "*.py"])
    bad = [f for f in out.split() if subprocess.run(
        [py(), "-m", "py_compile", f], cwd=REPO, capture_output=True).returncode != 0]
    record(OK if not bad else FAIL, "python compiles",
           f"{len(out.split())} files" if not bad else f"broken: {bad[:3]}")

    code, out = run(["git", "ls-files", "*.json"])
    bad = []
    for f in out.split():
        try:
            json.loads((REPO / f).read_text())
        except Exception:                                     # noqa: BLE001
            bad.append(f)
    record(OK if not bad else FAIL, "json parses",
           f"{len(out.split())} files" if not bad else f"broken: {bad[:3]}")


def check_links() -> None:
    dist = REPO / "dist"
    if not dist.exists():
        record(WARN, "internal links", "dist/ not built")
        return
    missing = []
    for html in dist.rglob("*.html"):
        for m in re.findall(r'(?:href|src)="([^"#?:]+)"', html.read_text(errors="ignore")):
            if m.startswith(("http", "//", "data:", "mailto:")):
                continue
            if not (html.parent / m).resolve().exists():
                missing.append(f"{html.name} -> {m}")
    record(OK if not missing else FAIL, "internal links",
           "no broken links" if not missing else "; ".join(missing[:3]))


def check_em_dashes() -> None:
    """House rule: no em dashes in authored docs."""
    code, out = run(["git", "ls-files", "*.md"])
    hits = []
    for f in out.split():
        if f.startswith(("archive/", "outreach/")):
            continue
        n = (REPO / f).read_text(errors="ignore").count("—")
        if n:
            hits.append(f"{f} ({n})")
    record(OK if not hits else WARN, "no em dashes in docs",
           "clean" if not hits else "; ".join(hits[:3]))


def check_dist_current() -> None:
    """A built site older than the sources it came from is a stale deploy."""
    dist = REPO / "dist"
    if not dist.exists():
        record(WARN, "dist/ freshness", "not built")
        return
    newest_src = max((p.stat().st_mtime for p in (REPO / "dashboard").rglob("*")
                      if p.is_file()), default=0)
    newest_dist = max((p.stat().st_mtime for p in dist.rglob("*") if p.is_file()), default=0)
    record(OK if newest_dist >= newest_src else WARN, "dist/ freshness",
           "current" if newest_dist >= newest_src
           else "dashboard/ is newer than dist/; run deploy/build_site.py")


def check_live_site() -> None:
    """All five partner letters point at the beta. If it is down, they are dead links."""
    for label, url in [("beta (Render)", "https://upstate-access-beta.onrender.com/"),
                       ("Pages fallback",
                        "https://upstateph.github.io/upstate-access-project/")]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "uap-daily-debug"})
            with urllib.request.urlopen(req, timeout=90) as r:
                code = r.status
            record(OK if code == 200 else FAIL, label, f"HTTP {code}")
        except Exception as e:                                # noqa: BLE001
            record(FAIL, label, f"{type(e).__name__}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true",
                    help="also check the public URLs (slow: the beta cold-starts)")
    args = ap.parse_args()

    print(f"Upstate Access Project, daily debug, {date.today().isoformat()}")
    print("=" * 62)

    for fn in (check_tests, check_claims_guard, check_published_numbers,
               check_gtfs_freshness, check_sensitive_not_shipped,
               check_syntax_and_json, check_links, check_em_dashes,
               check_dist_current):
        try:
            fn()
        except Exception as e:                                # noqa: BLE001
            record(FAIL, fn.__name__, f"check itself crashed: {type(e).__name__}: {e}")
    if args.live:
        check_live_site()

    for status, name, detail in results:
        mark = {OK: "  ok  ", WARN: " WARN ", FAIL: " FAIL "}[status]
        print(f"[{mark}] {name:26s} {detail}")

    fails = [r for r in results if r[0] == FAIL]
    warns = [r for r in results if r[0] == WARN]
    print("=" * 62)
    print(f"{len(results)} checks: {len(results)-len(fails)-len(warns)} ok, "
          f"{len(warns)} warn, {len(fails)} fail")
    if fails:
        print("\nNeeds attention today:")
        for _, name, detail in fails:
            print(f"  - {name}: {detail}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
