"""Load facility location data for a category (FQHC first).

Reads a processed JSON file produced by the data pipeline
(data/processed/facilities_<category>.json). Each facility record has at least:
    id, name, category, address, city, zip, county_fips, lat, lon, source

Keeping loading behind this interface means the engine doesn't care whether the
underlying data came from HRSA, SAMHSA, a manual seed list, etc.
"""
from __future__ import annotations

import json
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent
REPO_DIR = ENGINE_DIR.parent
PROCESSED_DIR = REPO_DIR / "data" / "processed"

# Categories the engine may support (spec §3). FQHC is the launch category.
CATEGORIES = ("fqhc", "substance_use", "hiv_ryan_white", "womens_health")


def facilities_path(category: str) -> Path:
    return PROCESSED_DIR / f"facilities_{category}.json"


def load_facilities(category: str) -> list[dict]:
    """Return the list of facility records for a category.

    Raises FileNotFoundError with a helpful message if the data hasn't been pulled.
    """
    if category not in CATEGORIES:
        raise ValueError(f"Unknown category '{category}'. Known: {', '.join(CATEGORIES)}")
    path = facilities_path(category)
    if not path.exists():
        raise FileNotFoundError(
            f"No facility data for '{category}' at {path}.\n"
            f"Run the corresponding pipeline pull (e.g. fetch_hrsa_fqhc.py for FQHCs)."
        )
    with path.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    return payload["facilities"] if isinstance(payload, dict) else payload
