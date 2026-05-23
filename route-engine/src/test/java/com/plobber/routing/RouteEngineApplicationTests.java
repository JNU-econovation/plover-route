package com.plobber.routing;

import com.graphhopper.GraphHopper;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class RouteEngineApplicationTests {

    @MockitoBean
    private GraphHopper graphHopper;

    @MockitoBean
    private com.plobber.routing.repository.HotspotRepository hotspotRepository;

	@Test
	void contextLoads() {
	}

}
