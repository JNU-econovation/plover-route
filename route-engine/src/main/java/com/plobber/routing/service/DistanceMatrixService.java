package com.plobber.routing.service;

import com.graphhopper.GHRequest;
import com.graphhopper.GHResponse;
import com.graphhopper.GraphHopper;
import com.graphhopper.util.shapes.GHPoint;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class DistanceMatrixService {

    public static final double UNREACHABLE = -1.0;

    private final GraphHopper graphHopper;

    public DistanceMatrixService(GraphHopper graphHopper) {
        this.graphHopper = graphHopper;
    }

    public double[][] computeMatrix(List<GHPoint> points) {
        int n = points.size();
        double[][] distances = new double[n][n];

        for (int i = 0; i < n; i++) {
            for (int j = i + 1; j < n; j++) {
                double dist = routeDistance(points.get(i), points.get(j));
                distances[i][j] = dist;
                distances[j][i] = dist;
            }
        }
        return distances;
    }

    private double routeDistance(GHPoint from, GHPoint to) {
        GHRequest request = new GHRequest(from, to)
                .setProfile("plogging_foot");
        request.getHints().putObject("ch.disable", true);

        GHResponse response = graphHopper.route(request);

        if (response.hasErrors()) {
            return UNREACHABLE;
        }

        return response.getBest().getDistance();
    }
}
