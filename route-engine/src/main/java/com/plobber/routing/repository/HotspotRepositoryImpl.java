package com.plobber.routing.repository;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class HotspotRepositoryImpl implements HotspotRepository {

    private final JdbcTemplate jdbcTemplate;
    private java.util.List<Hotspot> cache;
    private org.locationtech.jts.index.strtree.STRtree spatialIndex;
    private final Object lock = new Object();

    public HotspotRepositoryImpl(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    static class Hotspot {
        double minLat, maxLat, minLon, maxLon, score;

        public Hotspot() {}

        public Hotspot(double minLat, double maxLat, double minLon, double maxLon, double score) {
            this.minLat = minLat;
            this.maxLat = maxLat;
            this.minLon = minLon;
            this.maxLon = maxLon;
            this.score = score;
        }
    }

    @Override
    public double findProbabilityByPoint(double lat, double lon) {
        if (cache == null) {
            synchronized (lock) {
                if (cache == null) {
                    String sql = "SELECT ST_YMin(geometry) as minLat, ST_YMax(geometry) as maxLat, " +
                                 "ST_XMin(geometry) as minLon, ST_XMax(geometry) as maxLon, " +
                                 "trash_score FROM predicted_hotspots";
                    try {
                        cache = jdbcTemplate.query(sql, (rs, rowNum) -> {
                            Hotspot h = new Hotspot();
                            h.minLat = rs.getDouble("minLat");
                            h.maxLat = rs.getDouble("maxLat");
                            h.minLon = rs.getDouble("minLon");
                            h.maxLon = rs.getDouble("maxLon");
                            h.score = rs.getDouble("trash_score");
                            return h;
                        });

                        spatialIndex = new org.locationtech.jts.index.strtree.STRtree();
                        for (Hotspot h : cache) {
                            org.locationtech.jts.geom.Envelope env = new org.locationtech.jts.geom.Envelope(h.minLon, h.maxLon, h.minLat, h.maxLat);
                            spatialIndex.insert(env, h);
                        }
                        spatialIndex.build();
                    } catch (Exception e) {
                        e.printStackTrace();
                        cache = java.util.Collections.emptyList();
                        spatialIndex = new org.locationtech.jts.index.strtree.STRtree();
                    }
                }
            }
        }

        double maxScore = 0.0;
        if (spatialIndex != null && !spatialIndex.isEmpty()) {
            org.locationtech.jts.geom.Envelope queryEnv = new org.locationtech.jts.geom.Envelope(lon, lon, lat, lat);
            java.util.List results = spatialIndex.query(queryEnv);
            for (Object obj : results) {
                Hotspot h = (Hotspot) obj;
                if (lat >= h.minLat && lat <= h.maxLat && lon >= h.minLon && lon <= h.maxLon) {
                    if (h.score > maxScore) {
                        maxScore = h.score;
                    }
                }
            }
        }
        return maxScore;
    }
}
