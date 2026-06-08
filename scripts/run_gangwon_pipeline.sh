#!/bin/bash
# ==============================================================================
# Gangwon Targeted Re-run Pipeline Orchestrator
# ==============================================================================

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "======================================================================"
echo -e "      [강원도] 격자 생성부터 타일 배포까지 타겟 파이프라인 기동"
echo -e "======================================================================"

# 1. 환경 변수 로드
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

export DATABASE_URL="postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME"
ML_DIR="$(pwd)/ml-pipeline"

cd "$ML_DIR" || exit 1

# 타겟팅 리전 정의 (강원도 단독 실행)
REGIONS=(
    "Gangwon, South Korea"
)

# 임시 테이블 제거 함수
cleanup_temp_tables() {
    echo -e "   [CLEAN] PostGIS 임시 테이블 정리 작업을 시작합니다..."
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
}

# 기존 강원도 DB 데이터 삭제 함수 (중복 및 꼬임 방지)
purge_existing_gangwon_db() {
    echo -e "   [DB PURGE] 기존 DB의 강원도 격자 데이터를 안전하게 삭제합니다..."
    uv run python -c "
import psycopg2
import os
conn = psycopg2.connect(os.environ['DATABASE_URL'])
conn.autocommit = True
cur = conn.cursor()
cur.execute(\"DELETE FROM predicted_hotspots WHERE grid_id >= 'gangwon' AND grid_id < 'gangwoo';\")
print(f'     -> Deleted rows: {cur.rowcount:,}')
cur.close()
conn.close()
"
}

for region in "${REGIONS[@]}"; do
    safe_name=$(echo "$region" | tr '[:upper:]' '[:lower:]' | sed 's/,//g' | sed 's/ /_/g')
    GRID_GPKG="data/processed/grid_${safe_name}_10m_buf10m.gpkg"
    FEATURES_GPKG="data/processed/features_${safe_name}_10m_buf10m_poi_road.gpkg"
    
    echo -e "\n--------------------------------------------------"
    echo -e " Target Division: ${BLUE}${region}${NC} (처음 격자 빌드부터 강제 재수행)"
    echo -e "--------------------------------------------------"
    
    # 0. 기존 생성 파일 강제 삭제 (격자부터 완전히 새로 빌드하기 위함)
    echo -e "   [Phase 0 - RESET] 기존 중간 파일들을 리셋합니다..."
    rm -f "$GRID_GPKG" "$FEATURES_GPKG" "data/processed/result_hotspot_${safe_name}_10m_buf10m_poi_road.gpkg"
    
    # 0.5. 기존 DB 데이터 사전 퍼지
    purge_existing_gangwon_db
    
    # 1. 격자망 새로 생성
    echo -e "   [Phase 1 - RUN] 10m 격자망 도화지 생성 및 OSM 도로망 로딩..."
    uv run main.py add-grid --region "$region"
    STATUS=$?
    if [ $STATUS -ne 0 ]; then
        echo -e "${RED}Error: Grid generation failed for ${region} (Exit Code: $STATUS).${NC}"
        exit 1
    fi

    # 2. 피처 추출 (새로 업로드된 온전한 POI CSV 연계)
    echo -e "   [Phase 2 - RUN] 공간 피처(POI, 도로 밀도) 추출 중..."
    uv run main.py add-features --region "$region" --feature-type "poi,road"
    STATUS=$?
    if [ $STATUS -ne 0 ]; then
        echo -e "${RED}Error: Feature engineering failed for ${region} (Exit Code: $STATUS).${NC}"
        exit 1
    fi

    # 3. AI 추론 및 DB Upsert (unified trash_score 컬럼으로 Direct Push)
    echo -e "   [Phase 3 - RUN] AI 추론 실행 및 PostGIS DB 직접 푸시..."
    uv run main.py infer-hotspot \
        --target-region "$region" \
        --train-region "Dong-gu, Gwangju, South Korea" \
        --feature-type "poi,road" \
        --push
    STATUS=$?
    if [ $STATUS -ne 0 ]; then
        echo -e "${RED}Error: AI inference & DB loading failed for ${region} (Exit Code: $STATUS).${NC}"
        exit 1
    fi

    # 4. 즉시 임시 테이블 청소
    cleanup_temp_tables
    
    echo -e "${GREEN}✔ ${region} 파이프라인 처리가 성공적으로 완료되었습니다!${NC}"
done

# ==============================================================================
# 최종 릴리즈 및 롤아웃 통합 공정
# ==============================================================================
echo -e "\n======================================================================"
echo -e " 모든 타겟팅 리전 완료. 최종 전국 타일 컴파일 및 뷰 갱신 단계 돌입."
echo -e "======================================================================"

# 1. 전국 4500만 격자 기반 PMTiles 빌드 및 AWS S3 업로드
echo -e "\n${YELLOW}[Release 1/2] 전국단위 PMTiles 통합 컴파일 및 S3 최종 배포...${NC}"
uv run main.py build-tiles
STATUS=$?
if [ $STATUS -ne 0 ]; then
    echo -e "${RED}Error: PMTiles build or S3 sync failed (Exit Code: $STATUS).${NC}"
    exit 1
fi
echo -e "${GREEN}✔ 전국 PMTiles가 정상적으로 컴파일되어 S3 버킷에 재배포 완료되었습니다.${NC}"

# 2. 가중치 라우팅용 Materialized View 갱신
echo -e "\n${YELLOW}[Release 2/2] 가중치 라우팅용 Materialized View (osm_edge_trash_scores) 전체 재생성...${NC}"
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
echo -e "${GREEN}✔ 라우팅 인프라 동기화 완료.${NC}"

echo -e "\n======================================================================"
echo -e "         ${GREEN}강원도 targeted 릴리즈 공정이 성공적으로 종료되었습니다!${NC}"
echo -e "======================================================================"
