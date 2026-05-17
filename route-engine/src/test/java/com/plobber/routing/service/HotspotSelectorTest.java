package com.plobber.routing.service;

import com.graphhopper.jsprit.core.algorithm.box.Jsprit;
import com.graphhopper.jsprit.core.problem.VehicleRoutingProblem;
import com.graphhopper.util.shapes.GHPoint;
import com.plobber.routing.repository.HotspotInfo;
import com.plobber.routing.repository.HotspotRepository;
import org.assertj.core.data.Offset;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.BDDMockito.given;

@ExtendWith(MockitoExtension.class)
class HotspotSelectorTest {

    @Mock
    private HotspotRepository hotspotRepository;

    @Mock
    private DistanceMatrixService distanceMatrixService;

    @InjectMocks
    private HotspotSelector hotspotSelector;

    @Test
    @DisplayName("반경 내 핫스팟이 없으면 빈 리스트를 반환해야 한다.")
    void selectOptimalRoute_noHotspots_returnsEmpty() {
        // given
        given(hotspotRepository.findTopNearby(anyDouble(), anyDouble(), anyDouble(), anyInt()))
                .willReturn(Collections.emptyList());

        // when
        List<HotspotInfo> result = hotspotSelector.selectOptimalRoute(35.17, 126.91, 5000);

        // then
        assertThat(result).isEmpty();
    }

    @Test
    @DisplayName("UNREACHABLE 핫스팟은 후보에서 제거해야 한다.")
    void selectOptimalRoute_filtersUnreachableHotspots() {
        // given
        List<HotspotInfo> candidates = new ArrayList<>(List.of(
                new HotspotInfo("h1", 35.18, 126.91, 0.90),
                new HotspotInfo("h2", 36.00, 127.50, 0.95),
                new HotspotInfo("h3", 35.17, 126.92, 0.80)
        ));

        given(hotspotRepository.findTopNearby(anyDouble(), anyDouble(), anyDouble(), anyInt()))
                .willReturn(candidates);

        // h2는 출발지에서 UNREACHABLE
        double[][] matrix = {
            //  S      h1     h2      h3
            {  0,    800,    -1.0,   600 },   // S
            { 800,     0,    -1.0,   400 },   // h1
            { -1.0, -1.0,      0,   -1.0 },   // h2 (모든 곳에서 도달 불가)
            { 600,   400,    -1.0,     0 }    // h3
        };
        given(distanceMatrixService.computeMatrix(anyList())).willReturn(matrix);

        // when
        List<HotspotInfo> result = hotspotSelector.selectOptimalRoute(35.17, 126.91, 5000);

        // then
        assertThat(result).hasSize(2);
        assertThat(result).noneMatch(h -> h.id().equals("h2"));
        assertThat(result).extracting(HotspotInfo::id).containsExactlyInAnyOrder("h1", "h3");
        assertThat(result).extracting(HotspotInfo::score).allMatch(s -> s > 0.0);
    }

    @Test
    @DisplayName("도달 가능한 핫스팟만 결과에 포함되어야 한다.")
    void selectOptimalRoute_onlyReachableHotspots() {
        // given
        List<HotspotInfo> candidates = new ArrayList<>(List.of(
                new HotspotInfo("h1", 35.18, 126.91, 0.90),
                new HotspotInfo("h2", 35.17, 126.92, 0.80)
        ));

        given(hotspotRepository.findTopNearby(anyDouble(), anyDouble(), anyDouble(), anyInt()))
                .willReturn(candidates);

        double[][] matrix = {
            { 0,   800,  600 },
            { 800,   0,  400 },
            { 600, 400,    0 }
        };
        given(distanceMatrixService.computeMatrix(anyList())).willReturn(matrix);

        // when
        List<HotspotInfo> result = hotspotSelector.selectOptimalRoute(35.17, 126.91, 5000);

        // then
        assertThat(result).hasSize(2);
        assertThat(result).extracting(HotspotInfo::id).containsExactlyInAnyOrder("h1", "h2");
        assertThat(result).extracting(HotspotInfo::score).containsExactlyInAnyOrder(0.90, 0.80);
    }

    @Test
    @DisplayName("VRP 문제가 올바른 Vehicle, Service, CostMatrix로 구성되어야 한다.")
    void buildVrp_correctlyConfigured() {
        // given
        List<HotspotInfo> candidates = List.of(
                new HotspotInfo("h1", 35.18, 126.91, 0.90),
                new HotspotInfo("h2", 35.17, 126.92, 0.80)
        );
        double[][] distMatrix = {
            { 0,   800,  600 },
            { 800,   0,  400 },
            { 600, 400,    0 }
        };

        // when
        VehicleRoutingProblem vrp = hotspotSelector.buildVrp(candidates, distMatrix, 5000);

        // then
        assertThat(vrp.getVehicles()).hasSize(1);
        assertThat(vrp.getJobs()).hasSize(2);

        var vehicle = vrp.getVehicles().iterator().next();
        assertThat(vehicle.getStartLocation().getId()).isEqualTo("0");
        assertThat(vehicle.getEndLocation().getId()).isEqualTo("0");
        assertThat(vehicle.getLatestArrival()).isCloseTo(5000 / 1.39, Offset.offset(1.0));
    }

    @Test
    @DisplayName("UNREACHABLE 제거 후 거리 행렬이 올바르게 재구성되어야 한다.")
    void rebuildMatrix_correctlyRebuilds() {
        // given
        List<HotspotInfo> filtered = List.of(
                new HotspotInfo("h1", 35.18, 126.91, 0.90),
                new HotspotInfo("h3", 35.17, 126.92, 0.80)
        );
        List<GHPoint> originalPoints = List.of(
                new GHPoint(35.17, 126.91),
                new GHPoint(35.18, 126.91),
                new GHPoint(36.00, 127.50),
                new GHPoint(35.17, 126.92)
        );
        double[][] original = {
            {   0,  800, -1.0,  600 },
            { 800,    0, -1.0,  400 },
            {-1.0, -1.0,    0, -1.0 },
            { 600,  400, -1.0,    0 }
        };

        // when
        double[][] result = hotspotSelector.rebuildMatrix(filtered, originalPoints, original);

        // then
        assertThat(result).hasNumberOfRows(3);
        assertThat(result[0][0]).isEqualTo(0);
        assertThat(result[0][1]).isEqualTo(800);
        assertThat(result[0][2]).isEqualTo(600);
        assertThat(result[1][2]).isEqualTo(400);
        assertThat(result[1][0]).isEqualTo(result[0][1]);
    }

    @Test
    @DisplayName("jsprit 솔버가 예산 내 방문 가능한 핫스팟을 순서대로 반환해야 한다.")
    void solveAndExtract_returnsVisitOrder() {
        // given
        List<HotspotInfo> candidates = List.of(
                new HotspotInfo("h1", 35.18, 126.91, 0.90),
                new HotspotInfo("h2", 35.17, 126.92, 0.80)
        );
        double[][] distMatrix = {
            { 0,   800,  600 },
            { 800,   0,  400 },
            { 600, 400,    0 }
        };

        Map<String, Double> jobScoreMap = Map.of("job_1", 0.90, "job_2", 0.80);
        VehicleRoutingProblem vrp = hotspotSelector.buildVrp(candidates, distMatrix, 5000);

        // when
        List<String> visitOrder = hotspotSelector.solveAndExtract(vrp, jobScoreMap, 1250.0);

        // then
        assertThat(visitOrder).isNotEmpty();
        assertThat(visitOrder).hasSize(2);
        assertThat(visitOrder).allMatch(id -> id.startsWith("job_"));
        assertThat(visitOrder).doesNotHaveDuplicates();
        assertThat(visitOrder).containsExactlyInAnyOrder("job_1", "job_2");
    }

    @Test
    @DisplayName("예산이 극도로 작으면 일부 핫스팟만 방문해야 한다.")
    void solveAndExtract_tightBudget_skipsLowScoreHotspots() {
        // given: 예산 500m → 왕복하기엔 너무 작음
        List<HotspotInfo> candidates = List.of(
                new HotspotInfo("h1", 35.18, 126.91, 0.90),
                new HotspotInfo("h2", 35.19, 126.93, 0.30),
                new HotspotInfo("h3", 35.20, 126.94, 0.10)
        );
        double[][] distMatrix = {
            { 0,    800,  1500,  2000 },
            { 800,    0,   700,  1200 },
            { 1500, 700,     0,   500 },
            { 2000, 1200,  500,     0 }
        };

        Map<String, Double> jobScoreMap = Map.of(
                "job_1", 0.90, "job_2", 0.30, "job_3", 0.10);
        VehicleRoutingProblem vrp = hotspotSelector.buildVrp(candidates, distMatrix, 500);

        // when
        List<String> visitOrder = hotspotSelector.solveAndExtract(vrp, jobScoreMap, 125.0);

        // then
        assertThat(visitOrder.size()).isLessThan(3);
    }

    @Test
    @DisplayName("목적 함수는 미방문 핫스팟에 score × PENALTY_MULTIPLIER 패널티를 부과해야 한다.")
    void buildObjectiveFunction_penalizesUnassignedByScore() {
        // given
        List<HotspotInfo> candidates = List.of(
                new HotspotInfo("h1", 35.18, 126.91, 0.90)
        );
        double[][] distMatrix = {
            { 0,  800 },
            { 800,  0 }
        };

        Map<String, Double> jobScoreMap = Map.of("job_1", 0.90);
        VehicleRoutingProblem vrp = hotspotSelector.buildVrp(candidates, distMatrix, 5000);

        var objectiveFunction = hotspotSelector.buildObjectiveFunction(vrp, jobScoreMap);

        // when
        var allVisitedSolution = com.graphhopper.jsprit.core.util.Solutions.bestOf(
                Jsprit.Builder.newInstance(vrp).buildAlgorithm().searchSolutions());
        double allVisitedCost = objectiveFunction.getCosts(allVisitedSolution);

        // then
        assertThat(allVisitedCost).isGreaterThan(0);
        assertThat(allVisitedCost).isLessThan(0.90 * 2_000);
    }

    @Test
    @DisplayName("distance 2000m 이면 후보 수가 3개여야 한다.")
    void dynamicCandidates_shortDistance_returns3() {
        // given / when
        int candidates = hotspotSelector.calculateDynamicCandidates(2000);

        // then
        assertThat(candidates).isEqualTo(3);
    }

    @Test
    @DisplayName("distance 5000m 이면 후보 수가 7개여야 한다.")
    void dynamicCandidates_mediumDistance_returns7() {
        // given / when
        int candidates = hotspotSelector.calculateDynamicCandidates(5000);

        // then
        assertThat(candidates).isEqualTo(7);
    }

    @Test
    @DisplayName("distance 10000m 이면 후보 수가 10개(상한)여야 한다.")
    void dynamicCandidates_longDistance_cappedAt10() {
        // given / when
        int candidates = hotspotSelector.calculateDynamicCandidates(10000);

        // then
        assertThat(candidates).isEqualTo(10);
    }

    @Test
    @DisplayName("MAX_SEGMENT_DISTANCE는 budget의 25%여야 한다.")
    void dynamicSegmentDistance_is25PercentOfBudget() {
        // given / when
        double segDist5k = hotspotSelector.calculateDynamicSegmentDistance(5000);
        double segDist2k = hotspotSelector.calculateDynamicSegmentDistance(2000);

        // then
        assertThat(segDist5k).isEqualTo(1250.0);
        assertThat(segDist2k).isEqualTo(500.0);
    }
}
