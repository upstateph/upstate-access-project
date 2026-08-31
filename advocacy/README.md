# advocacy/: Outreach deliverables (Phase 5)

**Status: rebuilt 2026-08-27 around access-only framing.** The pedestrian-safety
brief and its generator moved to `archive/pedestrian-safety-tracker/` when that
analysis left the project (planned as a separate future effort).

```bash
python advocacy/build_brief_pdf.py
```

Produces (regenerated from published data, so figures never drift):

- **`briefs/brief-officials.pdf`**: one-page access brief for elected officials
  (transit reachability map + frequency finding + method and limits).
- **`briefs/brief-partners.pdf`**: the partner/agency variant with equity framing.

Also here, hand-maintained:

- **`greenlink-outreach-draft.md`**: a **DRAFT** note for the Greenlink Transit
  Development Plan team (`GreenlinkTDP@greenvillesc.gov`). Its generator was
  archived with the pedestrian brief; edit it directly and re-check its numbers
  against `dashboard/data/access_rollup_tract_45045.json` after a data refresh.

> ⚠️ Everything in this directory is a **template only**. Nothing is sent
> automatically; a human reviews and sends any external communication.

Inputs: `dashboard/data/access_rollup_tract_45045.json`,
`service_span_tract_45045.json`, `tracts_45045.geojson`, and the cached downtown
example (`data/processed/lookup_example_downtown.json`).

## flyers/: patient-facing, added 29 Aug 2026

```bash
python advocacy/build_flyer.py               # clinic wall / counter
python advocacy/build_flyer.py --tabs        # community board, tear-off strip
python advocacy/build_flyer.py --lang es     # ⚠️ UNREVIEWED, see below
```

Five partner letters promise this flyer and the plan for reaching Medicaid
patients depends on it. Deliberate decisions worth not undoing:

- **It carries the GitHub Pages URL, not the beta.** Print cannot be edited.
  Pages is permanent and repointable; the beta URL is not ours to guarantee.
  Pages shows one "Check my address" button through to the working tool.
- **A QR code is the primary call to action**, with the URL printed for
  anyone whose camera will not scan. Nobody types 42 characters off a wall.
- **Tear-off tabs are OFF by default.** A clinic wall wants a clean sheet;
  tabs suit libraries, laundromats, and community boards.
- **The Spanish version has not been reviewed by a native speaker.** Do not
  print it until someone has read it. A clumsy translation on a health flyer
  says the audience was an afterthought, which is worse than English only.
