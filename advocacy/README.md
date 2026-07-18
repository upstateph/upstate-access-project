# advocacy/ — Policy brief + outreach package (Phase 5)

**Status: built.** Generates advocacy deliverables from real pipeline data.

```bash
python advocacy/generate_brief.py
```

Produces (regenerated from data, so figures never drift):

- **`policy-brief.md`** — a short, cited brief tying SC pedestrian-danger figures
  (NHTSA FARS + Dangerous by Design) to the Greenville FQHC access findings (Phase 4
  rollup), with recommendations and a method/caveats section.
- **`greenlink-outreach-draft.md`** — a **DRAFT** note for the Greenlink Transit
  Development Plan team (`GreenlinkTDP@greenvillesc.gov`).

> ⚠️ The outreach file is a **template only**. Nothing is sent automatically — a human
> reviews and sends any external communication. The generator only writes local files.

Inputs: `data/processed/dashboard.json` (Phase 1) and
`data/processed/access_rollup_45045.json` (Phase 4). Run those pipelines first.

Local plan documents feed the narrative directly (spec §5): Greenlink's 2026 Transit
Development Plan and the city's Pedestrian Safety Action Plan.
