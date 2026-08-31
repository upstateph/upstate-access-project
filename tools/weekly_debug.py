#!/usr/bin/env python3
"""One command that answers: is anything about this project broken, stale or wrong?

Written to be run weekly and read in a minute. Every check is either OK, WARN
(worth knowing, not urgent) or FAIL (something published is wrong right now).

    .venv/bin/python tools/daily_debug.py           # fast, no network
    .venv/bin/python tools/daily_debug.py --live    # + public URLs and upstream sources

Exit code is 1 if anything FAILs, so it can gate a commit or a scheduled run.

The checks earn their place from things that have actually gone wrong here:
a withdrawn claim reappearing, a published number drifting from its data, a
spelling sweep silently narrowing a safety guard, a GTFS feed quietly expiring
under a router that keeps answering, and a sensitive category leaking into a
built artifact.
"""
from __future__ import annotations

import argparse
import bisect
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


# ---------------------------------------------- factual accuracy

# Every model parameter the prose describes, paired with where it lives.
# If someone tunes a constant, the docs silently become false; this catches it.
MODEL_CLAIMS = [
    ("engine.transit", "MAX_WAIT_MIN", 30.0,
     "docs say a 30-minute cap on any single wait"),
    ("engine.transit", "MAX_ROUNDS", 2,
     "docs say at most one transfer (2 rides)"),
    ("engine.transit", "WINDOW_MINUTES", 60,
     "docs say the median across an hour"),
    ("engine.transit", "WINDOW_STEP_MINUTES", 10,
     "docs say departures sampled every 10 minutes"),
    ("engine.transit", "DEFAULT_DEPART", "12:00:00",
     "docs say weekday midday"),
    ("engine.housing", "WALK_CAP_MIN", 20.0,
     "the housing page and proposal both say a 20-minute walk"),
]


def check_model_matches_prose() -> None:
    """The docs describe the model in words. Words do not track code changes."""
    import importlib
    sys.path.insert(0, str(REPO))
    wrong = []
    for mod, name, expected, why in MODEL_CLAIMS:
        try:
            actual = getattr(importlib.import_module(mod), name)
        except Exception as e:                                # noqa: BLE001
            wrong.append(f"{mod}.{name} unreadable ({type(e).__name__})")
            continue
        if actual != expected:
            wrong.append(f"{name}={actual} but {why}")
    record(OK if not wrong else FAIL, "model matches the prose",
           f"{len(MODEL_CLAIMS)} parameters" if not wrong else "; ".join(wrong[:3]))


def check_data_vintage_claims() -> None:
    """Docs cite an ACS vintage and a GTFS window. Both are stated, so both can rot."""
    problems = []
    acs = REPO / "data" / "processed" / "census_acs_tracts_45045.json"
    if acs.exists():
        vintage = json.loads(acs.read_text()).get("vintage")
        cited = set()
        for f in list((REPO / "docs").glob("*.md")) + [REPO / "README.md"]:
            cited |= set(re.findall(r"ACS\s+(\d{4})", f.read_text(errors="ignore")))
        bad = [c for c in cited if c != str(vintage)]
        if bad:
            problems.append(f"docs cite ACS {sorted(bad)}, data is {vintage}")
    record(OK if not problems else FAIL, "data vintage claims",
           "docs match the data" if not problems else "; ".join(problems))


def check_verification_freshness() -> None:
    """Sensitive categories publish nothing until every address is phone-verified."""
    try:
        sys.path.insert(0, str(REPO))
        from engine.facilities import available_categories, is_public_ready
    except Exception as e:                                    # noqa: BLE001
        record(WARN, "verification freshness", f"{type(e).__name__}")
        return
    SENS = ["abortion", "reproductive_health", "hiv_ryan_white", "substance_use"]
    live = set(available_categories())
    leaked = [k for k in SENS if k in live or is_public_ready(k)]
    record(OK if not leaked else FAIL, "verification freshness",
           "all stigma-sensitive categories still withheld"
           if not leaked else f"now public without verification: {leaked}")


def check_external_links() -> None:
    """Every URL a reader is actually invited to click.

    Only markdown links and href/src attributes count. A bare URL sitting in
    backticks in docs/data-sources.md is an endpoint being *documented*, not a
    link being offered, and several are documented precisely because they fail:
    one is a template with {YEAR} placeholders, one is annotated "(405)" because
    recording the failure is the point, and one is named only to say it is
    car-only. Checking those reports the docs back to themselves and trains the
    reader to skip this line.
    """
    urls = set()
    for f in (list((REPO / "docs").glob("*.md")) + [REPO / "README.md"]
              + list((REPO / "dashboard").glob("*.html"))):
        text = f.read_text(errors="ignore")
        urls |= set(re.findall(r"\]\((https://[^\s\)]+)\)", text))       # [text](url)
        urls |= set(re.findall(r'(?:href|src)="(https://[^"]+)"', text))  # href/src
    urls = {u.rstrip(".,;:`\'\"*)>") for u in urls}
    urls = {u for u in urls if "{" not in u and "}" not in u}
    dead = []
    for u in sorted(urls):
        status = None
        for method in ("HEAD", "GET"):
            # Plenty of servers refuse HEAD with 403/405 while serving GET fine,
            # so a HEAD failure is a reason to retry, not a verdict.
            try:
                req = urllib.request.Request(
                    u, method=method, headers={"User-Agent": "uap-weekly-debug"})
                with urllib.request.urlopen(req, timeout=45) as r:
                    status = r.status
                break
            except Exception as e:                            # noqa: BLE001
                status = getattr(e, "code", None) or type(e).__name__
        if status != 200:
            dead.append(f"{u} -> {status}")
    record(OK if not dead else WARN, "external links",
           f"{len(urls)} clickable URLs reachable" if not dead else "; ".join(dead[:3]))


def check_upstream_source_drift() -> None:
    """Has the world moved under a published count?

    The grocery figures come from a live USDA service. If the county's retailer
    list changes, "106 grocery stores" and "443 SNAP retailers" become wrong in
    the proposal, on the site, and in the partner letter citing it. Weekly is
    the right cadence for this: too slow to matter daily, too consequential to
    never check.
    """
    SERVICE = ("https://services1.arcgis.com/RLQu0rK7h4kbsBq5/arcgis/rest/services/"
               "snap_retailer_location_data/FeatureServer/0/query"
               "?where=State%3D%27SC%27+AND+County%3D%27GREENVILLE%27"
               "&outFields=Store_Type&returnGeometry=false&resultRecordCount=2000&f=json")
    GROCERY_TYPES = {"Supermarket", "Super Store", "Grocery Store"}
    local = REPO / "data" / "processed" / "facilities_grocery.json"
    if not local.exists():
        record(WARN, "USDA source drift", "no local grocery file to compare")
        return
    have = len(json.loads(local.read_text())["facilities"])
    try:
        req = urllib.request.Request(SERVICE, headers={"User-Agent": "uap-weekly-debug"})
        with urllib.request.urlopen(req, timeout=90) as r:
            rows = json.loads(r.read().decode())["features"]
    except Exception as e:                                    # noqa: BLE001
        record(WARN, "USDA source drift", f"could not reach USDA: {type(e).__name__}")
        return
    total = len(rows)
    now = sum(1 for f in rows if (f["attributes"].get("Store_Type") or "") in GROCERY_TYPES)
    if now == have:
        record(OK, "USDA source drift", f"{now} grocery of {total} SNAP retailers, unchanged")
    else:
        record(WARN, "USDA source drift",
               f"USDA now has {now} grocery of {total}; local data says {have}. "
               f"Re-run fetch_snap_grocery.py and build_housing_access.py, then update "
               f"the proposal and housing-access.html")


# Letters spell these counts out in words far more often than they use digits,
# so a digits-only pattern would miss most of the claims worth catching.
_WORDS = ("zero one two three four five six seven eight nine ten eleven twelve "
          "thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty "
          "twenty-one twenty-two twenty-three twenty-four twenty-five twenty-six "
          "twenty-seven twenty-eight twenty-nine thirty").split()
WORD_NUMBERS = {w: i for i, w in enumerate(_WORDS)}

# Longest alternatives first, or "twenty" swallows the "-one" of "twenty-one".
_NUMBER = "|".join([r"[0-9]{1,2}"] + sorted(_WORDS, key=len, reverse=True))
COUNT_CLAIM = re.compile(
    r"\b(" + _NUMBER + r")\s+(live\s+|published\s+)?"
    r"(?:categor(?:y|ies)|service\s+types?)\b", re.IGNORECASE)

# A bare "three categories" is usually the withheld ones (HIV care, reproductive
# health, substance use), which is a true and entirely different claim. Only a
# count asserted to be LIVE is comparable to the built site, so either the number
# carries a "live"/"published" adjective or the same sentence has to say it is
# live. [^.] keeps that search inside the sentence, so "three categories I've
# built and won't publish" cannot borrow a later sentence's "are live".
LIVE_CUE = re.compile(r"^[^.]{0,60}?\b(?:are|is|now|remain|stay|going)\s+live\b",
                      re.IGNORECASE)

_QUOTED = re.compile(r"\"[^\"]*\"|\u201c[^\u201d]*\u201d")


def live_category_count() -> int | None:
    """How many categories a visitor can actually pick on the built site."""
    f = REPO / "dist" / "data" / "categories.json"
    if not f.exists():
        return None
    try:
        cats = json.loads(f.read_text())["categories"]
    except Exception:                                         # noqa: BLE001
        return None
    return sum(1 for c in cats
               if c.get("available") and not c.get("hidden") and c.get("public_ready"))


def check_letter_category_counts() -> None:
    """Do the letters still state the right number of live categories?

    This is the one gap the published-numbers sweep cannot close. outreach/ is a
    separate private repo naming real people, so it is excluded from every other
    check here, which means a letter can keep asserting an outdated count for as
    long as nobody rereads it. On 31 Aug the live count went 11 to 18 in a
    single day and the send packet did not notice.

    Deliberately narrow, to stay safe against a private repo:
      - counts only, never the enumerations, which no regex should be trusted to
        count, and never the surrounding prose;
      - letters and action files only. outreach/feedback/ and outreach/archive/
        are dated records of what someone saw at the time, so an old count there
        is correct and must not be "fixed";
      - quoted spans are skipped, so a packet note quoting what an already-sent
        letter said does not read as a live claim;
      - reports file:line and the two numbers, so nothing private is ever
        printed into a report or a notification.
    """
    letters = REPO / "outreach"
    if not letters.exists():
        record(OK, "letter category counts", "outreach/ not cloned here, nothing to check")
        return
    live = live_category_count()
    if live is None:
        record(WARN, "letter category counts", "dist/data/categories.json unreadable")
        return

    files = sorted(letters.glob("*.md")) + sorted((letters / "letters").glob("*.md"))
    stale, scanned = [], 0
    for f in files:
        text = f.read_text(errors="ignore")
        # These letters are hard-wrapped, so "name the 18 categories" and the
        # "that ARE live" proving it is a live claim routinely land on different
        # lines. Blank out quotes and flatten newlines WITHOUT changing length,
        # so offsets still map back to the real line number for the report.
        flat = _QUOTED.sub(lambda m: " " * len(m.group()), text).replace("\n", " ")
        line_starts = [i for i, ch in enumerate(text) if ch == "\n"]
        for m in COUNT_CLAIM.finditer(flat):
            if not (m.group(2) or LIVE_CUE.match(flat[m.end():])):
                continue                        # not a claim about what is live
            scanned += 1
            raw = m.group(1).lower()
            said = int(raw) if raw.isdigit() else WORD_NUMBERS[raw]
            if said != live:
                n = bisect.bisect_right(line_starts, m.start()) + 1
                stale.append(f"{f.relative_to(REPO)}:{n} says {said}")
    if not stale:
        record(OK, "letter category counts",
               f"{scanned} count claims all say {live}")
    else:
        record(WARN, "letter category counts",
               f"{live} categories are live; " + "; ".join(stale[:3])
               + (f" (+{len(stale)-3} more)" if len(stale) > 3 else ""))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true",
                    help="also check public URLs, doc links and upstream sources (slow)")
    args = ap.parse_args()

    print(f"Upstate Access Project, weekly debug, {date.today().isoformat()}")
    print("=" * 62)

    for fn in (check_tests, check_claims_guard, check_published_numbers,
               check_model_matches_prose, check_data_vintage_claims,
               check_gtfs_freshness, check_sensitive_not_shipped,
               check_verification_freshness, check_syntax_and_json,
               check_links, check_em_dashes, check_dist_current,
               check_letter_category_counts):
        try:
            fn()
        except Exception as e:                                # noqa: BLE001
            record(FAIL, fn.__name__, f"check itself crashed: {type(e).__name__}: {e}")
    if args.live:
        check_live_site()
        check_external_links()
        check_upstream_source_drift()

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
