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
        # HRSA designates sites by FUNDING SCOPE, not by service line, so the raw
        # file mixes a dental-only site in with primary care sites. This category
        # means "somewhere you can get primary care" — enforced at load time.
        "require_service_line": "primary_care",
        "source": "HRSA Health Center Service Delivery Sites",
        "fetch": "fetch_hrsa_fqhc.py",
    },
    "hospital": {
        "label": "Hospital / emergency room",
        "group": "Health care",
        "sensitive": False,
        "source": "CMS Hospital General Information",
        "fetch": "fetch_hifld.py hospital",
    },
    "urgent_care": {
        "label": "Urgent care",
        "group": "Health care",
        "sensitive": False,
        "source": "NPPES NPI Registry (organizations only)",
        "fetch": 'fetch_nppes.py urgent_care "Urgent Care"',
    },
    "pharmacy": {
        "label": "Pharmacy",
        "group": "Health care",
        "sensitive": False,
        "source": "NPPES NPI Registry (organizations only)",
        "fetch": 'fetch_nppes.py pharmacy "Pharmacy"',
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

    # ── Care types beyond primary care ────────────────────────────────────────
    # Access to care is not only primary care. Dental, vision, hearing and mental
    # health are distinct destinations with distinct travel burdens, and they are
    # frequently the HARDEST services for safety-net patients to reach. They are
    # separate categories rather than being folded into "FQHC" because a dental
    # chair is not a primary-care appointment — counting one as the other is the
    # classification error this split exists to fix.
    # Dental is a composite for a different reason than behavioral health: not
    # privacy, but coverage. NPPES lists private dental organizations; it does NOT
    # list a health center's dental site, which is enumerated under the health
    # center's generic FQHC taxonomy. HRSA has those sites but files them by
    # funding scope. Neither source alone finds a safety-net dental clinic — the
    # destination that matters most to the people this tool is for.
    "dental": {
        "label": "Dental care",
        "group": "Health care",
        "sensitive": False,
        "members": ["dental_private", "fqhc_dental"],
        "source": "NPPES NPI Registry + HRSA health center sites",
    },
    "dental_private": {
        "label": "Dental care (private practices)",
        "group": "Health care",
        "sensitive": False,
        "hidden": True,
        "source": "NPPES NPI Registry (organizations only)",
        "fetch": 'fetch_nppes.py dental_private "Dentist"',
    },
    "fqhc_dental": {
        "label": "Community health center — dental",
        "group": "Health care",
        "sensitive": False,
        "hidden": True,
        "require_service_line": "dental",
        "source": "HRSA Health Center Service Delivery Sites",
        "fetch": "fetch_hrsa_fqhc.py",
    },
    "vision": {
        "label": "Eye care (optometry / ophthalmology)",
        "group": "Health care",
        "sensitive": False,
        "source": "NPPES NPI Registry (organizations only)",
        "fetch": 'fetch_nppes.py vision "Optometrist,Ophthalmology"',
    },
    "hearing": {
        "label": "Hearing / audiology",
        "group": "Health care",
        "sensitive": False,
        "source": "NPPES NPI Registry (organizations only)",
        "fetch": 'fetch_nppes.py hearing "Audiologist"',
    },
    # ── Composite: one menu option, several gated sources ─────────────────────
    # Behavioral health is presented as a SINGLE choice covering therapy and
    # substance-use treatment. Two reasons, and the second is the important one:
    #   1. Clinically it is one field — integrated behavioral health is standard,
    #      and splitting SUD off is itself a form of stigma.
    #   2. Selecting "Substance-use treatment" from a visible dropdown — on a
    #      library terminal, a shared phone, a caseworker's screen — discloses
    #      something about the person doing the searching. A single behavioral
    #      health option removes that disclosure from the interaction entirely.
    # The data files stay separate so `substance_use` keeps its verification gate:
    # a merged file would force one posture on both, either making 200+ therapy
    # practices wait on a call-down only the SUD sites need, or publishing
    # unverified treatment-center addresses. Members are gated independently.
    "behavioral_health": {
        "label": "Mental & behavioral health",
        "group": "Health care",
        "sensitive": False,
        "members": ["mental_health", "substance_use"],
        "source": "NPPES NPI Registry + SAMHSA N-SUMHSS (verified subset)",
    },

    "mental_health": {
        "label": "Mental health & therapy",
        "group": "Health care",
        # Hidden from the menu: reached through `behavioral_health` above. Still a
        # real category — it holds its own file and its own gate.
        "hidden": True,
        # NOT flagged sensitive: these are public provider-directory listings and
        # general mental-health care does not carry the acute being-seen-entering
        # risk that abortion, HIV and substance-use treatment do. That is a
        # judgment call worth revisiting with clinicians — if it changes, set
        # sensitive/verification_required here and the engine withholds it.
        "sensitive": False,
        "source": "NPPES NPI Registry (organizations only)",
        "fetch": 'fetch_nppes.py mental_health "Psychologist,Counselor,Social Worker"',
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
    # Substance-use treatment is a PRIORITY category, not a reluctant one: people
    # with SUD are core to the population this tool serves, and opioid treatment
    # programs require near-daily dosing visits, so travel burden directly drives
    # whether someone stays in treatment. It stays gated only because a wrong
    # address here is a safety issue. Run build_sud_candidates.py to assemble the
    # call-down worksheet, verify by phone, then seed_facilities.py.
    "substance_use": {
        "label": "Substance-use treatment",
        "group": "Reproductive & sensitive care",
        "sensitive": True,
        "verification_required": True,
        "hidden": True,  # surfaced via the behavioral_health composite, not alone
        "source": ("MANUAL verification of candidates from SAMHSA N-SUMHSS 2025 "
                   "+ NPPES addiction taxonomies (build_sud_candidates.py)"),
    },
}


def sensitive_keys() -> list[str]:
    return [k for k, v in CATEGORY_REGISTRY.items() if v.get("sensitive")]
