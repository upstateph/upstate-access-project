#!/usr/bin/env bash
# Build self-hosted OSRM routing graphs (walk + drive) for South Carolina.
#
# Run ONCE on the VPS before `docker compose -f deploy/docker-compose.prod.yml up`:
#   bash deploy/osrm/prepare.sh
#
# Downloads the South Carolina OpenStreetMap extract from Geofabrik (~150 MB) and
# builds one OSRM dataset per profile into deploy/osrm/foot/ and deploy/osrm/car/.
# Needs Docker and ~2 GB free RAM; takes a few minutes per profile.
#
# Privacy: this is the piece that keeps user coordinates on our own
# infrastructure instead of the public OSRM demo (docs/privacy-design.md).
set -euo pipefail

cd "$(dirname "$0")"
PBF=south-carolina-latest.osm.pbf
IMAGE=ghcr.io/project-osrm/osrm-backend:v5.27.1

if [ ! -f "$PBF" ]; then
  echo "Downloading $PBF from Geofabrik ..."
  curl -fL -o "$PBF" "https://download.geofabrik.de/north-america/us/south-carolina-latest.osm.pbf"
fi

for profile in foot car; do
  echo "=== Building $profile profile ==="
  mkdir -p "$profile"
  cp "$PBF" "$profile/$PBF"
  docker run --rm -v "$PWD/$profile:/data" "$IMAGE" \
    osrm-extract -p "/opt/$profile.lua" "/data/$PBF"
  docker run --rm -v "$PWD/$profile:/data" "$IMAGE" \
    osrm-partition "/data/${PBF%.osm.pbf}.osrm"
  docker run --rm -v "$PWD/$profile:/data" "$IMAGE" \
    osrm-customize "/data/${PBF%.osm.pbf}.osrm"
  rm "$profile/$PBF"
  echo "=== $profile done -> deploy/osrm/$profile/ ==="
done

echo "Both profiles built. Start the stack with:"
echo "  DOMAIN=yourdomain.org docker compose -f deploy/docker-compose.prod.yml up -d"
