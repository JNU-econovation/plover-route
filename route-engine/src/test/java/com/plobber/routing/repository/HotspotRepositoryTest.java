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

    @Test
    @DisplayName("반경 내 핫스팟을 점수 내림차순으로 반환해야 한다.")
    void findTopNearby_returnsHotspotsSortedByScore() {
        // given
        HotspotRepositoryImpl.Hotspot low = new HotspotRepositoryImpl.Hotspot(35.16, 35.18, 126.90, 126.92, 0.30);
        HotspotRepositoryImpl.Hotspot high = new HotspotRepositoryImpl.Hotspot(35.17, 35.19, 126.91, 126.93, 0.95);
        HotspotRepositoryImpl.Hotspot mid = new HotspotRepositoryImpl.Hotspot(35.15, 35.17, 126.89, 126.91, 0.60);

        given(jdbcTemplate.query(anyString(), any(RowMapper.class)))
                .willReturn(Arrays.asList(low, high, mid));

        // when
        java.util.List<HotspotInfo> results = hotspotRepository.findTopNearby(35.175, 126.91, 2000, 10);

        // then
        assertThat(results).isNotEmpty();
        assertThat(results.get(0).score()).isEqualTo(0.95);
        for (int i = 1; i < results.size(); i++) {
            assertThat(results.get(i).score()).isLessThanOrEqualTo(results.get(i - 1).score());
        }
    }

    @Test
    @DisplayName("limit 수만큼만 핫스팟을 반환해야 한다.")
    void findTopNearby_respectsLimit() {
        // given
        HotspotRepositoryImpl.Hotspot h1 = new HotspotRepositoryImpl.Hotspot(35.16, 35.18, 126.90, 126.92, 0.90);
        HotspotRepositoryImpl.Hotspot h2 = new HotspotRepositoryImpl.Hotspot(35.17, 35.19, 126.91, 126.93, 0.80);
        HotspotRepositoryImpl.Hotspot h3 = new HotspotRepositoryImpl.Hotspot(35.15, 35.17, 126.89, 126.91, 0.70);

        given(jdbcTemplate.query(anyString(), any(RowMapper.class)))
                .willReturn(Arrays.asList(h1, h2, h3));

        // when
        java.util.List<HotspotInfo> results = hotspotRepository.findTopNearby(35.175, 126.91, 2000, 2);

        // then
        assertThat(results).hasSizeLessThanOrEqualTo(2);
    }

    @Test
    @DisplayName("반경 밖의 핫스팟은 결과에 포함하지 않아야 한다.")
    void findTopNearby_excludesOutOfRange() {
        // given
        HotspotRepositoryImpl.Hotspot nearby = new HotspotRepositoryImpl.Hotspot(35.17, 35.18, 126.90, 126.91, 0.85);
        HotspotRepositoryImpl.Hotspot farAway = new HotspotRepositoryImpl.Hotspot(36.00, 36.01, 127.50, 127.51, 0.99);

        given(jdbcTemplate.query(anyString(), any(RowMapper.class)))
                .willReturn(Arrays.asList(nearby, farAway));

        // when
        java.util.List<HotspotInfo> results = hotspotRepository.findTopNearby(35.175, 126.905, 1000, 10);

        // then
        assertThat(results).allSatisfy(h ->
            assertThat(h.score()).isNotEqualTo(0.99)
        );
    }

    @Test
    @DisplayName("캐시에 데이터가 없으면 빈 리스트를 반환해야 한다.")
    void findTopNearby_whenNoData_returnsEmpty() {
        // given
        given(jdbcTemplate.query(anyString(), any(RowMapper.class)))
                .willReturn(Collections.emptyList());

        // when
        java.util.List<HotspotInfo> results = hotspotRepository.findTopNearby(35.175, 126.91, 2000, 10);

        // then
        assertThat(results).isEmpty();
    }
}
