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

import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@org.springframework.stereotype.Service
public class HotspotSelector {

    private static final int MIN_CANDIDATES = 3;
    private static final int MAX_CANDIDATES_CAP = 10;
    private static final double CANDIDATES_PER_METER = 1.0 / 700.0;
    private static final double SEGMENT_DISTANCE_RATIO = 0.25;
    private static final double SEARCH_RADIUS_RATIO = 0.25;
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
        double searchRadius = budgetMeters * SEARCH_RADIUS_RATIO;
        int dynamicCandidates = calculateDynamicCandidates(budgetMeters);
        List<HotspotInfo> candidates = hotspotRepository.findTopNearby(
                startLat, startLon, searchRadius, dynamicCandidates);

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
        List<String> visitOrder = solveAndExtract(vrp, jobScoreMap, dynamicSegmentDist);

        return orderCandidates(candidates, visitOrder);
    }

    List<String> solveAndExtract(VehicleRoutingProblem vrp, Map<String, Double> jobScoreMap, double maxSegmentDist) {
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
        return visitOrder;
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
