# Upstate Access Project

A two-tier public health tool for South Carolina.

- **Tier 1 — Statewide pedestrian safety & health-equity tracker.** Pedestrian
  fatality trends and county-level breakdowns (NHTSA FARS), overlaid with Census
  ACS income and race/ethnicity data. Fully public data, no PII.
- **Tier 2 — Greenville County access-lookup engine** *(future phases)*. Address →
  real walk + Greenlink transit time to the nearest facility of a chosen category,
  benchmarked against county averages by income and race.

Built as both a deployable tool for Upstate SC and a portfolio piece. See
[`docs/upstate-access-project-spec.md`](docs/upstate-access-project-spec.md) for the
full technical spec, and [`docs/privacy-design.md`](docs/privacy-design.md) for the
privacy-by-design decisions.

## Status

| Phase | Description | State |
|---|---|---|
| 0 | Repo scaffolding & data acquisition (FARS, Census ACS) | ✅ built |
| 1 | Statewide dashboard (fatality + equity tracker) | ✅ built¹ |
| 2 | Scoring engine core (geocoding + Greenlink GTFS routing) | ✅ geocode + walk + ≤1-transfer transit + equity |
| 3 | Interactive lookup, multi-category | ✅ built (6 service types + sensitive scaffolded) |
| 4 | Aggregated equity rollup (k-anonymity) | ✅ built (k-anon logic + modeled tract rollup + dashboard view) |
| 5 | Advocacy content + outreach package | ✅ built (data-driven brief + Greenlink draft) |

¹ Equity overlay needs a free Census API key (`CENSUS_API_KEY`); the rest runs on FARS.
² Phase 4 ships both the k-anonymity suppression logic (`engine/aggregate.py`, for real
usage) and a modeled tract-level access rollup that feeds a Greenville access page on
the dashboard (`dashboard/greenville-access.html`).

## Repo layout

```
upstate-access-project/
├── data-pipeline/     # scripts to pull/cache FARS, Census ACS (and later GTFS, GIS)
├── engine/            # geocoding + routing + equity scoring (Phase 2)
├── dashboard/         # Tier 1 statewide tracker — static site
├── lookup-tool/       # Tier 2 interactive address lookup (Phase 3)
├── advocacy/          # policy brief templates, outreach drafts (Phase 5)
├── data/
│   ├── raw/           # cached raw pulls (gitignored)
│   └── processed/     # small JSON the dashboard reads (tracked)
└── docs/              # spec, data-source notes, privacy design notes
```

## Quickstart

### 1. Set up the data pipeline

```bash
cd data-pipeline
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Optionally add a free Census API key (recommended for repeated pulls):

```bash
# get one at https://api.census.gov/data/key_signup.html
export CENSUS_API_KEY=your_key_here
```

### 2. Pull and process the data

```bash
python fetch_fars.py             # pedestrian fatalities by SC county, by year
python fetch_county_population.py # county population (keyless) for per-capita rates
python fetch_census_acs.py       # income + race/ethnicity by SC county (needs key)
python build_dashboard_data.py   # join + emit dashboard/data/*.json
```

The county map can be colored by total fatalities, average/yr, or **deaths per 100k
residents** (the per-capita rate works without the Census key, via PEP population).

Raw pulls are cached under `data/raw/`; processed outputs land in `data/processed/`
and are copied into `dashboard/data/` for the site to read.

### 3. View the dashboard

It's a static site — no build step, no server-side code.

```bash
cd dashboard
python3 -m http.server 8000
# open http://localhost:8000
```

### 4. Tier 2 — access-lookup engine (Phase 2)

```bash
cd data-pipeline
python fetch_hrsa_fqhc.py        # FQHC sites for Greenville County -> facilities_fqhc.json
python fetch_greenlink_gtfs.py   # cache the Greenlink GTFS feed

cd ..
# address in -> nearest FQHC by walk + Greenlink transit out
python -m engine.score "206 S Main St, Greenville, SC 29601"
python -m engine.tests.test_walk && python -m engine.tests.test_transit && python -m engine.tests.test_equity

# or run the Phase 3 lookup UI (no address logging):
python lookup-tool/server.py     # http://localhost:8138
```

### 5. Rollup + advocacy (Phases 4–5)

```bash
cd data-pipeline
python fetch_tract_geojson.py    # Greenville tract boundaries (Census TIGERweb)
python fetch_zcta_geojson.py     # Greenville ZIP-code (ZCTA) boundaries
python fetch_census_acs.py --tracts 45045   # tract income/race (needs key)
python fetch_census_acs.py --zctas 45045    # ZIP income/race (needs key)
python build_access_rollup.py    # modeled walk/drive/transit FQHC access, by tract & ZIP
python build_service_span.py     # transit access at 8am / midday / 5pm / Saturday
cd ..
python -m engine.tests.test_aggregate    # k-anonymity suppression logic
python advocacy/generate_brief.py        # policy brief + Greenlink outreach DRAFT
```

### 6. Ongoing analyses

```bash
cd data-pipeline
# De-identified usage telemetry (category + tract + times only; no addresses) accrues
# in data/usage/lookups.jsonl as the lookup tool is used. Roll it up (k-anonymized):
python build_usage_rollup.py     # disable recording with UAP_NO_TELEMETRY=1

# Pharmacy openings/closures over time (run e.g. monthly):
python fetch_nppes.py pharmacy "Pharmacy"   # refresh the list
python pharmacy_trend.py                     # snapshot + diff vs last snapshot
```

The ACS pull also computes **% of households with no vehicle** (B08201) at county,
tract, and ZIP level; re-run `fetch_census_acs.py` (all three variants) and
`build_access_rollup.py` to light up the car-free overlay on the access page and the
lookup tool's equity panel.

The rollup adds a **Greenville access** page to the dashboard
(`dashboard/greenville-access.html`) that can stratify by **census tract or ZIP code**
and color areas by **walk, drive, or transit** time to the nearest FQHC. The advocacy
brief regenerates from data so its figures never drift; the outreach file is a **draft
only** and is never sent.

### 6. Service categories (Phase 3 lookup)

```bash
cd data-pipeline
python fetch_cms_hospitals.py       # hospitals / ERs (CMS)
python fetch_nppes.py pharmacy "Pharmacy"          # pharmacies (NPPES)
python fetch_nppes.py urgent_care "Urgent Care"    # urgent care (NPPES)
python fetch_gov_offices.py         # DSS / DEW-SC Works / SSA (verified)
python fetch_food_assistance.py     # food pantries (verified)
python build_categories_manifest.py # publish the lookup menu
```

The lookup tool serves whatever categories have data. **Safety-sensitive** categories
(abortion, reproductive/women's health, HIV/Ryan White, substance-use treatment) are
**scaffolded but withheld** — they can only be populated from a manually verified CSV
(`seed_facilities.py`, see `data-pipeline/seeds/`) and stay off the public menu until
you clear their `verification_required` flag in `categories.py`. This matches the spec's
rule that a wrong address for these is a safety issue (§6).

## Deploy (beta)

Run the whole stack (dashboard + lookup) with Docker:

```bash
docker compose -f deploy/docker-compose.yml up --build   # -> http://localhost:8000
```

Or serve the static dashboard alone on any static host. See
[`deploy/README.md`](deploy/README.md) for all options, env vars, and privacy notes.

The engine geocodes with the free Census Geocoder (no key), ranks FQHCs by walk and
drive time — using **real OSRM road-network routing** when reachable, falling back to a
straight-line estimate (each result is tagged `routing_method`) — and computes Greenlink
transit time. Set `OSRM_DISABLE=1` to force the estimate, or `OSRM_CAR_URL`/`OSRM_FOOT_URL`
to use your own OSRM. See [`engine/README.md`](engine/README.md) for the models and limits.

## Data sources

See [`docs/data-sources.md`](docs/data-sources.md) for exact endpoints, variable codes,
filenames, and licensing notes for every source.

## License / privacy

No accounts, no logged addresses, aggregated views only. Sensitive destination
categories (substance-use treatment, HIV/Ryan White, reproductive health) are treated
as safety-critical — see the privacy notes before touching Tier 2 data.
