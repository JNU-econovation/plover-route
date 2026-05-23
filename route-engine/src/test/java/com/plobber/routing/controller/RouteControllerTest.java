package com.plobber.routing.controller;

import com.plobber.routing.service.RouteResult;
import com.plobber.routing.service.RouteService;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;

import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(RouteController.class)
class RouteControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private RouteService routeService;

    @Test
    @DisplayName("GET /api/v1/route 호출 시 정상적으로 왕복 경로(Round Trip) 계산 결과를 반환해야 한다.")
    void getRouteTest() throws Exception {
        // given
        RouteRequest request = new RouteRequest(35.1769, 126.9058, 5000, "PLOGGING");

        String mockEncodedPath = "_p~iF~ps|U_ulLnnqC_mqNvxq`@";
        RouteResult mockResult = new RouteResult(1500.0, 600000L, mockEncodedPath, 95);
        given(routeService.calculateRoute(request)).willReturn(List.of(mockResult));

        // when & then
        mockMvc.perform(get("/api/v1/route")
                .param("lat", String.valueOf(request.lat()))
                .param("lon", String.valueOf(request.lon()))
                .param("distance", String.valueOf(request.distance()))
                .param("mode", request.mode()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].distanceMeter").value(1500.0))
                .andExpect(jsonPath("$[0].timeMillis").value(600000L))
                .andExpect(jsonPath("$[0].encodedPath").value("_p~iF~ps|U_ulLnnqC_mqNvxq`@"))
                .andExpect(jsonPath("$[0].ploggingScore").value(95));
    }
}
