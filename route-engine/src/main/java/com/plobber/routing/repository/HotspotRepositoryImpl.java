package com.plobber.routing.repository;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class HotspotRepositoryImpl implements HotspotRepository {

    private final JdbcTemplate jdbcTemplate;

    public HotspotRepositoryImpl(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public double findProbabilityByPoint(double lat, double lon) {
        String sql = "SELECT COALESCE(MAX(trash_score), 0.0) FROM predicted_hotspots WHERE ST_Intersects(geometry, ST_SetSRID(ST_MakePoint(?, ?), 4326))";
        Double probability = jdbcTemplate.queryForObject(sql, Double.class, lon, lat);
        return probability != null ? probability : 0.0;
    }
}
