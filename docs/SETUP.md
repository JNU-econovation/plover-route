# 실행 가이드

[프로젝트 소개로 돌아가기](../README.md)

이 문서는 저장소의 코드와 설정을 기준으로 작성했습니다. 학습 데이터, 학습 모델, OSM PBF, DB 접속 정보는 별도로 준비해야 합니다. ML 작업은 호스트에서 `uv`로, 경로 서버는 JDK 21로 실행하는 흐름을 기준으로 설명합니다.

## 준비 환경

| 구성 요소 | 준비 사항 |
| --- | --- |
| ML CLI | Python 3.12 이상, uv |
| 경로 API | JDK 21, 저장소의 Gradle Wrapper |
| DB | PostGIS 확장이 활성화된 PostgreSQL. RDS 또는 로컬 DB 사용 가능 |
| 타일·OSM 처리 | Docker, Docker Compose v2 |
| 외부 데이터 접근 | OSM 다운로드·동구라미 API 호출이 가능한 네트워크, POI CSV |
| S3 업로드 | 대상 버킷, 코드에서 사용하는 AWS 환경변수 |

```bash
git clone https://github.com/JNU-econovation/plover-route.git
cd plover-route
```

아래 각 절의 명령은 별도 안내가 없으면 **저장소 루트에서 시작**합니다. 실제 자격 증명은 `.env`에 넣고 커밋하지 않습니다.

## ML 파이프라인

### 환경변수와 원본 데이터

`ml-pipeline/.env`를 생성합니다. 아래 값은 로컬 개발용 예시입니다.

```dotenv
DATABASE_URL=postgresql://postgres:local_password@localhost:5432/geoai
```

DB와 계정은 미리 생성하고 PostGIS를 활성화합니다. `fetch-raw-data`도 PostGIS 확장 생성을 시도하므로, 사용할 계정의 권한을 확인합니다.

POI 원본 CSV를 `ml-pipeline/data/raw/`에 둡니다. 광주 예시 파일명은 `poi_gwangju_south_korea_raw.csv`입니다. 동구 전용 파일이 없으면 상위 지역인 광주 파일을 찾습니다.

| CSV 열 | 용도 |
| --- | --- |
| `경도`, `위도` | POI 위치. WGS84 좌표 |
| `상권업종대분류명` | 음식·소매 등 대분류 |
| `상권업종중분류명` | 주점 등 중분류 |
| `상권업종소분류명` | 편의점·카페 등의 추가 분류에 사용. 선택 열 |

`config.yaml`의 기본 학습 지역은 `Dong-gu, Gwangju, South Korea`, 공간 격자와 도로 버퍼는 각각 `10m`입니다. `fetch-raw-data`는 제보 데이터를 가져오는 명령으로, POI CSV는 별도로 준비해야 합니다.

### 설치와 단계별 실행

```bash
cd ml-pipeline
uv sync --frozen
uv run --frozen python main.py --help

# 제보 데이터 → raw_trash_reports
uv run --frozen python main.py fetch-raw-data

# 학습 지역의 격자·POI·도로 피처 생성
uv run --frozen python main.py add-grid --region "Dong-gu, Gwangju, South Korea"
uv run --frozen python main.py add-features --region "Dong-gu, Gwangju, South Korea"

# 라벨 결합 → 학습 및 holdout 평가
uv run --frozen python main.py make-dataset --region "Dong-gu, Gwangju, South Korea"
uv run --frozen python main.py train-model --region "Dong-gu, Gwangju, South Korea"

# 추론 지역의 피처 생성 → 추론 결과 저장 및 PostGIS 적재
uv run --frozen python main.py add-grid --region "Gwangju, South Korea"
uv run --frozen python main.py add-features --region "Gwangju, South Korea"
uv run --frozen python main.py infer-hotspot \
  --train-region "Dong-gu, Gwangju, South Korea" \
  --target-region "Gwangju, South Korea" \
  --push
```

- 원본·중간 결과는 `ml-pipeline/data/raw/`, `data/processed/`에, 학습 모델은 `data/models/`에 저장됩니다.
- `infer-hotspot`의 `--push`를 생략하면 GeoPackage 파일만 생성합니다. 지정하면 `predicted_hotspots` 테이블에도 적재합니다.
- 기존 추론 결과는 입력 파일·모델의 수정 시각과 행 수를 기준으로 재사용합니다. 재계산하려면 `--force-infer`를 추가합니다.
- 제보를 추가 수집한 후 기존 라벨 뷰를 사용한다면 `REFRESH MATERIALIZED VIEW ml_unified_labels_view_baseline;`을 DB에서 실행한 뒤 데이터셋을 다시 만듭니다.
- 학습 지역과 추론 지역의 피처 열이 일치해야 합니다. 지역별로 없는 POI 분류가 있으면 열 구성을 확인합니다.

### ML을 Docker로 실행할 때

현재 Dockerfile의 최종 실행 이미지에는 Python 가상환경이 복사되며, `uv` 실행 파일은 복사되지 않습니다. 컨테이너 안에서는 `python main.py ...`를 사용합니다.

또한 기본 Compose의 `./data:/data`와 코드의 `/app/data` 경로가 다릅니다. 결과를 보존하려면 마운트 대상을 `/app/data`로 맞춰야 합니다. `build-tiles`는 Docker 소켓을 통해 추가 컨테이너를 실행하므로, 이 가이드에서는 해당 작업을 호스트의 `uv` 환경에서 수행합니다.

## 경로 추천 서버

### 도로별 예측 점수 준비

경로 서버는 시작 시 `osm_edge_trash_scores`를 읽습니다. 이 테이블 또는 뷰가 없으면 먼저 준비해야 합니다.

1. 앞 단계에서 `predicted_hotspots` 적재를 완료합니다.
2. OSM PBF를 `route-engine/data/south-korea.osm.pbf`에 준비합니다. 예: [Geofabrik 대한민국 데이터](https://download.geofabrik.de/asia/south-korea.html).
3. `scripts/.env`에 다음 변수를 설정합니다.

```dotenv
DB_HOST=localhost
DB_PORT=5432
DB_NAME=geoai
DB_USER=postgres
DB_PASSWORD=local_password
```

`scripts/init_route_db.sh`는 Docker 컨테이너에서 DB에 연결하므로, `DB_HOST`에는 **해당 컨테이너에서 접근 가능한 주소**를 사용해야 합니다. 위 `localhost` 값은 호스트 DB에 자동 연결되지 않습니다.

다음 스크립트는 OSM 데이터를 새로 적재하고 기존 `osm_edge_trash_scores` 뷰를 삭제·재생성합니다. **초기 구축용 DB에서 실행**하거나 기존 데이터의 영향을 확인한 뒤 실행합니다.

```bash
# 저장소 루트에서 실행
bash scripts/init_route_db.sh
```

스크립트는 `south-korea-highways.osm.pbf`, `planet_osm_line`, `osm_edge_trash_scores`와 조회용 인덱스를 준비합니다. 도로별 점수는 도로 주변 예측 격자의 평균으로 집계합니다.

### 로컬 API 실행

`route-engine/.env`를 생성합니다.

```dotenv
DB_URL=jdbc:postgresql://localhost:5432/geoai
DB_USER=postgres
DB_PASSWORD=local_password
```

```bash
cd route-engine
bash gradlew bootRun
```

기본 도로 파일 경로는 `data/south-korea-highways.osm.pbf`, 그래프 캐시는 `target/south-korea-routing-graph-cache`입니다. 첫 실행에서는 그래프를 생성하므로 준비 시간이 필요합니다.

```bash
curl --get 'http://localhost:8989/api/v1/route' \
  --data-urlencode 'lat=35.146' \
  --data-urlencode 'lon=126.923' \
  --data-urlencode 'distance=5000' \
  --data-urlencode 'mode=PLOGGING'

curl 'http://localhost:8989/actuator/health'
```

API는 생성에 성공한 경로를 최대 3개 반환합니다. 최종 fallback에서는 거리 제한을 만족하지 않는 후보도 선택할 수 있으므로, 목표 거리와 반환 거리가 항상 같지는 않습니다.

### Docker 배포 시 경로 확인

[`route-engine/docker-compose.yml`](../route-engine/docker-compose.yml)의 호스트 디렉터리는 다음과 같습니다.

| 호스트 | 컨테이너 |
| --- | --- |
| `route-engine/map-data/` | `/app/data` |
| `route-engine/graph-cache/` | `/app/target/gwangju-routing-graph-cache` |

PBF를 `map-data/south-korea-highways.osm.pbf`에 두고, Compose가 읽는 `route-engine/.env`에 다음 설정을 추가해 그래프 경로를 마운트 대상과 맞춥니다.

```dotenv
GRAPHHOPPER_GRAPH_LOCATION=/app/target/gwangju-routing-graph-cache
```

컨테이너는 UID/GID `1000`으로 실행하므로 PBF 읽기와 캐시 디렉터리 쓰기 권한이 필요합니다. Route CD는 `.env`를 다시 생성하므로, 자동 배포에서도 이 경로 설정을 유지하려면 워크플로 또는 Compose 설정에 반영해야 합니다.

현재 Dockerfile은 layered JAR 추출에 `layertools`를 사용합니다. 사용하는 Spring Boot 버전에서의 이미지 빌드·실행 호환성은 배포 전에 확인해야 합니다. 이 문서의 로컬 실행 경로는 `bootRun`을 기준으로 합니다.

새 예측 점수를 경로에 반영할 때는 도로별 집계 뷰를 갱신하고, 서버를 중지한 상태에서 기존 그래프 캐시를 백업·이동한 뒤 새 그래프를 생성합니다. DB 값만 바꿔서는 이미 생성된 그래프의 `trash_prob`이 자동으로 갱신되지 않습니다.

## 타일 생성과 제공

### PMTiles 생성

`predicted_hotspots` 적재 후, Docker가 실행 중인 호스트에서 수행합니다.

```bash
cd ml-pipeline
uv run --frozen python main.py build-tiles
```

H3 집계와 타일 변환 결과는 `ml-pipeline/data/processed/hotspots.pmtiles`에 생성됩니다. S3 버킷을 설정하지 않으면 로컬 생성까지만 수행합니다.

S3 업로드에는 `ml-pipeline/.env`의 `AWS_S3_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`이 필요합니다. 현재 업로드 코드는 `public-read` ACL을 요청하므로 버킷 설정과 호환되어야 합니다. 업로드 실패를 로그로 출력하고 종료할 수 있으므로, 명령 종료뿐 아니라 S3 객체 생성 여부도 확인합니다.

### Martin 실행

`tileserv/.env`를 생성합니다.

```dotenv
DATABASE_URL=postgresql://postgres:local_password@db-host:5432/geoai
AWS_S3_BUCKET=your-bucket-name
AWS_DEFAULT_REGION=ap-northeast-2
```

`db-host`에는 Martin 컨테이너에서 접근 가능한 주소를 사용합니다. Martin은 `https://<버킷>.s3.<리전>.amazonaws.com/hotspots.pmtiles`를 읽습니다. S3 버킷명을 비우면 PostGIS 소스만 제공합니다.

```bash
cd tileserv
docker compose up -d
curl 'http://localhost:3000/catalog'
```

카탈로그에서 실제 소스 ID를 확인합니다. PMTiles의 소스 ID가 `hotspots`라면 TileJSON은 `/hotspots`, 벡터 타일은 `/hotspots/{z}/{x}/{y}`에서 제공합니다. [`viewer.html`](../tileserv/viewer.html)의 타일 URL은 배포 당시 주소로 고정되어 있으므로 자신의 서버 주소로 변경합니다.

## 테스트와 확인 범위

```bash
# 저장소 루트 기준: ML 테스트
cd ml-pipeline
uv run --frozen python -m pytest -q
```

```bash
# 저장소 루트 기준: 경로 서버 테스트
cd route-engine
bash gradlew test --no-daemon
```

2026-09-22, 코드 기준 커밋 `37ef10f`에서 문서 작성 중 확인한 결과입니다.

| 확인 항목 | 결과 |
| --- | --- |
| `uv sync --frozen` | 설치 완료 |
| CLI `--help` | 9개 명령 확인 |
| ML 테스트 | 15개 통과, 3개 실패 |
| 경로 서버 테스트 | 검증 환경에서 Gradle 배포 파일 다운로드가 막혀 실행하지 못함. JDK 21도 별도 필요 |
| 실제 학습·추론·AWS 배포 | 원본 데이터·DB·배포 자격 증명을 사용한 전체 실행은 확인하지 않음 |

ML 실패 3건은 `tests/test_main.py`의 2건과 `tests/test_model_pipeline.py`의 1건입니다. 기존 출력 문자열, 분리되기 전 DB 업로드 메서드, 변경 전 `predict()` 인자를 기대하고 있어 현재 구현과 테스트를 맞추는 작업이 필요합니다.

경로 서버 CI는 `route-engine/` 변경 PR에만 적용됩니다. ML 테스트와 전체 서비스 통합 검증은 해당 워크플로에 포함되어 있지 않습니다.
