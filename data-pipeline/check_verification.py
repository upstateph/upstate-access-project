#!/usr/bin/env python3
"""Report verification freshness for safety-sensitive facility categories.

For categories where a wrong address is a safety issue (spec §6), a verified list is
only as good as its last check. This reports, per sensitive category, how many
facilities carry a verification record and how old the oldest one is — and exits
non-zero if anything is stale, so it can run as a scheduled check rather than
depending on someone remembering.

Exit codes:  0 = all current (or nothing seeded)   1 = at least one category stale

    python check_verification.py
    python check_verification.py --max-age-days 90     # tighter, e.g. quarterly
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR))

from categories import CATEGORY_REGISTRY  # noqa: E402
from engine.facilities import VERIFICATION_MAX_AGE_DAYS, verification_status  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Check sensitive-category verification freshness.")
    ap.add_argument("--max-age-days", type=int, default=VERIFICATION_MAX_AGE_DAYS,
                    help=f"days a verification stays valid (default {VERIFICATION_MAX_AGE_DAYS})")
    args = ap.parse_args()

    sensitive = [k for k, v in CATEGORY_REGISTRY.items() if v.get("sensitive")]
    print(f"Verification check — {len(sensitive)} safety-sensitive categories, "
          f"limit {args.max_age_days} days\n")

    any_stale = False
    any_data = False
    for key in sensitive:
        vs = verification_status(key, max_age_days=args.max_age_days)
        gate = "withheld (verification_required)" if CATEGORY_REGISTRY[key].get(
            "verification_required") else "cleared for public serving"
        if not vs["has_data"]:
            print(f"  {key:22} —  no data seeded  ({gate})")
            continue
        any_data = True
        status = "STALE" if vs["stale"] else "current"
        any_stale = any_stale or vs["stale"]
        age = f"{vs['age_days']}d" if vs["age_days"] is not None else "?"
        print(f"  {key:22} {status:8} {vs['n_verified']}/{vs['n_facilities']} verified, "
              f"oldest {vs['oldest_verified_on'] or '—'} ({age})  ({gate})")
        if vs["stale"]:
            print(f"      → {vs['reason']}")

    if not any_data:
        print("\nNothing seeded yet — nothing to verify.")
        return
    if any_stale:
        print("\nStale categories are automatically withheld from public serving "
              "(engine.facilities.is_public_ready) until re-verified.\n"
              "Re-verify, update verified_on in the seed CSV, then re-run "
              "seed_facilities.py and build_categories_manifest.py.")
        sys.exit(1)
    print("\nAll seeded sensitive categories are currently verified.")


if __name__ == "__main__":
    main()
