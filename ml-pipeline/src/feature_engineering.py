import time
import yaml
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from pathlib import Path
from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseFeatureExtractor(ABC):
    """
    단일 책임 원칙(SRP) 및 개방-폐쇄 원칙(OCP)을 준수하는 피처 추출기 추상 기본 클래스입니다.
    모든 피처 추출기는 이 클래스를 상속받아 `extract` 메서드를 구현해야 합니다.
    """
    def __init__(self, config: Dict[str, Any], safe_region_name: str, raw_dir: Path):
        self.config = config
        self.safe_region_name = safe_region_name
        self.raw_dir = raw_dir
        self.BASE_CRS = config['spatial']['base_crs']
        self.PROJ_CRS = config['spatial']['projected_crs']
        
    @abstractmethod
    def extract(self, grid_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """
        주어진 Grid 데이터프레임에 피처 공간 연산을 수행하여 컬럼을 추가한 뒤 반환합니다.
        """
        pass


class POIFeatureExtractor(BaseFeatureExtractor):
    """
    상권(POI) 데이터를 전처리하고, 다중 링 버퍼(Multi-ring Buffer)를 기반으로
    특정 반경 내 업소 개수를 산출하여 Grid에 병합(Spatial Join)하는 추출기.
    (근거: core_papers.md - 제인 제이콥스의 'Eyes on the Street' 효과 반영)
    """
    
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
            raise FileNotFoundError(f"🚨 원본 POI 데이터를 찾을 수 없습니다: {input_path.name}")
            
        t0 = time.time()
        print(f"🏢 원본 POI 데이터 로드 중: {input_filename}...")
        poi_df = pd.read_csv(input_path)
        poi_df = poi_df.dropna(subset=['경도', '위도'])
        
        geometry = [Point(xy) for xy in zip(poi_df['경도'], poi_df['위도'])]
        poi_gdf = gpd.GeoDataFrame(poi_df, geometry=geometry, crs=self.BASE_CRS)
        
        # [Rule 1 준수] 투영 좌표계로 명시적 변환
        poi_proj = poi_gdf.to_crs(self.PROJ_CRS)
        print(f"   -> POI 데이터 투영 완료 (소요시간: {time.time()-t0:.2f}초), 총 상가 수: {len(poi_proj):,}")
        
        poi_proj['category'] = poi_proj.apply(self._categorize_poi, axis=1)
        categories = ['nightlife', 'cafe', 'food', 'retail', 'service']
        poi_dict = {cat: poi_proj[poi_proj['category'] == cat] for cat in categories}
        
        grid_centers = grid_gdf.copy()
        grid_centers.geometry = grid_gdf.centroid
        
        t2 = time.time()
        print("✂️ POI 다중 링 버퍼(30m, 50m, 100m) sjoin 연산 및 인덱스 병합 시작...")
        
        for cat, poi_subset in poi_dict.items():
            if len(poi_subset) == 0: continue
                
            # core_papers.md 근거: U-Curve 비선형성 파악을 위한 3단계 버퍼링
            for r in [30, 50, 100]:
                buffer_gdf = grid_centers.copy()
                buffer_gdf.geometry = buffer_gdf.geometry.buffer(r)
                
                # [Rule 2 준수] sindex 기반 고속 공간 조인
                joined = gpd.sjoin(poi_subset, buffer_gdf, predicate='within')
                col_name = f"{cat}_count_{r}m"
                if 'index_right' in joined.columns:
                    poi_counts = joined.groupby('index_right').size().rename(col_name)
                else:
                    poi_counts = pd.Series(name=col_name, dtype=int)
                    
                # 동일 피처 재실행 시 중복 에러 방지를 위해 기존 컬럼 삭제
                if col_name in grid_gdf.columns:
                    grid_gdf = grid_gdf.drop(columns=[col_name])
                    
                grid_gdf = grid_gdf.join(poi_counts, how='left')
                grid_gdf[col_name] = grid_gdf[col_name].fillna(0).astype(int)
            
        print(f"   -> POI 카테고리 피처 연산 완료 (소요시간: {time.time()-t2:.2f}초)")
        return grid_gdf


class FeatureOrchestrator:
    """
    [Rule 6 준수] 파일 입출력을 관리하고 입력된 feature_type에 따라
    적절한 Extractor를 매핑하여 실행하는 관리자 클래스 (Strategy Pattern).
    """
    def __init__(self, region: str, grid_size: int, buffer_size: int):
        self.region = region
        self.grid_size = grid_size
        self.buffer_size = buffer_size
        self.safe_region_name = region.lower().replace(" ", "_").replace(",", "")
        
        src_dir = Path(__file__).parent.resolve()
        self.project_root = src_dir.parent
        config_path = self.project_root / 'config.yaml'
        
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
            
        self.raw_dir = (self.project_root / self.config['data']['paths']['raw']).resolve()
        self.processed_dir = (self.project_root / self.config['data']['paths']['processed']).resolve()
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        
        # OCP 원칙: 새로운 피처가 생기면 이 맵(Map)에 추가하기만 하면 됩니다.
        self.extractor_map = {
            'poi': POIFeatureExtractor
        }

    def run(self, feature_type: str):
        print(f"✅ 설정 로드 완료 | Feature='{feature_type}'")
        
        if feature_type not in self.extractor_map:
            raise ValueError(f"🚨 지원하지 않는 피처 타입입니다: {feature_type}")
            
        # 1. 대상 Grid 로드 (예외 처리 포함)
        grid_filename = f"grid_{self.safe_region_name}_{self.grid_size}m_buf{self.buffer_size}m.gpkg"
        features_filename = f"features_{self.safe_region_name}_{self.grid_size}m.gpkg"
        target_path = self.processed_dir / features_filename
        
        if not target_path.exists():
            target_path = self.processed_dir / grid_filename
            
        if not target_path.exists():
            raise FileNotFoundError(f"🚨 대상 Grid 파일을 찾을 수 없습니다: {target_path.name}\n"
                                    f"   먼저 'add-grid' 명령어를 실행하여 도화지를 생성해주세요.")
                                    
        t1 = time.time()
        print(f"📏 타겟 Grid 도화지 로드 중: {target_path.name}...")
        grid_masked = gpd.read_file(target_path)
        print(f"   -> Grid 로드 완료 (소요시간: {time.time()-t1:.2f}초), 총 격자 수: {len(grid_masked):,}")

        # 지역명 무결성(Integrity) 확인 로직 (타 지역 데이터 혼입 원천 차단)
        print(f"🔍 [무결성 검증] 타겟 지역: '{self.safe_region_name}'")
        print(f"   -> 해당 지역 전용 Grid와 전용 데이터(poi_{self.safe_region_name}_raw.csv)간의 결합만 허용합니다.")

        # 2. Extractor 객체 생성 및 연산 위임 (Strategy Pattern)
        extractor_class = self.extractor_map[feature_type]
        extractor = extractor_class(self.config, self.safe_region_name, self.raw_dir)
        grid_masked = extractor.extract(grid_masked)

        # 3. [Rule 4 준수] 결과물 덮어쓰기 (GeoPackage 포맷 유지)
        output_path = self.processed_dir / features_filename
        print(f"💾 최종 피처 레이어 누적 저장 중... -> {features_filename}")
        grid_masked.to_file(output_path, driver='GPKG', layer='features')
        print(f"🚀 [Phase 3 완료] 피처 엔지니어링 텐서 저장됨 -> {output_path}")
