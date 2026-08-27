# advocacy/ — Outreach deliverables (Phase 5)

**Status: rebuilt 2026-08-27 around access-only framing.** The pedestrian-safety
brief and its generator moved to `archive/pedestrian-safety-tracker/` when that
analysis left the project (planned as a separate future effort).

```bash
python advocacy/build_brief_pdf.py
```

Produces (regenerated from published data, so figures never drift):

- **`briefs/brief-officials.pdf`** — one-page access brief for elected officials
  (transit reachability map + frequency finding + method and limits).
- **`briefs/brief-partners.pdf`** — the partner/agency variant with equity framing.

Also here, hand-maintained:

- **`greenlink-outreach-draft.md`** — a **DRAFT** note for the Greenlink Transit
  Development Plan team (`GreenlinkTDP@greenvillesc.gov`). Its generator was
  archived with the pedestrian brief; edit it directly and re-check its numbers
  against `dashboard/data/access_rollup_tract_45045.json` after a data refresh.

> ⚠️ Everything in this directory is a **template only**. Nothing is sent
> automatically — a human reviews and sends any external communication.

Inputs: `dashboard/data/access_rollup_tract_45045.json`,
`service_span_tract_45045.json`, `tracts_45045.geojson`, and the cached downtown
example (`data/processed/lookup_example_downtown.json`).
