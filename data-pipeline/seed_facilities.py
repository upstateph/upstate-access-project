#!/usr/bin/env python3
"""Seed a category's facilities from a MANUALLY VERIFIED CSV (for sensitive categories).

Safety-sensitive categories (abortion, reproductive/women's health, HIV/Ryan White,
substance-use treatment) are NEVER auto-scraped — an incorrect address there is a
safety issue (spec §6). This script is the only supported way to populate them: you
provide a CSV of addresses you have verified, and it geocodes them into the standard
facilities file.

CSV columns (header required): name,address,city,state,zip,phone
Blank rows and rows without an address are skipped.

    python seed_facilities.py abortion data-pipeline/seeds/abortion.csv

After seeding, run build_categories_manifest.py. The category will show data but stays
withheld from the public menu until you clear `verification_required` for it in
categories.py — an explicit, deliberate step.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR))

from categories import CATEGORY_REGISTRY  # noqa: E402
from common import PROCESSED_DIR, ensure_dirs, write_json  # noqa: E402
from engine.geocode import geocode  # noqa: E402


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("Usage: python seed_facilities.py <category> <verified_csv>")
    category, csv_path = sys.argv[1], Path(sys.argv[2])
    if category not in CATEGORY_REGISTRY:
        sys.exit(f"Unknown category '{category}'. Known: {', '.join(CATEGORY_REGISTRY)}")
    if not csv_path.exists():
        sys.exit(f"CSV not found: {csv_path}")

    ensure_dirs()
    facilities = []
    with csv_path.open(encoding="utf-8-sig") as fh:
        for i, row in enumerate(csv.DictReader(fh)):
            name = (row.get("name") or "").strip()
            address = (row.get("address") or "").strip()
            if not name or not address:
                continue
            one_line = f"{address}, {row.get('city','').strip()}, " \
                       f"{row.get('state','').strip()} {row.get('zip','').strip()}"
            g = geocode(one_line)
            if g is None:
                print(f"  WARN: could not geocode '{name}' ({one_line}) — skipped")
                continue
            facilities.append({
                "id": name[:60], "name": name, "category": category,
                "address": address, "city": row.get("city", "").strip(),
                "state": row.get("state", "").strip(), "zip": row.get("zip", "").strip(),
                "phone": row.get("phone", "").strip(),
                "county_fips": g.county_fips, "lat": g.lat, "lon": g.lon,
                "source": "MANUAL verified seed",
            })
            print(f"  geocoded {name} -> {g.lat:.5f},{g.lon:.5f}")

    out = {
        "category": category, "source": "MANUAL verified seed",
        "verified": True, "facilities": facilities,
    }
    write_json(PROCESSED_DIR / f"facilities_{category}.json", out,
               label=f"{category} seed ({len(facilities)} verified facilities)")
    sensitive = CATEGORY_REGISTRY[category].get("sensitive")
    print(f"Done: {len(facilities)} facilities.")
    if sensitive:
        print("NOTE: this is a SENSITIVE category. It stays withheld from the public "
              "menu until you clear `verification_required` for it in categories.py.")


if __name__ == "__main__":
    main()
