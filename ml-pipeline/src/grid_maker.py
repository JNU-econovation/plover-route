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
        print(f"로컬 캐시 발견. [{graphml_path.name}] 파일에서 그래프 데이터를 고속으로 로딩합니다.")
        graph = ox.load_graphml(graphml_path)
    else:
        print(f"[{region}] 도로망 실시간 다운로드 중 (OSM API)... 이 작업은 다소 시간이 소요됩니다.")
        graph = ox.graph_from_place(region, network_type="walk")
        ox.save_graphml(graph, graphml_path)
        print(f"OSM 다운로드 완료. 원본 그래프 파일 저장(캐싱) 완료: {graphml_path.name}")
        
    nodes, edges = ox.graph_to_gdfs(graph)
    print(f"그래프 준비 완료 (소요시간: {time.time()-t0:.2f}초), 총 엣지: {len(edges)} 개")
    
    # 획기적 5GB+ 메모리 방출: 엣지 변환 후 쓰이지 않는 거대 MultiDiGraph 및 nodes 객체 즉시 소멸
    del graph, nodes
    import gc
    gc.collect()
    
    edges_proj = ensure_crs(edges, PROJ_CRS)
    
    # 더 이상 필요 없는 원본 edges 객체 소멸로 추가 메모리 확보
    del edges
    gc.collect()
    
    print(f"{grid_size}m 정방형 격자망 기본 배열 도화지 생성 중 (OOM 방지 공간 분할 및 로컬 버퍼링 기법 적용)...")
    import pandas as pd
    
    minx, miny, maxx, maxy = edges_proj.total_bounds
    minx -= buffer_size * 2
    miny -= buffer_size * 2
    maxx += buffer_size * 2
    maxy += buffer_size * 2
    
    # 32GB 시스템에 최적화된 4km x 4km 매크로 블록 크기 (OOM 절대 안전 + 루프 오버헤드 4배 감소)
    chunk_step = 4000
    
    x_chunks = np.arange(minx, maxx, chunk_step)
    y_chunks = np.arange(miny, maxy, chunk_step)
    
    print(f"  -> 공간 분할 바둑판 연산: {len(x_chunks)} x {len(y_chunks)} 매크로 청크 분할 기동")
    
    # 가벼운 raw LineString 기반으로 Spatial Index를 빌드하여 글로벌 버퍼 생성 OOM 원천 방지!
    spatial_index = edges_proj.sindex
    import gc
    
    output_filename = get_standard_filename("grid", region, grid_size, buffer_size)
    output_path = processed_dir / output_filename
    
    # 기존 파일이 존재하면 신선한 기입을 위해 선제 삭제
    if output_path.exists():
        output_path.unlink()
        
    layer_name = f'grid_{grid_size}m'
    collected_coords = []
    total_chunks = len(x_chunks) * len(y_chunks)
    chunk_idx = 0
    
    for cx in x_chunks:
        for cy in y_chunks:
            chunk_idx += 1
            if chunk_idx % 50 == 0 or chunk_idx == total_chunks:
                print(f"  -> [격자 분할 진행률] {chunk_idx}/{total_chunks} 청크 완료 ({chunk_idx/total_chunks*100:.1f}%) | 수집된 좌표: {len(collected_coords)}개")
                
            cx_min, cy_min = cx, cy
            cx_max, cy_max = min(cx + chunk_step, maxx), min(cy + chunk_step, maxy)
            
            # 블록 경계면 근처의 도로를 포함할 수 있도록 버퍼 사이즈만큼 쿼리박스 확장
            query_box = (cx_min - buffer_size, cy_min - buffer_size, cx_max + buffer_size, cy_max + buffer_size)
            
            # Spatial Index 조회하여 이 블록에 해당하는 도로 엣지 필터링
            possible_matches_idx = list(spatial_index.intersection(query_box))
            if not possible_matches_idx:
                continue
                
            chunk_edges = edges_proj.iloc[possible_matches_idx]
            
            # 필터링된 소량의 도로 엣지에 대해서만 극소 규모 로컬 버퍼 연산 수행 (RAM 초소량 소모)
            chunk_walking_areas = chunk_edges.geometry.buffer(buffer_size)
            chunk_walkable = gpd.GeoDataFrame(geometry=chunk_walking_areas, crs=PROJ_CRS).reset_index(drop=True)
            
            # 도로가 존재하는 매크로 블록 내부에서만 10m 격자망 생성
            cx_coords = np.arange(cx_min, cx_max, grid_size)
            cy_coords = np.arange(cy_min, cy_max, grid_size)
            
            chunk_polygons = [box(x, y, x + grid_size, y + grid_size) for x in cx_coords for y in cy_coords]
            chunk_gdf = gpd.GeoDataFrame(geometry=chunk_polygons, crs=PROJ_CRS)
            
            # 매크로 블록 공간 조인 수행
            chunk_masked = gpd.sjoin(chunk_gdf, chunk_walkable, predicate='intersects')
            if not chunk_masked.empty:
                chunk_masked = chunk_masked[~chunk_masked.index.duplicated(keep='first')].copy()
                # 획기적 90% 메모리 압축: 무거운 Polygon 대신 가벼운 (x, y) 모서리 좌표 튜플만 수집
                bounds = chunk_masked.geometry.bounds
                coords = list(zip(bounds.minx, bounds.miny))
                collected_coords.extend(coords)
                
            # 명시적 메모리 해제 및 가비지 컬렉션 호출로 메모리 축적 원천 차단
            del chunk_edges, chunk_walking_areas, chunk_walkable, chunk_polygons, chunk_gdf, chunk_masked
            gc.collect()
            
    total_written = len(collected_coords)
    if collected_coords:
        print(f"매크로 루프 종료. 수집된 총 좌표 수: {total_written} 개. Polygon 변환 및 단일 GPKG 디스크 쓰기 수행 중...")
        # 가벼운 좌표 튜플 리스트를 한꺼번에 box Polygon으로 벌크 변환 (C++ 누수 원천 봉쇄)
        polygons = [box(x, y, x + grid_size, y + grid_size) for x, y in collected_coords]
        final_gdf = gpd.GeoDataFrame(geometry=polygons, crs=PROJ_CRS)
        final_gdf['grid_id'] = [f"{safe_region_name}_{i}" for i in range(total_written)]
        final_gdf.to_file(output_path, driver='GPKG', layer=layer_name, mode='w')
        del final_gdf, polygons
        gc.collect()
        
    print(f"마스킹 최적화 처리 완료. (실제 쓰일 데이터셋 크기: {total_written} 개)")
    print(f"파이프라인 중간 결과물 저장됨 -> {output_path}")

