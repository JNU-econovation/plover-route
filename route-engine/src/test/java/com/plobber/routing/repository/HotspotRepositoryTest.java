package com.plobber.routing.repository;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;

@ExtendWith(MockitoExtension.class)
class HotspotRepositoryTest {

    @Mock
    private JdbcTemplate jdbcTemplate;

    @InjectMocks
    private HotspotRepositoryImpl hotspotRepository;

    @Test
    @DisplayName("좌표를 주면 PostGIS의 ST_Intersects 공간 쿼리를 통해 확률값을 정상적으로 가져와야 한다.")
    void findProbabilityByPointTest() {
        // given
        double lat = 37.5665;
        double lon = 126.9780;
        String expectedSql = "SELECT COALESCE(MAX(trash_score), 0.0) FROM predicted_hotspots WHERE ST_Intersects(geometry, ST_SetSRID(ST_MakePoint(?, ?), 4326))";

        given(jdbcTemplate.queryForObject(eq(expectedSql), eq(Double.class), eq(lon), eq(lat)))
                .willReturn(0.85);

        // when
        double probability = hotspotRepository.findProbabilityByPoint(lat, lon);

        // then

        assertThat(probability).isEqualTo(0.85);
        verify(jdbcTemplate).queryForObject(eq(expectedSql), eq(Double.class), eq(lon), eq(lat));
    }

    @Test
    @DisplayName("쿼리 결과가 null일 경우 (해당 좌표에 그리드가 없을 때) 0.0을 반환해야 한다.")
    void findProbabilityByPointReturnsZeroWhenNullTest() {
        // given
        double lat = 37.5665;
        double lon = 126.9780;
        
        given(jdbcTemplate.queryForObject(any(String.class), eq(Double.class), eq(lon), eq(lat)))
                .willReturn(null);

        // when
        double probability = hotspotRepository.findProbabilityByPoint(lat, lon);

        // then
        assertThat(probability).isEqualTo(0.0);
    }
}
