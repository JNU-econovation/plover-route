package com.plobber.routing.service;

import com.graphhopper.GHRequest;
import com.graphhopper.GHResponse;
import com.graphhopper.GraphHopper;
import com.graphhopper.ResponsePath;
import com.graphhopper.util.shapes.GHPoint;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;

@ExtendWith(MockitoExtension.class)
class DistanceMatrixServiceTest {

    @Mock
    private GraphHopper graphHopper;

    @InjectMocks
    private DistanceMatrixService distanceMatrixService;

    @Test
    @DisplayName("3개 지점의 대칭 거리 행렬을 올바르게 계산해야 한다.")
    void computeMatrix_returnsSymmetricMatrix() {
        // given
        List<GHPoint> points = List.of(
                new GHPoint(35.17, 126.90),
                new GHPoint(35.18, 126.91),
                new GHPoint(35.19, 126.92)
        );

        GHResponse mockResponse = createMockResponse(500.0);
        given(graphHopper.route(any(GHRequest.class))).willReturn(mockResponse);

        // when
        double[][] matrix = distanceMatrixService.computeMatrix(points);

        // then
        assertThat(matrix).hasNumberOfRows(3);
        assertThat(matrix[0][0]).isEqualTo(0.0);
        assertThat(matrix[1][1]).isEqualTo(0.0);
        assertThat(matrix[0][1]).isEqualTo(matrix[1][0]);
        assertThat(matrix[0][2]).isEqualTo(matrix[2][0]);
    }

    @Test
    @DisplayName("라우팅 실패 시 UNREACHABLE(-1)을 반환해야 한다.")
    void computeMatrix_returnsUnreachable_whenRoutingFails() {
        // given
        List<GHPoint> points = List.of(
                new GHPoint(35.17, 126.90),
                new GHPoint(35.18, 126.91)
        );

        GHResponse errorResponse = new GHResponse();
        errorResponse.addError(new RuntimeException("No route found"));
        given(graphHopper.route(any(GHRequest.class))).willReturn(errorResponse);

        // when
        double[][] matrix = distanceMatrixService.computeMatrix(points);

        // then
        assertThat(matrix[0][1]).isEqualTo(DistanceMatrixService.UNREACHABLE);
        assertThat(matrix[0][1]).isEqualTo(matrix[1][0]);
    }

    @Test
    @DisplayName("지점이 1개면 0으로 채워진 1x1 행렬을 반환해야 한다.")
    void computeMatrix_singlePoint_returnsZeroMatrix() {
        // given
        List<GHPoint> points = List.of(new GHPoint(35.17, 126.90));

        // when
        double[][] matrix = distanceMatrixService.computeMatrix(points);

        // then
        assertThat(matrix).hasNumberOfRows(1);
        assertThat(matrix[0][0]).isEqualTo(0.0);
    }

    private GHResponse createMockResponse(double distance) {
        GHResponse response = new GHResponse();
        ResponsePath path = new ResponsePath();
        path.setDistance(distance);
        path.setTime(360000L);
        response.add(path);
        return response;
    }
}
