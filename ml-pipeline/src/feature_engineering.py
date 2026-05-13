import time
import yaml
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from pathlib import Path
from src.utils import get_safe_region_name, load_config, get_data_dirs, get_standard_filename, ensure_crs, Timer
from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseFeatureExtractor(ABC):
    def __init__(self, config: Dict[str, Any], region: str, raw_dir: Path):
        self.config = config
        self.region = region
        self.safe_region_name = get_safe_region_name(region)
        self.raw_dir = raw_dir
        self.BASE_CRS = config['spatial']['base_crs']
        self.PROJ_CRS = config['spatial']['projected_crs']
        
    @abstractmethod
    def extract(self, grid_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        pass

class POIFeatureExtractor(BaseFeatureExtractor):
    
    BUFFER_RADII = [30, 50, 100]
    
    @staticmethod
    def _categorize_poi(row) -> str:
        large = str(row['상권업종대분류명'])
        med = str(row['상권업종중분류명']).strip()
        
        if med == '주점': return 'nightlife'
        elif med in ['비알코올', '기타 간이']: return 'cafe'
        elif large == '음식': return 'food'
        elif large == '소매': return 'retail'
        else: return 'service'

    def extract(self, grid_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        input_filename = f"poi_{self.safe_region_name}_raw.csv"
        input_path = self.raw_dir / input_filename
        
        if not input_path.exists():
            parts = [p.strip() for p in self.region.split(',')]
            if len(parts) > 1:
                parent_region = ", ".join(parts[1:])
                parent_safe_name = get_safe_region_name(parent_region)
                parent_filename = f"poi_{parent_safe_name}_raw.csv"
                parent_path = self.raw_dir / parent_filename
                
                if parent_path.exists():
                    print(f"지역 전용 POI 파일이 없어, 상위 행정구역 데이터({parent_filename})로 대체(Fallback)합니다.")
                    input_filename = parent_filename
                    input_path = parent_path
                    
        if not input_path.exists():
            raise FileNotFoundError(f" 원본 POI 데이터를 찾을 수 없습니다: {input_filename} (상위 지역 파일도 없음)")
            
        t0 = time.time()
        print(f"원본 POI 데이터 로드 중: {input_filename}...")
        poi_df = pd.read_csv(input_path)
        poi_df = poi_df.dropna(subset=['경도', '위도'])
        
        geometry = [Point(xy) for xy in zip(poi_df['경도'], poi_df['위도'])]
        poi_gdf = gpd.GeoDataFrame(poi_df, geometry=geometry, crs=self.BASE_CRS)
        
        poi_proj = ensure_crs(poi_gdf, self.PROJ_CRS)
        print(f"  -> POI 데이터 투영 완료 (소요시간: {time.time()-t0:.2f}초), 총 상가 수: {len(poi_proj):,}")
        
        poi_proj['category'] = poi_proj.apply(self._categorize_poi, axis=1)
        categories = ['nightlife', 'cafe', 'food', 'retail', 'service']
        poi_dict = {cat: poi_proj[poi_proj['category'] == cat] for cat in categories}
        
        grid_centers = grid_gdf.copy()
        grid_centers.geometry = grid_gdf.centroid
        
        t2 = time.time()
        print("POI 다중 링 버퍼(30m, 50m, 100m) 미리 계산(Pre-calculate) 중...")
        
        buffer_cache = {}
        for r in self.BUFFER_RADII:
            b_gdf = grid_centers.copy()
            b_gdf.geometry = b_gdf.geometry.buffer(r)
            buffer_cache[r] = b_gdf
            
        print("sjoin 연산 및 인덱스 병합 시작...")
        for cat, poi_subset in poi_dict.items():
            if len(poi_subset) == 0: continue
                
            for r in self.BUFFER_RADII:
                buffer_gdf = buffer_cache[r]
                
                joined = gpd.sjoin(poi_subset, buffer_gdf, predicate='within')
                col_name = f"{cat}_count_{r}m"
                if 'index_right' in joined.columns:
                    poi_counts = joined.groupby('index_right').size().rename(col_name)
                else:
                    poi_counts = pd.Series(name=col_name, dtype=int)
                    
                if col_name in grid_gdf.columns:
                    grid_gdf = grid_gdf.drop(columns=[col_name])
                    
                grid_gdf = grid_gdf.join(poi_counts, how='left')
                grid_gdf[col_name] = grid_gdf[col_name].fillna(0).astype(int)
            
        print(f"  -> POI 카테고리 피처 연산 완료 (소요시간: {time.time()-t2:.2f}초)")
        return grid_gdf

class FeatureOrchestrator:
    def __init__(self, region: str, grid_size: int, buffer_size: int):
        self.region = region
        self.grid_size = grid_size
        self.buffer_size = buffer_size
        self.safe_region_name = get_safe_region_name(region)
        
        self.config = load_config()
        self.raw_dir, self.processed_dir = get_data_dirs(self.config)
        
        self.extractor_map = {
            'poi': POIFeatureExtractor
        }

    def run(self, feature_type: str):
        print(f"설정 로드 완료 | Feature='{feature_type}'")
        
        if feature_type not in self.extractor_map:
            raise ValueError(f" 지원하지 않는 피처 타입입니다: {feature_type}")
            
        grid_filename = get_standard_filename("grid", self.region, self.grid_size, self.buffer_size)
        features_filename = get_standard_filename("features", self.region, self.grid_size, self.buffer_size, suffix=feature_type)
        target_path = self.processed_dir / features_filename
        
        if not target_path.exists():
            target_path = self.processed_dir / grid_filename
            
        if not target_path.exists():
            raise FileNotFoundError(f" 대상 Grid 파일을 찾을 수 없습니다: {target_path.name}\n"
                                    f"   먼저 'add-grid' 명령어를 실행하여 도화지를 생성해주세요.")
                                    
        t1 = time.time()
        print(f"타겟 Grid 도화지 로드 중: {target_path.name}...")
        grid_masked = gpd.read_file(target_path)
        print(f"  -> Grid 로드 완료 (소요시간: {time.time()-t1:.2f}초), 총 격자 수: {len(grid_masked):,}")

        print(f"타겟 지역: '{self.safe_region_name}'")
        print(f"  -> 해당 지역 전용 Grid와 전용 데이터(poi_{self.safe_region_name}_raw.csv)간의 결합만 허용합니다.")

        feature_list = [f.strip() for f in feature_type.split(',')]
        
        for ft in feature_list:
            if ft not in self.extractor_map:
                raise ValueError(f" 지원하지 않는 피처 종류입니다: '{ft}'\n"
                                 f"   사용 가능한 피처: {list(self.extractor_map.keys())}")
            
            print(f"\n [{ft.upper()}] 피처 추출 파이프라인 가동 중...")
            extractor_class = self.extractor_map[ft]
            extractor = extractor_class(self.config, self.region, self.raw_dir)
            grid_masked = extractor.extract(grid_masked)

        output_path = self.processed_dir / features_filename
        print(f"최종 피처 레이어 누적 저장 중... -> {features_filename}")
        grid_masked.to_file(output_path, driver='GPKG', layer='features')
        print(f"피처 엔지니어링 텐서 저장됨 -> {output_path}")
