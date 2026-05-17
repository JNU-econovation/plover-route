package com.plobber.routing.repository;

public record HotspotInfo(
    String id,
    double centerLat,
    double centerLon,
    double score
) {}
