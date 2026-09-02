#!/usr/bin/env python3
"""Watch verified addresses for change, so re-verification targets the ones that moved.

    .venv/bin/python tools/check_address_drift.py            # all seed lists
    .venv/bin/python tools/check_address_drift.py --category substance_use

WHY THIS EXISTS. Verification of a stigma-sensitive address expires after
`VERIFICATION_MAX_AGE_DAYS` (180) and then the category re-blocks itself. That
rule is right and it is also expensive in the wrong way: it says "call all 47
again in March" regardless of whether anything changed, which is burdensome for
Nikhil and, more importantly, burdensome for clinic staff who did him a favour
the first time. Calling a methadone clinic twice a year to ask a question they
already answered spends goodwill on nothing.

**The reframe: you do not need to re-verify. You need to detect change.** Almost
nothing moves in six months. The cost is in re-asking everyone rather than in
the handful that actually moved.

WHAT IT DOES. For every already-verified facility with an NPI, it asks the NPPES
registry (free, no key, refreshed weekly by CMS) what address that provider
currently lists, and compares it to the address that was verified by phone. Three
outcomes:

  OK          address unchanged since verification. No call needed.
  MOVED       the registry now says something else, or the NPI is deactivated.
              THIS is the one to call, and it is now known within a week rather
              than within six months.
  UNMONITORED no NPI recorded, so nothing to compare. The 180-day clock is the
              only protection these have, and they are the ones it exists for.

A LIMIT WORTH KNOWING BEFORE RELYING ON THIS. An NPI belongs to a provider and
carries ONE registered practice location. An organisation running several sites
usually has one NPI, filed against the site where its providers practise, so its
other sites are invisible here: they have no NPI of their own, cannot be
compared to anything, and keep the 180-day clock. One of the seed rows is
exactly this shape today.

Do not paste an organisation's NPI onto every row bearing its name. That
manufactures a false match on the row that happens to sit at the registered
location and a false alarm on the row that does not, which is what happened on
the first run of this script.

NO REAL ROW IS NAMED HERE, DELIBERATELY. An earlier version explained this with
an actual organisation and both of its street addresses, which put a verified
withheld-category address into public source: this repo is on GitHub, and
`check_sensitive_not_shipped` only ever looks at `dist/`, so nothing caught it.
The harm in that instance was near nil because the organisation publishes those
addresses itself; the precedent was the problem, because the same explanation
written with a `reproductive_health` row would disclose something genuinely
dangerous. `check_sensitive_addresses_in_source` now fails on any candidate
address in tracked source. Explain the limit with the shape, not with a row.

WHAT IT DOES NOT DO, and this is the honest limit. NPPES tells you what a
provider has filed, not whether the doors are open, not whether they still offer
the service, and not whether the record is current. A clinic can close and its
NPI can sit stale for months. **So this cannot replace the first phone call and
should not silence re-contact forever.** What it can honestly support is a longer
clock for monitored facilities plus fast detection when something does change,
which is strictly better than a blanket six-month re-call that catches a move an
average of three months late.

Fail-closed throughout: an unreachable API, an unparseable response and an
ambiguous match all report as problems rather than as OK.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SEEDS = REPO / "data-pipeline" / "seeds"
NPPES = "https://npiregistry.cms.hhs.gov/api/?version=2.1&number={npi}"

# The three stigma-sensitive lists. Column names differ between them because they
# were built by different scripts at different times.
LISTS = {
    "hiv_ryan_white": "candidates-hiv_ryan_white.csv",
    "reproductive_health": "candidates-reproductive_health.csv",
    "substance_use": "substance_use_candidates.csv",
}

OK, MOVED, UNMONITORED, ERROR = "OK", "MOVED", "UNMONITORED", "ERROR"


def normalize(addr: str) -> str:
    """Compare street addresses without tripping over punctuation or STE vs Suite.

    Deliberately loose on formatting and strict on content: it lowercases, drops
    punctuation, and folds the common USPS abbreviations, but it does not try to
    parse. Two addresses that differ in the street number or name will differ
    here, which is the case that matters.
    """
    s = (addr or "").lower()
    s = re.sub(r"[.,#]", " ", s)
    for long, short in (("street", "st"), ("avenue", "ave"), ("road", "rd"),
                        ("drive", "dr"), ("boulevard", "blvd"), ("suite", "ste"),
                        ("north", "n"), ("south", "s"), ("east", "e"), ("west", "w"),
                        ("parkway", "pkwy"), ("highway", "hwy"), ("court", "ct"),
                        ("lane", "ln"), ("place", "pl")):
        s = re.sub(rf"\b{long}\b", short, s)
    return re.sub(r"\s+", " ", s).strip()


def find_npi(row: dict) -> str | None:
    """An explicit `npi` column wins; otherwise recover one recorded in prose.

    build_sud_candidates.py wrote provenance like "NPPES NPI 1083332878" into
    _source, so 30 of the 41 substance-use rows already carry one without anybody
    having planned for this.
    """
    explicit = (row.get("npi") or "").strip()
    if re.fullmatch(r"\d{10}", explicit):
        return explicit
    haystack = " ".join(str(row.get(k) or "") for k in
                        ("_source", "source_url", "notes", "verification_method"))
    m = re.search(r"\bNPI[: ]+(\d{10})\b", haystack, re.I)
    return m.group(1) if m else None


def fetch(npi: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(NPPES.format(npi=npi),
                                 headers={"User-Agent": "uap-address-drift"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def check_row(row: dict) -> tuple[str, str]:
    """Return (status, detail) for one already-verified facility."""
    npi = find_npi(row)
    if not npi:
        return UNMONITORED, "no NPI recorded; 180-day clock is its only guard"
    try:
        data = fetch(npi)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        return ERROR, f"NPPES unreachable for {npi}: {type(e).__name__}"

    results = data.get("results") or []
    if not results:
        return MOVED, f"NPI {npi} returns no record; it may have been deactivated"

    basic = results[0].get("basic", {})
    if (basic.get("status") or "").upper() != "A":
        return MOVED, f"NPI {npi} status is {basic.get('status')!r}, not active"

    locations = [a for a in results[0].get("addresses", [])
                 if (a.get("address_purpose") or "").upper() == "LOCATION"]
    if not locations:
        return MOVED, f"NPI {npi} lists no practice location"

    # NPPES splits the suite into address_2, so comparing address_1 alone reports
    # "100 Example St Ste 11" as moved away from "100 EXAMPLE ST". Join them.
    # Illustrative address on purpose; see the docstring on not naming real rows.
    want = normalize(row.get("address", ""))
    have = [normalize(" ".join(filter(None, (a.get("address_1"), a.get("address_2")))))
            for a in locations]
    if any(h == want for h in have):
        return OK, f"NPI {npi} still lists {row.get('address','')}"

    # A street match with a differing suite is worth knowing about but is not the
    # same event as a facility moving, so it is reported separately rather than
    # sent to the top of a call list.
    street = lambda s: " ".join(s.split()[:3])
    if any(street(h) == street(want) for h in have if h):
        return MOVED, (f"NPI {npi} same street, different unit: registry says "
                       f"{have[0]!r}, verified {want!r}. Probably a suite change.")

    return MOVED, (f"NPI {npi} now lists {locations[0].get('address_1')}, "
                   f"{locations[0].get('city')} (verified: {row.get('address','')})")


def run(only: str | None) -> int:
    problems = 0
    for category, filename in LISTS.items():
        if only and category != only:
            continue
        path = SEEDS / filename
        if not path.exists():
            print(f"\n{category}: no seed list at {path.relative_to(REPO)}")
            continue

        rows = list(csv.DictReader(path.open()))
        verified = [r for r in rows if (r.get("verified_on") or "").strip()]
        print(f"\n{category}: {len(verified)} verified of {len(rows)}")
        if not verified:
            print("  nothing verified yet, so nothing to watch")
            continue

        for row in verified:
            status, detail = check_row(row)
            mark = {OK: "  ok  ", MOVED: " MOVED", UNMONITORED: " unmon",
                    ERROR: " ERROR"}[status]
            print(f"  [{mark}] {(row.get('name') or '')[:38]:40s} {detail}")
            if status in (MOVED, ERROR):
                problems += 1
            time.sleep(0.4)          # be polite to a free federal API

    print()
    if problems:
        print(f"{problems} facility/facilities need a human call. Re-verify those, "
              f"not the whole list, then update verified_on in the seed CSV.")
    else:
        print("No monitored address has changed. Nothing needs re-calling today.")
    return 1 if problems else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--category", choices=sorted(LISTS), help="check one list only")
    return run(ap.parse_args().category)


if __name__ == "__main__":
    sys.exit(main())
