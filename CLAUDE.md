# Upstate Access Project — working notes for Claude Code

Two-tier public health tool for South Carolina, built as both a deployable
community tool and a portfolio piece. Full spec: `docs/upstate-access-project-spec.md`.
Privacy decisions: `docs/privacy-design.md`. All six build phases are complete
(see README status table).

- **Tier 1** — statewide pedestrian safety & health-equity tracker (NHTSA FARS +
  Census ACS). Static site in `dashboard/`.
- **Tier 2** — Greenville County address → walk / drive / Greenlink-transit time
  to nearest facility, benchmarked by income and race. UI in `lookup-tool/`,
  scoring in `engine/`.

## Running locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r data-pipeline/requirements.txt
python3 dashboard/serve.py 8137          # Tier 1 dashboard (static, stdlib only)
.venv/bin/python lookup-tool/server.py 8138   # Tier 2 lookup UI + /api/score
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
- For elected-official audiences, lead with pedestrian safety and access-to-care
  framing; reserve category-specific detail (reproductive health, HIV, SUD) for
  professional and institutional contacts. Never misrepresent the project's scope.
- Modeled numbers are labeled as modeled; cite sources (FARS, ACS vintage, GTFS
  feed date).

Detailed outreach strategy and personal-network context now live in a **separate
private repo**, `upstate-access-outreach` (checked out alongside this one at
`../upstate-access-outreach`): the 17 letter drafts, the positioning brief, and
filled partner-feedback logs. They name real people — a neighbor, a family friend,
candid conversation notes — so they are not in this public repo. Never copy their
contents into tracked files here.
