"""Load facility location data for a category (FQHC first).

Reads a processed JSON file produced by the data pipeline
(data/processed/facilities_<category>.json). Each facility record has at least:
    id, name, category, address, city, zip, county_fips, lat, lon, source

Keeping loading behind this interface means the engine doesn't care whether the
underlying data came from HRSA, SAMHSA, a manual seed list, etc.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
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


# How long a manual verification stays good for a sensitive category. Clinic
# locations, and which site of an organization actually provides a service, both
# change; a list verified once and never revisited silently rots. Sensitive
# categories are withdrawn from public serving automatically when their oldest
# verification ages past this, so freshness never depends on remembering to check.
VERIFICATION_MAX_AGE_DAYS = int(os.environ.get("UAP_VERIFICATION_MAX_AGE_DAYS", "180"))


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


def is_known_category(category: str) -> bool:
    """True if the manifest declares this category at all, withheld or not.

    Servers use this to reject a garbage category key BEFORE it reaches the file
    layer. Without it, an unknown key sails through is_public_ready() — which
    fails OPEN for keys absent from the manifest, deliberately, so an unreadable
    manifest still serves non-sensitive categories — and dies as FileNotFoundError,
    which servers translate to 503 "data_not_loaded". A client typo then looks
    like a server outage, and a genuine missing-data incident on a PUBLISHED
    category looks like a client typo.

    Deliberately checks the manifest, never the files on disk: available_categories()
    would reveal which withheld categories already have seed data. The manifest is
    itself public, and callers must map unknown and withheld to the SAME response,
    so this adds no oracle.
    """
    return _manifest_entry(category) is not None


def _manifest_entry(category: str) -> dict | None:
    try:
        with MANIFEST.open(encoding="utf-8") as fh:
            for entry in json.load(fh).get("categories", []):
                if entry.get("key") == category:
                    return entry
    except (OSError, ValueError):
        return None
    return None


def verification_status(category: str, *, max_age_days: int | None = None,
                        today: _dt.date | None = None) -> dict:
    """Freshness of a category's manual address verification.

    Reads the per-facility `verified_on` dates written by seed_facilities.py.
    Fail-closed in every ambiguous case: a facility with no date, an unparseable
    date, or a future date all count as unverified, because "we don't know when
    this was checked" is not the same as "this is current".

    Returns {has_data, n_facilities, n_verified, oldest_verified_on, age_days,
             stale, reason}. `stale` is False when there is no data at all (there
             is nothing to serve, so nothing to withdraw).
    """
    max_age = VERIFICATION_MAX_AGE_DAYS if max_age_days is None else max_age_days
    today = today or _dt.date.today()
    path = facilities_path(category)
    if not path.exists():
        return {"has_data": False, "n_facilities": 0, "n_verified": 0,
                "oldest_verified_on": None, "age_days": None, "stale": False,
                "reason": "no facility data"}
    try:
        with path.open(encoding="utf-8") as fh:
            payload = json.load(fh)
        facs = payload["facilities"] if isinstance(payload, dict) else payload
    except (OSError, ValueError, KeyError):
        return {"has_data": False, "n_facilities": 0, "n_verified": 0,
                "oldest_verified_on": None, "age_days": None, "stale": True,
                "reason": "facility file unreadable"}

    dates = []
    for f in facs:
        raw = (f or {}).get("verified_on")
        try:
            d = _dt.date.fromisoformat(str(raw))
        except (TypeError, ValueError):
            continue
        if d > today:  # a future date is a data-entry error, not a verification
            continue
        dates.append(d)

    n, n_ok = len(facs), len(dates)
    if not facs:
        return {"has_data": False, "n_facilities": 0, "n_verified": 0,
                "oldest_verified_on": None, "age_days": None, "stale": False,
                "reason": "no facilities in file"}
    if n_ok < n:
        return {"has_data": True, "n_facilities": n, "n_verified": n_ok,
                "oldest_verified_on": min(dates).isoformat() if dates else None,
                "age_days": (today - min(dates)).days if dates else None,
                "stale": True,
                "reason": f"{n - n_ok} of {n} facilities have no usable verified_on date"}
    oldest = min(dates)
    age = (today - oldest).days
    return {"has_data": True, "n_facilities": n, "n_verified": n_ok,
            "oldest_verified_on": oldest.isoformat(), "age_days": age,
            "stale": age > max_age,
            "reason": (f"oldest verification is {age} days old (limit {max_age})"
                       if age > max_age else "current")}


def is_public_ready(category: str) -> bool:
    """True only if the category is explicitly cleared for public serving.

    Fail-closed: an unreadable manifest still blocks every SENSITIVE_FALLBACK key,
    and a sensitive category whose verification has gone stale is withdrawn even if
    the published manifest still says public_ready (the manifest is a build-time
    snapshot; freshness is evaluated at request time).
    """
    entry = _manifest_entry(category)
    if entry is None:
        return category not in SENSITIVE_FALLBACK
    # A composite is servable as soon as ANY member is — its withheld members are
    # simply absent from results until they clear. Requiring all members would let
    # one ungated list block every other one.
    members = entry.get("members") or []
    if members:
        return any(is_public_ready(m) for m in members)
    if not entry.get("public_ready"):
        return False
    if entry.get("sensitive") and verification_status(category)["stale"]:
        return False
    return True


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

    # Composite category: one menu entry backed by several facility files, each
    # keeping its own gate. "Mental & behavioral health" is the motivating case —
    # merging therapy and substance-use treatment into a single option means a
    # person never has to pick a stigmatizing label off a dropdown in public, while
    # the SUD list still cannot publish until its addresses are verified. Members
    # are evaluated independently, so an unverified member is omitted rather than
    # taking the whole category down with it.
    members = (_manifest_entry(category) or {}).get("members") or []
    if members:
        facilities: list[dict] = []
        for member in members:
            if not allow_withheld and not is_public_ready(member):
                continue
            try:
                facilities.extend(load_facilities(member, allow_withheld=allow_withheld))
            except FileNotFoundError:
                continue
        if not facilities:
            raise CategoryWithheld(category)
        return facilities

    path = facilities_path(category)
    if not path.exists():
        raise FileNotFoundError(
            f"No facility data for '{category}' at {path}. "
            f"Run the corresponding pipeline pull to add it."
        )
    with path.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    records = payload["facilities"] if isinstance(payload, dict) else payload
    return [f for f in records if _is_servable_destination(f, category)]


def _is_servable_destination(fac: dict, category: str) -> bool:
    """Whether a facility record may be offered as a travel-time destination.

    Two ways a record can be real but not a valid answer to "how long to get
    there", both of which would otherwise produce a confident wrong number:

    `routable: False` — the record's address is not where service happens. HRSA
    lists every mobile unit at its dispatch base, so a mobile dental van in
    Greenville County resolves to New Horizon's administrative office. The van is
    genuine access and stays in the file; it is just not somewhere to send a
    person on foot.

    Service line — a health center site is not automatically primary care. A
    dental-only site answering "nearest community health center" tells someone
    they are 12 minutes from a clinic that cannot give them a physical.
    """
    if fac.get("routable") is False:
        return False
    required = (_manifest_entry(category) or {}).get("require_service_line")
    if required:
        lines = fac.get("service_lines")
        # Absent service_lines means an older file that predates the field. Keep
        # the record rather than emptying the category on a schema change.
        if lines is not None and required not in lines:
            return False
    return True
