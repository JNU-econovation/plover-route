package com.plobber.routing.repository;

import java.util.List;

public interface HotspotRepository {
    double findProbabilityByOsmId(long osmId);

    List<HotspotInfo> findTopNearby(double lat, double lon, double radiusMeters, int limit);
}
