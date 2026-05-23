package com.plobber.routing.service;

import com.graphhopper.GHRequest;
import com.graphhopper.GHResponse;
import com.graphhopper.GraphHopper;
import com.graphhopper.ResponsePath;
import com.graphhopper.util.CustomModel;
import com.graphhopper.util.PointList;
import com.graphhopper.util.shapes.GHPoint;
import com.plobber.routing.controller.RouteRequest;
import com.plobber.routing.graphhopper.CustomModelBuilder;
import com.plobber.routing.repository.HotspotInfo;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;

@Service
public class RouteService {

    private static final Logger log = LoggerFactory.getLogger(RouteService.class);

    private static final int MONTE_CARLO_SAMPLES = 15;
    private static final int MAX_RECOMMENDED_ROUTES = 3;
    
    private static final double IDEAL_DISTANCE_TOLERANCE = 0.20;
    private static final double RELAXED_DISTANCE_TOLERANCE = 0.40;
    
    private static final double IDEAL_HEADING_TOLERANCE = Math.toRadians(60);
    private static final double RELAXED_HEADING_TOLERANCE = Math.toRadians(30);
    private static final double NO_HEADING_TOLERANCE = 0.0;

    private static final int BASELINE_PLOGGING_SCORE = 15;
    private static final int MAXIMUM_PLOGGING_SCORE = 98;
    private static final int NEUTRAL_PLOGGING_SCORE = 50;
    private static final int WAYPOINT_ROUTE_SCORE = 95;

    private final GraphHopper graphHopper;
    private final CustomModelBuilder customModelBuilder;
    private final HotspotSelector hotspotSelector;

    public RouteService(GraphHopper graphHopper, CustomModelBuilder customModelBuilder,
                        HotspotSelector hotspotSelector) {
        this.graphHopper = graphHopper;
        this.customModelBuilder = customModelBuilder;
        this.hotspotSelector = hotspotSelector;
    }

    private record Candidate(
        ResponsePath path,
        long seed,
        double score,
        double heading
    ) {}

    public List<RouteResult> calculateRoute(RouteRequest requestDto) {
        validateRequest(requestDto);

        List<HotspotInfo> selectedHotspots = java.util.Collections.emptyList();
        CustomModel customModel = customModelBuilder.build(requestDto.mode());

        if (!selectedHotspots.isEmpty()) {
            GHRequest request = buildWaypointRequest(requestDto, selectedHotspots, customModel);
            GHResponse response = graphHopper.route(request);
            if (response.hasErrors()) {
                throw new RuntimeException("Waypoint routing failed: " + response.getErrors().toString());
            }
            ResponsePath bestPath = response.getBest();
            return List.of(new RouteResult(bestPath.getDistance(), bestPath.getTime(), encodePolyline(bestPath.getPoints()), WAYPOINT_ROUTE_SCORE));
        }

        List<Candidate> allCandidates = new ArrayList<>();
        GHPoint startPoint = new GHPoint(requestDto.lat(), requestDto.lon());

        for (int i = 0; i < MONTE_CARLO_SAMPLES; i++) {
            long seed = (long) (Math.random() * 1000);
            GHRequest request = buildRoundTripRequest(requestDto, customModel, seed);
            try {
                GHResponse response = graphHopper.route(request);
                if (!response.hasErrors()) {
                    ResponsePath path = response.getBest();
                    double distance = path.getDistance();
                    double weight = path.getRouteWeight();
                    double score = (weight > 0) ? (distance / weight) : 0.0;
                    double heading = calculateHeading(startPoint, path.getPoints());
                    allCandidates.add(new Candidate(path, seed, score, heading));
                }
            } catch (Exception e) {
                log.warn("Round trip routing iteration failed for seed={}", seed, e);
            }
        }

        if (allCandidates.isEmpty()) {
            throw new RuntimeException("모든 왕복 경로 생성 시도가 실패했습니다.");
        }

        double maxScore = allCandidates.stream().mapToDouble(Candidate::score).max().orElse(1.0);
        double minScore = allCandidates.stream().mapToDouble(Candidate::score).min().orElse(0.0);
        double scoreDiff = maxScore - minScore;

        allCandidates.sort((c1, c2) -> Double.compare(c2.score(), c1.score()));

        List<Candidate> selected = new ArrayList<>();
        double targetDist = requestDto.distance();

        selectDiverseCandidates(allCandidates, selected, targetDist, IDEAL_DISTANCE_TOLERANCE, IDEAL_HEADING_TOLERANCE);

        if (selected.size() < MAX_RECOMMENDED_ROUTES) {
            selectDiverseCandidates(allCandidates, selected, targetDist, IDEAL_DISTANCE_TOLERANCE, RELAXED_HEADING_TOLERANCE);
        }

        if (selected.size() < MAX_RECOMMENDED_ROUTES) {
            selectDiverseCandidates(allCandidates, selected, targetDist, RELAXED_DISTANCE_TOLERANCE, NO_HEADING_TOLERANCE);
        }

        if (selected.size() < MAX_RECOMMENDED_ROUTES) {
            for (Candidate c : allCandidates) {
                if (selected.size() >= MAX_RECOMMENDED_ROUTES) break;
                if (!selected.contains(c)) {
                    selected.add(c);
                }
            }
        }

        return selected.stream()
                .limit(MAX_RECOMMENDED_ROUTES)
                .map(c -> {
                    int ploggingScore = (scoreDiff > 1e-6)
                            ? (int) (BASELINE_PLOGGING_SCORE + (c.score() - minScore) / scoreDiff * (MAXIMUM_PLOGGING_SCORE - BASELINE_PLOGGING_SCORE))
                            : NEUTRAL_PLOGGING_SCORE;
                    return new RouteResult(
                            c.path().getDistance(),
                            c.path().getTime(),
                            encodePolyline(c.path().getPoints()),
                            ploggingScore
                    );
                })
                .collect(Collectors.toList());
    }

    private void selectDiverseCandidates(List<Candidate> candidates, List<Candidate> selected,
                                         double targetDistance, double distanceTolerance, double headingTolerance) {
        for (Candidate c : candidates) {
            if (selected.size() >= MAX_RECOMMENDED_ROUTES) break;
            if (selected.contains(c)) continue;

            double dist = c.path().getDistance();
            if (dist < targetDistance * (1.0 - distanceTolerance) || dist > targetDistance * (1.0 + distanceTolerance)) {
                continue;
            }

            boolean isDiverse = true;
            for (Candidate s : selected) {
                double diff = Math.abs(c.heading() - s.heading());
                if (diff > Math.PI) {
                    diff = 2 * Math.PI - diff;
                }
                if (diff < headingTolerance) {
                    isDiverse = false;
                    break;
                }
            }

            if (isDiverse) {
                selected.add(c);
            }
        }
    }

    private double calculateHeading(GHPoint start, PointList points) {
        if (points.size() <= 2) return 0.0;
        double sumLat = 0;
        double sumLon = 0;
        int count = 0;
        for (int i = 1; i < points.size() - 1; i++) {
            sumLat += points.getLat(i);
            sumLon += points.getLon(i);
            count++;
        }
        if (count == 0) return 0.0;
        double avgLat = sumLat / count;
        double avgLon = sumLon / count;
        return Math.atan2(avgLon - start.getLon(), avgLat - start.getLat());
    }

    private GHRequest buildWaypointRequest(RouteRequest requestDto,
                                           List<HotspotInfo> hotspots,
                                           CustomModel customModel) {
        GHRequest request = new GHRequest();
        request.addPoint(new GHPoint(requestDto.lat(), requestDto.lon()));

        for (HotspotInfo h : hotspots) {
            request.addPoint(new GHPoint(h.centerLat(), h.centerLon()));
        }

        request.addPoint(new GHPoint(requestDto.lat(), requestDto.lon()));

        request.setProfile("plogging_foot");
        request.getHints().putObject("ch.disable", true);
        request.setCustomModel(customModel);

        return request;
    }

    private GHRequest buildRoundTripRequest(RouteRequest requestDto, CustomModel customModel, long seed) {
        GHRequest request = new GHRequest()
                .addPoint(new GHPoint(requestDto.lat(), requestDto.lon()))
                .setProfile("plogging_foot")
                .setAlgorithm("round_trip");

        request.getHints().putObject("round_trip.distance", requestDto.distance());
        request.getHints().putObject("round_trip.seed", seed);
        request.getHints().putObject("ch.disable", true);
        request.setCustomModel(customModel);

        return request;
    }

    private void validateRequest(RouteRequest requestDto) {
        if (requestDto.distance() <= 0) {
            throw new IllegalArgumentException("Distance must be greater than 0");
        }
        if (Double.isNaN(requestDto.lat()) || Double.isNaN(requestDto.lon())) {
            throw new IllegalArgumentException("Coordinates cannot be NaN");
        }
        if (requestDto.lat() < -90 || requestDto.lat() > 90
                || requestDto.lon() < -180 || requestDto.lon() > 180) {
            throw new IllegalArgumentException("Coordinates are out of bounds");
        }
    }

    private String encodePolyline(PointList points) {
        long prevLat = 0;
        long prevLon = 0;
        StringBuilder sb = new StringBuilder();

        for (int i = 0; i < points.size(); i++) {
            long lat = Math.round(points.getLat(i) * 1e5);
            long lon = Math.round(points.getLon(i) * 1e5);

            encodeNumber(lat - prevLat, sb);
            encodeNumber(lon - prevLon, sb);

            prevLat = lat;
            prevLon = lon;
        }
        return sb.toString();
    }

    private void encodeNumber(long v, StringBuilder sb) {
        v = v < 0 ? ~(v << 1) : v << 1;
        while (v >= 0x20) {
            sb.append((char) ((0x20 | (v & 0x1f)) + 63));
            v >>= 5;
        }
        sb.append((char) (v + 63));
    }
}
