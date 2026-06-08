#!/bin/bash
# ==============================================================================
# GeoAI Plogging: Pure Vertical Administrative-Division Batch Pipeline
# ==============================================================================

# ANSI Color Codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "======================================================================"
echo -e "         GeoAI Pure Vertical Production Pipeline Orchestrator"
echo -e "======================================================================"

# [START OFFSET CONTROL]
# Specify the exact division name to resume the pipeline.
START_FROM="Daegu, South Korea"

# 1. Load Environment Variables from scripts/.env
ENV_FILE="$(pwd)/scripts/.env"
if [ -f "$ENV_FILE" ]; then
    echo -e " -> Loading database configuration from scripts/.env..."
    export $(grep -v '^#' "$ENV_FILE" | xargs)
else
    echo -e "${RED}Error: .env file not found at $ENV_FILE${NC}"
    exit 1
fi

ML_ENV_FILE="$(pwd)/ml-pipeline/.env"
if [ -f "$ML_ENV_FILE" ]; then
    echo -e " -> Loading pipeline configurations from ml-pipeline/.env..."
    export $(grep -v '^#' "$ML_ENV_FILE" | xargs)
fi

# Construct & Export DATABASE_URL
export DATABASE_URL="postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME"

ML_DIR="$(pwd)/ml-pipeline"

# Go to ml-pipeline directory
cd "$ML_DIR" || exit 1

# 17 Administrative divisions of South Korea (Strict sequential execution order)
REGIONS=(
    "Seoul, South Korea"
    "Incheon, South Korea"
    "Gyeonggi, South Korea"
    "Gangwon, South Korea"
    "Chungcheongbuk-do, South Korea"
    "Chungcheongnam-do, South Korea"
    "Jeollabuk-do, South Korea"
    "Jeollanam-do, South Korea"
    "Gyeongsangbuk-do, South Korea"
    "Gyeongsangnam-do, South Korea"
    "Daejeon, South Korea"
    "Sejong, South Korea"
    "Gwangju, South Korea"
    "Busan, South Korea"
    "Daegu, South Korea"
    "Ulsan, South Korea"
    "Jeju, South Korea"
)

echo -e "\n${YELLOW}[Start] Executing Pure Vertical Batch Loop starting from: ${START_FROM}...${NC}"

# Internal control flag to start execution
SHOULD_RUN=false

for region in "${REGIONS[@]}"; do
    safe_name=$(echo "$region" | tr '[:upper:]' '[:lower:]' | sed 's/,//g' | sed 's/ /_/g')
    GRID_GPKG="data/processed/grid_${safe_name}_10m_buf10m.gpkg"
    FEATURES_GPKG="data/processed/features_${safe_name}_10m_buf10m_poi_road.gpkg"
    
    # Check if we reached the start region
    if [ "$SHOULD_RUN" = false ]; then
        if [ "$region" = "$START_FROM" ]; then
            SHOULD_RUN=true
            echo -e "\n>>> [RESUME SIGNAL] Target region reached. Initiating active execution loop... <<<\n"
        else
            echo -e "   [SKIP] Skip Division: ${BLUE}${region}${NC} (Offset Guard Active)"
            continue
        fi
    fi
    
    echo -e "\n--------------------------------------------------"
    echo -e " Target Division: ${BLUE}${region}${NC}"
    echo -e "--------------------------------------------------"
    
    # 1. Grid Validation & Generation
    if [ -f "$GRID_GPKG" ]; then
        echo -e "   ${GREEN}[Phase 1 - SKIP] Grid file already exists.${NC}"
    else
        echo -e "   [Phase 1 - RUN] Building 10m grid and downloading OSM road networks..."
        uv run main.py add-grid --region "$region" --force-download
        STATUS=$?
        if [ $STATUS -ne 0 ]; then
            echo -e "${RED}Error: Grid generation failed for ${region} (Exit Code: $STATUS). Aborting pipeline.${NC}"
            exit 1
        fi
    fi

    # 2. Feature Validation & Extraction
    if [ -f "$FEATURES_GPKG" ]; then
        echo -e "   ${GREEN}[Phase 2 - SKIP] Spatial features file already exists.${NC}"
    else
        echo -e "   [Phase 2 - RUN] Extracting multi-dimensional GIS spatial features (poi, road)..."
        uv run main.py add-features --region "$region" --feature-type "poi,road"
        STATUS=$?
        if [ $STATUS -ne 0 ]; then
            echo -e "${RED}Error: Feature engineering failed for ${region} (Exit Code: $STATUS). Aborting pipeline.${NC}"
            exit 1
        fi
    fi

    # 3. AI Inference & Direct PostGIS Upsert
    echo -e "   [Phase 3 - RUN] Executing PU-Bagging-XGBoost inference and direct PostGIS upsert..."
    uv run main.py infer-hotspot \
        --target-region "$region" \
        --train-region "Dong-gu, Gwangju, South Korea" \
        --feature-type "poi,road" \
        --push
    STATUS=$?
    if [ $STATUS -ne 0 ]; then
        echo -e "${RED}Error: AI inference & DB loading failed for ${region} (Exit Code: $STATUS). Aborting pipeline.${NC}"
        exit 1
    fi

    # 4. Critical Post-Load Garbage Collection (Drop Temp Tables CASCADE)
    echo -e "   [Phase 4 - CLEAN] Purging PostGIS staging tables (dropping temp tables cascade)..."
    uv run python -c "
import sqlalchemy
from sqlalchemy import text
import os
engine = sqlalchemy.create_engine(os.environ['DATABASE_URL'])
with engine.begin() as conn:
    res = conn.execute(text(\"SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'predicted_hotspots_temp_%';\"))
    for row in res.fetchall():
        t_name = row[0]
        print(f'     -> Dropped and unlinked staging table: {t_name}')
        conn.execute(text(f'DROP TABLE IF EXISTS \"{t_name}\" CASCADE;'))
"
    
    echo -e "${GREEN}✔ Processing and DB load complete for: ${region}${NC}"
done

# ==============================================================================
# Post-Processing & Production Rollout Operations
# ==============================================================================
echo -e "\n======================================================================"
echo -e " All 17 Administrative Divisions successfully loaded to DB. Rollout start."
echo -e "======================================================================"

# 1. Compile PMTiles & Upload to AWS S3 Bucket
echo -e "\n${YELLOW}[Final 1/4] Compiling nationwide PMTiles (45M grids) & pushing to S3...${NC}"
uv run main.py build-tiles
STATUS=$?
if [ $STATUS -ne 0 ]; then
    echo -e "${RED}Error: PMTiles build or S3 sync failed (Exit Code: $STATUS).${NC}"
    exit 1
fi
echo -e "${GREEN}✔ Nationwide PMTiles successfully compiled and uploaded to S3 bucket.${NC}"

# 2. Rebuild OSM Highway Routing Materialized View & Unique Index
echo -e "\n${YELLOW}[Final 2/4] Rebuilding OSM Routing Materialized View (osm_edge_trash_scores)...${NC}"
uv run python -c "
import os, psycopg2
conn = psycopg2.connect(os.environ['DATABASE_URL'])
cur = conn.cursor()
print(' -> [MV Query] Performing spatial join between planet_osm_line and hotspots...')
sql_mv = '''
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
'''
cur.execute(sql_mv)
print(' -> [Unique Index] Building high-performance index on osm_id...')
sql_idx = 'CREATE UNIQUE INDEX IF NOT EXISTS idx_osm_edge_trash_scores_osm_id ON osm_edge_trash_scores(osm_id);'
cur.execute(sql_idx)
conn.commit()
cur.close()
conn.close()
print('✔ Materialized View and performance index rebuilt successfully.')
"
STATUS=$?
if [ $STATUS -ne 0 ]; then
    echo -e "${RED}Error: Materialized View rebuild failed (Exit Code: $STATUS).${NC}"
    exit 1
fi
echo -e "${GREEN}✔ Routing data sync complete.${NC}"

# 3. Route Engine (GraphHopper Graph Cache Reset) Instruction
echo -e "\n${YELLOW}[Final 3/4] Reset Routing Engine Graph Cache (EC2 Action)...${NC}"
echo -e " -> Route Engine is hosted on target EC2 server. Please execute the following:"
echo -e "    ${BLUE}cd ~/plover-route/route-engine && docker-compose down && rm -rf ./graph-cache/* && docker-compose up -d --build${NC}"

# 4. Martin Tile Server Reload Instruction
echo -e "\n${YELLOW}[Final 4/4] Restart Martin Tile Server Container (EC2 Action)...${NC}"
echo -e " -> Martin Tile Server is hosted on target EC2 server. Please execute the following:"
echo -e "    ${BLUE}cd ~/plover-route/tileserv && docker-compose restart martin${NC}"

echo -e "\n======================================================================"
echo -e " ${GREEN}Production roll-out completed successfully!${NC}"
echo -e "======================================================================"
