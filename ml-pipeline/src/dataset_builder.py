import os
from dotenv import load_dotenv
import time
import yaml
import pandas as pd
import geopandas as gpd
from sqlalchemy import create_engine, text
from pathlib import Path
from src.utils import get_safe_region_name, load_config, get_data_dirs, get_standard_filename, ensure_crs, Timer
from abc import ABC, abstractmethod

class BaseViewLoader(ABC):
    @abstractmethod
    def load_view(self, engine) -> gpd.GeoDataFrame:
        pass

class BaselineViewLoader(BaseViewLoader):
    def load_view(self, engine) -> gpd.GeoDataFrame:
        print("DB에서 'ml_unified_labels_view_baseline' 뷰를 불러옵니다...")
        
        view_sql = """
        CREATE MATERIALIZED VIEW IF NOT EXISTS ml_unified_labels_view_baseline AS
        SELECT 
            geometry as geom,
            1 AS is_trash
        FROM 
            raw_trash_reports;
        """
        
        with engine.connect() as conn:
            conn.execute(text(view_sql))
            conn.commit()
            
        gdf = gpd.read_postgis(
            "SELECT geom, is_trash FROM ml_unified_labels_view_baseline", 
            con=engine,
            geom_col='geom'
        )
        return gdf

class DatasetBuilder:
    def __init__(self, region: str, grid_size: int, buffer_size: int, view_type: str = "baseline", feature_type: str = "poi"):
        self.region = region
        self.grid_size = grid_size
        self.buffer_size = buffer_size
        self.feature_type = feature_type
        self.safe_region_name = get_safe_region_name(region)
        
        self.config = load_config()
        self.raw_dir, self.processed_dir = get_data_dirs(self.config)
        self.PROJ_CRS = self.config['spatial']['projected_crs']
        
        self.view_loader_map = {
            'baseline': BaselineViewLoader
        }
        
        if view_type not in self.view_loader_map:
            raise ValueError(f" 지원하지 않는 View 타입입니다: {view_type}")
            
        self.view_loader = self.view_loader_map[view_type]()
        self.view_type_name = view_type

    def build(self):
        t0 = time.time()
        db_url = os.environ.get('DATABASE_URL')
        if not db_url:
            raise ValueError(" .env 파일에 DATABASE_URL이 설정되지 않았습니다.")
        engine = create_engine(db_url)
        
        labels_gdf = self.view_loader.load_view(engine)
        print(f"  -> DB 로드 완료: 총 {len(labels_gdf):,}건 (현재 좌표계: {labels_gdf.crs})")
        
        labels_gdf = ensure_crs(labels_gdf, self.PROJ_CRS)
        
        features_filename = get_standard_filename("features", self.region, self.grid_size, self.buffer_size, suffix=self.feature_type)
        target_path = self.processed_dir / features_filename
        
        if not target_path.exists():
            raise FileNotFoundError(f" 대상 Grid 피처 파일을 찾을 수 없습니다: {target_path.name}\n"
                                    f"   먼저 'add-grid' 및 'add-features' 명령어를 실행해주세요.")
                                    
        print(f"타겟 피처 Grid 로드 중: {target_path.name}...")
        grid_features = gpd.read_file(target_path)
        print(f"  -> Grid 로드 완료: 총 {len(grid_features):,}개")

        print("공간 조인을 통한 정답 라벨(Y) 맵핑 시작...")
        labels_gdf = ensure_crs(labels_gdf, grid_features.crs)
        
        # Preserve the actual frequency (count) of trash reports inside each grid cell
        print(" -> [정보 보존] 각 격자 공간 내 실제 쓰레기 발생 빈도(trash_count) 집계 중...")
        if not labels_gdf.empty:
            count_join = gpd.sjoin(grid_features, labels_gdf, how='inner', predicate='contains')
            trash_counts = count_join.groupby(count_join.index).size().rename("trash_count")
            grid_features = grid_features.join(trash_counts, how='left')
            grid_features['trash_count'] = grid_features['trash_count'].fillna(0).astype(int)
        else:
            grid_features['trash_count'] = 0
            
        # Apply spatial smoothing buffer to mitigate GPS errors and grid boundary alignment issues
        smoothing_radius = float(self.grid_size)
        print(f" -> [공간 스무딩] GPS 수신 오차 흡수 및 경계선 왜곡 극복을 위해 쓰레기 지점 주변 {smoothing_radius}m 버퍼 스무딩 적용 중...")
        smoothed_labels = labels_gdf.copy()
        smoothed_labels.geometry = smoothed_labels.geometry.buffer(smoothing_radius)
        
        merged_gdf = gpd.sjoin(grid_features, smoothed_labels, how='left', predicate='intersects')
        
        merged_gdf = merged_gdf[~merged_gdf.index.duplicated(keep='first')]
        merged_gdf['is_trash'] = merged_gdf['is_trash'].fillna(0).astype(int)
        
        if 'index_right' in merged_gdf.columns:
            merged_gdf = merged_gdf.drop(columns=['index_right'])
            
        trash_count = merged_gdf['is_trash'].sum()
        total_count = len(merged_gdf)
        ratio = (trash_count / total_count) * 100
        print(f"쓰레기 투기 위험 구역 격자 수 (스무딩 적용): {trash_count:,}개")
        print(f"안전 구역 격자 수: {total_count - trash_count:,}개")
        print(f"클래스 불균형 비율: {ratio:.4f}%")

        suffix = f"{self.view_type_name}_{self.feature_type.replace(',', '_').replace(' ', '')}"
        output_filename = get_standard_filename("dataset", self.region, self.grid_size, self.buffer_size, suffix=suffix)
        output_path = self.processed_dir / output_filename
        print(f"최종 학습 데이터셋 저장 중... -> {output_filename}")
        merged_gdf.to_file(output_path, driver='GPKG', layer='dataset')
        print(f" 최종 데이터셋 생성됨 (소요시간: {time.time()-t0:.2f}초) -> {output_path}")
