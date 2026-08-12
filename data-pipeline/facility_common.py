"""Shared helpers for building facility datasets from address-only sources.

Live public directories (CMS, NPPES) return clean addresses but no coordinates, so we
geocode with the free Census Geocoder and keep only facilities that geocode inside the
target county (accurate county filtering even when the source can't filter by county).
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR))

from engine.geocode import geocode  # noqa: E402

GEOCODE_DELAY_S = 0.4  # be gentle on the Census geocoder — it throttles bulk use,
                       # and a large category pull is ~700 sequential requests


def build_facility(category: str, *, name: str, address: str, city: str, state: str,
                   zip_code: str, phone: str = "", source: str,
                   keep_county_fips: str | None = None, extra: dict | None = None) -> dict | None:
    """Geocode one facility into the standard schema. Returns None if it doesn't
    geocode, or (when keep_county_fips is set) falls outside that county."""
    name = (name or "").strip()
    address = (address or "").strip()
    if not name or not address:
        return None
    one_line = f"{address}, {city.strip()}, {state.strip()} {str(zip_code).strip()}"
    g = geocode(one_line)
    time.sleep(GEOCODE_DELAY_S)
    if g is None:
        return None
    if keep_county_fips and g.county_fips != keep_county_fips:
        return None
    rec = {
        "id": name[:60], "name": name, "category": category,
        "address": address, "city": city.strip(), "state": state.strip(),
        "zip": str(zip_code).strip(), "phone": (phone or "").strip(),
        "county_fips": g.county_fips, "lat": g.lat, "lon": g.lon,
        "matched_address": g.matched_address, "source": source,
    }
    if extra:
        rec.update(extra)
    return rec
