package com.plobber.routing.service;

import com.graphhopper.jsprit.core.problem.Location;
import com.graphhopper.jsprit.core.problem.VehicleRoutingProblem;
import com.graphhopper.jsprit.core.problem.cost.VehicleRoutingTransportCosts;
import com.graphhopper.jsprit.core.problem.job.Service;
import com.graphhopper.jsprit.core.problem.vehicle.VehicleImpl;
import com.graphhopper.jsprit.core.problem.vehicle.VehicleType;
import com.graphhopper.jsprit.core.problem.vehicle.VehicleTypeImpl;
import com.graphhopper.jsprit.core.util.VehicleRoutingTransportCostsMatrix;
import com.graphhopper.util.shapes.GHPoint;
import com.plobber.routing.repository.HotspotInfo;
import com.plobber.routing.repository.HotspotRepository;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

@org.springframework.stereotype.Service
public class HotspotSelector {

    private static final int MAX_CANDIDATES = 15;
    private static final double SEARCH_RADIUS_RATIO = 0.4;
    private static final double WALKING_SPEED_MPS = 1.39;

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

        double[][] filteredMatrix = rebuildMatrix(candidates, points, distMatrix);
        VehicleRoutingProblem vrp = buildVrp(candidates, filteredMatrix, budgetMeters);

        // TODO: Phase 4c에서 알고리즘 실행 + 결과 추출
        return candidates;
    }

    VehicleRoutingProblem buildVrp(List<HotspotInfo> candidates, double[][] distMatrix, int budgetMeters) {
        VehicleRoutingTransportCosts costMatrix = buildCostMatrix(candidates, distMatrix);

        VehicleType walkerType = VehicleTypeImpl.Builder.newInstance("walker_type")
                .setCostPerDistance(1.0)
                .setCostPerTransportTime(0.0)
                .build();

        double maxTimeSeconds = budgetMeters / WALKING_SPEED_MPS;
        VehicleImpl walker = VehicleImpl.Builder.newInstance("walker")
                .setStartLocation(Location.newInstance("0"))
                .setEndLocation(Location.newInstance("0"))
                .setType(walkerType)
                .setLatestArrival(maxTimeSeconds)
                .build();

        VehicleRoutingProblem.Builder vrpBuilder = VehicleRoutingProblem.Builder.newInstance()
                .setRoutingCost(costMatrix)
                .addVehicle(walker)
                .setFleetSize(VehicleRoutingProblem.FleetSize.FINITE);

        for (int i = 0; i < candidates.size(); i++) {
            Service job = Service.Builder.newInstance("job_" + (i + 1))
                    .setLocation(Location.newInstance(String.valueOf(i + 1)))
                    .setServiceTime(0)
                    .build();
            vrpBuilder.addJob(job);
        }

        return vrpBuilder.build();
    }

    private VehicleRoutingTransportCosts buildCostMatrix(List<HotspotInfo> candidates, double[][] distMatrix) {
        int n = candidates.size() + 1;
        VehicleRoutingTransportCostsMatrix.Builder builder =
                VehicleRoutingTransportCostsMatrix.Builder.newInstance(true);

        for (int i = 0; i < n; i++) {
            for (int j = i + 1; j < n; j++) {
                String fromId = String.valueOf(i);
                String toId = String.valueOf(j);
                double dist = distMatrix[i][j];
                double time = dist / WALKING_SPEED_MPS;
                builder.addTransportDistance(fromId, toId, dist);
                builder.addTransportTime(fromId, toId, time);
            }
        }
        return builder.build();
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

    double[][] rebuildMatrix(List<HotspotInfo> filtered, List<GHPoint> originalPoints, double[][] original) {
        List<Integer> kept = new ArrayList<>();
        kept.add(0);
        for (HotspotInfo h : filtered) {
            for (int i = 1; i < originalPoints.size(); i++) {
                GHPoint p = originalPoints.get(i);
                if (Math.abs(p.getLat() - h.centerLat()) < 1e-9
                        && Math.abs(p.getLon() - h.centerLon()) < 1e-9) {
                    kept.add(i);
                    break;
                }
            }
        }

        int n = kept.size();
        double[][] result = new double[n][n];
        for (int i = 0; i < n; i++) {
            for (int j = 0; j < n; j++) {
                result[i][j] = original[kept.get(i)][kept.get(j)];
            }
        }
        return result;
    }
}
