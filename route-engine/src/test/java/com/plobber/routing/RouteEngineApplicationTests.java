package com.plobber.routing;

import com.graphhopper.GraphHopper;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBootTest
class RouteEngineApplicationTests {

    @MockitoBean
    private GraphHopper graphHopper;

	@Test
	void contextLoads() {
	}

}
