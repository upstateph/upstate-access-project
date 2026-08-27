# Upstate Access Project — working notes for Claude Code

Public health access tool for Greenville County, SC, built as both a deployable
community tool and a portfolio piece. Full spec: `docs/upstate-access-project-spec.md`.
Privacy decisions: `docs/privacy-design.md`. All six build phases are complete
(see README status table).

- **The tool** — Greenville County address → walk / bike / drive / Greenlink-transit
  time to nearest facility, benchmarked by income and race. Site in `dashboard/`,
  scoring in `engine/`.
- **Removed 2026-08-27:** the Tier 1 statewide pedestrian-safety tracker. It read
  as tangential and confused reviewers; it is planned as a separate future project.
  Display layer + data preserved in `archive/pedestrian-safety-tracker/`; the
  FARS pipeline scripts remain in `data-pipeline/` but feed nothing published.
  Do not reintroduce pedestrian-safety content into the site or outreach copy.

## Running locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r data-pipeline/requirements.txt
python3 dashboard/serve.py 8137          # static site (stdlib only; widget degrades without API)
.venv/bin/python lookup-tool/server.py 8138   # dev API for the lookup (:8137 pages point here)
.venv/bin/python deploy/app_server.py         # or: full production server (dist/ + API, :8000)
```

Gitignored inputs that must be regenerated on a fresh checkout:
`.venv/` and `data/raw/` (run `data-pipeline/fetch_greenlink_gtfs.py` for the
GTFS feed — without it, transit results return "not reachable"). The dashboard's
live equity overlay wants a free Census API key in `CENSUS_API_KEY`.

## Non-negotiables

**Privacy by design.** No accounts, no logging of searched addresses (the lookup
server suppresses request logs deliberately), addresses only in POST bodies,
aggregate outputs k-anonymity-suppressed (`engine/aggregate.py`, threshold
placeholder ~25). Stigma-sensitive categories (reproductive health, HIV care,
substance-use treatment) stay withheld from the UI until every facility address
is manually verified — address accuracy is a safety issue for those categories,
not a UX bug.

**Don't rebuild what exists.** iMap, HRSA/SAMHSA locators, etc. already map
locations. This project's value is computed transit-time access + built-in equity
comparison. New data sources are inputs to the scoring engine, not new display
layers.

## Positioning rules for any public-facing or outreach copy

- Say **"Greenville County"**, not "Greenville".
- Nikhil's Upstate credibility comes from his own roots (family here since 2004,
  back full-time since 2019) — never framed through his employer, which is
  headquartered in Silver Spring, MD, not Greenville.
- For elected-official audiences, lead with access-to-care framing (pedestrian
  safety was removed from the project 2026-08-27 and must not be used as a hook);
  reserve category-specific detail (reproductive health, HIV, SUD) for
  professional and institutional contacts. Never misrepresent the project's scope.
- Modeled numbers are labeled as modeled; cite sources (FARS, ACS vintage, GTFS
  feed date).

Detailed outreach strategy and personal-network context live in a **separate private
repo**, `upstate-access-outreach`, cloned in place at **`./outreach/`** (gitignored,
so this repo never tracks it): the 17 letter drafts, the positioning brief, and
filled partner-feedback logs. They name real people — a neighbor, a family friend,
candid conversation notes — so they are not in this public repo. Never copy their
contents into tracked files here, and never remove `outreach/` from `.gitignore` or
`.dockerignore`.
