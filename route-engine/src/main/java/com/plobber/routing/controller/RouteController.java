package com.plobber.routing.controller;

import com.plobber.routing.service.RouteResult;
import com.plobber.routing.service.RouteService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import jakarta.validation.Valid;

@RestController
@RequestMapping("/api/v1/route")
public class RouteController {

    private final RouteService routeService;

    public RouteController(RouteService routeService) {
        this.routeService = routeService;
    }

    @GetMapping
    public ResponseEntity<RouteResult> getRoute(@Valid @org.springframework.web.bind.annotation.ModelAttribute RouteRequest request) {
        RouteResult result = routeService.calculateRoute(request);
        return ResponseEntity.ok(result);
    }
}
