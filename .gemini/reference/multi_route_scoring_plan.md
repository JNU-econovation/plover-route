# 다중 경로 추천 및 스코어링 구현 계획 (GraphHopper RoundTrip 기반)

아차, `RouteService.java`를 다시 확인해 보니 Jsprit 우회(주석 처리) 후 **GraphHopper의 내장 `round_trip` 알고리즘**을 직접 사용하고 계셨군요! 이를 기반으로 프론트엔드의 요구사항(경로 3개 반환, 0~100 스코어)을 반영하기 위한 구현 계획을 전면 수정했습니다.

## 1. 다중 경로(3개) 생성 전략 (GraphHopper RoundTrip)

GraphHopper의 `round_trip` 알고리즘은 `round_trip.seed` 값에 따라 무작위 방향과 분기를 선택하여 완전히 다른 순환 경로를 만들어냅니다.

**제안하는 전략:**
1. `RouteService`에서 난수 시드(seed)를 다르게 하여 **GraphHopper `route()`를 10~15회 반복 호출**합니다.
2. 반환된 `ResponsePath` 10개 중에서 에러가 난 경로나 거리가 너무 짧은 경로를 필터링합니다.
3. 남은 경로들의 **스코어(Score)를 계산**하고, 내림차순 정렬하여 **상위 3개**를 반환합니다.

## 2. 0~100 경로 스코어(Route Score) 계산 공식

현재 `PloggingTagParser`가 도로 세그먼트(`Edge`)에 `trash_prob` (0~1.0)를 주입하고 있습니다. 하지만 GraphHopper의 `ResponsePath`는 단순히 총 이동거리, 시간, 가중치만 알 뿐, 그 경로 안에 포함된 "쓰레기 확률의 순수 합"을 바로 꺼낼 수 없습니다.

**제안하는 스코어 계산 로직:**
1. **Raw Score 계산**: 반환된 `ResponsePath`를 구성하는 모든 Edge(도로 세그먼트)를 순회하며, 메모리에 적재된 `DecimalEncodedValue("trash_prob")` 값을 읽어와 전부 합산합니다.
2. **Target Score 산출**: 해당 거리(예: 3km)를 걸을 때 보통 겪게 되는 평균 Edge 개수(또는 최대 달성 가능 핫스팟 합계)를 임계값으로 설정합니다. (예: 1km당 5.0점 만점)
3. **정규화 (0~100)**: `(Raw Score / Target Score) * 100` (최대 100 제한)

*예: 3km 요청 시 목표점수가 15점인데, 생성된 경로의 `trash_prob` 총합이 12.5라면 → `(12.5 / 15) * 100 = 83점`*

## 3. 구체적 변경 대상

* `RouteService.java`: `List<RouteResult>` 반환 시그니처 변경. 다수 시드 호출 루프 추가 및 Edge 순회를 통한 `trash_prob` 추출 합산 로직 추가.
* `RouteResult.java`: `int score` 필드 추가
