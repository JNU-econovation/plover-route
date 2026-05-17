package com.plobber.routing.service;

import com.graphhopper.jsprit.core.algorithm.VehicleRoutingAlgorithm;
import com.graphhopper.jsprit.core.algorithm.box.Jsprit;
import com.graphhopper.jsprit.core.algorithm.recreate.Insertion;
import com.graphhopper.jsprit.core.algorithm.ruin.Ruin;
import com.graphhopper.jsprit.core.algorithm.state.StateManager;
import com.graphhopper.jsprit.core.problem.Location;
import com.graphhopper.jsprit.core.problem.VehicleRoutingProblem;
import com.graphhopper.jsprit.core.problem.constraint.ConstraintManager;
import com.graphhopper.jsprit.core.problem.constraint.HardActivityConstraint;
import com.graphhopper.jsprit.core.problem.cost.VehicleRoutingTransportCosts;
import com.graphhopper.jsprit.core.problem.job.Job;
import com.graphhopper.jsprit.core.problem.job.Service;
import com.graphhopper.jsprit.core.problem.misc.JobInsertionContext;
import com.graphhopper.jsprit.core.problem.solution.SolutionCostCalculator;
import com.graphhopper.jsprit.core.problem.solution.VehicleRoutingProblemSolution;
import com.graphhopper.jsprit.core.problem.solution.route.VehicleRoute;
import com.graphhopper.jsprit.core.problem.solution.route.activity.TourActivity;
import com.graphhopper.jsprit.core.problem.vehicle.VehicleImpl;
import com.graphhopper.jsprit.core.problem.vehicle.VehicleType;
import com.graphhopper.jsprit.core.problem.vehicle.VehicleTypeImpl;
import com.graphhopper.jsprit.core.util.Solutions;
import com.graphhopper.jsprit.core.util.VehicleRoutingTransportCostsMatrix;
import com.graphhopper.util.shapes.GHPoint;
import com.plobber.routing.repository.HotspotInfo;
import com.plobber.routing.repository.HotspotRepository;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@org.springframework.stereotype.Service
public class HotspotSelector {

    private static final Logger log = LoggerFactory.getLogger(HotspotSelector.class);
    private static final int MIN_CANDIDATES = 3;
    private static final int MAX_CANDIDATES_CAP = 10;
    private static final double CANDIDATES_PER_METER = 1.0 / 700.0;
    private static final int FETCH_MULTIPLIER = 3;
    private static final double SEGMENT_DISTANCE_RATIO = 0.25;
    private static final double SEARCH_RADIUS_RATIO = 0.4;
    private static final double WALKING_SPEED_MPS = 1.39;
    private static final double PENALTY_MULTIPLIER = 2000.0;
    private static final int MAX_ITERATIONS = 100;

    private final HotspotRepository hotspotRepository;
    private final DistanceMatrixService distanceMatrixService;

    public HotspotSelector(HotspotRepository hotspotRepository,
                           DistanceMatrixService distanceMatrixService) {
        this.hotspotRepository = hotspotRepository;
        this.distanceMatrixService = distanceMatrixService;
    }

    public List<HotspotInfo> selectOptimalRoute(double startLat, double startLon, int budgetMeters) {
        int targetVisitCount = calculateDynamicCandidates(budgetMeters);
        int fetchCount = targetVisitCount * FETCH_MULTIPLIER * 2; // Fetch even more to allow filtering
        double searchRadius = budgetMeters * SEARCH_RADIUS_RATIO;

        List<HotspotInfo> rawCandidates = hotspotRepository.findTopNearby(
                startLat, startLon, searchRadius, fetchCount);

        List<HotspotInfo> candidates = enforceSpatialDiversity(rawCandidates, 250.0);

        log.info("[HotspotSelector] budget={}m, targetVisit={}, fetched={}, diverse={}, radius={}m",
                budgetMeters, targetVisitCount, rawCandidates.size(), candidates.size(), searchRadius);

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
        Map<String, Double> jobScoreMap = buildJobScoreMap(candidates);
        VehicleRoutingProblem vrp = buildVrp(candidates, filteredMatrix, budgetMeters);

        double dynamicSegmentDist = calculateDynamicSegmentDistance(budgetMeters);
        SolverResult solverResult = solveAndExtract(vrp, jobScoreMap, dynamicSegmentDist);

        List<Integer> visitIndices = jobIdsToIndices(solverResult.visitOrder());
        List<Integer> unassignedIndices = jobIdsToIndices(solverResult.unassignedJobIds());

        log.info("[HotspotSelector] jsprit result: visited={}, unassigned={}",
                visitIndices.size(), unassignedIndices.size());

        Map<Integer, Double> indexScoreMap = new HashMap<>();
        for (int i = 0; i < candidates.size(); i++) {
            indexScoreMap.put(i + 1, candidates.get(i).score());
        }

        double currentDistance = calculateRouteDistance(visitIndices, filteredMatrix);
        double remainingBudget = budgetMeters - currentDistance;

        log.info("[HotspotSelector] matrix distance={}m, remainingBudget={}m",
                String.format("%.0f", currentDistance), String.format("%.0f", remainingBudget));

        if (remainingBudget > 0 && !unassignedIndices.isEmpty()) {
            visitIndices = greedyFillRemaining(
                    visitIndices, unassignedIndices, indexScoreMap, filteredMatrix, remainingBudget);
            log.info("[HotspotSelector] after greedy fill: visited={}", visitIndices.size());
        }

        List<String> finalJobIds = visitIndices.stream()
                .map(i -> "job_" + i)
                .toList();

        return orderCandidates(candidates, finalJobIds);
    }

    record SolverResult(List<String> visitOrder, List<String> unassignedJobIds) {}

    SolverResult solveAndExtract(VehicleRoutingProblem vrp, Map<String, Double> jobScoreMap, double maxSegmentDist) {
        SolutionCostCalculator objectiveFunction = buildObjectiveFunction(vrp, jobScoreMap);

        StateManager stateManager = new StateManager(vrp);
        ConstraintManager constraintManager = new ConstraintManager(vrp, stateManager);
        constraintManager.addTimeWindowConstraint();
        constraintManager.addConstraint(buildMaxSegmentConstraint(vrp, maxSegmentDist), ConstraintManager.Priority.HIGH);

        VehicleRoutingAlgorithm algorithm = Jsprit.Builder.newInstance(vrp)
                .setObjectiveFunction(objectiveFunction)
                .setStateAndConstraintManager(stateManager, constraintManager)
                .addRuinOperator(0.3, Ruin.radial(0.3))
                .addRuinOperator(0.2, Ruin.random(0.3))
                .addRuinOperator(0.2, Ruin.cluster())
                .addRuinOperator(0.3, Ruin.kruskalCluster())
                .addInsertionOperator(0.7, Insertion.regretFast())
                .addInsertionOperator(0.3, Insertion.best())
                .buildAlgorithm();

        algorithm.setMaxIterations(MAX_ITERATIONS);
        Collection<VehicleRoutingProblemSolution> solutions = algorithm.searchSolutions();
        VehicleRoutingProblemSolution best = Solutions.bestOf(solutions);

        List<String> visitOrder = new ArrayList<>();
        for (VehicleRoute route : best.getRoutes()) {
            for (TourActivity activity : route.getActivities()) {
                if (activity instanceof TourActivity.JobActivity jobActivity) {
                    visitOrder.add(jobActivity.getJob().getId());
                }
            }
        }

        List<String> unassignedJobIds = best.getUnassignedJobs().stream()
                .map(Job::getId)
                .toList();

        return new SolverResult(visitOrder, unassignedJobIds);
    }

    SolutionCostCalculator buildObjectiveFunction(VehicleRoutingProblem vrp, Map<String, Double> jobScoreMap) {
        return solution -> {
            double transportCost = 0.0;
            for (VehicleRoute route : solution.getRoutes()) {
                transportCost += route.getVehicle().getType().getVehicleCostParams().fix;
                TourActivity prev = route.getStart();
                for (TourActivity act : route.getActivities()) {
                    transportCost += vrp.getTransportCosts().getTransportCost(
                            prev.getLocation(), act.getLocation(),
                            prev.getEndTime(), route.getDriver(), route.getVehicle());
                    prev = act;
                }
                transportCost += vrp.getTransportCosts().getTransportCost(
                        prev.getLocation(), route.getEnd().getLocation(),
                        prev.getEndTime(), route.getDriver(), route.getVehicle());
            }

            double unassignedPenalty = 0.0;
            for (Job job : solution.getUnassignedJobs()) {
                double score = jobScoreMap.getOrDefault(job.getId(), 0.0);
                unassignedPenalty += score * PENALTY_MULTIPLIER;
            }

            return transportCost + unassignedPenalty;
        };
    }

    private HardActivityConstraint buildMaxSegmentConstraint(VehicleRoutingProblem vrp, double maxSegmentDist) {
        return (JobInsertionContext iFacts, TourActivity prevAct,
                TourActivity newAct, TourActivity nextAct, double prevActDepTime) -> {
            double dist = vrp.getTransportCosts().getTransportCost(
                    prevAct.getLocation(), newAct.getLocation(),
                    prevActDepTime, iFacts.getRoute().getDriver(), iFacts.getNewVehicle());

            if (dist > maxSegmentDist) {
                return HardActivityConstraint.ConstraintsStatus.NOT_FULFILLED;
            }
            return HardActivityConstraint.ConstraintsStatus.FULFILLED;
        };
    }

    int calculateDynamicCandidates(int budgetMeters) {
        return Math.clamp((int)(budgetMeters * CANDIDATES_PER_METER), MIN_CANDIDATES, MAX_CANDIDATES_CAP);
    }

    double calculateDynamicSegmentDistance(int budgetMeters) {
        return budgetMeters * SEGMENT_DISTANCE_RATIO;
    }

    List<Integer> greedyFillRemaining(List<Integer> visitOrder,
                                       List<Integer> unassignedIndices,
                                       Map<Integer, Double> scoreMap,
                                       double[][] distMatrix,
                                       double remainingBudget) {
        List<Integer> result = new ArrayList<>(visitOrder);

        if (unassignedIndices.isEmpty()) {
            return result;
        }

        List<int[]> insertionCandidates = new ArrayList<>();
        for (int idx : unassignedIndices) {
            int bestPos = 0;
            double minAdditional = Double.MAX_VALUE;

            for (int pos = 0; pos <= result.size(); pos++) {
                double additional = calculateAdditionalDistance(result, idx, pos, distMatrix);
                if (additional < minAdditional) {
                    minAdditional = additional;
                    bestPos = pos;
                }
            }
            insertionCandidates.add(new int[]{idx, bestPos, (int)(minAdditional * 1000)});
        }

        insertionCandidates.sort((a, b) -> {
            double ratioA = scoreMap.getOrDefault(a[0], 0.0) / Math.max(a[2] / 1000.0, 1.0);
            double ratioB = scoreMap.getOrDefault(b[0], 0.0) / Math.max(b[2] / 1000.0, 1.0);
            return Double.compare(ratioB, ratioA);
        });

        double budget = remainingBudget;
        for (int[] candidate : insertionCandidates) {
            int idx = candidate[0];
            double additional = candidate[2] / 1000.0;

            if (additional > budget) {
                continue;
            }

            int bestPos = findBestInsertionPosition(result, idx, distMatrix);
            double actualAdditional = calculateAdditionalDistance(result, idx, bestPos, distMatrix);

            if (actualAdditional <= budget) {
                result.add(bestPos, idx);
                budget -= actualAdditional;
            }
        }

        return result;
    }

    private double calculateAdditionalDistance(List<Integer> route, int newIdx, int pos, double[][] distMatrix) {
        int prevIdx = (pos == 0) ? 0 : route.get(pos - 1);
        int nextIdx = (pos >= route.size()) ? 0 : route.get(pos);

        double oldDist = distMatrix[prevIdx][nextIdx];
        double newDist = distMatrix[prevIdx][newIdx] + distMatrix[newIdx][nextIdx];

        return newDist - oldDist;
    }

    private int findBestInsertionPosition(List<Integer> route, int newIdx, double[][] distMatrix) {
        int bestPos = 0;
        double minAdditional = Double.MAX_VALUE;

        for (int pos = 0; pos <= route.size(); pos++) {
            double additional = calculateAdditionalDistance(route, newIdx, pos, distMatrix);
            if (additional < minAdditional) {
                minAdditional = additional;
                bestPos = pos;
            }
        }
        return bestPos;
    }

    double calculateRouteDistance(List<Integer> visitIndices, double[][] distMatrix) {
        if (visitIndices.isEmpty()) {
            return 0.0;
        }
        double total = distMatrix[0][visitIndices.get(0)];
        for (int i = 0; i < visitIndices.size() - 1; i++) {
            total += distMatrix[visitIndices.get(i)][visitIndices.get(i + 1)];
        }
        total += distMatrix[visitIndices.get(visitIndices.size() - 1)][0];
        return total;
    }

    private List<Integer> jobIdsToIndices(List<String> jobIds) {
        return jobIds.stream()
                .map(id -> Integer.parseInt(id.replace("job_", "")))
                .collect(ArrayList::new, ArrayList::add, ArrayList::addAll);
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

    private Map<String, Double> buildJobScoreMap(List<HotspotInfo> candidates) {
        Map<String, Double> map = new HashMap<>();
        for (int i = 0; i < candidates.size(); i++) {
            map.put("job_" + (i + 1), candidates.get(i).score());
        }
        return map;
    }

    private List<HotspotInfo> orderCandidates(List<HotspotInfo> candidates, List<String> visitOrder) {
        Map<String, HotspotInfo> jobToHotspot = new HashMap<>();
        for (int i = 0; i < candidates.size(); i++) {
            jobToHotspot.put("job_" + (i + 1), candidates.get(i));
        }

        List<HotspotInfo> ordered = new ArrayList<>();
        for (String jobId : visitOrder) {
            HotspotInfo h = jobToHotspot.get(jobId);
            if (h != null) {
                ordered.add(h);
            }
        }
        return ordered;
    }

    private List<HotspotInfo> enforceSpatialDiversity(List<HotspotInfo> candidates, double minDistanceMeters) {
        List<HotspotInfo> diverse = new ArrayList<>();
        for (HotspotInfo candidate : candidates) {
            boolean tooClose = false;
            for (HotspotInfo selected : diverse) {
                double dist = calculateHaversineDistance(
                        candidate.centerLat(), candidate.centerLon(),
                        selected.centerLat(), selected.centerLon());
                if (dist < minDistanceMeters) {
                    tooClose = true;
                    break;
                }
            }
            if (!tooClose) {
                diverse.add(candidate);
            }
        }
        return diverse;
    }

    private double calculateHaversineDistance(double lat1, double lon1, double lat2, double lon2) {
        final int R = 6371000; // Earth radius in meters
        double latDistance = Math.toRadians(lat2 - lat1);
        double lonDistance = Math.toRadians(lon2 - lon1);
        double a = Math.sin(latDistance / 2) * Math.sin(latDistance / 2)
                + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2))
                * Math.sin(lonDistance / 2) * Math.sin(lonDistance / 2);
        double c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        return R * c;
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
