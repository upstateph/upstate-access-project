# Data source notes

Exact endpoints, filenames, variable codes, and gotchas for every source. Verified
July 2026. Tier 1 (statewide dashboard) uses the first three; the rest are Tier 2.

---

## NHTSA FARS — pedestrian fatalities (Tier 1)

- **Access:** bulk download, **no API key**. Per-year "National CSV" zip:
  `https://static.nhtsa.gov/nhtsa/downloads/FARS/{YEAR}/National/FARS{YEAR}NationalCSV.zip`
- **Latest year:** **2024** (2025 → 404). Works for every year 2014–2024 (~33–35 MB each).
- **File used:** `person.csv` — one row per person. It already carries `STATE` and
  `COUNTY`, so **no join to `accident.csv` is needed** for county counts.
- **Filter for a fatal pedestrian:** `PER_TYP == 5` (pedestrian) **and** `INJ_SEV == 4`
  (fatal) **and** `STATE == 45` (SC). Bicyclist is a separate code (6).
- **County FIPS:** `COUNTY` is a 3-digit county FIPS as an **unpadded integer** (e.g. 19).
  Full 5-digit GEOID = `"45"` + zero-padded 3-digit county (19 → `45019` = Charleston).
  Codes `0` and `997/998/999` are unknown/not-reported — bucketed under `45999`.
- **Gotchas:**
  - Filename casing varies by year (`person.csv` in 2023, `PERSON.CSV` in 2014) —
    match case-insensitively.
  - Select columns **by header name**, not position (positions shift across years).
  - `...NAME` companion columns (`COUNTYNAME`, `PER_TYPNAME`) exist only in newer
    years — we use our own `SC_COUNTIES` map for names instead.
  - Files are **latin-1 / cp1252** encoded, not strict UTF-8.
  - `PER_TYP=5` / `INJ_SEV=4` codes are stable across 2014–2024.
- **CrashAPI** (`crashviewer.nhtsa.dot.gov/CrashAPI`) exists but returns **403 (Akamai)**
  for non-browser/datacenter egress — **not** usable for an unattended pipeline. Bulk
  CSV is the reliable path; reserve the API as a manual browser cross-check.
- **Sanity check:** 2023 → 187 SC pedestrian fatalities across 37 counties.
- **Script:** [`data-pipeline/fetch_fars.py`](../data-pipeline/fetch_fars.py)

---

## Census ACS 5-Year — income + race/ethnicity (Tier 1 & 2)

- **Latest vintage:** **ACS 2024 5-year** (2020–2024), released Jan 2026.
  Base: `https://api.census.gov/data/2024/acs/acs5`
- **API key now REQUIRED** for every request (as of May 12, 2026 keyless calls
  302-redirect to a missing-key page). Free key:
  `https://api.census.gov/data/key_signup.html` — register with a
  .com/.net/.org/.gov/.edu email, activate via the emailed link, then set
  `CENSUS_API_KEY` in the environment.
- **Variables used:**
  | Code | Meaning |
  |---|---|
  | `B19013_001E` | Median household income (inflation-adj. to vintage year) |
  | `B01003_001E` | Total population |
  | `B02001_001E` | Race — total |
  | `B02001_002E` | White alone |
  | `B02001_003E` | Black or African American alone |
  | `B03003_003E` | Hispanic or Latino (of any race) |
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
- **Sentinels:** `-666666666` (and similar large negatives) mean "not available" —
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

## Census TIGERweb — tract & ZCTA boundaries (Tier 2, keyless)

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

## Smart Growth America — *Dangerous by Design* (Tier 1, framing only)

- Use for **state-ranking context and national framing**, not raw data pulls. The
  report ranks states/metros by a Pedestrian Danger Index (PDI). SC and the
  Greenville metro consistently rank among the most dangerous nationally.
- Stored as editable context in
  [`data-pipeline/context.py`](../data-pipeline/context.py) → `dashboard/data/context.json`,
  so the figure/citation can be updated when a new edition lands. **Verify the exact
  rank and edition year against the current report before publishing** — the values
  in `context.py` are marked as needing confirmation.

---

## OSRM — real road-network walk/drive times (Tier 2)

- **Access:** OSRM *table* service, no key. Public FOSSGIS demo instances support
  car + foot profiles:
  `https://routing.openstreetmap.de/routed-car` and `.../routed-foot`.
  (`https://router.project-osrm.org` is car-only.)
- **Used by:** `engine/osrm.py` → `engine/routing.py`; the interactive lookup and
  `score()` use it by default and fall back to the straight-line estimate when it's
  unreachable. `build_access_rollup.py --osrm` uses it for the bulk rollup (rate-limited).
- **Usage / config:** the public demo asks for light, non-bulk use — **self-host OSRM**
  for anything real and set `OSRM_CAR_URL` / `OSRM_FOOT_URL`. `OSRM_DISABLE=1` forces
  the estimate. Coordinates are **lon,lat** order; durations are seconds, distances metres.
- **Gotcha:** some locked-down TLS stacks (old LibreSSL) can't handshake with these
  hosts via Python `requests`; `osrm.py` transparently falls back to a `curl` subprocess.

## Greenlink GTFS — transit routing (Tier 2)

- **Feed (verified July 2026, no key):** Greenlink's canonical GTFS-static endpoint,
  hosted by AVL vendor Cadavl — the upstream that Transitland / the Mobility Database
  poll (not a mirror). ~800 KB.
  `https://gtfs.greenlink.cadavl.com/GTA/GTFS/GTFS_GTA.zip`
- **Fallback / versioned archive:** Transitland feed `f-dnjq-greenlink`
  (transit.land/feeds/f-dnjq-greenlink). Dead URL — do **not** use
  `https://trackgreenlink.com/gtfs` (405).
- **Freshness:** service span 2026-07-17 → 2027-07-12. 16 routes, ~997 stops, shapes.
  Coverage: Greenville metro incl. Travelers Rest, Greer, Simpsonville, Woodruff.
- **Gotchas:** service is in **`calendar_dates.txt`** (`calendar.txt` is header-only —
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
  Description == Permanent` (drop `Mobile Van` / `Seasonal` — no fixed destination).
- **Look-Alikes:** `Health Center Type` distinguishes FQHC vs `FQHC Look-Alike`
  (Greenville has 1: Unity Health On Main). Included by default; `--exclude-lookalikes`
  to drop.
- **Script:** [`fetch_hrsa_fqhc.py`](../data-pipeline/fetch_hrsa_fqhc.py) →
  `data/processed/facilities_fqhc.json`.

## Other Tier 2 sources (later phases — see spec §4)

| Source | Provides | Notes |
|---|---|---|
| Greenville City GIS Hub (gis.greenvillesc.gov) | Bus stops, essential-services layers | 140+ layers; check licensing per layer |
| Greenville County GIS (gcgis.org) | Parcel/address, boundary, demographics | Some free, some paid |
| SAMHSA treatment locator | Substance-use treatment sites | Less structured; may need scraping |
| Ryan White / SC DHEC | HIV care providers | Fragmented; verify each manually |
| Planned Parenthood / women's health | Reproductive health sites | Verify addresses directly — safety-critical |
