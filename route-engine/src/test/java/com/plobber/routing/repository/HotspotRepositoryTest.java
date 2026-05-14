package com.plobber.routing.repository;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;

import java.util.Arrays;
import java.util.Collections;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.BDDMockito.given;

@ExtendWith(MockitoExtension.class)
class HotspotRepositoryTest {

    @Mock
    private JdbcTemplate jdbcTemplate;

    @InjectMocks
    private HotspotRepositoryImpl hotspotRepository;

    @Test
    @DisplayName("캐시된 데이터 중 좌표를 포함하는 핫스팟이 있으면 그 점수를 반환해야 한다.")
    void findProbabilityByPoint_whenInsideHotspot_ReturnsScore() {
        // given
        HotspotRepositoryImpl.Hotspot hotspot1 = new HotspotRepositoryImpl.Hotspot(37.0, 38.0, 126.0, 127.0, 0.85);
        HotspotRepositoryImpl.Hotspot hotspot2 = new HotspotRepositoryImpl.Hotspot(35.0, 36.0, 128.0, 129.0, 0.40);
        
        given(jdbcTemplate.query(anyString(), any(RowMapper.class)))
                .willReturn(Arrays.asList(hotspot1, hotspot2));

        // when
        double probability = hotspotRepository.findProbabilityByPoint(37.5, 126.5);

        // then
        assertThat(probability).isEqualTo(0.85);
    }

    @Test
    @DisplayName("좌표가 여러 핫스팟에 겹칠 경우 가장 높은 점수를 반환해야 한다.")
    void findProbabilityByPoint_whenOverlapping_ReturnsMaxScore() {
        // given
        HotspotRepositoryImpl.Hotspot hotspot1 = new HotspotRepositoryImpl.Hotspot(37.0, 38.0, 126.0, 127.0, 0.50);
        HotspotRepositoryImpl.Hotspot hotspot2 = new HotspotRepositoryImpl.Hotspot(37.0, 38.0, 126.0, 127.0, 0.95);
        
        given(jdbcTemplate.query(anyString(), any(RowMapper.class)))
                .willReturn(Arrays.asList(hotspot1, hotspot2));

        // when
        double probability = hotspotRepository.findProbabilityByPoint(37.5, 126.5);

        // then
        assertThat(probability).isEqualTo(0.95);
    }

    @Test
    @DisplayName("캐시된 데이터 중 좌표를 포함하는 핫스팟이 없으면 0.0을 반환해야 한다.")
    void findProbabilityByPoint_whenOutsideHotspot_ReturnsZero() {
        // given
        HotspotRepositoryImpl.Hotspot hotspot = new HotspotRepositoryImpl.Hotspot(35.0, 36.0, 128.0, 129.0, 0.40);
        
        given(jdbcTemplate.query(anyString(), any(RowMapper.class)))
                .willReturn(Collections.singletonList(hotspot));

        // when
        double probability = hotspotRepository.findProbabilityByPoint(37.5, 126.5);

        // then
        assertThat(probability).isEqualTo(0.0);
    }

    @Test
    @DisplayName("DB에 핫스팟 데이터가 아예 없으면 0.0을 반환해야 한다.")
    void findProbabilityByPoint_whenNoData_ReturnsZero() {
        // given
        given(jdbcTemplate.query(anyString(), any(RowMapper.class)))
                .willReturn(Collections.emptyList());

        // when
        double probability = hotspotRepository.findProbabilityByPoint(37.5, 126.5);

        // then
        assertThat(probability).isEqualTo(0.0);
    }
}
