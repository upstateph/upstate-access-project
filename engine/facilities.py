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
MANIFEST = REPO_DIR / "dashboard" / "data" / "categories.json"

# Category keys are data-driven: any category with a data/processed/facilities_<key>.json
# is loadable. The authoritative registry (labels, sensitivity, source) lives in
# data-pipeline/categories.py and is published to dashboard/data/categories.json.

# Fail-closed backstop. Stigma-sensitive categories must never be served publicly
# until every facility address is manually verified (spec §6 — accuracy here is a
# safety issue, not a UX bug). Enforcing this ONLY in the /api/categories menu is
# not enough: the scoring endpoint takes a caller-supplied key. These keys stay
# withheld even if the manifest is missing or unreadable.
SENSITIVE_FALLBACK = frozenset(
    {"abortion", "reproductive_health", "hiv_ryan_white", "substance_use"})


class CategoryWithheld(PermissionError):
    """Category exists in the registry but is not cleared for public serving.

    Raised BEFORE any file-existence check so the response cannot reveal whether a
    seed file for a sensitive category exists on disk."""

    def __init__(self, category: str):
        self.category = category
        super().__init__(f"Category {category!r} is withheld pending address verification.")


def facilities_path(category: str) -> Path:
    return PROCESSED_DIR / f"facilities_{category}.json"


def available_categories() -> list[str]:
    """Category keys that have a facilities data file present."""
    return sorted(p.stem.replace("facilities_", "")
                  for p in PROCESSED_DIR.glob("facilities_*.json"))


def _manifest_entry(category: str) -> dict | None:
    try:
        with MANIFEST.open(encoding="utf-8") as fh:
            for entry in json.load(fh).get("categories", []):
                if entry.get("key") == category:
                    return entry
    except (OSError, ValueError):
        return None
    return None


def is_public_ready(category: str) -> bool:
    """True only if the category is explicitly cleared for public serving.

    Fail-closed: an unreadable manifest still blocks every SENSITIVE_FALLBACK key.
    """
    entry = _manifest_entry(category)
    if entry is not None:
        return bool(entry.get("public_ready"))
    return category not in SENSITIVE_FALLBACK


def load_facilities(category: str, *, allow_withheld: bool = False) -> list[dict]:
    """Return the list of facility records for a category.

    Raises CategoryWithheld if the category is not cleared for public serving
    (pass allow_withheld=True for local verification work), or FileNotFoundError
    if the data hasn't been pulled. The FileNotFoundError message is for operators
    and CLI use — servers must NOT echo it to clients (it names on-disk files).
    """
    if not category or "/" in category or ".." in category:  # basic path-safety
        raise ValueError(f"Invalid category key: {category!r}")
    if not allow_withheld and not is_public_ready(category):
        raise CategoryWithheld(category)
    path = facilities_path(category)
    if not path.exists():
        raise FileNotFoundError(
            f"No facility data for '{category}' at {path}. "
            f"Run the corresponding pipeline pull to add it."
        )
    with path.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    return payload["facilities"] if isinstance(payload, dict) else payload
