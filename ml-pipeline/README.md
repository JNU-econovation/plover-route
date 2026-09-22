# GeoAI Plogging ML Pipeline & Architecture

[프로젝트 전체 소개](../README.md) · [환경변수·데이터 준비·실행 가이드](../docs/SETUP.md)

본 저장소는 공간 데이터(OSM, POI)와 쓰레기 무단투기 정답지(Ground Truth)를 활용하여, 지역 전체의 쓰레기 핫스팟(투기 위험도)을 예측하고 시각화하는 머신러닝 파이프라인(PU-Learning 기반)입니다.

이 프로젝트는 동구라미 API 등에서 수집한 라벨링 데이터를 바탕으로 국지적 지역(예: 동구)에서 모델을 학습시키고, 라벨이 없는 광역 지역(예: 광주 전체)으로 핫스팟 예측을 확장하는 공간 전이 학습(Spatial Transfer Learning)을 지원합니다.

## 1. 환경 설정 (`config.yaml`)

파이프라인을 실행하기 전, `ml-pipeline/config.yaml` 파일에서 대상 지역과 마스킹 설정을 구성합니다.

```yaml
spatial:
  target_region: "Dong-gu, Gwangju, South Korea"  # 기본 학습 대상 지역
  grid_size_meters: 10                            # 공간 격자의 해상도 (기본 10m)
  buffer_size_meters: 10                          # 도로 중심선 기준 마스킹 버퍼 반경 (기본 10m)
```
* **참고:** 모델 학습은 `target_region`에 맞춰 진행되지만, 추론 단계의 CLI 옵션을 통해 타겟 지역을 동적으로 오버라이드할 수 있습니다.

---

## 2. 로컬 개발 환경 세팅 (uv 기반)

본 파이프라인은 초고속 파이썬 패키지 매니저인 [uv](https://github.com/astral-sh/uv)를 표준으로 사용합니다. 로컬에서 코드를 직접 실행하거나 테스트하려면 아래 과정을 거쳐야 합니다.

1. **uv 설치** (Mac/Linux 기준)
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
2. **의존성 설치 및 가상환경 구성**
   ```bash
   uv sync
   ```
   *(이 명령어를 실행하면 `.venv` 가상환경이 자동 생성되고 모든 필수 패키지가 설치됩니다.)*

---

## 3. 실행 및 배포 환경 (Docker / .env)

### 환경변수 세팅 (.env)
`ml-pipeline/.env` 파일을 생성하고 데이터베이스 연결 정보를 기입합니다.
```env
DATABASE_URL=postgresql://[아이디]:[비밀번호]@[호스트주소]:5432/[DB명]
```

### Docker Compose 기반 실행
서버 배포 시 종속성 충돌 없이 컨테이너 환경에서 파이프라인을 실행할 수 있습니다.

**명령어 도움말 확인:**
```bash
docker compose run --rm ml-pipeline python main.py --help
```

**파이프라인 단계별 도커 실행 예시:**
로컬 환경의 CLI 명령어를 `docker compose run --rm ml-pipeline` 컨텍스트에서 동일하게 실행합니다.
```bash
# 데이터 수집 (ETL)
docker compose run --rm ml-pipeline python main.py fetch-raw-data

# 공간 격자망 생성
docker compose run --rm ml-pipeline python main.py add-grid --region "Dong-gu, Gwangju, South Korea"

# 모델 학습
docker compose run --rm ml-pipeline python main.py train-model --region "Dong-gu, Gwangju, South Korea"
```
최종 실행 이미지에는 `uv`가 포함되지 않으므로 `python`을 사용합니다. 결과물은 컨테이너의 `/app/data/`에 저장됩니다. 호스트에 보존하려면 Compose의 `./data:/data`를 `./data:/app/data`로 맞춰야 합니다. 위 명령은 개별 단계의 호출 예시이며, 데이터 준비부터 학습까지의 순서는 아래 시나리오를 따릅니다.

---

## 4. CLI 파이프라인 시나리오 (공간 전이 학습)

아래는 광주 동구(학습 지역)의 데이터를 기반으로 모델을 학습시키고, 광주 전체(타겟 지역)의 쓰레기 투기 위험도를 예측하는 전체 파이프라인 실행 시나리오입니다. 실제 서버 환경에서 실행할 땐 도커 컴포즈 명령어를 사용하면 됩니다. (2번 참고)

시작 전에 학습·추론 대상 지역의 POI CSV를 `data/raw/`에 준비해야 합니다. 파일명과 필요한 열은 [실행 가이드](../docs/SETUP.md#환경변수와-원본-데이터)를 참고하세요. `fetch-raw-data`는 POI가 아닌 쓰레기 제보 데이터를 수집합니다.

### Step 1: 데이터 수집 (ETL)
외부 API에서 쓰레기 신고 데이터를 수집하여 PostGIS 데이터베이스에 적재합니다.
```bash
uv run main.py fetch-raw-data
```

### Step 2: 학습 대상 지역 공간 격자 및 피처 생성
학습 대상 지역(동구)에 대한 10m 공간 격자망을 생성하고 POI 피처를 추출합니다.
```bash
uv run main.py add-grid --region "Dong-gu, Gwangju, South Korea"
uv run main.py add-features --region "Dong-gu, Gwangju, South Korea"
```

### Step 3: 데이터셋 구축 및 모델 학습
데이터베이스의 정답지(Ground Truth) 뷰를 로드하여 공간 피처와 결합한 뒤, PU-XGBoost 모델을 학습시킵니다.
```bash
uv run main.py make-dataset --region "Dong-gu, Gwangju, South Korea"
uv run main.py train-model --region "Dong-gu, Gwangju, South Korea"
```
*(정상적으로 학습이 완료되면 `data/models/` 경로에 `.pkl` 파일이 생성됩니다.)*

### Step 4: 타겟 지역 공간 격자 및 피처 생성
추론 대상 지역(광주 전체)에 대한 공간 격자망과 피처를 준비합니다.
```bash
uv run main.py add-grid --region "Gwangju, South Korea"
uv run main.py add-features --region "Gwangju, South Korea"
```

### Step 5: 핫스팟 추론 및 시각화
학습된 모델(`--train-region`)을 로드하여 타겟 지역(`--target-region`)에 대한 핫스팟 확률(`trash_score`)을 추론하고 히트맵 렌더링을 수행합니다.
```bash
uv run main.py infer-hotspot \
  --train-region "Dong-gu, Gwangju, South Korea" \
  --target-region "Gwangju, South Korea"

uv run main.py visualize-hotspot --target-region "Gwangju, South Korea"
```
*(추론 결과가 담긴 `.gpkg` 파일과 `.png` 시각화 이미지는 `data/processed/` 경로에 저장됩니다.)*
