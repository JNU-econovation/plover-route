package com.plobber.routing.repository;

import java.util.List;

public interface HotspotRepository {
    double findProbabilityByPoint(double lat, double lon);

    List<HotspotInfo> findTopNearby(double lat, double lon, double radiusMeters, int limit);
}
