package com.plobber.routing.service;

import com.graphhopper.util.shapes.GHPoint;
import com.plobber.routing.repository.HotspotInfo;
import com.plobber.routing.repository.HotspotRepository;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

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
}
