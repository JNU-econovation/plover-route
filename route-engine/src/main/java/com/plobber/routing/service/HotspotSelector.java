package com.plobber.routing.service;

import com.graphhopper.util.shapes.GHPoint;
import com.plobber.routing.repository.HotspotInfo;
import com.plobber.routing.repository.HotspotRepository;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

@Service
public class HotspotSelector {

    private static final int MAX_CANDIDATES = 15;
    private static final double SEARCH_RADIUS_RATIO = 0.4;

    private final HotspotRepository hotspotRepository;
    private final DistanceMatrixService distanceMatrixService;

    public HotspotSelector(HotspotRepository hotspotRepository,
                           DistanceMatrixService distanceMatrixService) {
        this.hotspotRepository = hotspotRepository;
        this.distanceMatrixService = distanceMatrixService;
    }

    public List<HotspotInfo> selectOptimalRoute(double startLat, double startLon, int budgetMeters) {
        double searchRadius = budgetMeters * SEARCH_RADIUS_RATIO;
        List<HotspotInfo> candidates = hotspotRepository.findTopNearby(
                startLat, startLon, searchRadius, MAX_CANDIDATES);

        if (candidates.isEmpty()) {
            return Collections.emptyList();
        }

        List<GHPoint> points = buildPointList(startLat, startLon, candidates);
        double[][] distMatrix = distanceMatrixService.computeMatrix(points);

        candidates = filterUnreachable(candidates, distMatrix);

        if (candidates.isEmpty()) {
            return Collections.emptyList();
        }

        // TODO: Phase 4b/4c에서 jsprit 최적화로 교체
        return candidates;
    }

    private List<GHPoint> buildPointList(double startLat, double startLon, List<HotspotInfo> candidates) {
        List<GHPoint> points = new ArrayList<>();
        points.add(new GHPoint(startLat, startLon));
        candidates.forEach(h -> points.add(new GHPoint(h.centerLat(), h.centerLon())));
        return points;
    }

    List<HotspotInfo> filterUnreachable(List<HotspotInfo> candidates, double[][] distMatrix) {
        List<HotspotInfo> reachable = new ArrayList<>();
        for (int i = 0; i < candidates.size(); i++) {
            if (distMatrix[0][i + 1] != DistanceMatrixService.UNREACHABLE) {
                reachable.add(candidates.get(i));
            }
        }
        return reachable;
    }
}
