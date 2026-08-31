# Data source notes

> **Scope note (2026-08-27):** the statewide pedestrian-safety tracker described
> in this document was removed from the project and is planned as a separate
> future effort (see `archive/pedestrian-safety-tracker/`). Pedestrian/FARS
> material below is retained as history of the original design.

Exact endpoints, filenames, variable codes, and gotchas for every source. Verified
July 2026. Tier 1 (statewide dashboard) uses the first three; the rest are Tier 2.

---

## NHTSA FARS: pedestrian fatalities (Tier 1)

- **Access:** bulk download, **no API key**. Per-year "National CSV" zip:
  `https://static.nhtsa.gov/nhtsa/downloads/FARS/{YEAR}/National/FARS{YEAR}NationalCSV.zip`
- **Latest year:** **2024** (2025 → 404). Works for every year 2014–2024 (~33–35 MB each).
- **File used:** `person.csv`, one row per person. It already carries `STATE` and
  `COUNTY`, so **no join to `accident.csv` is needed** for county counts.
- **Filter for a fatal pedestrian:** `PER_TYP == 5` (pedestrian) **and** `INJ_SEV == 4`
  (fatal) **and** `STATE == 45` (SC). Bicyclist is a separate code (6).
- **County FIPS:** `COUNTY` is a 3-digit county FIPS as an **unpadded integer** (e.g. 19).
  Full 5-digit GEOID = `"45"` + zero-padded 3-digit county (19 → `45019` = Charleston).
  Codes `0` and `997/998/999` are unknown/not-reported, bucketed under `45999`.
- **Gotchas:**
  - Filename casing varies by year (`person.csv` in 2023, `PERSON.CSV` in 2014), so
    match case-insensitively.
  - Select columns **by header name**, not position (positions shift across years).
  - `...NAME` companion columns (`COUNTYNAME`, `PER_TYPNAME`) exist only in newer
    years; we use our own `SC_COUNTIES` map for names instead.
  - Files are **latin-1 / cp1252** encoded, not strict UTF-8.
  - `PER_TYP=5` / `INJ_SEV=4` codes are stable across 2014–2024.
- **CrashAPI** (`crashviewer.nhtsa.dot.gov/CrashAPI`) exists but returns **403 (Akamai)**
  for non-browser/datacenter egress, so **not** usable for an unattended pipeline. Bulk
  CSV is the reliable path; reserve the API as a manual browser cross-check.
- **Sanity check:** 2023 → 187 SC pedestrian fatalities across 37 counties.
- **Script:** [`data-pipeline/fetch_fars.py`](../data-pipeline/fetch_fars.py)

---

## Census ACS 5-Year: income + race/ethnicity (Tier 1 & 2)

- **Latest vintage:** **ACS 2024 5-year** (2020–2024), released Jan 2026.
  Base: `https://api.census.gov/data/2024/acs/acs5`
- **API key now REQUIRED** for every request (as of May 12, 2026 keyless calls
  302-redirect to a missing-key page). Free key:
  `https://api.census.gov/data/key_signup.html`; register with a
  .com/.net/.org/.gov/.edu email, activate via the emailed link, then set
  `CENSUS_API_KEY` in the environment.
- **Variables used:**
  | Code | Meaning |
  |---|---|
  | `B19013_001E` | Median household income (inflation-adj. to vintage year) |
  | `B01003_001E` | Total population |
  | `B02001_001E` | Race, total |
  | `B02001_002E` | White alone |
  | `B02001_003E` | Black or African American alone |
  | `B03003_003E` | Hispanic or Latino (of any race) |
  | `B08201_001E` | Households, total (vehicles available universe) |
  | `B08201_002E` | Households with **no vehicle available** (car-free overlay) |
- **Geography:** `for=county:*&in=state:45` (all SC counties); `--tracts 45045` →
  `for=tract:*&in=state:45 county:045`; `--zctas 45045` → `for=zip code tabulation
  area:<codes>` (ZCTAs don't nest in state/county in ACS 2024, so we query the specific
  ZIP codes from the county's zcta geojson). Feeds the dashboard equity panel and the
  access page's income overlay in both tract and ZIP modes.
- **Example call:**
  `https://api.census.gov/data/2024/acs/acs5?get=NAME,B19013_001E,B01003_001E,B02001_001E,B02001_002E,B02001_003E,B03003_003E&for=county:*&in=state:45&key=YOUR_KEY`
- **Response:** array-of-arrays; row 0 is headers, rest are data rows. Trailing
  `state`,`county` columns are appended automatically. **All values are strings**
  (keep FIPS as strings to preserve leading zeros; cast numbers with `to_numeric`).
- **Sentinels:** `-666666666` (and similar large negatives) mean "not available";
  treat as null, never average in. Handled by `common.clean_census_value`.
- **Script:** [`data-pipeline/fetch_census_acs.py`](../data-pipeline/fetch_census_acs.py)

---

## Census PEP county population (Tier 1, keyless)

- **Access:** static flat CSV, **no API key** (this is *not* the key-gated Data API).
  `https://www2.census.gov/programs-surveys/popest/datasets/2020-2024/counties/totals/co-est2024-alldata.csv`
- **Used for:** per-capita pedestrian-fatality rate on the county map
  (`ped_per_100k_pop` = total deaths ÷ population × 100k). Works without the ACS key.
- **Fields:** `STATE`, `COUNTY` (FIPS parts), `POPESTIMATE2024` (latest vintage).
  Filter `STATE==45`, drop `COUNTY==000` (state total). Read as latin-1.
- **Script:** [`fetch_county_population.py`](../data-pipeline/fetch_county_population.py).

## Census TIGERweb: tract & ZCTA boundaries (Tier 2, keyless)

- **Tracts:** `.../TIGERweb/Tracts_Blocks/MapServer/0/query` filtered by
  `STATE='45' AND COUNTY='045'` → 123 Greenville tracts (GEOID + INTPTLAT/INTPTLON +
  geometry). Script: [`fetch_tract_geojson.py`](../data-pipeline/fetch_tract_geojson.py).
- **ZIP codes (ZCTAs):** `.../TIGERweb/PUMA_TAD_TAZ_UGA_ZCTA/MapServer/1/query`
  over the county bounding box, then kept if the ZCTA internal point falls inside the
  county polygon → 22 ZIPs centered in Greenville. ZCTAs don't nest in counties, so
  this point-in-polygon filter defines "ZIPs of the county."
  Script: [`fetch_zcta_geojson.py`](../data-pipeline/fetch_zcta_geojson.py).
- Both feed the modeled access rollup ([`build_access_rollup.py`](../data-pipeline/build_access_rollup.py)),
  which computes walk / drive / transit access per area for the dashboard access page.

## Smart Growth America: *Dangerous by Design* (Tier 1, framing only)

- Use for **state-ranking context and national framing**, not raw data pulls. The
  report ranks states/metros by a Pedestrian Danger Index (PDI). SC and the
  Greenville metro consistently rank among the most dangerous nationally.
- Stored as editable context in
  [`data-pipeline/context.py`](../data-pipeline/context.py) → `dashboard/data/context.json`,
  so the figure/citation can be updated when a new edition lands. **Verify the exact
  rank and edition year against the current report before publishing**; the values
  in `context.py` are marked as needing confirmation.

---

## OSRM: real road-network walk/drive times (Tier 2)

- **Access:** OSRM *table* service, no key. Public FOSSGIS demo instances support
  car + foot profiles:
  `https://routing.openstreetmap.de/routed-car` and `.../routed-foot`.
  (`https://router.project-osrm.org` is car-only.)
- **Used by:** `engine/osrm.py` → `engine/routing.py`; the interactive lookup and
  `score()` use it by default and fall back to the straight-line estimate when it's
  unreachable. `build_access_rollup.py --osrm` uses it for the bulk rollup (rate-limited).
- **Usage / config:** the public demo asks for light, non-bulk use: **self-host OSRM**
  for anything real and set `OSRM_CAR_URL` / `OSRM_FOOT_URL`. `OSRM_DISABLE=1` forces
  the estimate. Coordinates are **lon,lat** order; durations are seconds, distances meters.
- **Gotcha:** some locked-down TLS stacks (old LibreSSL) can't handshake with these
  hosts via Python `requests`; `osrm.py` transparently falls back to a `curl` subprocess.

## Greenlink GTFS: transit routing (Tier 2)

- **Feed (verified July 2026, no key):** Greenlink's canonical GTFS-static endpoint,
  hosted by AVL vendor Cadavl, the upstream that Transitland / the Mobility Database
  poll (not a mirror). ~800 KB.
  `https://gtfs.greenlink.cadavl.com/GTA/GTFS/GTFS_GTA.zip`
- **Fallback / versioned archive:** Transitland feed `f-dnjq-greenlink`
  (transit.land/feeds/f-dnjq-greenlink). Dead URL; do **not** use
  `https://trackgreenlink.com/gtfs` (405).
- **Freshness:** service span 2026-07-17 → 2027-07-12. 16 routes, ~997 stops, shapes.
  Coverage: Greenville metro incl. Travelers Rest, Greer, Simpsonville, Woodruff.
- **Gotchas:** service is in **`calendar_dates.txt`** (`calendar.txt` is header-only, so
  parse the former). No `feed_info.txt`, so track freshness via HTTP last-modified.
  `transfers.txt` is empty. `agency.txt` has 3 rows (main + Maintenance + Training).
- **Licensing:** no explicit license published; public consumer/routing use. Attribute
  Greenlink; contact them for formal terms.
- **Scripts:** [`fetch_greenlink_gtfs.py`](../data-pipeline/fetch_greenlink_gtfs.py) →
  [`engine/transit.py`](../engine/transit.py).

## HRSA FQHC sites (Tier 2, launch category)

- **Download (verified July 2026, no key):** national "Health Center Service Delivery
  and Look-Alike Sites" CSV (~14 MB, ~18.9k rows).
  `https://data.hrsa.gov/DataDownload/DD_Files/Health_Center_Service_Delivery_and_LookAlike_Sites.csv`
- **Coordinates:** `Geocoding Artifact Address Primary X Coordinate` = **lon**,
  `...Y Coordinate` = **lat**.
- **County filter:** use **`Complete County Name`** (`County Description` is a junk
  padded field). Greenville County → 12 raw rows → **7** after filtering.
- **Keep real brick-and-mortar sites:** `Site Status Description == Active` AND
  `Health Center Type Description ∈ {Service Delivery Site, Administrative/Service
  Delivery Site}` (drop pure `Administrative`) AND `Health Center Location Type
  Description == Permanent` (drop `Mobile Van` / `Seasonal`, no fixed destination).
- **Look-Alikes:** `Health Center Type` distinguishes FQHC vs `FQHC Look-Alike`
  (Greenville has 1: Unity Health On Main). Included by default; `--exclude-lookalikes`
  to drop.
- **Script:** [`fetch_hrsa_fqhc.py`](../data-pipeline/fetch_hrsa_fqhc.py) →
  `data/processed/facilities_fqhc.json`.

## Additional service categories (Tier 2 lookup, keyless)

HIFLD Open was **deactivated Aug 2025**; the live keyless replacements return addresses
only, so we geocode them via the Census Geocoder and keep facilities that land inside
Greenville County (`county_fips == 45045`).

| Category | Source (verified 2026) | Endpoint / basis | Notes |
|---|---|---|---|
| Hospitals / ER | CMS "Hospital General Information" (`xubh-q36u`) | `data.cms.gov/provider-data/api/1/datastore/query/xubh-q36u/0` filtered `state=SC`, `countyparish=GREENVILLE` | Has `emergency_services` flag; no lat/lon → geocode. `fetch_cms_hospitals.py` |
| Pharmacy | NPPES NPI Registry (orgs) | `npiregistry.cms.hhs.gov/api` `enumeration_type=NPI-2`, `taxonomy_description=Pharmacy`, looped over county cities | No county filter → geocode + filter. `fetch_nppes.py` |
| Urgent care | NPPES NPI Registry (orgs) | same, `taxonomy_description=Urgent Care` | same. `fetch_nppes.py` |
| Government / social services | Official .gov directories (SC DSS, SC Works/SCDEW, SSA) | curated verified list, geocoded | `fetch_gov_offices.py` |
| Food assistance | 211 / Harvest Hope (no open API) | curated verified list, geocoded | `fetch_food_assistance.py`; expand manually |

**Safety-sensitive categories** (abortion, reproductive/women's health, HIV/Ryan White,
substance-use treatment) are **not** sourced from any of these; they are populated only
from manually verified CSVs via `seed_facilities.py` and withheld from the public menu
until verified. See `docs/privacy-design.md` and `data-pipeline/seeds/README.md`.

The category registry (labels, sensitivity) lives in `data-pipeline/categories.py`;
`build_categories_manifest.py` publishes `dashboard/data/categories.json`, which the
lookup menu reads.

## Legacy Tier 2 sources (later phases: see spec §4)

| Source | Provides | Notes |
|---|---|---|
| Greenville City GIS Hub (gis.greenvillesc.gov) | Bus stops, essential-services layers | 140+ layers; check licensing per layer |
| Greenville County GIS (gcgis.org) | Parcel/address, boundary, demographics | Some free, some paid |
| SAMHSA treatment locator | Substance-use treatment sites | Less structured; may need scraping |
| Ryan White / SC DHEC | HIV care providers | Fragmented; verify each manually |
| Planned Parenthood / women's health | Reproductive health sites | Verify addresses directly, safety-critical |

## Listing exclusions: what never goes in a category, and why

A locator's job is to send someone to a place that provides what they came for.
Two kinds of facility are therefore excluded permanently, regardless of how well
their address checks out. The objection is what the facility *is*, not whether
the data about it is correct, so a verification record does not override it.

**1. Facilities that do not provide the category's service but rank as if they
do.** The clearest case is a crisis pregnancy center listed under reproductive
health. These centers do not provide contraception, abortion, or prenatal
medical care, but they are named and optimized to surface in searches for
clinics that do. Someone seeking time-sensitive care who is routed to one loses
time they may not have. The test is not the facility's viewpoint; it is whether
a person arriving for the category's service would receive it.

**2. Programs whose address is confidential.** Domestic-violence shelters and
similar programs withhold their locations to protect the people inside.
Publishing a computed walking route to one would defeat that protection, and
"the address was already findable elsewhere" does not justify amplifying it.

**3. Facilities that serve only their own patients.** A health center's in-house
pharmacy, a clinic's internal dispensary: real facilities, at real addresses,
that a member of the public cannot walk into with an outside prescription. No
taxonomy expresses this. The federal registry enumerates an in-house pharmacy as
"Pharmacy, Community/Retail Pharmacy", the same code a chain drugstore carries,
because that code describes dispensing to walk-ins rather than *whose* walk-ins.
Counting one as a destination overstates access exactly where it is thinnest: in
one county test the nearest pharmacy was reported at a **0.0-minute walk** when
the true nearest usable one was **57 minutes** on foot. This is the same
reasoning that already excludes mail-order and long-term-care-only pharmacies,
and it can only be resolved by asking the operator.

**Enforcement.** The rule is a gate, not a memo: `seed_facilities.py` and
`fetch_nppes.py` both read a local exclusion list
(`data-pipeline/seeds/exclusions.csv`) and drop matching rows *before*
verification and geocoding, printing what they dropped and why. Both paths honor
it deliberately: an organization kept out of manual seeding could otherwise walk
straight back in through a taxonomy query, which is what happened with the
in-house pharmacies above. That
list names specific organizations and stays local with the seed CSVs it governs
and this document holds the policy, which is meant to be public and arguable;
naming a particular local organization in a public repo is a different act, and
not one this project needs to perform in order to route people correctly.

**Adding an exclusion** is a safety decision: record a reason another person
could evaluate, and prefer excluding to guessing. If a facility is merely
uncertain, unclear services, stale listing, that is a verification question,
not an exclusion; call them.
