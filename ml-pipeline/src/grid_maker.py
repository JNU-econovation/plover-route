import os
import time
import argparse
import yaml
import numpy as np
import geopandas as gpd
import osmnx as ox
from shapely.geometry import box
from pathlib import Path

def generate_grid(region: str, grid_size: int, buffer_size: int, force_download: bool):
    """
    OSMnx API를 활용해 보행망 네트워크를 수집하고, 
    지정된 크기의 격자망(Grid)을 생성하여 모델 도화지를 마스킹합니다.
    """
    # 1. 경로 및 설정 세팅
    src_dir = Path(__file__).parent.resolve()
    project_root = src_dir.parent
    config_path = project_root / 'config.yaml'
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
        
    BASE_CRS = config['spatial']['base_crs']
    PROJ_CRS = config['spatial']['projected_crs']
    
    raw_dir = (project_root / config['data']['paths']['raw']).resolve()
    processed_dir = (project_root / config['data']['paths']['processed']).resolve()
    
    # 폴더 안전장치
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"✅ 설정 로드 완료: Region='{region}' | Proj='{PROJ_CRS}' | Grid={grid_size}m | Buffer={buffer_size}m")
    
    # 2. OSM 데이터 가져오기 및 캐싱
    # 파일명을 위해 불필요한 특수문자 제거 후 변환
    safe_region_name = region.lower().replace(" ", "_").replace(",", "")
    graphml_path = raw_dir / f"network_{safe_region_name}_raw.graphml"
    
    t0 = time.time()
    if graphml_path.exists() and not force_download:
        print(f"📦 로컬 캐시 발견! [{graphml_path.name}] 파일에서 그래프 데이터를 고속으로 로딩합니다.")
        # Rule 1, 4 준수: 내부적으로 EPSG:4326으로 저장됨
        graph = ox.load_graphml(graphml_path)
    else:
        print(f"🌐 [{region}] 도로망 실시간 다운로드 중 (OSM API)... 이 작업은 다소 시간이 소요됩니다.")
        graph = ox.graph_from_place(region, network_type="walk")
        # Rule 4: 원본 API 데이터 백업/캐싱
        ox.save_graphml(graph, graphml_path)
        print(f"💾 원본 그래프 캐싱 완료: {graphml_path.name}")
        
    # 선형 에지(도로)만 추출 (nodes는 사용 안 함)
    nodes, edges = ox.graph_to_gdfs(graph)
    print(f"⏱️ 그래프 준비 완료 (소요시간: {time.time()-t0:.2f}초), 총 엣지: {len(edges)} 개")
    
    # Rule 1: 미터(Meter) 단위 처리를 위해 타겟 좌표계로 강제 투영
    edges_proj = edges.to_crs(PROJ_CRS)
    
    # 3. 보행 구역 마스킹 (Buffer)
    print(f"✂️ 도로 중심선 기준 {buffer_size}m 보행 면적 버퍼 연산 중...")
    walking_areas = edges_proj.geometry.buffer(buffer_size)
    gdf_walkable = gpd.GeoDataFrame(geometry=walking_areas, crs=PROJ_CRS).reset_index(drop=True)
    
    # 4. 전체 격자(Grid) 생성 구역 추출 (BB)
    print(f"📏 {grid_size}m 정방형 격자망(Grid) 기본 배열 도화지 생성 중...")
    minx, miny, maxx, maxy = edges_proj.total_bounds
    minx -= buffer_size * 2
    miny -= buffer_size * 2
    maxx += buffer_size * 2
    maxy += buffer_size * 2
    
    x_coords = np.arange(minx, maxx, grid_size)
    y_coords = np.arange(miny, maxy, grid_size)
    
    # 격자 폴리곤 생성
    polygons = [box(x, y, x + grid_size, y + grid_size) for x in x_coords for y in y_coords]
    grid_gdf = gpd.GeoDataFrame(geometry=polygons, crs=PROJ_CRS)
    print(f"초기 생성된 전체 격자 타일 수: {len(grid_gdf)} 개")
    
    # 5. 공간 조인(Spatial Index링 최적화)으로 쓰레기 구역 마스킹
    print("📍 Rule 2 적용: sjoin을 이용한 위치 기반 타겟팅 연산 최적화 중...")
    grid_masked = gpd.sjoin(grid_gdf, gdf_walkable, predicate='intersects')
    
    # 중복 교차된 격자 제거
    grid_masked = grid_masked[~grid_masked.index.duplicated(keep='first')].copy()
    grid_masked = grid_masked.drop(columns=['index_right']).reset_index(drop=True)
    grid_masked['grid_id'] = grid_masked.index.astype(str)
    
    print(f"✅ 마스킹 최적화 처리 성공! (실제 쓰일 데이터셋 크기: {len(grid_masked)} 개)")
    
    # 6. GeoPackage 포맷으로 내보내기 (Rule 4 준수)
    output_filename = f"grid_{safe_region_name}_{grid_size}m_buf{buffer_size}m.gpkg"
    output_path = processed_dir / output_filename
    grid_masked.to_file(output_path, driver='GPKG', layer=f'grid_{grid_size}m')
    print(f"🚀 [완료] 파이프라인 중간 결과물 저장됨 -> {output_path}")

