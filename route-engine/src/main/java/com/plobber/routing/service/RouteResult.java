package com.plobber.routing.service;

public record RouteResult(
    double distanceMeter,
    long timeMillis,
    String encodedPath,
    int ploggingScore
) {}
