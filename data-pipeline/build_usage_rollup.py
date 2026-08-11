#!/usr/bin/env python3
"""Build the OBSERVED usage rollup from de-identified lookup telemetry.

Reads data/usage/lookups.jsonl (written by lookup-tool/server.py — category, tract,
travel times; never an address) and rolls it up per category with the k-anonymity
suppression in engine/aggregate.py: any tract with fewer than K lookups is dropped
entirely, fail-closed. The output is safe to publish; the input file is gitignored
and never leaves the machine.

Usage:
    python build_usage_rollup.py           # k = engine default (25)
    python build_usage_rollup.py --k 10    # explicit threshold (document why!)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR))

from common import DASHBOARD_DATA_DIR, PROCESSED_DIR, ensure_dirs, write_json  # noqa: E402
from engine.aggregate import AccessRecord, K_ANONYMITY_THRESHOLD, aggregate  # noqa: E402

USAGE_FILE = REPO_DIR / "data" / "usage" / "lookups.jsonl"
COUNTY_FIPS = "45045"


def load_records() -> dict[str, list[AccessRecord]]:
    """Read the telemetry file into AccessRecords, grouped by category."""
    by_cat: dict[str, list[AccessRecord]] = {}
    if not USAGE_FILE.exists():
        return by_cat
    with USAGE_FILE.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
                if not isinstance(d, dict):
                    continue  # fail-closed: valid JSON but not a record
                rec = AccessRecord(
                    tract_fips=d.get("tract_fips") or "",
                    walk_minutes=d.get("walk_minutes"),
                    transit_minutes=d.get("transit_minutes"),
                    transit_reachable=bool(d.get("transit_reachable")),
                )
            except (json.JSONDecodeError, TypeError):
                continue  # fail-closed: malformed line is dropped
            by_cat.setdefault(d.get("category") or "unknown", []).append(rec)
    return by_cat


def main() -> None:
    ap = argparse.ArgumentParser(description="k-anonymized rollup of real lookups.")
    ap.add_argument("--k", type=int, default=K_ANONYMITY_THRESHOLD,
                    help=f"suppression threshold (default {K_ANONYMITY_THRESHOLD})")
    args = ap.parse_args()

    ensure_dirs()
    by_cat = load_records()
    n_total = sum(len(v) for v in by_cat.values())
    if not n_total:
        print(f"No usage records at {USAGE_FILE.relative_to(REPO_DIR)} yet — "
              "nothing to roll up. (Records accrue as the lookup tool is used.)")
        return

    # Small-count safety: a category with < k lookups total publishes NOTHING —
    # "exactly 1 person searched X" is itself a disclosure, worst for the future
    # stigma-sensitive categories. Suppression metadata is coarsened the same way:
    # when only one tract was suppressed, its exact count would be recoverable.
    categories = {}
    n_withheld = 0
    for cat, recs in sorted(by_cat.items()):
        if len(recs) < args.k:
            # Omit the category ENTIRELY. Listing it as "suppressed" would itself
            # disclose that between 1 and k-1 people searched it — exactly the
            # disclosure that matters for stigma-sensitive categories.
            n_withheld += 1
            print(f"  {cat}: <{args.k} lookups -> omitted from the published rollup")
            continue
        agg = aggregate(recs, k=args.k)
        # Suppressed-observation totals are recoverable by arithmetic
        # (n_lookups - sum of visible per-tract n), so coarsen the category total
        # and drop the suppressed-observation count instead of "coarsening" a
        # figure that can be re-derived.
        agg.pop("n_observations_suppressed", None)
        bucket = (len(recs) // args.k) * args.k
        categories[cat] = {"n_lookups_at_least": bucket, **agg}
        print(f"  {cat}: >={bucket} lookups -> {agg['n_tracts_visible']} tracts visible, "
              f"{agg['n_tracts_suppressed']} suppressed (k={args.k})")
    if n_withheld:
        print(f"  ({n_withheld} categor{'y' if n_withheld == 1 else 'ies'} omitted entirely "
              f"for having fewer than {args.k} lookups)")

    out = {
        "county_fips": COUNTY_FIPS,
        "source": "OBSERVED — de-identified lookup usage, k-anonymity suppressed",
        "k_anonymity_threshold": args.k,
        "note": (
            "Built from de-identified lookup records (category, tract, travel times "
            "only — no addresses). Tracts with fewer than k lookups are suppressed, "
            "fail-closed, and each published statistic must itself rest on at least k "
            "observations. Categories with fewer than k lookups are omitted entirely "
            "(listing them would disclose that 1..k-1 people searched them). Counts "
            "are coarsened so suppressed totals cannot be recovered by subtraction. "
            "See docs/privacy-design.md."
        ),
        "n_lookups_total_at_least": (n_total // args.k) * args.k,
        "categories": categories,
    }
    fname = f"usage_rollup_{COUNTY_FIPS}.json"
    write_json(PROCESSED_DIR / fname, out, label=f"{fname} (processed)")
    write_json(DASHBOARD_DATA_DIR / fname, out, label=f"{fname} (site)")


if __name__ == "__main__":
    main()
