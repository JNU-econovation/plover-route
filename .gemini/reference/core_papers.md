# 🧠 [Full Context] GeoAI 플로깅 시스템 아키텍처 및 핵심 논문 딥다이브 리포트

본 문서는 AI 에이전트(본인)가 프로젝트의 E2E 파이프라인(GeoAI 예측 -> XAI -> 라우팅 엔진)을 구현할 때, 수학적/알고리즘적 근거로 활용하기 위해 구체적인 기술 스펙과 이론적 토대를 영구히 보존하는 딥다이브(Deep-Dive) 컨텍스트 맵입니다.

---

## 📌 1. 예측 도화지 생성 & PU-Learning 프레임워크 (PLOS One, 2026/2024기반)
**Title:** *A GeoAI framework for detecting risk zones from illegal dumping sites* 

### 💡 에이전트 구현(Implementation) 핵심 컨텍스트
*   **MAUP(Modifiable Areal Unit Problem) 극복:** 1km/500m 단위의 거시적 격자는 상업 시설이나 도로와 같은 초국지적 변수(Hyper-local features)를 희석시킵니다. 쓰레기 발생은 골목길 단위에서 발생하므로, V1 모델 구현 시 **반드시 10m x 10m 정방형 격자(Grid)**를 Base Geometry로 사용해야 합니다.
*   **PU Learning (Positive-Unlabeled) 메트릭스:**
    *   **문제 요인:** 무단투기 공공데이터(제보)가 없는 지역의 라벨을 통상적인 방법론처럼 0(Negative)으로 처리할 경우, 실제로는 엄청나게 오염되었으나 '아직 신고되지 않은 곳(False Negative)'이 대량으로 섞이게 되어 모델이 심각한 Bias를 가지게 됩니다.
    *   **기술 적용 (PU-Bagging 등):** 확정된 $P$(Positive) 집합과 확률적 $U$(Unlabeled) 집합으로 데이터를 나눕니다. V1 코드 구현 시 $U$ 집합에서 랜덤 샘플링(Bootstrap)을 여러 번 수행하여 다수의 하위 분류기를 만들고, 이들의 확률값을 앙상블 평균(Ensembling) 내어 실제 쓰레기가 없을 확률(Negative Prior)을 보정합니다.
*   **Feature 중요도 (Feature Importance):** RF 모델이 검증한 핵심 피처 상위 3개는 **도로와의 거리(35.5%), 배수로와의 거리(23.1%), 건물 접근성(6.3%)**입니다. 이는 V1에서 우리가 OSMnx 보행망(도로망)을 바로 Grid 생성의 기준으로 잡은 점(도로 기반 마스킹)이 매우 과학적인 접근임을 뒷받침합니다.

---

## 📌 2. 비선형 데이터 처리 및 XAI 시스템 구축 (Sustainability, 2025)
**Title:** *Explaining Urban Vitality Through Interpretable Machine Learning*

### 💡 에이전트 구현(Implementation) 핵심 컨텍스트
*   **알고리즘 선택의 당위성 (GBDT/Random Forest):** 상권 밀도(POI)나 유동인구 같은 공간 변수는 선형(Linear) 관계가 아닙니다. GBDT나 Random Forest 같은 결정 트리(Decision Tree) 기반 앙상블 모델은 이러한 공간 데이터의 비선형(Non-linear) 및 이질적(Heterogeneous) 상호작용을 파악하는 데 가장 뛰어납니다. 실제 코드 구현 시 `sklearn.ensemble.RandomForestClassifier` 또는 `xgboost`를 채택합니다.
*   **SHAP (SHapley Additive exPlanation) 커스터마이징:**
    *   **수학적 정의:** $f(x) = \phi_0 + \sum_{i=1}^{M} \phi_i x_i$ (각 피처 $i$의 한계 기여도 $\phi_i$ 의 합).
    *   **시스템 연계:** V1 시스템에서 모델이 한 10m 격자에 오염 확률 0.85 (85%)를 반환했다면, AI는 백엔드에 SHAP 벡터를 계산하여 JSON 형태로 반환해야 합니다.
    *   *예: `{"predict_proba": 0.85, "shap_values": {"poi_30m": +0.35, "poi_50m": +0.10, "dist_to_road": -0.05}}`*
*   **임계 효과(Threshold Effect) 처리 로직:** SHAP Local Dependence Plot(LDP)을 도출하면, "반경 30m 내 상가 업소가 5개를 넘어서는 순간 투기 확률이 비약적으로 급등한다" 형태의 임계점을 발견할 수 있습니다. 이는 추후 프론트엔드에 "이곳은 카페/식당 밀집도가 임계 상태입니다"라는 인사이트 문구 로직에 활용됩니다.

---

## 📌 3. 독립 변수 엔지니어링 및 공간 회귀 메타데이터 (Sustainability, 2023)
**Title:** *Analysis of Factors Influencing Illegal Waste Dumping Generation Using GIS Spatial Regression Methods*

### 💡 에이전트 구현(Implementation) 핵심 컨텍스트
*   **GWR (Geographically Weighted Regression):** "모든 것은 다른 모든 것과 관련되어 있지만, 가까운 것은 먼 것보다 더 관련이 있다"(Tobler's 1st Law of Geography)는 법칙을 입증. 나중에 모델 고도화(V2) 시 XY 좌표 자체를 모델이 학습할 수 있도록 Feature화(Spatial Embedding) 해야 할 필요성을 제공합니다.
*   **핵심 도메인 지식(Feature Engineering 가이드라인):**
    *   **고도(Elevation) / 경사도 (역상관관계):** 언덕진 골목 등 수거 인프라 진입이 힘들고 은폐가 쉬운 곳이 오히려 투기장이 됩니다.
    *   **제인 제이콥스의 '거리의 눈(Eyes on the Street)' 효과:** 인구 밀도 변수는 단순히 많다고 오염도가 비례하지 않습니다 (U-Curve 현상). 매우 고립된 지역(인구 최하)은 방치투기 증가 $\rightarrow$ 적정 수준 거주(중간 밀도)는 억제 $\rightarrow$ 번화가/유흥가(인구 최상)는 다시 폭증. 이는 V1에서 단일 변수(상권 데이터)를 쓸 때, 반드시 반경 크기(`30m`, `50m`, `100m`)를 다중 링 버퍼(Multi-ring Buffer) 형태로 분리해서 모델에 넣어야 하는 이유입니다.

---

## 📌 4. 동적 라우팅 엔진 가중치 주입 (Electronics, 2024)
**Title:** *Toward Greener Smart Cities: A Critical Review of Classic and Machine-Learning-Based Algorithms*

### 💡 에이전트 구현(Implementation) 핵심 컨텍스트
*   **그래프 변환 파이프라인 구조:**
    1.  OSMnx가 GeoJSON(또는 NetworkX 형태)으로 맵핑 $\rightarrow$ `Node`(교차로), `Edge`(도로 Segment).
    2.  우리 모델이 예측한 10m 헥사곤/그리드별 `Trash Score (0.0~1.0)`를 도출.
    3.  `Spatial Join(Intersect)`를 통해 특정 도로 엣지(`Edge`)가 가로지르는 여러 격자의 평균 `Trash Score`를 구해 해당 엣지의 속성(Attribute)으로 부여.
*   **GraphHopper 라우팅 휴리스틱 (A* 목적함수 튜닝):**
    *   일반적인 길찾기 Cost Function: $f(n) = g(n) + h(n)$ *(실제 거리/시간 + 목적지까지의 추정 거리/시간)*
    *   **우리 플로깅 앱의 수정된 Cost Function:** 엣지 $e$의 거리를 $w(e)$, 오염도를 $T(e)$라 할 때, 
        $w'(e) = w(e) \times (1 - \alpha \cdot T(e))$ (여기서 $\alpha$는 유저가 설정한 쓰레기 탐색 우선순위 가중치 0~1).
    *   즉, 쓰레기 오염도 $T(e)$가 높은 엣지일수록 $w'(e)$(논리적 Cost)가 줄어들어 길찾기 알고리즘이 그 길로 흡수되게끔(Attraction) 만들어야 합니다.

---

## 📌 5. E2E 데이터 플로우 통합 설계도 (Actionable Workflow)
위 4개의 논문 방법론을 융합하여 본 에이전트가 앞으로 코드로 짜야할 파이썬(GeoPandas + ML) / API 파이프라인을 아래와 같이 명문화합니다.

1.  **[Ingestion]**: `osmnx.graph_from_polygon(network_type='walk')` 호출 $\rightarrow$ Line/Point 도출.
2.  **[Masking]**: Line의 `buffer(distance=30)` 처리 후 합집합 $\rightarrow$ 생성된 폴리곤 내부에 `10x10 Grid (Polygon)` 생성.
3.  **[Feature Ops]**: 
    - 공공데이터포털 상가 API 다운로드 $\rightarrow$ GeoPandas Point 변환.
    - Grid 1개마다 중심점(Centroid) 기준 30m 반경 원을 그려 그 안의 Point Count 산출 $\rightarrow$ `Feature_1`
4.  **[Labeling]**: 국토부 무단투기 데이터(Polygon)와 Grid를 중첩($>0.5$ Area 중첩 기준)하여 `Y=[1 or 0]` 라벨 할당.
5.  **[Training]**: `RandomForestClassifier(n_estimators=100, class_weight='balanced')`로 학습.
    - `clf.predict_proba(X_test)` 로 격자별 0.0~1.0 계수 할당.
6.  **[Explanation]**: `shap.TreeExplainer(clf)`로 각 확률 결정 사유 추출.
7.  **[Serving & DB]**: 결과 테이블(Grid_ID, Geometry, TrashScore, ShapJSON)을 PostGIS / JSON 형태로 export.
8.  **[Routing Setup]**: NetworkX/GraphHopper의 Edge Properties에 `TrashScore` 병합 $\rightarrow$ A* 탐색 가중치 재계산.

본 컨텍스트는 향후 파일럿 코드 작성(Phase 1~4) 과정에서 "무엇을", "어떤 도구로", "왜 그렇게 짜는지(수학적 근거)"를 잃지 않도록 강제하는 나침반 역할을 수행할 것입니다.
