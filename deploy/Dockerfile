# Upstate Access Project — full-stack image (static dashboard + lookup API).
# Build context is the repo root:  docker build -f deploy/Dockerfile -t upstate-access .
FROM python:3.12-slim

WORKDIR /app

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

ENV PORT=8000 HOST=0.0.0.0
EXPOSE 8000

# Geocoding + OSRM routing happen per-request at runtime (outbound HTTPS).
CMD ["python", "deploy/app_server.py"]
