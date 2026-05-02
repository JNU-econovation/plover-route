# GeoAI Plogging ML Pipeline

이 저장소는 공공 공간 데이터와 상권 데이터를 활용하여 쓰레기 투기 공간 분포를 예측하고 최적의 플로깅 경로를 식별하는 머신러닝 파이프라인을 포함하고 있습니다. 이 파이프라인은 지역 기반으로 설계되었으며, 다양한 피처 타입으로 쉽게 확장할 수 있도록 구성되었습니다.

## 1. CLI 사용법

이 파이프라인은 `uv` 환경에서 `main.py`를 통해 실행됩니다.

### Phase 1: Grid 생성 (`add-grid`)
대상 지역의 도로망을 추출하고 그 위를 마스킹하는 공간 격자(예: 10m x 10m)를 생성합니다.

```bash
uv run python main.py add-grid --region "Gwangju, South Korea"
```

**옵션:**
- `--region`: 대상 지역 이름. 생략할 경우 `config.yaml`의 값을 사용합니다.
- `--grid-size`: 단일 격자의 크기 (단위: 미터, 기본값: 10).
- `--buffer`: 도로 중심선을 기준으로 확장할 마스킹 버퍼 반경 (단위: 미터, 기본값: 10).
- `--force-download`: 로컬 캐시를 무시하고 OSM 도로망 데이터를 다시 다운로드합니다.

### Phase 2: Feature Engineering (`add-features`)
다중 링 버퍼(Multi-ring buffer) 기반의 공간 피처를 계산하고 앞서 생성된 격자에 추가합니다.

```bash
uv run python main.py add-features --region "Gwangju, South Korea" --feature-type poi
```

**옵션:**
- `--region`: 대상 지역 이름.
- `--feature-type`: 처리 및 추가할 피처 데이터의 종류 (예: `poi`, `pop`, `cctv`).
- `--grid-size`: 격자 크기 (기본값: 10).
- `--buffer`: 버퍼 반경 (기본값: 10).

*(참고: 출력되는 `features_*.gpkg` 파일은 누적(Cumulative) 파일입니다. 새로운 `--feature-type`으로 명령어를 다시 실행하면 기존 파일에 새로운 피처 컬럼이 추가됩니다.)*

---

## 2. 데이터셋 네이밍 규칙

CLI가 `--region` 및 `--feature-type` 인자를 기반으로 파일 경로를 동적으로 추적할 수 있도록, **모든 원본 및 가공 데이터 파일은 반드시 아래의 명명 규칙을 엄격히 준수해야 합니다.**

### 지역명(Region) 문자열 파싱 규칙
파이프라인이 지역명 문자열을 받을 때, 자동으로 소문자로 변환하고 쉼표(,)를 제거하며 공백을 언더바(_)로 바꿉니다.
- **입력:** `"Gwangju, South Korea"`
- **파싱 결과:** `gwangju_south_korea`
- **입력:** `"Gwangju"`
- **파싱 결과:** `gwangju`

### 원본 데이터 (`data/raw/`)
새로운 원본 데이터(예: 공공데이터포털에서 다운받은 CSV)를 추가할 때는 `data/raw/` 디렉토리에 정확히 다음 형식으로 이름을 지정하여 넣어야 합니다.

**형식:** `[feature_type]_[parsed_region]_raw.[ext]`

**예시:**
- `poi_gwangju_raw.csv` (광주 지역의 상권/POI 데이터)
- `pop_seoul_raw.csv` (서울 지역의 유동인구 데이터)
- `cctv_busan_raw.csv` (부산 지역의 CCTV 위치 데이터)

### 가공 데이터 (`data/processed/`)
가공된 데이터 파일들은 파이프라인에 의해 자동으로 생성됩니다. 이 파일들의 이름은 수동으로 변경하지 마십시오.

- **네트워크 그래프:** `network_[parsed_region]_raw.graphml`
- **마스킹 격자:** `grid_[parsed_region]_[grid_size]m_buf[buffer]m.gpkg`
- **최종 피처 파일:** `features_[parsed_region]_[grid_size]m.gpkg`

**예시:**
- `network_gwangju_raw.graphml`
- `grid_gwangju_10m_buf10m.gpkg`
- `features_gwangju_10m.gpkg`
