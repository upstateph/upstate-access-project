"""Category registry for the access-lookup tool.

The authoritative list of service categories, their display labels, data source, and
— critically — whether they are **safety-sensitive** (spec §6: for these, an incorrect
address is a safety issue, not a UX bug, so they must be manually verified before
launch and are NOT auto-populated from scraped data).

`build_categories_manifest.py` reads this + scans for facilities_<key>.json to publish
dashboard/data/categories.json, which the lookup UI reads to build its menu.
"""
from __future__ import annotations

# key -> metadata
CATEGORY_REGISTRY: dict[str, dict] = {
    # ── Non-sensitive: auto-sourced from public datasets ──────────────────────
    "fqhc": {
        "label": "Community health center (FQHC)",
        "group": "Health care",
        "sensitive": False,
        "source": "HRSA Health Center Service Delivery Sites",
        "fetch": "fetch_hrsa_fqhc.py",
    },
    "hospital": {
        "label": "Hospital / emergency room",
        "group": "Health care",
        "sensitive": False,
        "source": "HIFLD Hospitals",
        "fetch": "fetch_hifld.py hospital",
    },
    "urgent_care": {
        "label": "Urgent care",
        "group": "Health care",
        "sensitive": False,
        "source": "HIFLD Urgent Care Facilities",
        "fetch": "fetch_hifld.py urgent_care",
    },
    "pharmacy": {
        "label": "Pharmacy",
        "group": "Health care",
        "sensitive": False,
        "source": "HIFLD Pharmacies",
        "fetch": "fetch_hifld.py pharmacy",
    },
    "gov_social": {
        "label": "Government & social services (DSS, DEW, SSA)",
        "group": "Public services",
        "sensitive": False,
        "source": "Verified official .gov office list (geocoded)",
        "fetch": "fetch_gov_offices.py",
    },
    "food": {
        "label": "Food assistance (pantries / food bank)",
        "group": "Public services",
        "sensitive": False,
        "source": "Verified pantry list (geocoded)",
        "fetch": "fetch_food_assistance.py",
    },

    # ── Safety-sensitive: SCAFFOLDED ONLY, verify before launch (spec §6) ──────
    # These are registered so the framework supports them, but they are NOT
    # auto-populated from scraped data. Each needs a manually verified seed list
    # (see seed_sensitive_category.py and docs/privacy-design.md) before it may be
    # shown to the public. Accuracy here is a safety issue.
    "abortion": {
        "label": "Abortion clinic",
        "group": "Reproductive & sensitive care",
        "sensitive": True,
        "verification_required": True,
        "source": "MANUAL — verify every address before launch",
    },
    "reproductive_health": {
        "label": "Women's / reproductive health",
        "group": "Reproductive & sensitive care",
        "sensitive": True,
        "verification_required": True,
        "source": "MANUAL — verify every address before launch",
    },
    "hiv_ryan_white": {
        "label": "HIV / Ryan White care",
        "group": "Reproductive & sensitive care",
        "sensitive": True,
        "verification_required": True,
        "source": "MANUAL — verify every provider before launch",
    },
    "substance_use": {
        "label": "Substance-use treatment",
        "group": "Reproductive & sensitive care",
        "sensitive": True,
        "verification_required": True,
        "source": "MANUAL — verify every address before launch",
    },
}


def sensitive_keys() -> list[str]:
    return [k for k, v in CATEGORY_REGISTRY.items() if v.get("sensitive")]
