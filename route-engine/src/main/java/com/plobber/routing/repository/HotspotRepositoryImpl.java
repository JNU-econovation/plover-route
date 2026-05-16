package com.plobber.routing.repository;

import com.graphhopper.util.DistanceCalcEarth;
import org.locationtech.jts.geom.Envelope;
import org.locationtech.jts.index.strtree.STRtree;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;

@Repository
public class HotspotRepositoryImpl implements HotspotRepository {

    private final JdbcTemplate jdbcTemplate;
    private List<Hotspot> cache;
    private STRtree spatialIndex;
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

                        spatialIndex = new STRtree();
                        for (Hotspot h : cache) {
                            Envelope env = new Envelope(h.minLon, h.maxLon, h.minLat, h.maxLat);
                            spatialIndex.insert(env, h);
                        }
                        spatialIndex.build();
                    } catch (Exception e) {
                        e.printStackTrace();
                        cache = Collections.emptyList();
                        spatialIndex = new STRtree();
                    }
                }
            }
        }

        double maxScore = 0.0;
        if (spatialIndex != null && !spatialIndex.isEmpty()) {
            Envelope queryEnv = new Envelope(lon, lon, lat, lat);
            List<?> results = spatialIndex.query(queryEnv);
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

    @Override
    public List<HotspotInfo> findTopNearby(double lat, double lon, double radiusMeters, int limit) {
        ensureCacheLoaded();

        if (spatialIndex == null || spatialIndex.isEmpty()) {
            return Collections.emptyList();
        }

        double radiusDegLat = radiusMeters / 111_320.0;
        double radiusDegLon = radiusMeters / (111_320.0 * Math.cos(Math.toRadians(lat)));

        Envelope searchEnv = new Envelope(
                lon - radiusDegLon, lon + radiusDegLon,
                lat - radiusDegLat, lat + radiusDegLat
        );

        List<?> candidates = spatialIndex.query(searchEnv);
        List<HotspotInfo> results = new ArrayList<>();
        int idx = 0;

        for (Object obj : candidates) {
            Hotspot h = (Hotspot) obj;
            double centerLat = (h.minLat + h.maxLat) / 2.0;
            double centerLon = (h.minLon + h.maxLon) / 2.0;

            double distMeters = DistanceCalcEarth.DIST_EARTH.calcDist(lat, lon, centerLat, centerLon);
            if (distMeters <= radiusMeters && h.score > 0.0) {
                results.add(new HotspotInfo("h_" + idx, centerLat, centerLon, h.score));
            }
            idx++;
        }

        results.sort(Comparator.comparingDouble(HotspotInfo::score).reversed());

        return results.size() <= limit ? results : results.subList(0, limit);
    }

    private void ensureCacheLoaded() {
        if (cache == null) {
            findProbabilityByPoint(0, 0);
        }
    }


}
