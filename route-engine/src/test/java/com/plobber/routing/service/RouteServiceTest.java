package com.plobber.routing.service;

import com.graphhopper.GHRequest;
import com.graphhopper.GHResponse;
import com.graphhopper.GraphHopper;
import com.graphhopper.ResponsePath;
import com.graphhopper.util.CustomModel;
import com.graphhopper.util.PointList;
import com.plobber.routing.controller.RouteRequest;
import com.plobber.routing.graphhopper.CustomModelBuilder;
import com.plobber.routing.repository.HotspotInfo;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.Collections;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyDouble;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;

@ExtendWith(MockitoExtension.class)
class RouteServiceTest {

    @Mock
    private GraphHopper graphHopper;

    @Mock
    private CustomModelBuilder customModelBuilder;

    @Mock
    private HotspotSelector hotspotSelector;

    @InjectMocks
    private RouteService routeService;

    @Test
    @DisplayName("핫스팟이 있으면 waypoint 경유 라우팅을 수행해야 한다.")
    void calculateRoute_withHotspots_usesWaypointRouting() {
        // given
        RouteRequest requestDto = new RouteRequest(35.1769, 126.9058, 5000, "PLOGGING");

        List<HotspotInfo> hotspots = List.of(
                new HotspotInfo("h1", 35.18, 126.91, 0.90),
                new HotspotInfo("h2", 35.17, 126.92, 0.80)
        );
        given(hotspotSelector.selectOptimalRoute(anyDouble(), anyDouble(), anyInt()))
                .willReturn(hotspots);

        CustomModel mockCustomModel = new CustomModel();
        given(customModelBuilder.build("PLOGGING")).willReturn(mockCustomModel);

        GHResponse mockResponse = createMockResponse(requestDto.lat(), requestDto.lon());
        given(graphHopper.route(any(GHRequest.class))).willReturn(mockResponse);

        // when
        RouteResult result = routeService.calculateRoute(requestDto);

        // then
        assertThat(result).isNotNull();
        assertThat(result.distanceMeter()).isEqualTo(1500.0);

        ArgumentCaptor<GHRequest> captor = ArgumentCaptor.forClass(GHRequest.class);
        verify(graphHopper).route(captor.capture());
        GHRequest captured = captor.getValue();

        // 출발지 + 핫스팟 2개 + 복귀지 = 4개 포인트
        assertThat(captured.getPoints()).hasSize(4);
        assertThat(captured.getProfile()).isEqualTo("plogging_foot");
        assertThat(captured.getCustomModel()).isNotNull();
        assertThat(captured.getHints().getBool("ch.disable", false)).isTrue();
    }

    @Test
    @DisplayName("핫스팟이 없으면 기존 round_trip 라우팅을 수행해야 한다.")
    void calculateRoute_noHotspots_fallsBackToRoundTrip() {
        // given
        RouteRequest requestDto = new RouteRequest(35.1769, 126.9058, 5000, "PLOGGING");

        given(hotspotSelector.selectOptimalRoute(anyDouble(), anyDouble(), anyInt()))
                .willReturn(Collections.emptyList());

        CustomModel mockCustomModel = new CustomModel();
        given(customModelBuilder.build("PLOGGING")).willReturn(mockCustomModel);

        GHResponse mockResponse = createMockResponse(requestDto.lat(), requestDto.lon());
        given(graphHopper.route(any(GHRequest.class))).willReturn(mockResponse);

        // when
        RouteResult result = routeService.calculateRoute(requestDto);

        // then
        ArgumentCaptor<GHRequest> captor = ArgumentCaptor.forClass(GHRequest.class);
        verify(graphHopper).route(captor.capture());
        GHRequest captured = captor.getValue();

        assertThat(captured.getAlgorithm()).isEqualTo("round_trip");
        assertThat(captured.getPoints()).hasSize(1);
    }

    @Test
    @DisplayName("거리(distance)가 0 이하일 경우 IllegalArgumentException을 던져야 한다.")
    void calculateRoute_InvalidDistance_ThrowsException() {
        // given
        RouteRequest requestDto = new RouteRequest(35.1769, 126.9058, -500, "PLOGGING");

        // when & then
        assertThatThrownBy(() -> routeService.calculateRoute(requestDto))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("Distance must be greater than 0");
    }

    @Test
    @DisplayName("위경도 값이 범위를 벗어날 경우 IllegalArgumentException을 던져야 한다.")
    void calculateRoute_OutOfBoundsCoordinates_ThrowsException() {
        // given
        RouteRequest requestDto = new RouteRequest(91.0, 126.9058, 5000, "PLOGGING");

        // when & then
        assertThatThrownBy(() -> routeService.calculateRoute(requestDto))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("Coordinates are out of bounds");
    }

    private GHResponse createMockResponse(double lat, double lon) {
        GHResponse response = new GHResponse();
        ResponsePath path = new ResponsePath();
        path.setDistance(1500.0);
        path.setTime(600000L);

        PointList points = new PointList();
        points.add(lat, lon);
        points.add(lat + 0.01, lon + 0.01);
        points.add(lat, lon);
        path.setPoints(points);

        response.add(path);
        return response;
    }
}
