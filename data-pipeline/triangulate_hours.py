#!/usr/bin/env python3
"""Merge the hours registry into the facility files, with provenance.

Reads data-pipeline/overrides/hours_sources.csv and patches every
data/processed/facilities_*.json record it can match by id:

  open_hours            the published string
  hours_provenance      "phone_verified" | "reported"
  hours_verified_on     date of the phone call (phone tier only)
  hours_sources         the agreeing non-phone sources (reported tier only)

Publish rules (KD feedback, decided by Nikhil 2026-08-27):
  - A phone row publishes alone: someone at the facility said it.
  - Non-phone rows (website, google, sc211, other) publish only when two or
    more sources AGREE on the normalized string, labeled "reported".
  - A lone non-phone source, or disagreement, publishes NOTHING and lands on
    data/processed/hours_call_worksheet.csv for a phone follow-up. Wrong hours
    cause the exact wasted trip the project exists to prevent; ties go to
    silence.

Run AFTER the fetchers (they rebuild the facility files from scratch):
    python data-pipeline/fetch_hrsa_fqhc.py && python data-pipeline/triangulate_hours.py
"""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REGISTRY = Path(__file__).resolve().parent / "overrides" / "hours_sources.csv"
PROCESSED = REPO / "data" / "processed"
WORKSHEET = PROCESSED / "hours_call_worksheet.csv"

PHONE = "phone"
NON_PHONE = {"website", "google", "sc211", "other"}


def norm(hours: str) -> str:
    """Comparison key: case/space/punctuation-insensitive."""
    return re.sub(r"[\s.,;]+", " ", hours.strip().lower())


def load_registry():
    rows = []
    with REGISTRY.open() as fh:
        for r in csv.DictReader(l for l in fh if not l.startswith("#")):
            src = (r.get("source") or "").strip().lower()
            if src and src != PHONE and src not in NON_PHONE:
                raise SystemExit(f"unknown source {src!r} for {r.get('facility_id')} "
                                 f"— add it to the tier rules, don't guess")
            if r.get("facility_id") and r.get("hours"):
                rows.append(r)
    return rows


def decide(rows: list[dict]):
    """One facility's rows -> (publish dict or None, worksheet reason or None)."""
    phones = [r for r in rows if r["source"].strip().lower() == PHONE]
    if phones:
        p = sorted(phones, key=lambda r: r.get("collected_on") or "")[-1]
        return ({"open_hours": p["hours"].strip(),
                 "hours_provenance": "phone_verified",
                 "hours_verified_on": (p.get("collected_on") or "").strip() or None},
                None)
    others = [r for r in rows if r["source"].strip().lower() in NON_PHONE]
    by_norm = defaultdict(list)
    for r in others:
        by_norm[norm(r["hours"])].append(r)
    agreeing = [v for v in by_norm.values() if len({x["source"] for x in v}) >= 2]
    if len(by_norm) == 1 and agreeing:
        v = agreeing[0]
        return ({"open_hours": v[0]["hours"].strip(),
                 "hours_provenance": "reported",
                 "hours_sources": sorted({x["source"].strip().lower() for x in v})},
                None)
    if len(by_norm) > 1:
        return None, "sources disagree: " + " | ".join(
            f"{r['source']}={r['hours']}" for r in others)
    if others:
        return None, f"single source only ({others[0]['source']})"
    return None, None


def main() -> None:
    rows = load_registry()
    by_fac = defaultdict(list)
    for r in rows:
        by_fac[r["facility_id"]].append(r)

    decisions, worksheet = {}, []
    for fid, frs in by_fac.items():
        publish, reason = decide(frs)
        if publish:
            decisions[fid] = publish
        if reason:
            worksheet.append({"facility_id": fid,
                              "category": frs[0].get("category", ""),
                              "reason": reason})

    patched = unmatched = 0
    matched_ids = set()
    for path in sorted(PROCESSED.glob("facilities_*.json")):
        doc = json.loads(path.read_text())
        recs = doc if isinstance(doc, list) else doc.get("facilities", [])
        changed = False
        for rec in recs:
            d = decisions.get(rec.get("id"))
            if not d:
                continue
            matched_ids.add(rec["id"])
            if any(rec.get(k) != v for k, v in d.items()):
                rec.update(d)
                changed = True
                patched += 1
        if changed:
            path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
            print(f"  patched {path.name}")
    for fid in decisions:
        if fid not in matched_ids:
            unmatched += 1
            print(f"  WARNING: {fid} matches no facility record — check the id")

    with WORKSHEET.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["facility_id", "category", "reason"])
        w.writeheader()
        w.writerows(sorted(worksheet, key=lambda r: r["facility_id"]))
    print(f"{len(decisions)} publishable ({patched} records updated), "
          f"{len(worksheet)} on the call worksheet, {unmatched} unmatched ids")


if __name__ == "__main__":
    main()
