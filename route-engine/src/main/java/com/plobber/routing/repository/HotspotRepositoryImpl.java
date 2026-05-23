package com.plobber.routing.repository;

import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowCallbackHandler;
import org.springframework.stereotype.Repository;

import jakarta.annotation.PostConstruct;

@Repository
public class HotspotRepositoryImpl implements HotspotRepository {

    private static final Logger log = LoggerFactory.getLogger(HotspotRepositoryImpl.class);
    private final JdbcTemplate jdbcTemplate;
    private Map<Long, Double> edgeScoreMap;

    public HotspotRepositoryImpl(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @PostConstruct
    public void init() {
        Map<Long, Double> temp = new HashMap<>();
        jdbcTemplate.query(
            "SELECT osm_id, trash_score FROM osm_edge_trash_scores",
            (RowCallbackHandler) rs -> temp.put(rs.getLong("osm_id"), rs.getDouble("trash_score"))
        );
        edgeScoreMap = Collections.unmodifiableMap(temp);
        log.info("Edge scores loaded: {} entries, ~{}MB",
            edgeScoreMap.size(),
            edgeScoreMap.size() * 16 / 1024 / 1024);
    }

    @Override
    public double findProbabilityByOsmId(long osmId) {
        return edgeScoreMap.getOrDefault(osmId, 0.0);
    }

    @Override
    public List<HotspotInfo> findTopNearby(double lat, double lon, double radiusMeters, int limit) {
        String sql = "SELECT ST_Y(ST_Centroid(geometry)) as lat, ST_X(ST_Centroid(geometry)) as lon, trash_score " +
                     "FROM predicted_hotspots " +
                     "WHERE ST_DWithin(geometry::geography, ST_SetSRID(ST_MakePoint(?, ?), 4326)::geography, ?) " +
                     "ORDER BY trash_score DESC LIMIT ?";

        try {
            return jdbcTemplate.query(sql, (rs, rowNum) -> new HotspotInfo(
                    "h_" + rowNum,
                    rs.getDouble("lat"),
                    rs.getDouble("lon"),
                    rs.getDouble("trash_score")
            ), lon, lat, radiusMeters, limit);
        } catch (Exception e) {
            log.error("Error querying nearby hotspots at lat={}, lon={}", lat, lon, e);
            return Collections.emptyList();
        }
    }
}
