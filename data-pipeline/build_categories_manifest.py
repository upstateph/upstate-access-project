#!/usr/bin/env python3
"""Publish dashboard/data/categories.json — the menu the lookup UI reads.

Combines the category registry (categories.py) with a scan of which categories
actually have data (data/processed/facilities_<key>.json). Sensitive categories that
aren't verified are marked so the UI can gate them.

Usage:
    python build_categories_manifest.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from categories import CATEGORY_REGISTRY
from common import DASHBOARD_DATA_DIR, PROCESSED_DIR, ensure_dirs, read_json, write_json
from engine.facilities import verification_status  # noqa: E402


def facility_count(key: str) -> int | None:
    path = PROCESSED_DIR / f"facilities_{key}.json"
    if not path.exists():
        return None
    payload = read_json(path)
    facs = payload["facilities"] if isinstance(payload, dict) else payload
    return len(facs)


def main() -> None:
    ensure_dirs()
    cats = []
    for key, meta in CATEGORY_REGISTRY.items():
        n = facility_count(key)
        available = n is not None and n > 0
        sensitive = bool(meta.get("sensitive"))
        cleared = available and not (sensitive and meta.get("verification_required"))
        # Sensitive categories additionally need CURRENT verification: a list checked
        # once and left to rot is exactly the failure this gate exists to prevent.
        vs = verification_status(key) if sensitive else None
        stale = bool(vs and vs["stale"])
        entry = {
            "key": key,
            "label": meta["label"],
            "group": meta.get("group", "Other"),
            "sensitive": sensitive,
            "verification_required": bool(meta.get("verification_required")),
            "source": meta.get("source"),
            "available": available,
            "count": n,
            # Offered publicly only if it has data, is non-sensitive or explicitly
            # cleared, AND (for sensitive categories) its verification is current.
            "public_ready": cleared and not stale,
        }
        if sensitive:
            # Publishable freshness signal — dates and counts only. The verifier's
            # name stays in the server-side facilities file, never in this manifest.
            entry["verification"] = {
                "oldest_verified_on": vs["oldest_verified_on"],
                "age_days": vs["age_days"],
                "stale": stale,
                "reason": vs["reason"],
            }
            if stale and cleared:
                print(f"  WITHHELD {key}: {vs['reason']}")
        cats.append(entry)

    out = {
        "county": "Greenville County",
        "note": ("Sensitive categories are scaffolded but withheld from the public menu "
                 "until every address is verified (spec §6)."),
        "categories": cats,
    }
    write_json(DASHBOARD_DATA_DIR / "categories.json", out, label="categories.json")
    ready = [c["key"] for c in cats if c["public_ready"]]
    scaffolded = [c["key"] for c in cats if c["sensitive"]]
    print(f"Public-ready categories ({len(ready)}): {', '.join(ready) or '(none)'}")
    print(f"Sensitive scaffolded (withheld): {', '.join(scaffolded)}")


if __name__ == "__main__":
    main()
