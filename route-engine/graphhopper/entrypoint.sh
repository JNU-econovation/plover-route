#!/bin/bash
set -e

MAP_URL="https://download.geofabrik.de/asia/south-korea-latest.osm.pbf"
MAP_FILE="/app/map-data/south-korea-latest.osm.pbf"

echo "🗺️ 지리 데이터 확인 중..."
if [ ! -f "$MAP_FILE" ]; then
    echo "⚠️ 대한민국 최신 도로망 데이터(OSM)가 없습니다. 다운로드를 시작합니다 (약 150MB)..."
    wget -O "$MAP_FILE" "$MAP_URL"
    echo "✅ 다운로드 완료!"
else
    echo "✅ 기존 도로망 데이터를 사용합니다."
fi

echo "🚀 GraphHopper 엔진을 시작합니다..."
exec java $JAVA_OPTS -jar /app/graphhopper-web.jar server /app/config.yml
