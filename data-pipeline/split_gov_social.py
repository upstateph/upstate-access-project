#!/usr/bin/env python3
"""Split the verified gov_social list into DSS and workforce (DEW) categories.

`gov_social` bundles DSS, DEW and SSA and answers "where is the nearest government
office". For a housing placement that is the wrong question: enrolling in SNAP and
Medicaid happens at DSS, and job search support happens at SC Works, and a unit can
reach one without reaching the other. These are the same verified records, filtered
by the `agency` already carried on each one. No new data source.

Usage:
    python split_gov_social.py
"""
from __future__ import annotations

from common import ensure_dirs, PROCESSED_DIR, read_json, write_json

SPLITS = {
    "dss": ("DSS", "Verified official .gov office list (geocoded), DSS sites only"),
    "workforce": ("DEW", "Verified official .gov office list (geocoded), DEW sites only"),
}


def main() -> None:
    ensure_dirs()
    src = read_json(PROCESSED_DIR / "facilities_gov_social.json")
    rows = src["facilities"]
    print(f"gov_social: {len(rows)} records")

    for key, (agency, source) in SPLITS.items():
        picked = []
        for r in rows:
            if (r.get("agency") or "").upper() != agency:
                continue
            rec = dict(r)
            rec["category"] = key
            rec["source"] = source
            picked.append(rec)
        write_json(PROCESSED_DIR / f"facilities_{key}.json",
                   {"category": key, "county": src.get("county", "Greenville County"),
                    "source": source, "facilities": picked},
                   label=f"{key} ({len(picked)})")
        for r in picked:
            print(f"  {key}: {r['name']}")
        if not picked:
            print(f"  WARN: no {agency} records found; is `agency` still populated?")


if __name__ == "__main__":
    main()
