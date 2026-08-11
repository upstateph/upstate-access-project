#!/usr/bin/env python3
"""Seed a category's facilities from a MANUALLY VERIFIED CSV (for sensitive categories).

Safety-sensitive categories (abortion, reproductive/women's health, HIV/Ryan White,
substance-use treatment) are NEVER auto-scraped — an incorrect address there is a
safety issue (spec §6). This script is the only supported way to populate them: you
provide a CSV of addresses you have verified, and it geocodes them into the standard
facilities file.

CSV columns (header required):
    name,address,city,state,zip,phone,verified_on,verified_by,verification_method

For SENSITIVE categories every row must carry a real verification record —
`verified_on` (ISO YYYY-MM-DD, not in the future) and `verification_method` (how you
confirmed it, e.g. "phone call to clinic"). Rows missing them are REJECTED rather
than seeded: the file must record that a human checked, not merely assert it.

Verifying the address text is not sufficient. This script geocodes each row, and
everything downstream (walk time, transit itinerary, nearest-facility ranking) uses
the resulting coordinate, not your text — a correct address can still geocode to a
street centroid or the wrong side of a block. Check the printed lat/lon against the
actual building before you publish the category.

Blank rows and rows without an address are skipped.

    python seed_facilities.py abortion data-pipeline/seeds/abortion.csv

After seeding, run build_categories_manifest.py. The category will show data but stays
withheld from the public menu until you clear `verification_required` for it in
categories.py — an explicit, deliberate step. Verifications expire: a sensitive
category is withdrawn automatically once its oldest verified_on ages past
engine.facilities.VERIFICATION_MAX_AGE_DAYS. Run check_verification.py to see status.
"""
from __future__ import annotations

import csv
import datetime as _dt
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR))

from categories import CATEGORY_REGISTRY  # noqa: E402
from common import PROCESSED_DIR, ensure_dirs, write_json  # noqa: E402
from engine.facilities import VERIFICATION_MAX_AGE_DAYS  # noqa: E402
from engine.geocode import geocode  # noqa: E402


def parse_verified_on(raw: str, today: _dt.date) -> tuple[str | None, str | None]:
    """Return (iso_date, error). Fail-closed: anything unusable is an error."""
    raw = (raw or "").strip()
    if not raw:
        return None, "missing verified_on"
    try:
        d = _dt.date.fromisoformat(raw)
    except ValueError:
        return None, f"verified_on '{raw}' is not an ISO date (YYYY-MM-DD)"
    if d > today:
        return None, f"verified_on '{raw}' is in the future"
    return d.isoformat(), None


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("Usage: python seed_facilities.py <category> <verified_csv>")
    category, csv_path = sys.argv[1], Path(sys.argv[2])
    if category not in CATEGORY_REGISTRY:
        sys.exit(f"Unknown category '{category}'. Known: {', '.join(CATEGORY_REGISTRY)}")
    if not csv_path.exists():
        sys.exit(f"CSV not found: {csv_path}")

    ensure_dirs()
    sensitive = bool(CATEGORY_REGISTRY[category].get("sensitive"))
    today = _dt.date.today()
    facilities, errors = [], []
    with csv_path.open(encoding="utf-8-sig") as fh:
        for i, row in enumerate(csv.DictReader(fh), start=2):  # row 1 is the header
            name = (row.get("name") or "").strip()
            address = (row.get("address") or "").strip()
            if not name or not address:
                continue

            verified_on, err = parse_verified_on(row.get("verified_on", ""), today)
            method = (row.get("verification_method") or "").strip()
            if sensitive:
                # Fail closed: a sensitive facility with no verification record is
                # not seeded at all, so the file can never claim more than was checked.
                if err:
                    errors.append(f"row {i} ({name}): {err}")
                    continue
                if not method:
                    errors.append(f"row {i} ({name}): missing verification_method")
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
                # Verification provenance — an auditable record, not an assertion.
                "verified_on": verified_on,
                "verified_by": (row.get("verified_by") or "").strip() or None,
                "verification_method": method or None,
            })
            print(f"  geocoded {name} -> {g.lat:.5f},{g.lon:.5f}"
                  + (f"  (verified {verified_on})" if verified_on else ""))

    if errors:
        print(f"\nREJECTED {len(errors)} row(s) — sensitive categories require a "
              "verification record on every row:")
        for e in errors:
            print(f"  - {e}")
        if not facilities:
            sys.exit("Nothing seeded. Add verified_on (YYYY-MM-DD) and "
                     "verification_method to the CSV and re-run.")

    dates = sorted(f["verified_on"] for f in facilities if f.get("verified_on"))
    out = {
        "category": category, "source": "MANUAL verified seed",
        "verification": {
            "n_facilities": len(facilities),
            "n_verified": len(dates),
            "oldest_verified_on": dates[0] if dates else None,
            "newest_verified_on": dates[-1] if dates else None,
            "max_age_days": VERIFICATION_MAX_AGE_DAYS,
            "note": ("Per-facility verified_on dates are the source of truth; a "
                     "sensitive category is withdrawn from public serving once the "
                     "oldest one ages past max_age_days."),
        },
        "facilities": facilities,
    }
    write_json(PROCESSED_DIR / f"facilities_{category}.json", out,
               label=f"{category} seed ({len(facilities)} facilities, {len(dates)} with verification)")
    print(f"Done: {len(facilities)} facilities"
          + (f", oldest verification {dates[0]}." if dates else "."))
    print("NEXT: check each printed lat/lon against the real building — routing uses "
          "the coordinate, not the address text.")
    if sensitive:
        print("NOTE: this is a SENSITIVE category. It stays withheld from the public "
              "menu until you clear `verification_required` for it in categories.py, "
              f"and is withdrawn again automatically after {VERIFICATION_MAX_AGE_DAYS} days.")


if __name__ == "__main__":
    main()
