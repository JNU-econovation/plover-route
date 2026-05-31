#!/bin/bash
# ==============================================================================
# GeoAI Plogging: 100% Automated Multi-Region Pipeline Execution Script
# ==============================================================================

# ANSI Color Codes
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 1. Input Validation & Options Parsing
if [ -z "$1" ]; then
    echo -e "${RED}Error: Argument is required!${NC}"
    echo -e "Usage (Single Region):   $0 \"[Region Name], South Korea\""
    echo -e "Example:                 $0 \"Busan, South Korea\""
    echo -e "Usage (All 17 Regions):  $0 all   OR   $0 --all"
    exit 1
fi

# Define the list of all 17 administrative divisions of South Korea
ALL_REGIONS=(
    "Seoul, South Korea"
    "Gyeonggi, South Korea"
    "Incheon, South Korea"
    "Busan, South Korea"
    "Daegu, South Korea"
    "Daejeon, South Korea"
    "Ulsan, South Korea"
    "Sejong, South Korea"
    "Gwangju, South Korea"
    "Jeju, South Korea"
    "Gangwon, South Korea"
    "Jeollanam-do, South Korea"
    "Jeollabuk-do, South Korea"
    "Gyeongsangnam-do, South Korea"
    "Gyeongsangbuk-do, South Korea"
    "Chungcheongnam-do, South Korea"
    "Chungcheongbuk-do, South Korea"
)

IS_ALL_MODE=false
REGIONS=()

if [ "$1" == "all" ] || [ "$1" == "--all" ]; then
    IS_ALL_MODE=true
    REGIONS=("${ALL_REGIONS[@]}")
    echo -e "======================================================================"
    echo -e " ${BLUE}Mode:${NC} ${YELLOW}Batch processing ALL 17 Regions of South Korea${NC}"
    echo -e "======================================================================"
else
    REGIONS=("$1")
    echo -e "======================================================================"
    echo -e " ${BLUE}Mode:${NC} ${YELLOW}Single Region processing: $1${NC}"
    echo -e "======================================================================"
fi

# 2. Load Environment Variables from scripts/.env
ENV_FILE="$(pwd)/scripts/.env"
if [ -f "$ENV_FILE" ]; then
    echo -e " -> Loading database configuration from scripts/.env..."
    export $(grep -v '^#' "$ENV_FILE" | xargs)
else
    echo -e "${RED}Error: .env file not found at $ENV_FILE${NC}"
    exit 1
fi

# 3. Construct & Export DATABASE_URL for python/SQLAlchemy
export DATABASE_URL="postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME"

# 4. Check if python virtualenv is ready
ML_DIR="$(pwd)/ml-pipeline"
if [ ! -d "$ML_DIR" ]; then
    echo -e "${RED}Error: ml-pipeline directory not found at $ML_DIR${NC}"
    exit 1
fi

# Move into ml-pipeline directory to keep relative paths intact
cd "$ML_DIR"

TRAIN_REGION="Dong-gu, Gwangju, South Korea" # Pre-trained A+ Academic Model
SUCCESS_COUNT=0
FAILED_COUNT=0
FAILED_REGIONS=()

# 5. Pipeline Execution Loop
for REGION in "${REGIONS[@]}"; do
    echo -e "\n----------------------------------------------------------------------"
    echo -e " ${BLUE}Running Pipeline for:${NC} ${YELLOW}$REGION${NC}"
    echo -e "----------------------------------------------------------------------"
    
    # Execute steps in a subshell and capture the exact exit status
    # Note: Bash disables 'set -e' inside subshells that are tested as part of an 'if' condition.
    # To bypass this gotcha, we run the subshell standalone and catch the exit status with '|| STATUS=$?'
    STATUS=0
    (
        set -e
        # STEP 1: Generate Grid
        echo -e " [STEP 1] Generating 10x10 grid from OSM..."
        uv run main.py add-grid --region "$REGION"
        
        # STEP 2: Extract Spatial Features
        echo -e " [STEP 2] Extracting spatial features (poi, road)..."
        uv run main.py add-features --region "$REGION" --feature-type "poi,road"
        
        # STEP 3: ML Inference & Push to PostGIS
        echo -e " [STEP 3] Running AI inference and pushing to PostGIS..."
        uv run main.py infer-hotspot \
            --target-region "$REGION" \
            --train-region "$TRAIN_REGION" \
            --feature-type "poi,road" \
            --push
    ) || STATUS=$?
    
    if [ $STATUS -eq 0 ]; then
        echo -e "${GREEN}✔ SUCCESS:${NC} $REGION processed and pushed to DB."
        SUCCESS_COUNT=$((SUCCESS_COUNT + 1))
    else
        echo -e "${RED}✘ FAILED:${NC} Error occurred while processing $REGION (Exit Code: $STATUS)."
        FAILED_COUNT=$((FAILED_COUNT + 1))
        FAILED_REGIONS+=("$REGION")
        
        # In single region mode, exit immediately on error
        if [ "$IS_ALL_MODE" = false ]; then
            echo -e "${RED}Exiting immediately due to error in single-region mode.${NC}"
            exit 1
        fi
    fi
done

# 6. Print Execution Summary
echo -e "\n======================================================================"
echo -e " ${BLUE}GeoAI Plogging: Batch Pipeline Execution Summary${NC}"
echo -e "======================================================================"
echo -e "  - Total Regions:   $((${#REGIONS[@]}))"
echo -e "  - ${GREEN}Successful:${NC}      $SUCCESS_COUNT"
echo -e "  - ${RED}Failed:${NC}          $FAILED_COUNT"

if [ ${#FAILED_REGIONS[@]} -ne 0 ]; then
    echo -e "  - ${RED}Failed Region List:${NC}"
    for F_REG in "${FAILED_REGIONS[@]}"; do
        echo -e "    * ${RED}$F_REG${NC}"
    done
fi
echo -e "======================================================================"
