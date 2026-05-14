package com.plobber.routing.service;

import com.graphhopper.GHRequest;
import com.graphhopper.GHResponse;
import com.graphhopper.GraphHopper;
import com.graphhopper.ResponsePath;
import com.graphhopper.util.CustomModel;
import com.graphhopper.util.shapes.GHPoint;
import com.plobber.routing.controller.RouteRequest;
import com.plobber.routing.graphhopper.CustomModelBuilder;
import org.springframework.stereotype.Service;

@Service
public class RouteService {

    private final GraphHopper graphHopper;
    private final CustomModelBuilder customModelBuilder;

    public RouteService(GraphHopper graphHopper, CustomModelBuilder customModelBuilder) {
        this.graphHopper = graphHopper;
        this.customModelBuilder = customModelBuilder;
    }

    public RouteResult calculateRoute(RouteRequest requestDto) {
        if (requestDto.distance() <= 0) {
            throw new IllegalArgumentException("Distance must be greater than 0");
        }
        if (Double.isNaN(requestDto.lat()) || Double.isNaN(requestDto.lon())) {
            throw new IllegalArgumentException("Coordinates cannot be NaN");
        }
        if (requestDto.lat() < -90 || requestDto.lat() > 90 || requestDto.lon() < -180 || requestDto.lon() > 180) {
            throw new IllegalArgumentException("Coordinates are out of bounds");
        }

        CustomModel customModel = customModelBuilder.build(requestDto.mode());

        GHRequest request = new GHRequest()
                .addPoint(new GHPoint(requestDto.lat(), requestDto.lon()))
                .setProfile("plogging_foot")
                .setAlgorithm("round_trip");
        
        request.getHints().putObject("round_trip.distance", requestDto.distance());
        request.getHints().putObject("round_trip.seed", (long) (Math.random() * 1000));
        request.getHints().putObject("ch.disable", true);
        request.setCustomModel(customModel);

        GHResponse response = graphHopper.route(request);

        if (response.hasErrors()) {
            throw new RuntimeException("Routing failed: " + response.getErrors().toString());
        }

        ResponsePath bestPath = response.getBest();
        
        String encodedPath = encodePolyline(bestPath.getPoints());
        
        return new RouteResult(bestPath.getDistance(), bestPath.getTime(), encodedPath);
    }

    private String encodePolyline(com.graphhopper.util.PointList points) {
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
