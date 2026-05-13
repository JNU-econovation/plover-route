package com.plobber.routing.controller;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

@Data
public class RouteRequest {
    
    @NotNull(message = "위도(lat)는 필수입니다.")
    @Min(value = -90, message = "위도는 -90 이상이어야 합니다.")
    @Max(value = 90, message = "위도는 90 이하이어야 합니다.")
    private Double lat;

    @NotNull(message = "경도(lon)는 필수입니다.")
    @Min(value = -180, message = "경도는 -180 이상이어야 합니다.")
    @Max(value = 180, message = "경도는 180 이하이어야 합니다.")
    private Double lon;

    @Min(value = 500, message = "왕복 거리는 최소 500m 이상이어야 합니다.")
    @Max(value = 30000, message = "왕복 거리는 최대 30km(30000m)를 넘을 수 없습니다.")
    private Integer distance = 5000;

    private String mode = "PLOGGING";
}
