#!/usr/bin/env python3
"""Download the Greenlink GTFS static feed for transit routing.

Tier 2 transit data. Grabs the live feed zip and caches it under data/raw/gtfs/.
The engine's transit module reads directly from this zip.

Source (verified July 2026, no API key): Greenlink's canonical GTFS-static endpoint,
hosted by their AVL vendor Cadavl — the upstream that Transitland and the Mobility
Database themselves poll. ~821 KB.
  https://gtfs.greenlink.cadavl.com/GTA/GTFS/GTFS_GTA.zip

Notes:
  - Service is expressed via calendar_dates.txt (calendar.txt is header-only).
  - No feed_info.txt, so freshness = HTTP last-modified / calendar_dates range.

Usage:
    python fetch_greenlink_gtfs.py
"""
from __future__ import annotations

import io
import zipfile

import requests

from common import RAW_DIR, ensure_dirs

GTFS_URL = "https://gtfs.greenlink.cadavl.com/GTA/GTFS/GTFS_GTA.zip"
GTFS_ZIP = RAW_DIR / "gtfs" / "greenlink_gtfs.zip"


def main() -> None:
    ensure_dirs()
    GTFS_ZIP.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading Greenlink GTFS from {GTFS_URL} ...")
    resp = requests.get(GTFS_URL, timeout=120)
    resp.raise_for_status()
    GTFS_ZIP.write_bytes(resp.content)
    last_mod = resp.headers.get("Last-Modified", "unknown")

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        members = sorted(n for n in zf.namelist() if n.endswith(".txt"))
    print(f"  wrote {GTFS_ZIP.relative_to(RAW_DIR.parent.parent)} "
          f"({len(resp.content) // 1024} KB, last-modified {last_mod})")
    print(f"  feed files: {', '.join(members)}")


if __name__ == "__main__":
    main()
