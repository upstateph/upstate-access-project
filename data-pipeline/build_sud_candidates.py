#!/usr/bin/env python3
"""Build a CALL-DOWN WORKSHEET of substance-use treatment candidates to verify.

People with substance use disorder are squarely in the population this project
exists to serve, and transportation is a documented reason treatment is missed —
opioid treatment programs in particular require near-daily dosing visits, so travel
burden is not an inconvenience for those patients, it is the difference between
staying in treatment and dropping out. So SUD belongs in the tool.

What it does NOT get is a shortcut around verification. `substance_use` is a
safety-sensitive category (spec §6): being seen entering a methadone clinic carries
real consequences, so sending someone to a WRONG address is a safety problem, not a
UX problem. The rule is that a human confirms every address before it is published.

This script therefore does the tedious 80% — assembling candidates from authoritative
public sources — and stops short of the part that requires a person. It writes a
seed CSV with `verified_on` / `verified_by` / `verification_method` left BLANK.
`seed_facilities.py` rejects rows with those blank, by design, so nothing here can
reach the public menu until someone actually makes the calls.

Sources:
  1. SAMHSA N-SUMHSS National Directory of Drug and Alcohol Use Treatment Facilities
     (2025 edition, reflecting the 2024 survey) — state-licensed/certified facilities.
     This is the authoritative list and it carries service codes (OTP, methadone,
     buprenorphine, etc.), which tell you what a site actually does.
     NOTE: findtreatment.gov's live locator API would be fresher, but it is gated
     behind an access-request form and returns zero rows without a key.
  2. NPPES organizations enumerated under addiction taxonomies — catches counseling
     practices that are not state-licensed treatment facilities and so are absent
     from N-SUMHSS. These are exactly the records the mental_health fetch rejects;
     they are routed here rather than discarded.

Usage:
    python build_sud_candidates.py
    # then verify by phone, fill in the three verification columns, and run:
    #   python seed_facilities.py substance_use data-pipeline/seeds/substance_use_candidates.csv
"""
from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

import pandas as pd
import requests

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR))

from fetch_nppes import CITIES, NPPES_URL, SENSITIVE_TAXONOMY_TERMS  # noqa: E402

SAMHSA_XLSX = ("https://www.samhsa.gov/data/sites/default/files/reports/rpt57009/"
               "2025_SU_Facilities_for_All_City_All.xlsx")
SAMHSA_EDITION = "SAMHSA N-SUMHSS National Directory 2025 (2024 survey)"

OUT_CSV = Path(__file__).resolve().parent / "seeds" / "substance_use_candidates.csv"

# City filter, matching the NPPES fetch. Widened slightly: county-line towns whose
# mailing city sits in an adjacent county still serve Greenville County residents,
# and the geocode step at seed time is what actually enforces the county boundary.
COUNTY_CITIES = {c.lower() for c in CITIES} | {"marietta", "slater", "duncan", "pelzer"}

HEADER = ["name", "address", "city", "state", "zip", "phone",
          "verified_on", "verified_by", "verification_method", "_source", "_services"]


def from_samhsa() -> list[dict]:
    resp = requests.get(SAMHSA_XLSX, timeout=120)
    resp.raise_for_status()
    df = pd.read_excel(io.BytesIO(resp.content))
    sc = df[df["state"].astype(str).str.upper().str.strip() == "SC"]
    local = sc[sc["city"].astype(str).str.strip().str.lower().isin(COUNTY_CITIES)]

    rows, skipped = [], 0
    for _, r in local.iterrows():
        street = str(r.get("street1") or "").strip()
        if not street or street.lower() == "nan":
            # A directory row with no street address cannot be verified OR routed.
            # Report it instead of dropping it silently — someone has to chase it.
            skipped += 1
            print(f"  NO ADDRESS, needs manual lookup: {r.get('name1')} ({r.get('city')})")
            continue
        name = str(r.get("name1") or "").strip()
        if str(r.get("name2") or "").strip().lower() not in ("", "nan"):
            name = f"{name} — {str(r['name2']).strip()}"
        rows.append({
            "name": name, "address": street, "city": str(r.get("city") or "").strip(),
            "state": "SC", "zip": str(r.get("zip") or "").strip()[:5],
            "phone": str(r.get("phone") or "").strip(),
            "_source": "SAMHSA N-SUMHSS 2025",
            "_services": str(r.get("service_code_info") or "").strip(),
        })
    if skipped:
        print(f"  ({skipped} SAMHSA row(s) had no street address)")
    return rows


def from_nppes() -> list[dict]:
    """NPPES orgs whose taxonomies indicate addiction treatment.

    Deliberately the same term list the mental_health fetch excludes on, so the two
    stay in lockstep: anything filtered OUT of mental_health for being SUD lands
    HERE as a candidate. If those lists ever drift, records disappear from both.
    """
    seen, rows = set(), []
    for term in ("Addiction", "Substance Use"):
        for city in CITIES:
            params = {"version": "2.1", "enumeration_type": "NPI-2", "state": "SC",
                      "city": city, "taxonomy_description": term, "limit": 200}
            try:
                results = requests.get(NPPES_URL, params=params, timeout=60).json().get("results", [])
            except (requests.RequestException, ValueError) as e:
                print(f"  NPPES query failed for {term}/{city}: {type(e).__name__}")
                continue
            for res in results:
                npi = res.get("number")
                if npi in seen:
                    continue
                descs = [(t.get("desc") or "").lower() for t in res.get("taxonomies", [])]
                if not any(term_ in d for d in descs for term_ in SENSITIVE_TAXONOMY_TERMS):
                    continue
                seen.add(npi)
                loc = next((a for a in res.get("addresses", [])
                            if a.get("address_purpose") == "LOCATION"), None)
                if not loc:
                    continue
                # Query the state, but TRUST the location address. A city+state
                # query matches organizations whose practice location is somewhere
                # else entirely — the "Greenville" queries returned Crossroads sites
                # in Paducah KY, Nashville, Memphis and Knoxville. Stamping "SC" on
                # those would put a dozen out-of-state clinics on a call-down list.
                loc_state = (loc.get("state") or "").strip().upper()
                loc_city = (loc.get("city") or "").strip()
                if loc_state != "SC" or loc_city.lower() not in COUNTY_CITIES:
                    continue
                rows.append({
                    "name": (res.get("basic", {}) or {}).get("organization_name", "").strip(),
                    "address": (loc.get("address_1") or "").strip(),
                    "city": loc_city, "state": loc_state,
                    "zip": (loc.get("postal_code") or "")[:5],
                    "phone": (loc.get("telephone_number") or "").strip(),
                    "_source": f"NPPES NPI {npi}",
                    "_services": "; ".join(t.get("desc", "") for t in res.get("taxonomies", [])),
                })
    return rows


def main() -> None:
    print(f"Pulling {SAMHSA_EDITION} ...")
    samhsa = from_samhsa()
    print(f"  {len(samhsa)} SAMHSA facilities in the Greenville County area")

    print("Pulling NPPES addiction-taxonomy organizations ...")
    nppes = from_nppes()
    print(f"  {len(nppes)} NPPES organizations")

    # Dedupe on street address — the same site is routinely in both sources under
    # different names (a treatment center's legal entity vs its trading name).
    merged: dict[str, dict] = {}
    for row in samhsa + nppes:  # SAMHSA first: it wins on conflict, being licensed data
        key = (row["address"].lower().replace(".", ""), row["zip"])
        if key in merged:
            merged[key]["_source"] += f" + {row['_source']}"
            continue
        merged[key] = row

    rows = sorted(merged.values(), key=lambda r: r["name"].lower())
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=HEADER)
        w.writeheader()
        for r in rows:
            w.writerow({**{k: "" for k in HEADER}, **r})

    print(f"\nWrote {len(rows)} candidates -> {OUT_CSV}")
    print("\nThese are CANDIDATES, not a verified list. Nothing is published yet.")
    print("Next: call each site, confirm the address AND that this specific site")
    print("provides treatment (administrative offices are common in this directory),")
    print("fill verified_on / verified_by / verification_method, then run:")
    print(f"  python seed_facilities.py substance_use {OUT_CSV}")


if __name__ == "__main__":
    main()
