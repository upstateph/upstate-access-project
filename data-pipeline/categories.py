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
        # Source changed 3 Sep 2026 from a four-row hand-typed list to the
        # Harvest Hope partner directory, which turned out to be machine-readable
        # behind the Vivery widget on their own site. No coverage_note here on
        # purpose: the fetcher computes one from the data, because the honest
        # version of it counts how many sites publish hours and that number moves.
        "source": "Harvest Hope partner directory via Vivery (api.accessfood.org)",
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
    # Added 3 Sep 2026 at Nikhil's request, alongside day_services below.
    #
    # NOT sensitive, and that is a judgment worth stating rather than assuming.
    # The four sensitive categories all reveal a health condition by the fact of
    # the visit: HIV care, substance-use treatment, abortion, reproductive
    # health. A shelter reveals housing status, which is usually already
    # visible, and its operators advertise their addresses because being found
    # is the point. Marking it sensitive would withhold the whole category until
    # every row had been phone-verified, in a category where the need is acute
    # and the addresses are already published by the people who run them.
    #
    # THE EXCLUSION THAT DOES APPLY IS THE CONFIDENTIAL-ADDRESS ONE, and it is
    # not the same as "shelter". docs/data-sources.md excludes programs that
    # withhold their location to protect the people inside; the test is whether
    # the operator publishes the address themselves, not what kind of shelter it
    # is. A domestic-violence or confidential-placement program is listed by its
    # HOTLINE or not at all, because a phone number is how that service is
    # actually reached: you call, they screen, they place you, and only then are
    # you told where to go. A map pin would misdescribe the access path even if
    # publishing it were safe.
    "shelter": {
        "label": "Shelter (emergency and overnight)",
        "group": "Public services",
        "sensitive": False,
        "source": "MANUAL — operator-published addresses only; see docs/data-sources.md",
    },
    # One category, not five, decided 3 Sep 2026. These services bundle: a day
    # centre routinely offers showers, laundry and a mail drop at one address, so
    # five categories would be five near-identical thin lists and a worse menu.
    # Per-facility `service_lines` already carries which ones a site actually has,
    # the same field fqhc uses, so the distinction survives without the split.
    #
    # NO require_service_line HERE ON PURPOSE. That key filters records OUT at
    # load time, which is right for "FQHCs that do dental" and wrong here: a site
    # offering only a clothing closet still belongs in the list.
    #
    # WARMING CENTRES ARE THE HARD CASE and must not ship as ordinary rows. They
    # are activation-triggered, opening when the temperature drops below a
    # threshold, so a static listing is wrong most of the year and wrong on the
    # night it matters most. That is the locked-door failure the free_clinic
    # coverage_note exists for, with hypothermia attached. Either carry an
    # activation status or say "call first" in the record itself.
    "day_services": {
        "label": "Day services (showers, laundry, mail, clothing)",
        "group": "Public services",
        "sensitive": False,
        "source": "MANUAL — no bulk feed exists; built by hand",
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
        # Seeded 31 Aug 2026 from the SC Free Clinic Association member directory.
        # NPPES was checked first and rejected: its "Voluntary or Charitable"
        # taxonomy returns 12 county organizations, of which one is a free clinic
        # and the rest are churches, home-care agencies and a children's charity.
        # Three of the five county sites are satellites open a single afternoon a
        # week, so every record carries its published hours.
        "source": "Clinic operators' published locations pages (greenvillefreeclinic.org, taylorsfmc.org)",
        "fetch": "fetch_free_clinics.py",
        "coverage_note": (
            "Four of the five sites open only on named days, and two gate entry on "
            "a registration window rather than closing time, so check the hours "
            "before travelling. Taylors takes new patients on Wednesdays from "
            "9:00 to 11:30am only."),
    },
    "health_department": {
        "label": "County health department",
        "group": "Health care",
        "sensitive": False,
        # Seeded 31 Aug 2026 from SC DPH's own clinic directory. ONE site: the
        # other four DPH locations in the county are WIC offices offering nothing
        # else, and listing them here would tell someone they can get
        # immunizations at a WIC office.
        "source": "SC DPH public health clinic directory (dph.sc.gov)",
        "fetch": "fetch_dph_clinics.py",
        "coverage_note": (
            "One county health department, at 352 Halton Road, offering family "
            "planning, immunizations, STD/HIV/Hep C, WIC, PrEP, doxyPEP, TB and "
            "opioid overdose kits. Appointments statewide: (855) 472-3432."),
    },
    "wic": {
        "label": "WIC clinics",
        "group": "Food & benefits",
        "sensitive": False,
        # Seeded 31 Aug 2026 from SC DPH. Days matter more than hours here: WIC
        # requires in-person visits and its participants are disproportionately
        # without a car, so a two-day-a-week office is a different destination.
        "source": "SC DPH public health clinic directory (dph.sc.gov)",
        "fetch": "fetch_dph_clinics.py",
        "coverage_note": (
            "All five SC DPH sites in the county offering WIC. Two open on named "
            "days only: Simpsonville on Mondays and Thursdays, Slater on Tuesdays "
            "and Wednesdays. Appointments statewide: (855) 472-3432."),
    },
    "community_mental_health": {
        "label": "Community mental health centers",
        "group": "Health care",
        "sensitive": False,
        # Seeded 31 Aug 2026 from BHDD, the agency formerly called SCDMH. Kept
        # separate from behavioral_health on purpose: that count is dominated by
        # private practices that take the insurance they choose, while these take
        # Medicaid and the uninsured. For someone without coverage they are not
        # substitutes, and merging them would hide the distinction that decides
        # whether the trip is worth making.
        "source": "SC Dept. of Behavioral Health and Developmental Disabilities (bhdd.sc.gov)",
        "fetch": "fetch_community_mental_health.py",
        "coverage_note": (
            "The three Greater Greenville Mental Health Center clinics, the public "
            "system for the county, which take Medicaid and the uninsured. Private "
            "practices are counted separately under mental health."),
    },

    # ── Safety-sensitive: SCAFFOLDED ONLY, verify before launch (spec §6) ──────
    # These are registered so the framework supports them, but they are NOT
    # auto-populated from scraped data. Each needs a manually verified seed list
    # (see seed_sensitive_category.py and docs/privacy-design.md) before it may be
    # shown to the public. Accuracy here is a safety issue.
# GROUP RENAMED 2 Sep 2026, from "Reproductive & sensitive care".
#
# Evie Suarez-adjacent advice, Queer Wellness Center, in the 2 Sep call: use
# neutral, community-based language rather than anything that denotes an
# identity or flags a section as the sensitive one. Her own phrase was
# "community health resources". Two arguments, and the second was not ours:
#
#   1. Someone can be seen choosing it. A group header reading "sensitive care"
#      discloses before any option is picked, to anyone looking at the screen.
#   2. It is also inaccurate. Conditions like HIV disproportionately affect the
#      queer community but are not exclusive to it, so an identity-adjacent
#      header misdescribes who the services are for while narrowing who feels
#      invited. Same reasoning that renamed reproductive_health away from
#      "Women's / reproductive health" on 31 Aug.
#
# The INDIVIDUAL labels below stay clinically accurate on purpose. Evie's first
# condition for referring a client to this tool was breadth: that whatever they
# need is probably in it and findable. A label vague enough to hide what it is
# fails the person the category exists for, which is a worse trade than the
# exposure it saves. Whether they should soften further is a real question and
# it is hers to answer; it is in the open thread with her rather than decided
# here.
#
# None of this changes what publishes. All four remain withheld pending human
# address verification: 48 of 50 candidate addresses have never been checked by
# a person (docs/sensitive-categories-status.md). Labelling fixes being seen
# choosing; it does nothing about being sent to a wrong address.
    "abortion": {
        "label": "Abortion clinic",
        "group": "Community health resources",
        "sensitive": True,
        "verification_required": True,
        "source": "MANUAL — verify every address before launch",
    },
    "reproductive_health": {
        # Renamed 31 Aug 2026 from "Women's / reproductive health". Trans men and
        # nonbinary people need this care, and a label that says "women's"
        # excludes them at the menu, before the tool has done anything. The
        # abortion category folds in here rather than existing separately: map
        # the place, not the procedure.
        "label": "Reproductive and sexual health",
        "group": "Community health resources",
        "sensitive": True,
        "verification_required": True,
        "source": "MANUAL — verify every address before launch",
    },
    "hiv_ryan_white": {
        "label": "HIV / Ryan White care",
        "group": "Community health resources",
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
        "group": "Community health resources",
        "sensitive": True,
        "verification_required": True,
        "hidden": True,  # surfaced via the behavioral_health composite, not alone
        "source": ("MANUAL verification of candidates from SAMHSA N-SUMHSS 2025 "
                   "+ NPPES addiction taxonomies (build_sud_candidates.py)"),
    },
}


def sensitive_keys() -> list[str]:
    return [k for k, v in CATEGORY_REGISTRY.items() if v.get("sensitive")]
