import os
import time
from src.utils import get_safe_region_name, load_config, get_data_dirs, get_standard_filename, ensure_crs, Timer
import argparse
import yaml
import numpy as np
import geopandas as gpd
import osmnx as ox
from shapely.geometry import box
from pathlib import Path

def generate_grid(region: str, grid_size: int, buffer_size: int, force_download: bool):
    config = load_config()
    BASE_CRS = config['spatial']['base_crs']
    PROJ_CRS = config['spatial']['projected_crs']
    raw_dir, processed_dir = get_data_dirs(config)
    
    print(f"설정 로드 완료: Region='{region}' | Proj='{PROJ_CRS}' | Grid={grid_size}m | Buffer={buffer_size}m")
    
    safe_region_name = get_safe_region_name(region)
    graphml_path = raw_dir / f"network_{safe_region_name}_raw.graphml"
    
    t0 = time.time()
    if graphml_path.exists() and not force_download:
        print(f"로컬 캐시 발견! [{graphml_path.name}] 파일에서 그래프 데이터를 고속으로 로딩합니다.")
        graph = ox.load_graphml(graphml_path)
    else:
        print(f"[{region}] 도로망 실시간 다운로드 중 (OSM API)... 이 작업은 다소 시간이 소요됩니다.")
        graph = ox.graph_from_place(region, network_type="walk")
        ox.save_graphml(graph, graphml_path)
        print(f"OSM 다운로드 성공! 원본 그래프 파일 저장(캐싱) 완료: {graphml_path.name}")
        
    nodes, edges = ox.graph_to_gdfs(graph)
    print(f"그래프 준비 완료 (소요시간: {time.time()-t0:.2f}초), 총 엣지: {len(edges)} 개")
    
    edges_proj = ensure_crs(edges, PROJ_CRS)
    
    print(f"도로 중심선 기준 {buffer_size}m 보행 면적 버퍼 연산 중...")
    walking_areas = edges_proj.geometry.buffer(buffer_size)
    gdf_walkable = gpd.GeoDataFrame(geometry=walking_areas, crs=PROJ_CRS).reset_index(drop=True)
    
    print(f"{grid_size}m 정방형 격자망(Grid) 기본 배열 도화지 생성 중...")
    minx, miny, maxx, maxy = edges_proj.total_bounds
    minx -= buffer_size * 2
    miny -= buffer_size * 2
    maxx += buffer_size * 2
    maxy += buffer_size * 2
    
    x_coords = np.arange(minx, maxx, grid_size)
    y_coords = np.arange(miny, maxy, grid_size)
    
    polygons = [box(x, y, x + grid_size, y + grid_size) for x in x_coords for y in y_coords]
    grid_gdf = gpd.GeoDataFrame(geometry=polygons, crs=PROJ_CRS)
    print(f"초기 생성된 전체 격자 타일 수: {len(grid_gdf)} 개")
    
    print("sjoin을 이용한 위치 기반 타겟팅 연산 최적화 중...")
    grid_masked = gpd.sjoin(grid_gdf, gdf_walkable, predicate='intersects')
    
    grid_masked = grid_masked[~grid_masked.index.duplicated(keep='first')].copy()
    grid_masked = grid_masked.drop(columns=['index_right']).reset_index(drop=True)
    grid_masked['grid_id'] = grid_masked.index.astype(str)
    
    print(f"마스킹 최적화 처리 성공! (실제 쓰일 데이터셋 크기: {len(grid_masked)} 개)")
    
    output_filename = get_standard_filename("grid", region, grid_size, buffer_size)
    output_path = processed_dir / output_filename
    grid_masked.to_file(output_path, driver='GPKG', layer=f'grid_{grid_size}m')
    print(f"🚀 [완료] 파이프라인 중간 결과물 저장됨 -> {output_path}")

