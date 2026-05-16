package com.plobber.routing.service;

import com.graphhopper.GHRequest;
import com.graphhopper.GHResponse;
import com.graphhopper.GraphHopper;
import com.graphhopper.ResponsePath;
import com.graphhopper.util.CustomModel;
import com.plobber.routing.graphhopper.CustomModelBuilder;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;

@ExtendWith(MockitoExtension.class)
class RouteServiceTest {

    @Mock
    private GraphHopper graphHopper;

    @Mock
    private CustomModelBuilder customModelBuilder;

    @InjectMocks
    private RouteService routeService;

    @Test
    @DisplayName("출발지와 목표 거리를 입력하면, 왕복(Round Trip) 알고리즘이 적용된 경로 탐색을 수행해야 한다.")
    void calculateRouteTest() {
        // given
        com.plobber.routing.controller.RouteRequest requestDto = new com.plobber.routing.controller.RouteRequest(35.1769, 126.9058, 5000, "PLOGGING");

        CustomModel mockCustomModel = new CustomModel();
        given(customModelBuilder.build(requestDto.mode())).willReturn(mockCustomModel);

        GHResponse mockResponse = new GHResponse();
        ResponsePath mockPath = new ResponsePath();
        mockPath.setDistance(1500.0);
        mockPath.setTime(600000L); // 10 minutes
        
        com.graphhopper.util.PointList points = new com.graphhopper.util.PointList();
        points.add(requestDto.lat(), requestDto.lon());
        points.add(requestDto.lat() + 0.01, requestDto.lon() + 0.01);
        points.add(requestDto.lat(), requestDto.lon());
        mockPath.setPoints(points);
        
        mockResponse.add(mockPath);

        given(graphHopper.route(any(GHRequest.class))).willReturn(mockResponse);

        // when
        RouteResult result = routeService.calculateRoute(requestDto);

        // then
        assertThat(result).isNotNull();
        assertThat(result.distanceMeter()).isEqualTo(1500.0);
        assertThat(result.timeMillis()).isEqualTo(600000L);

        ArgumentCaptor<GHRequest> requestCaptor = ArgumentCaptor.forClass(GHRequest.class);
        verify(graphHopper).route(requestCaptor.capture());
        GHRequest capturedRequest = requestCaptor.getValue();
        
        assertThat(capturedRequest.getPoints().get(0).lat).isEqualTo(requestDto.lat());
        assertThat(capturedRequest.getProfile()).isEqualTo("plogging_foot");
        assertThat(capturedRequest.getAlgorithm()).isEqualTo("round_trip");

        assertThat(capturedRequest.getHints().getInt("round_trip.distance", 0)).isEqualTo(5000);
        assertThat(capturedRequest.getHints().getBool("ch.disable", false)).isTrue();

        assertThat(capturedRequest.getCustomModel()).isNotNull();
    }

    @Test
    @DisplayName("거리(distance)가 0 이하일 경우 IllegalArgumentException을 던져야 한다.")
    void calculateRoute_InvalidDistance_ThrowsException() {
        // given
        com.plobber.routing.controller.RouteRequest requestDto = new com.plobber.routing.controller.RouteRequest(35.1769, 126.9058, -500, "PLOGGING");

        // when & then
        org.assertj.core.api.Assertions.assertThatThrownBy(() -> routeService.calculateRoute(requestDto))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("Distance must be greater than 0");
    }

    @Test
    @DisplayName("위경도 값이 범위를 벗어날 경우 IllegalArgumentException을 던져야 한다.")
    void calculateRoute_OutOfBoundsCoordinates_ThrowsException() {
        // given
        com.plobber.routing.controller.RouteRequest requestDto = new com.plobber.routing.controller.RouteRequest(91.0, 126.9058, 5000, "PLOGGING");

        // when & then
        org.assertj.core.api.Assertions.assertThatThrownBy(() -> routeService.calculateRoute(requestDto))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("Coordinates are out of bounds");
    }
}
