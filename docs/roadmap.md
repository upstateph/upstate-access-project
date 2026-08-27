# Roadmap

> **Scope note (2026-08-27):** the statewide pedestrian-safety tracker described
> in this document was removed from the project and is planned as a separate
> future effort (see `archive/pedestrian-safety-tracker/`). Pedestrian/FARS
> material below is retained as history of the original design.

Where the Upstate Access Project goes from here. Phases are gated, not scheduled —
each one ships when its gate clears, and partner feedback (see
[feedback-log-template.md](feedback-log-template.md)) reorders the backlog inside
each phase.

**Live today:** the public analysis site (statewide pedestrian safety tracker +
Greenville County access page). The address lookup runs in private beta.

---

## Phase A — public launch of the address lookup

*The gap visitors notice first: the public site shows the analysis, not the
"type your address, see how you reach care" tool. That tool exists; it stays
private until routing is self-hosted so home coordinates never touch a
third-party demo server (see [privacy-design.md](privacy-design.md)).*

- Domain name (~$10–12/yr) and a small VPS (~$5–7/mo — SC's road network routes
  comfortably on the cheapest tier).
- Self-hosted OSRM (walk + drive) beside the app: `deploy/docker-compose.prod.yml`
  runs the whole stack; `deploy/osrm/prepare.sh` builds the routing graphs from a
  Geofabrik South Carolina extract. Runbook: [../deploy/README.md](../deploy/README.md).
- HTTPS automatic via Caddy once DNS points at the VPS.

**Gate:** no user coordinate leaves infrastructure we control. Total cost: under
$100/yr.

*Backlog (from feedback):* the "About the address lookup" page should let a visitor
ask to be notified at launch — the first cold visitor came looking for exactly this
tool, and today the page simply turns them away.

## Phase B — verified sensitive categories

Reproductive health, HIV/Ryan White, and substance-use treatment are scaffolded
but withheld. Each goes live only from a manually verified seed list
(`data-pipeline/seeds/`), because a wrong address in these categories is a safety
failure, not a bug.

**Gate (per category):** every address verified by a human; category cleared in
`data-pipeline/categories.py`.

## Phase C — partner feedback loop

After every organization conversation, one entry in the feedback log; entries are
triaged into this roadmap. The de-identified usage rollup
(`build_usage_rollup.py`, k-anonymity ≥ 25) becomes the quantitative complement
once real lookups accumulate: which categories people search, and where transit
fails them.

**Gate:** none — starts with the first conversation and never ends.

## Phase D — beyond Greenville County

The engine is county-parameterized: a new county needs its transit agency's GTFS
feed, a facility pull, and boundary files. Priority order comes from partners
(rural access gaps are often starker than urban ones) rather than from us.

**Gate (per county):** a local partner who wants it and a usable GTFS feed.

## Phase E — community-specific extensions

Same engine, new categories whose defining dataset is community knowledge
(e.g., verified affirming providers). These ship partner-first: local
organizations define the verification criteria, consent is obtained from every
listed provider, and the public-exposure decision is made jointly — the
`public_ready` flag in the category manifest exists for exactly this.

**Gate:** partner organizations own the vetting; no listing without provider
consent.

---

## Standing rules (apply to every phase)

- Privacy design is non-negotiable: no accounts, no address logging, k-anonymity
  on anything published from usage. See [privacy-design.md](privacy-design.md).
- Modeled numbers are labeled modeled, with sources (FARS, ACS vintage, GTFS
  feed date).
- Don't rebuild what exists — new data sources are inputs to the scoring engine,
  not new display layers.
- **Verify user-facing claims on the deployed site, not localhost.** The first
  cold visitor hit two defects that existed only live: orientation copy that was
  written but never deployed, and a "Check an address" link that promised the one
  gated feature. Both were invisible in dev.
- **Never label a link with something the destination can't deliver.** Say what
  the page actually is.
