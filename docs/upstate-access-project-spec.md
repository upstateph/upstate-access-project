# Upstate Access Project — Technical Spec & Build Plan

> **Scope note (2026-08-27):** the statewide pedestrian-safety tracker described
> in this document was removed from the project and is planned as a separate
> future effort (see `archive/pedestrian-safety-tracker/`). Pedestrian/FARS
> material below is retained as history of the original design.

**Working name:** Upstate Access Project
**Author:** Nikhil Jain, DO, MPH
**Purpose of this document:** Kickoff spec for building this in Claude Code. Covers scope, data sources, architecture, build order, and open decisions.

---

## 1. Project summary

A two-tier public health tool for South Carolina:

- **Statewide tier:** a pedestrian safety and health-equity tracker, using public fatality and demographic data.
- **Greenville County pilot tier:** an address-based access lookup that answers "can a person at this address actually reach [a category of care], how long does it really take by foot or transit, and how does that compare to other people in the county by income and race."

The project is meant to serve two purposes equally: a real, deployable tool for Upstate SC, and a portfolio piece demonstrating public health policy fluency, data/technical build skill, and thoughtful equity- and privacy-by-design thinking.

---

## 2. Why this isn't redundant

Greenville already has resource-mapping tools (Greenville County's iMap, HRSA's health center locator, SAMHSA's treatment locator, Ryan White provider directories, Planned Parenthood's own locator). None of them compute real transit-time access or tie it to equity data. This project's differentiators:

1. **Real transit-time computation** from Greenlink's GTFS feed (walk + wait + ride + transfer), not a static pin on a map.
2. **Built-in equity comparison** — every result is benchmarked against county averages by income and race, not left as a separate report.
3. **Policy feedback loop** — aggregated findings are structured to be shared directly with Greenlink (contact: GreenlinkTDP@greenvillesc.gov) once the pilot has real results.
4. **Privacy-by-design** — no accounts, no logged addresses, k-anonymity threshold on all aggregated views. This matters specifically because several destination categories (substance use treatment, HIV/Ryan White care, reproductive health) carry real stigma and safety risk if searches were ever tied to an identity.

Existing tools (iMap, GIS layers) should be treated as **data inputs**, not competitors — reuse their underlying location data rather than re-collecting it.

---

## 3. Scope & tiers

### Tier 1: Statewide pedestrian safety & equity tracker
- Pedestrian fatality trend and state ranking (grounded in NHTSA FARS + Smart Growth America's Dangerous by Design report)
- County-level breakdown, overlaid with Census ACS income and race/ethnicity data
- No PII, no address-level data — lower complexity, good first deliverable

### Tier 2: Greenville County pilot — access lookup engine
- Address input → geocode → compute time to nearest facility of a chosen category via walk and via Greenlink transit (with wait/transfer time)
- Single category per lookup for the trial version (see Section 10 for which category to launch with)
- Categories to eventually support: FQHCs, substance use treatment, HIV/Ryan White care, women's health (including reproductive health), plus bus stops, food pantries, and other essential services as inputs/additional categories once the core engine is proven
- Aggregated, anonymized rollup feeds back into the Tier 1 dashboard's equity panel

---

## 4. Data sources

| Source | Provides | Tier | Notes |
|---|---|---|---|
| NHTSA FARS | Pedestrian crash/fatality records | 1 | Public, county-level |
| Smart Growth America, Dangerous by Design (2026) | State rankings, national context | 1 | Use for framing/validation, not raw data pulls |
| Census ACS | Income, race/ethnicity by tract | 1 & 2 | Standard Census API |
| Greenlink GTFS feed | Transit routes, stops, schedules | 2 | Powers real transit-time computation |
| Greenville City GIS Hub (gis.greenvillesc.gov) | Bus stops, essential services layers | 2 | 140+ layers, some public; check licensing per layer |
| Greenville County GIS portal (gcgis.org) | Parcel/address, boundary, demographic layers | 2 | Some free, some paid |
| HRSA Find a Health Center API | FQHC locations | 2 | Cleanest, most complete public dataset — good MVP category |
| SAMHSA treatment locator | Substance use treatment facility locations | 2 | Less structured; may need scraping or manual seed list |
| Ryan White HRSA / SC DHEC | HIV/Ryan White provider locations | 2 | Fragmented; verify each provider manually before launch |
| Planned Parenthood / women's health locators | Reproductive health facility locations | 2 | Verify addresses directly; accuracy is safety-critical here |

---

## 5. System architecture

```
[FARS] [Census ACS] [Greenlink GTFS] [GIS layers: care sites, bus stops, pantries]
                          ↓
                 Scoring engine
   (geocodes address, computes route/time, joins demographics)
                          ↓
        ┌─────────────────┼─────────────────┐
   Interactive lookup   Statewide dashboard   Advocacy content
   (Greenville pilot)   (trends + equity)     (brief + templates)
        └── aggregated, anonymized data rolls up into dashboard equity panel
```

Local plan documents (Greenlink's 2026 Transit Development Plan, the city's Pedestrian Safety Action Plan) feed the advocacy content layer directly, bypassing the scoring engine.

---

## 6. Privacy & ethics by design

- No user accounts, no login required
- No server-side logging of searched addresses
- Aggregated views only, never individual-level
- **k-anonymity threshold:** suppress any tract-level stat computed from fewer than ~25 lookups (tune this number once real usage volume is known)
- Be especially careful with reproductive health and HIV/Ryan White facility data — verify every address before launch; an error here is a safety issue, not just a UX bug

---

## 7. Build order

**Phase 0 — Repo scaffolding & data acquisition**
Set up the repo structure (Section 8). Write scripts to pull and cache FARS, Census ACS, and the Smart Growth America context data. No PII involved — safe starting point.

**Phase 1 — Statewide dashboard**
Build the fatality/equity tracker first. Fully public data, no geocoding or routing complexity, gives you a working, demoable piece early.

**Phase 2 — Scoring engine core**
Geocoding + Greenlink GTFS routing (walk + wait + transfer time). This is the hardest technical piece — isolate it so it can be tested independently before wiring it into any UI.

**Phase 3 — Interactive lookup, single category**
Wire the scoring engine to one facility category (recommend FQHC — see Section 10) with a simple address-in, result-out UI.

**Phase 4 — Aggregated equity rollup**
Add the k-anonymity logic and feed rolled-up results into the Tier 1 dashboard's equity panel.

**Phase 5 — Advocacy content + outreach package**
Policy brief generator pulling from Phases 1 and 4. Prepare a short findings summary suitable for the Greenlink conversation once real data exists.

---

## 8. Suggested repo structure

```
upstate-access-project/
├── data-pipeline/        # scripts to pull/cache FARS, Census, GTFS, GIS layers
├── engine/                # geocoding + routing + equity scoring logic
├── dashboard/             # Tier 1 statewide tracker (frontend + any backend)
├── lookup-tool/           # Tier 2 interactive address lookup (frontend + backend)
├── advocacy/              # policy brief templates, comment/outreach drafts
├── data/                  # cached/processed datasets (gitignore raw pulls if large)
└── docs/
    └── this spec, data source notes, privacy design notes
```

---

## 9. Tech stack suggestions

- **Data pipeline:** Python — `pandas` for Census/FARS, a GTFS library (e.g. `gtfs-kit` or `partridge`) for Greenlink parsing, a geocoding library or API for address lookups
- **Scoring engine:** Python service exposing a simple function/API: address in → access results out
- **Frontend:** keep it simple for a pilot — a lightweight web app is enough; no need for a heavy framework unless you want the practice
- **Hosting:** for a pet project, a static site plus a small serverless function for the lookup is the lowest-maintenance option

Leave final tech choices to Claude Code's judgment during the build — this section is guidance, not a hard requirement.

---

## 10. Open decisions to confirm before/during build

1. **Which category to launch the Tier 2 trial with.** Recommendation: **FQHCs** — HRSA's data is the cleanest and most complete of the four, and it's the least politically sensitive, so it's the fastest path to proving the engine end-to-end. Substance use treatment, HIV/Ryan White, and women's health can follow once the pipeline is validated.
2. Exact k-anonymity suppression threshold (25 is a placeholder).
3. Hosting/deployment choice.
4. Whether the Greenville pilot boundary should follow city limits, county limits, or Greenlink's actual service area (these aren't identical).

---

## 11. Portfolio narrative

What this project demonstrates, for interviews or applications:
- Translating fragmented public data (FARS, Census, GTFS, HRSA/SAMHSA/Ryan White) into a single decision-useful tool
- Equity analysis grounded in real disparity data, not just described in prose
- Privacy- and stigma-aware design for sensitive health categories
- A direct line from analysis to policy action (the Greenlink relationship)
- Full-stack build ability, from data pipeline to public-facing product
