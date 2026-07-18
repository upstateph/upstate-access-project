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

# Category keys are data-driven: any category with a data/processed/facilities_<key>.json
# is loadable. The authoritative registry (labels, sensitivity, source) lives in
# data-pipeline/categories.py and is published to dashboard/data/categories.json.


def facilities_path(category: str) -> Path:
    return PROCESSED_DIR / f"facilities_{category}.json"


def available_categories() -> list[str]:
    """Category keys that have a facilities data file present."""
    return sorted(p.stem.replace("facilities_", "")
                  for p in PROCESSED_DIR.glob("facilities_*.json"))


def load_facilities(category: str) -> list[dict]:
    """Return the list of facility records for a category.

    Raises FileNotFoundError with a helpful message if the data hasn't been pulled.
    """
    if not category or "/" in category or ".." in category:  # basic path-safety
        raise ValueError(f"Invalid category key: {category!r}")
    path = facilities_path(category)
    if not path.exists():
        avail = available_categories()
        raise FileNotFoundError(
            f"No facility data for '{category}' at {path}.\n"
            f"Available now: {', '.join(avail) or '(none)'}. "
            f"Run the corresponding pipeline pull to add it."
        )
    with path.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    return payload["facilities"] if isinstance(payload, dict) else payload
