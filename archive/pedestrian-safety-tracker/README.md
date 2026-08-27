# Pedestrian-safety tracker (archived 2026-08-27)

The Tier 1 statewide pedestrian-safety and health-equity tracker was removed
from the published site on 2026-08-27. It read as tangential next to the access
tool, and two physician reviewers independently misread the access model as
being derived from the crash data. It is planned as a separate, standalone
project at a future date.

What is here: the display layer exactly as it last shipped —
`pedestrian-safety.html`, `app.js`, and the data files only the tracker used
(`dashboard.json`, `crash_corridors_45045.json`, `fars_ped_points_45045.json`).
`sc_counties.geojson` stayed in `dashboard/data/` because it is a pipeline input
(`fetch_zcta_geojson.py` reads it), but `deploy/build_site.py` excludes it and
the three files above from the published site, so a pipeline rerun cannot leak
tracker data back into dist/.

What is NOT here: the data pipeline. `data-pipeline/fetch_fars.py` and the
crash-corridor build scripts still live in `data-pipeline/` and still run; they
just no longer feed anything the site publishes.

Standing constraint that survives the move: the corridor-overlap claim was
publicly withdrawn (see `tools/check_withdrawn_claims.py`). Any revival of this
tracker must not reassert it, and must keep the access model and the crash data
explicitly separate.

Also still referencing the tracker data, deliberately untouched: the legacy
one-file builders `deploy/build_lite.py` / `deploy/build_artifact.py` and the
Phase 5 `advocacy/` brief scripts. They will not run until the pipeline
regenerates `dashboard/data/dashboard.json` (or they are pointed here), and they
are part of the same future project this archive is for.
