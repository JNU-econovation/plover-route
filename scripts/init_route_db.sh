#!/bin/bash
set -e

# Load environment variables from scripts/.env
ENV_FILE="$(pwd)/scripts/.env"
if [ -f "$ENV_FILE" ]; then
    export $(grep -v '^#' "$ENV_FILE" | xargs)
else
    echo "Error: .env file not found at $ENV_FILE"
    exit 1
fi

DB_PASS="$DB_PASSWORD"

PBF_FILE="$(pwd)/route-engine/data/south-korea.osm.pbf"
FILTERED_PBF_FILE="$(pwd)/route-engine/data/south-korea-highways.osm.pbf"

echo "========================================="
echo " 1. Filtering Highway Data using Osmium (Official)"
echo "========================================="
if [ ! -f "$PBF_FILE" ]; then
    echo "Error: PBF file not found at $PBF_FILE"
    exit 1
fi

# Extract only highway tags to drastically reduce file size (from 276MB to ~20MB) using working community image
docker run --rm \
  -v "$(pwd)/route-engine/data":/data \
  stefda/osmium-tool:latest \
  osmium tags-filter /data/south-korea.osm.pbf w/highway -o /data/south-korea-highways.osm.pbf --overwrite

echo "========================================="
echo " 2. Loading Filtered OSM PBF to PostGIS (Official Recommended)"
echo "========================================="
# Load the filtered, much smaller PBF file to RDS using the official-recommended Docker Hub image
# The image entrypoint is 'osm2pgsql', so we only pass the arguments directly.
docker run --rm \
  -e PGPASSWORD=$DB_PASS \
  -v "$(pwd)/route-engine/data":/data \
  iboates/osm2pgsql:latest \
  --slim --drop -c -l -d $DB_NAME -U $DB_USER -H $DB_HOST -P $DB_PORT /data/south-korea-highways.osm.pbf

echo "========================================="
echo " 3. Creating Materialized View (postgres:alpine)"
echo "========================================="
SQL_CREATE_MV="
DROP MATERIALIZED VIEW IF EXISTS osm_edge_trash_scores;
CREATE MATERIALIZED VIEW osm_edge_trash_scores AS
SELECT
    w.osm_id,
    AVG(h.trash_score) AS trash_score
FROM planet_osm_line w
JOIN predicted_hotspots h
  ON ST_DWithin(w.way, h.geometry, 0.00003)
WHERE w.highway IS NOT NULL
GROUP BY w.osm_id;
"

docker run --rm \
  -e PGPASSWORD=$DB_PASS \
  postgres:alpine \
  psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "$SQL_CREATE_MV"

echo "========================================="
echo " 4. Creating Unique Index for Fast Lookup"
echo "========================================="
SQL_CREATE_INDEX="
CREATE UNIQUE INDEX IF NOT EXISTS idx_osm_edge_trash_scores_osm_id 
ON osm_edge_trash_scores(osm_id);
"

docker run --rm \
  -e PGPASSWORD=$DB_PASS \
  postgres:alpine \
  psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "$SQL_CREATE_INDEX"

echo "========================================="
echo " DB Setup Complete! Ready for Routing."
echo "========================================="

