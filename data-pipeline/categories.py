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
    "grocery": {
        "label": "Grocery store (SNAP-accepting)",
        "group": "Public services",
        "sensitive": False,
        # 443 retailers in the county accept SNAP; only 106 of them sell a week of
        # food. The fetcher keeps Supermarket / Super Store / Grocery Store and
        # drops convenience, dollar, specialty and farmers markets. Same principle
        # as fqhc's require_service_line: the authorization is not the service.
        "source": "USDA FNS SNAP Retailer Location data (grocery store types only)",
        "fetch": "fetch_snap_grocery.py",
    },
    # gov_social answers "nearest government office", which is the wrong question
    # when the two offices do different jobs. A housing placement needs to know
    # about benefits enrollment and about work support separately, so these split
    # the same verified list by agency rather than adding a new source.
    "dss": {
        "label": "DSS benefits office (SNAP / Medicaid / TANF)",
        "group": "Public services",
        "sensitive": False,
        "source": "Verified official .gov office list (geocoded), DSS sites only",
        "fetch": "split_gov_social.py",
    },
    "workforce": {
        "label": "Workforce services (SC Works / DEW)",
        "group": "Public services",
        "sensitive": False,
        "source": "Verified official .gov office list (geocoded), DEW sites only",
        "fetch": "split_gov_social.py",
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
    # Added 24 Aug. Ranked first among candidate categories because the burden is
    # structural rather than occasional: three sessions a week, indefinitely, and
    # a missed session is a medical emergency rather than a rescheduled
    # appointment. Medicare covers ESRD regardless of age, so the population
    # skews hard toward the people this project is about. NPPES enumerates it
    # cleanly — 11 organizations county-wide, all unambiguous.
    "dialysis": {
        "label": "Dialysis",
        "group": "Health care",
        "sensitive": False,
        "source": "NPPES NPI Registry (organizations only)",
        "fetch": 'fetch_nppes.py dialysis "End-Stage Renal Disease (ESRD) Treatment"',
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
        "members": ["mental_health", "fqhc_behavioral", "substance_use"],
        "source": ("NPPES NPI Registry + HRSA health center sites + "
                   "SAMHSA N-SUMHSS (verified subset)"),
    },

    # Confirmed by phone 24 Aug: New Horizon provides behavioral health at every
    # fixed site. None of them appear in the 260 NPPES behavioral-health records
    # for this county, because a health center enumerates under a generic FQHC
    # taxonomy rather than a counseling one. So a NPPES-only category silently
    # omits the most reachable behavioral health available to someone uninsured
    # or on Medicaid — a site required to serve them regardless of ability to
    # pay. These sites keep their primary-care role as well; appearing in both
    # categories is correct, not double-counting.
    "fqhc_behavioral": {
        "label": "Community health center — behavioral health",
        "group": "Health care",
        "sensitive": False,
        "hidden": True,
        "require_service_line": "behavioral",
        "source": "HRSA Health Center Service Delivery Sites (phone-verified)",
        "fetch": "fetch_hrsa_fqhc.py",
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
        # "Clinic/Center" added 24 Aug and it is not cosmetic. NPPES retrieval and
        # NPPES classification are different things: a practice enumerated as
        # "Clinic/Center, Mental Health (Including Community Mental Health
        # Center)" was never RETRIEVED by the three practitioner taxonomies, so
        # 78 organizations — 30% of the category — were missing. Amaryllis
        # Counseling is one of them, which is how it surfaced: it was absent from
        # the tool while being an obvious thing to search for.
        #
        # The post-filter already allowed "mental health", so nothing about
        # classification changes; only the retrieval net widens. The broad term
        # also pulls methadone clinics and sleep-disorder centers, which
        # SENSITIVE_TAXONOMY_TERMS and the allow-list reject as before.
        "fetch": ('fetch_nppes.py mental_health '
                  '"Psychologist,Counselor,Social Worker,Clinic/Center"'),
    },

    # ── Registered, but NOT sensitive — they simply have no bulk source ────────
    # Added 24 Aug. Each was checked against NPPES before being scaffolded rather
    # than assumed unavailable, and each failed for a specific reason recorded
    # here so nobody re-runs the same dead end:
    #
    #   free_clinic          "Voluntary or Charitable" returns 12 organizations
    #                        county-wide, of which one is a free clinic and the
    #                        rest are churches, home-care agencies and a
    #                        children's charity. Greenville Free Medical Clinic
    #                        IS in there, so the term is not useless — it is a
    #                        candidate source, not a category.
    #   health_department    "Public Health or Welfare" returns COSTCO, CVS
    #                        PHARMACY and "STATE OF SOUTH CAROLINA". Unusable.
    #   wic                  Absent from NPPES entirely; WIC clinics are a state
    #                        program, not enumerated providers.
    #   community_mental_health
    #                        The taxonomy exists ("Clinic/Center, Mental Health
    #                        (Including Community Mental Health Center)") and 58
    #                        records carry it, but NPPES will not return it as a
    #                        query term — searching the exact string yields zero.
    #                        Reachable only by pulling the broad "Clinic/Center"
    #                        query and post-filtering, which is worth doing but
    #                        is a change to how the fetcher works, not a config.
    #
    # These stay `available: false` until seeded, which the manifest already
    # handles — an unavailable category is absent from the menu rather than
    # offered empty. NOT flagged sensitive: none of them carry the being-seen
    # risk that gates abortion, HIV and substance-use treatment, so they need
    # accurate addresses like anything else, not the verification gate.
    "free_clinic": {
        "label": "Free & charitable clinics",
        "group": "Health care",
        "sensitive": False,
        "source": ("MANUAL — SC Free Clinic Association + NPPES 'Voluntary or "
                   "Charitable' as a candidate source"),
    },
    "health_department": {
        "label": "County health department",
        "group": "Health care",
        "sensitive": False,
        "source": "MANUAL — SC DPH published locations",
    },
    "wic": {
        "label": "WIC clinics",
        "group": "Food & benefits",
        "sensitive": False,
        "source": "MANUAL — SC DPH WIC clinic directory",
    },
    "community_mental_health": {
        "label": "Community mental health centers",
        "group": "Health care",
        "sensitive": False,
        "source": ("MANUAL — SC DMH; or NPPES broad Clinic/Center query with "
                   "post-filter (see note above)"),
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
