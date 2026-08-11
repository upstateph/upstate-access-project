# Deploying the Upstate Access Project

The app has two parts:

- **Static site** — the statewide dashboard + the Greenville access map. Pure static
  files; hostable anywhere.
- **Lookup API** — `POST /api/score` + `GET /api/categories`, wrapping the Python
  engine (geocoding, walk/drive/transit routing). Needs a running process.

`deploy/app_server.py` serves **both** from one process, which is the simplest way to
run the whole thing.

## Production (Phase A): VPS + domain + self-hosted OSRM

The full public-launch runbook (docs/roadmap.md Phase A). One-time cost: a domain
(~$10–12/yr) and any small VPS (~$5–7/mo, 2 GB RAM) with Docker installed.

```bash
# on the VPS, from the repo root:
bash deploy/osrm/prepare.sh          # one-time: build SC walk+drive routing graphs
# point your domain's A record at this host, then:
DOMAIN=yourdomain.org docker compose -f deploy/docker-compose.prod.yml up -d --build
# → https://yourdomain.org  (HTTPS is automatic via Caddy/Let's Encrypt)
```

This runs the app with **routing on-box** (`OSRM_CAR_URL`/`OSRM_FOOT_URL` point at
the bundled OSRM containers), which is the privacy gate for making the address
lookup public: no user coordinate leaves the host. The Census geocoder remains the
one disclosed external call. To refresh the routing graphs after an OSM update,
re-run `prepare.sh` and restart the two osrm containers.

## Option A — Docker (local full stack)

```bash
# from the repo root
docker compose -f deploy/docker-compose.yml up --build
# → http://localhost:8000   (dashboard at /, address lookup at /lookup/)
```

The image installs deps, fetches the Greenlink GTFS feed, publishes the category
manifest, builds `dist/`, and runs `app_server.py`. Committed data (FARS, ACS equity,
facility locations) is baked in, so it works out of the box.

**Environment variables** (all optional — see `docker-compose.yml`):
- `CENSUS_API_KEY` — only to *refresh* ACS equity data; committed data already works.
- `OSRM_CAR_URL` / `OSRM_FOOT_URL` — point at **your own OSRM** for real routing at
  scale (the public demo is fine for a pilot but asks for light use).
- `OSRM_DISABLE=1` — use straight-line estimates only (no outbound routing calls).

## Option B — run the server directly (no Docker)

```bash
cd data-pipeline && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python fetch_greenlink_gtfs.py           # one-time: cache the transit feed
cd .. && python data-pipeline/build_categories_manifest.py
python deploy/build_site.py              # -> dist/
PORT=8000 python deploy/app_server.py    # -> http://localhost:8000
```

Put it behind nginx/Caddy for TLS, or run under systemd / a process manager. The server
is threaded stdlib HTTP — fine for a pilot; front it with a real reverse proxy for
production traffic.

## Option C — static dashboard only (no lookup)

The `dist/` folder minus `/lookup` and the API is fully static. Upload `dist/` to
Netlify, Cloudflare Pages, S3+CloudFront, GitHub Pages, etc. The statewide dashboard and
the Greenville access map work with no backend; the address-lookup tool won't (it needs
the API from Option A/B).

## Outbound calls at runtime

Per request, the lookup makes outbound HTTPS to the **Census Geocoder** (address →
coordinates) and **OSRM** (routing). No inbound data is stored. Ensure the host allows
outbound 443. If it can't, set `OSRM_DISABLE=1` (routing falls back to estimates;
geocoding still needs the Census call).

## Privacy

`app_server.py` disables all request logging and never persists the searched address
(it arrives in the POST body, never a URL). See `docs/privacy-design.md`. Keep this
guarantee intact in any reverse proxy — **do not** enable access logs that capture POST
bodies.
