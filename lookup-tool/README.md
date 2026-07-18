# lookup-tool/ — Interactive address lookup (Phase 3)

**Status: built.** Tier 2 pilot for Greenville County — address in, access result out,
for a single facility category (launch category **FQHC**).

## Run it

```bash
# from the repo root, with the pipeline venv active (needs `requests`):
python lookup-tool/server.py            # http://localhost:8138
```

Then open the page and enter a Greenville County address. The server wraps
`engine.score()` — geocode → nearest FQHC by **walk, drive, and Greenlink transit**
(≤1 transfer) → optional equity comparison. Walk/drive use real OSRM road-network
routing when reachable (labeled in the result), falling back to the straight-line
estimate.

## Files
- `server.py` — stdlib HTTP server: serves the static UI + a `POST /api/score` JSON API.
- `index.html` / `styles.css` / `app.js` — the front-end.

## Privacy by design (see `docs/privacy-design.md`)
- No accounts, no login.
- The address is sent via **POST body**, never a URL/query string.
- Default request logging is **disabled** — the address is never written to any log.
  (Verified: no address or request path appears in server output.)
- Nothing about the request is persisted.

## Pilot boundary (open decision, spec §10.4)
Facility data currently covers **Greenville County** (`fetch_hrsa_fqhc.py` default).
City limits vs. county vs. Greenlink service area aren't identical; the engine accepts
whatever facility set is pulled, so rescoping is a data-pull change, not a code change.

## Notes
- Transit times use the RAPTOR-style ≤1-transfer model in `engine/transit.py`
  (weekday midday). Walking uses a 3 mph / 1.3× detour estimate. Both are documented
  approximations — see `engine/README.md`.
- The equity comparison needs a Census API key (`fetch_census_acs.py --tracts 45045`);
  until then that section shows how to enable it and the rest of the result still works.
