#!/usr/bin/env python3
"""Track pharmacy openings/closures in Greenville County over time.

Snapshots the current pharmacy facility list (data/processed/facilities_pharmacy.json)
into data/processed/pharmacy_snapshots/<YYYY-MM-DD>.json and diffs the two most recent
snapshots by (name, address) to surface additions and closures. Pharmacy closures are
an accelerating access problem statewide; a periodic re-fetch + snapshot makes emerging
pharmacy deserts visible almost for free.

Intended cadence (e.g. monthly):
    python fetch_nppes.py pharmacy "Pharmacy"     # refresh the facility list
    python pharmacy_trend.py                       # snapshot + diff

Snapshots are small and tracked in git, so the history survives any one machine.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR))

from common import DASHBOARD_DATA_DIR, PROCESSED_DIR, ensure_dirs, read_json, write_json  # noqa: E402

FACILITIES_FILE = PROCESSED_DIR / "facilities_pharmacy.json"
SNAPSHOT_DIR = PROCESSED_DIR / "pharmacy_snapshots"


def facility_key(f: dict) -> str:
    return f"{(f.get('name') or '').strip().lower()}|{(f.get('address') or '').strip().lower()}"


def slim(f: dict) -> dict:
    """Keep only the fields the diff needs (all already public directory data)."""
    return {k: f.get(k) for k in ("name", "address", "city", "zip", "phone")}


def main() -> None:
    ensure_dirs()
    if not FACILITIES_FILE.exists():
        sys.exit(f"ERROR: {FACILITIES_FILE} missing — run fetch_nppes.py pharmacy first.")
    doc = read_json(FACILITIES_FILE)
    current = sorted((slim(f) for f in doc.get("facilities", [])),
                     key=lambda f: (f["name"] or "", f["address"] or ""))

    today = _dt.date.today().isoformat()
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    snap_path = SNAPSHOT_DIR / f"{today}.json"
    write_json(snap_path, {"date": today, "count": len(current),
                           "source": doc.get("source"), "facilities": current},
               label=f"pharmacy snapshot {today} ({len(current)} pharmacies)")

    snaps = sorted(SNAPSHOT_DIR.glob("*.json"))
    history = []
    for p in snaps:
        s = read_json(p)
        history.append({"date": s["date"], "count": s["count"]})

    if len(snaps) < 2:
        print("Baseline snapshot created. Re-run after the next fetch to see changes.")
        prev = None
        added, removed = [], []
    else:
        prev_doc = read_json(snaps[-2])
        prev = prev_doc["date"]
        prev_by_key = {facility_key(f): f for f in prev_doc["facilities"]}
        cur_by_key = {facility_key(f): f for f in current}
        added = [cur_by_key[k] for k in sorted(cur_by_key.keys() - prev_by_key.keys())]
        removed = [prev_by_key[k] for k in sorted(prev_by_key.keys() - cur_by_key.keys())]
        print(f"Compared {prev} -> {today}: {len(added)} added, {len(removed)} removed "
              f"(possible closures/renames — verify before citing).")
        for f in added:
            print(f"  + {f['name']} — {f['address']}, {f['city']}")
        for f in removed:
            print(f"  - {f['name']} — {f['address']}, {f['city']}")

    out = {
        "county": "Greenville County",
        "category": "pharmacy",
        "generated": today,
        "compared_against": prev,
        "n_current": len(current),
        "history": history,
        "added": added,
        "removed": removed,
        "note": (
            "Diff of NPPES-derived pharmacy lists by (name, address). A removal may be "
            "a closure, relocation, or NPPES record change — verify before citing as a "
            "closure. Snapshots live in data/processed/pharmacy_snapshots/."
        ),
    }
    fname = "pharmacy_trend.json"
    write_json(PROCESSED_DIR / fname, out, label=fname)
    write_json(DASHBOARD_DATA_DIR / fname, out, label=f"{fname} (site)")


if __name__ == "__main__":
    main()
