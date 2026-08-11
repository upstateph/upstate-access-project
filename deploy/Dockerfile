# Upstate Access Project — full-stack image (static dashboard + lookup API).
# Build context is the repo root:  docker build -f deploy/Dockerfile -t upstate-access .
FROM python:3.12-slim

WORKDIR /app

# Unprivileged runtime user. Created before the build steps so it lands in an
# early cached layer. The server binds 8000 (>1024), so it needs no privileges.
RUN useradd --system --create-home --uid 10001 app

# Dependencies (requests + pandas)
COPY data-pipeline/requirements.txt data-pipeline/requirements.txt
RUN pip install --no-cache-dir -r data-pipeline/requirements.txt

# App source + committed processed data (FARS, ACS, facilities, rollups, geojson)
COPY . .

# Fetch runtime data that isn't committed (the Greenlink GTFS feed), publish the
# category manifest, and assemble the static site into dist/.
RUN python data-pipeline/fetch_greenlink_gtfs.py \
 && python data-pipeline/build_categories_manifest.py \
 && python deploy/build_site.py

# The ONLY path written at runtime is the de-identified usage log. Pre-create and
# hand it to the app user: without this, record_usage()'s mkdir fails, and its
# catch-all would swallow the error and silently disable telemetry rather than
# reporting it. Everything else is read-only to the app user by design.
RUN mkdir -p /app/data/usage && chown -R app:app /app/data/usage

USER app

ENV PORT=8000 HOST=0.0.0.0
EXPOSE 8000

# Geocoding + OSRM routing happen per-request at runtime (outbound HTTPS).
CMD ["python", "deploy/app_server.py"]
