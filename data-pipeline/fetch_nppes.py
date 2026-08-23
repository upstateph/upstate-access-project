#!/usr/bin/env python3
"""Fetch organization facilities from the NPPES NPI Registry (keyless), by taxonomy.

Used for categories the live directories cover as provider taxonomies — pharmacies and
urgent care. NPPES filters by city (not county), so we loop the county's cities, then
geocode and keep only facilities that land inside Greenville County.

Usage:
    python fetch_nppes.py pharmacy "Pharmacy"
    python fetch_nppes.py urgent_care "Urgent Care"
"""
from __future__ import annotations

import sys

import requests

from common import ensure_dirs, PROCESSED_DIR, write_json
from facility_common import build_facility

GREENVILLE_FIPS = "45045"
NPPES_URL = "https://npiregistry.cms.hhs.gov/api/"
# Cities in / around Greenville County (county filter is enforced by geocoding).
CITIES = ["Greenville", "Greer", "Simpsonville", "Mauldin", "Travelers Rest",
          "Fountain Inn", "Taylors", "Piedmont"]

# ── Post-filter ───────────────────────────────────────────────────────────────
# NPPES `taxonomy_description` is a RETRIEVAL filter, not a classification: it
# returns an organization if ANY of its enumerated taxonomies matches, so a broad
# term pulls in unrelated practices. Querying "Counselor" returned a massage
# therapist, a chiropractor, a home-health agency, a cardiology practice, a
# preschool and the county school district. So every record is re-checked here
# against its OWN taxonomy list before it is kept.
#
# EXCLUDE runs before ALLOW and is checked across ALL of a record's taxonomies,
# not just the primary one.
#
# The substance-use exclusion is about CLASSIFICATION, not about leaving SUD out of
# the tool — it belongs in the tool, and `build_sud_candidates.py` populates it.
# Addiction-treatment organizations are routinely co-enumerated under ordinary
# mental-health taxonomies: the "Counselor" query surfaced 12 addiction counselors
# and 16 opioid-treatment-program records whose primary taxonomy was only a generic
# "Clinic/Center". Letting those through would be wrong twice over. It mislabels an
# OTP as "Mental health & therapy" — the same defect as counting a dental site as
# primary care. And because the withholding gate keys on the CATEGORY name, it would
# publish sensitive addresses through a category the gate never inspects, skipping
# the address verification that exists because being seen entering these sites
# carries real consequences.
#
# Rejected records are not discarded: build_sud_candidates.py re-queries these same
# terms to build the substance_use verification worksheet. Keep the two in lockstep.
# "Methadone" and "opioid treatment" were added 23 Aug after METRO TREATMENT OF
# SOUTH CAROLINA — an opioid treatment program already on the substance_use
# candidate list — was found PUBLISHED in the pharmacy category. Its NPPES
# taxonomy is "Clinic/Center, Methadone Clinic", which contains none of the
# original terms. The lesson generalises: this list must match how the taxonomy
# is WORDED, not how the service is described, and a term list is only as good
# as the vocabulary it was written against.
SENSITIVE_TAXONOMY_TERMS = ("addiction", "substance use", "substance abuse",
                            "chemical dependency", "methadone",
                            "opioid treatment")

TAXONOMY_FILTERS: dict[str, dict[str, tuple[str, ...]]] = {
    "dental": {"allow": ("dentist", "dental"),
               "exclude": ("durable medical equipment", "medical supplies")},
    # Eyewear and DME suppliers sell equipment; they are not a care destination.
    "vision": {"allow": ("optometrist", "ophthalmology", "vision therapy"),
               "exclude": ("eyewear supplier", "durable medical equipment",
                           "medical supplies")},
    # Hearing-instrument specialists fit devices and ARE a real destination;
    # "Hearing Aid Equipment" suppliers are not.
    "hearing": {"allow": ("audiolog", "hearing instrument specialist",
                          "hearing and speech"),
                "exclude": ("equipment", "medical supplies")},
    # Added 23 Aug. Both were pulled from NPPES before this filter existed, so
    # they shipped unfiltered — pharmacy carried an opioid treatment program and
    # urgent_care carried a billing company.
    #
    # Mail-order, long-term-care and home-infusion pharmacies are excluded not
    # as data errors but because they are not places a person travels TO, and
    # this tool measures travel. A mail-order pharmacy counted as the nearest
    # pharmacy makes someone's access look better than it is.
    # `not_a_destination` is NOT the same as `exclude`, and conflating them was a
    # real bug: excluding on ANY taxonomy match dropped every chain pharmacy,
    # because a CVS enumerates retail AND long-term-care AND mail-order. The
    # result was 75 pharmacies with no CVS, Walgreens, Publix, Kroger or Walmart
    # — a map missing most of the county's actual pharmacies.
    #
    # So: `exclude` rejects the whole record (safety — an OTP is an OTP whether
    # that taxonomy is primary or fifth). `not_a_destination` merely stops THAT
    # taxonomy from counting as a match, so an organisation still qualifies on
    # any other. A pharmacy that also does mail order is still a pharmacy you
    # can walk into; a mail-order-only pharmacy is not, and is still rejected.
    "pharmacy": {"allow": ("pharmacy",),
                 "exclude": SENSITIVE_TAXONOMY_TERMS,
                 "not_a_destination": ("mail order", "long term care",
                                       "home infusion", "durable medical equipment",
                                       "medical supplies")},
    "urgent_care": {"allow": ("urgent care",),
                    "exclude": SENSITIVE_TAXONOMY_TERMS,
                    "not_a_destination": ("billing", "durable medical equipment",
                                          "medical supplies")},
    "mental_health": {"allow": ("psychologist", "counselor", "social worker",
                                "marriage & family therapist", "mental health",
                                "psychiatry", "psychoanalyst",
                                "community/behavioral health"),
                      "exclude": SENSITIVE_TAXONOMY_TERMS},
}


def _classify(category: str, taxonomies: list[dict]) -> str | None:
    """Return the matched taxonomy description, or None if the record is rejected."""
    rules = TAXONOMY_FILTERS.get(category)
    descs = [(t.get("desc") or "").strip() for t in taxonomies]
    if not rules:
        # Unknown category: keep, but say so — silence here would look like a filter.
        return descs[0] if descs else ""
    lowered = [d.lower() for d in descs]
    # Record-level rejection: one matching taxonomy anywhere condemns the record.
    for d in lowered:
        if any(term in d for term in rules["exclude"]):
            return None
    # Taxonomy-level disqualification: does not condemn the record, only stops
    # this particular taxonomy from being what qualifies it.
    skip = rules.get("not_a_destination", ())
    for desc, d in zip(descs, lowered):
        if any(term in d for term in skip):
            continue
        if any(term in d for term in rules["allow"]):
            return desc
    return None


def fetch_orgs(category: str, taxonomy_desc: str) -> tuple[list[dict], int]:
    """Organizations matching one or more taxonomies (comma-separated).

    ORGANIZATIONS ONLY (enumeration_type=NPI-2), deliberately. NPPES also lists
    individual practitioners (NPI-1), and for solo therapists, counselors and
    optometrists the enumerated "practice location" is frequently a home address.
    Publishing those on a map would expose private residences, so individuals are
    never pulled — the trade-off is that solo practices are missed, which
    undercounts mental-health and vision capacity and must be stated wherever
    those counts appear.
    """
    taxonomies = [t.strip() for t in taxonomy_desc.split(",") if t.strip()]
    seen, raw, rejected = set(), [], 0
    for taxonomy in taxonomies:
        for city in CITIES:
            params = {"version": "2.1", "enumeration_type": "NPI-2", "state": "SC",
                      "city": city, "taxonomy_description": taxonomy, "limit": 200}
            results = requests.get(NPPES_URL, params=params, timeout=60).json().get("results", [])
            for res in results:
                npi = res.get("number")
                if npi in seen:
                    continue
                seen.add(npi)
                matched = _classify(category, res.get("taxonomies", []))
                if matched is None:
                    rejected += 1
                    continue
                loc = next((a for a in res.get("addresses", []) if a.get("address_purpose") == "LOCATION"), None)
                if not loc:
                    continue
                raw.append({
                    "name": (res.get("basic", {}) or {}).get("organization_name", ""),
                    "address": loc.get("address_1", ""), "city": loc.get("city", ""),
                    "state": loc.get("state", "SC"), "zip": (loc.get("postal_code", "") or "")[:5],
                    "phone": loc.get("telephone_number", ""), "taxonomy": matched,
                })
    return raw, rejected


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit('Usage: python fetch_nppes.py <category> "<taxonomy_description>"')
    category, taxonomy = sys.argv[1], sys.argv[2]
    ensure_dirs()

    print(f"Fetching NPPES '{taxonomy}' orgs across {len(CITIES)} cities ...")
    raw, rejected = fetch_orgs(category, taxonomy)
    print(f"  {len(raw)} orgs kept, {rejected} rejected by taxonomy filter; "
          f"geocoding + filtering to Greenville County ...")

    facilities = []
    for r in raw:
        fac = build_facility(category, name=r["name"], address=r["address"], city=r["city"],
                             state=r["state"], zip_code=r["zip"], phone=r["phone"],
                             source="NPPES NPI Registry", keep_county_fips=GREENVILLE_FIPS)
        if fac:
            fac["taxonomy"] = r["taxonomy"]
            facilities.append(fac)

    # Dedupe by (name, address) after geocoding.
    uniq = {(f["name"].lower(), f["address"].lower()): f for f in facilities}
    facilities = sorted(uniq.values(), key=lambda f: f["name"])
    write_json(PROCESSED_DIR / f"facilities_{category}.json",
               {"category": category, "county": "Greenville County",
                "source": "NPPES NPI Registry", "taxonomy": taxonomy, "facilities": facilities},
               label=f"{category} ({len(facilities)})")
    print(f"Done: {len(facilities)} {category} facilities in Greenville County.")


if __name__ == "__main__":
    main()
