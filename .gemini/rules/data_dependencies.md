# 데이터 종속성 및 원천 카탈로그 (Data Dependencies & Origins)

본 문서는 `plover-route` (또는 `machine-learning-practice`) 모노레포를 구성하는 세 가지 마이크로서비스(`ml-pipeline`, `route-engine`, `tileserv`)에서 사용하는 모든 데이터의 출처와 흐름을 기록한 단일 진실 공급원(Single Source of Truth)입니다.

---

## 1. 수동 관리 데이터 (Manual Inputs)

현재 자동화되어 있지 않고 관리자가 직접 다운로드 및 배치해야 하는 파일들입니다.

### 1.1. 도로망 지도 데이터 (OSM PBF)
- **위치**: `route-engine/data/*.osm.pbf` (예: `gwangju.osm.pbf`)
- **용도**: GraphHopper 라우팅 엔진의 베이스 맵이자, 향후 `osm2pgsql`을 통한 `planet_osm_line` 도로 세그먼트 생성에 사용.
- **출처**: Geofabrik (https://download.geofabrik.de) 등
- **자동화 로드맵 (Future Work)**:
  - `route-engine`의 인프라 셋업 스크립트(`Makefile` 또는 `setup.sh`)에 `wget` 명령어를 추가하여 원클릭 다운로드로 자동화할 예정입니다.

### 1.2. 소상공인/상가 데이터 (POI)
- **위치**: `ml-pipeline/data/raw/poi_*.csv` (예: `poi_gwangju_south_korea_raw.csv`)
- **용도**: 쓰레기 투기 구역을 예측하기 위한 상업 시설 밀집도 피처(Feature) 생성.
- **출처**: 공공데이터포털(Localdata 등)에서 상가업소 정보 다운로드.
- **자동화 로드맵 (Future Work)**:
  - 초기 MVP에서는 수동 배치로 타협하였으나, 향후 파이썬의 `requests`를 이용해 공공데이터 OpenAPI를 정기적(Cron)으로 찔러 최신 JSON/XML을 받아오고 전처리하는 데이터 파이프라인으로 100% 자동화 가능합니다.

---

## 2. 자동화 스크립트 및 API (Automated APIs)

파이썬 코드 내에서 외부 서버나 API를 자동으로 호출하여 데이터를 적재하는 항목들입니다.

### 2.1. 동구라미 쓰레기 제보 데이터 (DongguramiFetcher)
- **소스 코드**: `ml-pipeline/src/data_fetcher.py`
- **호출 대상**: 외부 API (`https://donggurami.kr/api/comap/mapping/get-mapping-list-all`)
- **수행 동작**: JSON 응답을 파싱하여, 기존 DB(`raw_trash_reports` 테이블)와 `source_id`를 비교해 중복을 제거한 후 **신규 데이터만 PostGIS에 Append**합니다. 완전 자동화되어 있습니다.

### 2.2. 보행자 도로망 네트워크 다운로드 (OSMnx)
- **소스 코드**: `ml-pipeline/src/grid_maker.py`
- **호출 대상**: OSM Overpass API (`osmnx.graph_from_place`)
- **수행 동작**: 타겟 지역(예: "Gwangju, South Korea")의 "walk" 네트워크를 실시간으로 받아옵니다. 다운로드 후 로컬에 `network_..._raw.graphml`로 **캐싱(Caching)**하므로 동일 지역 반복 실행 시 오프라인 모드로 빠르게 작동합니다.

---

## 3. 내부 파생 산출물 및 캐시 (Generated Outputs)

위의 수동/자동 원천 데이터를 가공하여 생성되는 중간/최종 산출물입니다. 모두 `git`에서 제외되어야 합니다(`.gitignore`).

### 3.1. `ml-pipeline` 로컬 산출물
- **디렉토리**: `ml-pipeline/data/processed/`
- **종류**:
  - `grid_*.gpkg`: 10m 정방형 격자 도화지
  - `features_*.gpkg`: 격자별 피처 결합 데이터
  - `result_hotspot_*.gpkg`: ML 추론 완료 결과 (이후 DB로 `--push`)
- **생성 시점**: `main.py`의 `add-grid`, `add-features`, `infer-hotspot` 명령어 실행 시 덮어씌워짐.

### 3.2. `route-engine` 캐시 산출물
- **디렉토리**: `route-engine/target/*-routing-graph-cache` (또는 `graph-cache`)
- **용도**: GraphHopper가 PBF와 Java 코드를 파싱해 메모리에 올리기 직전의 MMap 바이너리 파일들.
- **생성 시점**: `route-engine` (Spring Boot) 서버 기동 시 존재하지 않으면 자동 생성.
- **주의사항**: 추론 결과 갱신으로 도로별 점수(MV)가 바뀌면, 이 **캐시 폴더를 삭제(`rm -rf`)한 뒤 서버를 재시작**해야 갱신된 점수가 라우팅에 반영됩니다.

---

## 4. 전체 데이터 흐름 요약

1. **[수동 확보]** PBF 지도와 POI CSV를 로컬 폴더에 배치.
2. **[API 자동 확보]** `DongguramiFetcher`가 신고 데이터를 DB에 적재. `OSMnx`가 네트워크를 다운로드.
3. **[ML 파이프라인]** 이 모든 데이터를 조합해 `predicted_hotspots`을 추론하고 DB로 Push.
4. **[뷰 생성]** `planet_osm_line`과 `predicted_hotspots`가 조인되어 `osm_edge_trash_scores` 생성. (향후 Flyway로 관리)
5. **[라우팅]** `route-engine`이 뷰에서 점수를 읽고 PBF를 파싱해 `graph-cache` 생성 후 서비스 제공.
