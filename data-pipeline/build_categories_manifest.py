#!/usr/bin/env python3
"""Publish dashboard/data/categories.json — the menu the lookup UI reads.

Combines the category registry (categories.py) with a scan of which categories
actually have data (data/processed/facilities_<key>.json). Sensitive categories that
aren't verified are marked so the UI can gate them.

Usage:
    python build_categories_manifest.py
"""
from __future__ import annotations

from categories import CATEGORY_REGISTRY
from common import DASHBOARD_DATA_DIR, PROCESSED_DIR, ensure_dirs, read_json, write_json


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
        cats.append({
            "key": key,
            "label": meta["label"],
            "group": meta.get("group", "Other"),
            "sensitive": bool(meta.get("sensitive")),
            "verification_required": bool(meta.get("verification_required")),
            "source": meta.get("source"),
            "available": available,
            "count": n,
            # A category is offered in the public UI only if it has data AND is either
            # non-sensitive or has been explicitly verified (verification_required cleared).
            "public_ready": available and not (meta.get("sensitive") and meta.get("verification_required")),
        })

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
