package com.plobber.routing.repository;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowCallbackHandler;
import org.springframework.jdbc.core.RowMapper;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class HotspotRepositoryTest {

    @Mock
    private JdbcTemplate jdbcTemplate;

    @Mock
    private ResultSet resultSet;

    private HotspotRepositoryImpl createAndInit() throws SQLException {
        HotspotRepositoryImpl repo = new HotspotRepositoryImpl(jdbcTemplate);

        doAnswer(invocation -> {
            RowCallbackHandler handler = invocation.getArgument(1);

            when(resultSet.getLong("osm_id")).thenReturn(100L);
            when(resultSet.getDouble("trash_score")).thenReturn(0.75);
            handler.processRow(resultSet);

            when(resultSet.getLong("osm_id")).thenReturn(200L);
            when(resultSet.getDouble("trash_score")).thenReturn(0.42);
            handler.processRow(resultSet);

            when(resultSet.getLong("osm_id")).thenReturn(300L);
            when(resultSet.getDouble("trash_score")).thenReturn(0.0);
            handler.processRow(resultSet);

            return null;
        }).when(jdbcTemplate).query(anyString(), any(RowCallbackHandler.class));

        repo.init();
        return repo;
    }

    @Nested
    @DisplayName("init() 캐시 로딩")
    class InitTests {

        @Test
        @DisplayName("init()이 DB에서 올바른 SQL을 실행해야 한다.")
        void init_executesCorrectQuery() throws SQLException {
            createAndInit();
            verify(jdbcTemplate).query(
                eq("SELECT osm_id, trash_score FROM osm_edge_trash_scores"),
                any(RowCallbackHandler.class)
            );
        }

        @Test
        @DisplayName("DB에 데이터가 없어도 init()이 정상 완료되어야 한다.")
        void init_withEmptyDb_completesSuccessfully() {
            HotspotRepositoryImpl repo = new HotspotRepositoryImpl(jdbcTemplate);

            doAnswer(invocation -> null)
                .when(jdbcTemplate).query(anyString(), any(RowCallbackHandler.class));

            assertThatCode(repo::init).doesNotThrowAnyException();
            assertThat(repo.findProbabilityByOsmId(999L)).isEqualTo(0.0);
        }
    }

    @Nested
    @DisplayName("findProbabilityByOsmId() 조회")
    class FindProbabilityTests {

        @Test
        @DisplayName("캐시된 osmId가 존재하면 해당 점수를 반환해야 한다.")
        void whenExists_returnsScore() throws SQLException {
            HotspotRepositoryImpl repo = createAndInit();

            assertThat(repo.findProbabilityByOsmId(100L)).isEqualTo(0.75);
            assertThat(repo.findProbabilityByOsmId(200L)).isEqualTo(0.42);
        }

        @Test
        @DisplayName("점수가 0.0인 도로도 정확히 0.0을 반환해야 한다.")
        void whenScoreIsZero_returnsZero() throws SQLException {
            HotspotRepositoryImpl repo = createAndInit();

            assertThat(repo.findProbabilityByOsmId(300L)).isEqualTo(0.0);
        }

        @Test
        @DisplayName("캐시에 없는 osmId는 기본값 0.0을 반환해야 한다.")
        void whenNotExists_returnsDefaultZero() throws SQLException {
            HotspotRepositoryImpl repo = createAndInit();

            assertThat(repo.findProbabilityByOsmId(999L)).isEqualTo(0.0);
        }
    }

    @Nested
    @DisplayName("findTopNearby() 공간 쿼리")
    class FindTopNearbyTests {

        @Test
        @DisplayName("DB 결과가 있으면 점수 내림차순으로 반환해야 한다.")
        void whenResultsExist_returnsOrderedList() throws SQLException {
            HotspotRepositoryImpl repo = createAndInit();

            HotspotInfo h1 = new HotspotInfo("h_0", 35.16, 126.90, 0.90);
            HotspotInfo h2 = new HotspotInfo("h_1", 35.17, 126.91, 0.80);

            given(jdbcTemplate.query(anyString(), any(RowMapper.class), anyDouble(), anyDouble(), anyDouble(), anyInt()))
                    .willReturn(Arrays.asList(h1, h2));

            List<HotspotInfo> results = repo.findTopNearby(35.175, 126.91, 2000, 10);

            assertThat(results).hasSize(2);
            assertThat(results.get(0).score()).isGreaterThan(results.get(1).score());
        }

        @Test
        @DisplayName("DB 결과가 없으면 빈 리스트를 반환해야 한다.")
        void whenNoResults_returnsEmptyList() throws SQLException {
            HotspotRepositoryImpl repo = createAndInit();

            given(jdbcTemplate.query(anyString(), any(RowMapper.class), anyDouble(), anyDouble(), anyDouble(), anyInt()))
                    .willReturn(Collections.emptyList());

            List<HotspotInfo> results = repo.findTopNearby(0.0, 0.0, 100, 5);

            assertThat(results).isEmpty();
        }

        @Test
        @DisplayName("DB 쿼리 실패 시 예외를 삼키고 빈 리스트를 반환해야 한다.")
        void whenQueryFails_returnsEmptyList() throws SQLException {
            HotspotRepositoryImpl repo = createAndInit();

            given(jdbcTemplate.query(anyString(), any(RowMapper.class), anyDouble(), anyDouble(), anyDouble(), anyInt()))
                    .willThrow(new RuntimeException("DB connection lost"));

            List<HotspotInfo> results = repo.findTopNearby(35.0, 126.0, 500, 3);

            assertThat(results).isEmpty();
        }
    }
}
