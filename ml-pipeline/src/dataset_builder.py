import time
import yaml
import pandas as pd
import geopandas as gpd
from sqlalchemy import create_engine, text
from pathlib import Path
from src.utils import get_safe_region_name, load_config, get_data_dirs, get_standard_filename, ensure_crs, Timer
from abc import ABC, abstractmethod

class BaseViewLoader(ABC):
    """
    [Rule 6 준수] 단일 책임 원칙(SRP) 및 개방-폐쇄 원칙(OCP)을 준수하는 View 로더 추상 기본 클래스입니다.
    새로운 형태의 머신러닝 정답지(View)가 추가되면 이 클래스를 상속받아 구현하면 됩니다.
    """
    @abstractmethod
    def load_view(self, engine) -> gpd.GeoDataFrame:
        """PostGIS에서 특정 View를 읽어와 GeoDataFrame으로 반환합니다."""
        pass


class BaselineViewLoader(BaseViewLoader):
    """
    어떠한 전처리(DBSCAN 등)도 거치지 않은 원본 그대로의 Baseline View를 로드합니다.
    """
    def load_view(self, engine) -> gpd.GeoDataFrame:
        print("🔍 [BaselineViewLoader] DB에서 'ml_unified_labels_view_baseline' 뷰를 불러옵니다...")
        
        # 1년치 필터링 없는 완전한 Raw 뷰 쿼리 (노트북 06 로직 반영)
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
    """
    [Rule 6 준수] DB View와 정적 피처(Grid)를 결합하여 최종 머신러닝 데이터셋을 생성하는 빌더 클래스입니다.
    전략 패턴(Strategy Pattern)을 사용하여 View 로더를 유연하게 교체할 수 있습니다.
    """
    def __init__(self, region: str, grid_size: int, buffer_size: int, view_type: str = "baseline", feature_type: str = "poi"):
        self.region = region
        self.grid_size = grid_size
        self.buffer_size = buffer_size
        self.feature_type = feature_type
        self.safe_region_name = get_safe_region_name(region)
        
        self.config = load_config()
        self.raw_dir, self.processed_dir = get_data_dirs(self.config)
        self.PROJ_CRS = self.config['spatial']['projected_crs']
        
        # OCP 원칙: 새로운 View 전략이 생기면 이 맵(Map)에 추가하기만 하면 됩니다.
        self.view_loader_map = {
            'baseline': BaselineViewLoader
        }
        
        if view_type not in self.view_loader_map:
            raise ValueError(f"🚨 지원하지 않는 View 타입입니다: {view_type}")
            
        self.view_loader = self.view_loader_map[view_type]()
        self.view_type_name = view_type

    def build(self):
        t0 = time.time()
        # 1. DB 엔진 설정
        # 실제 환경에서는 config나 환경변수에서 가져와야 하지만 로컬 도커이므로 하드코딩 유지
        DB_URI = 'postgresql://postgres:postgres@localhost:5432/geoai'
        engine = create_engine(DB_URI)
        
        # 2. Strategy 객체에 View 로딩 위임
        labels_gdf = self.view_loader.load_view(engine)
        print(f"   -> DB 로드 완료: 총 {len(labels_gdf):,}건 (현재 좌표계: {labels_gdf.crs})")
        
        # [Rule 1 준수] 투영 변환
        labels_gdf = ensure_crs(labels_gdf, self.PROJ_CRS)
        
        # 3. 타겟 Grid 로드
        features_filename = get_standard_filename("features", self.region, self.grid_size, self.buffer_size, suffix=self.feature_type)
        target_path = self.processed_dir / features_filename
        
        if not target_path.exists():
            raise FileNotFoundError(f"🚨 대상 Grid 피처 파일을 찾을 수 없습니다: {target_path.name}\n"
                                    f"   먼저 'add-grid' 및 'add-features' 명령어를 실행해주세요.")
                                    
        print(f"📏 타겟 피처 Grid 로드 중: {target_path.name}...")
        grid_features = gpd.read_file(target_path)
        print(f"   -> Grid 로드 완료: 총 {len(grid_features):,}개")

        # 4. 공간 조인 (Spatial Join)
        print("✂️ 공간 조인(sjoin)을 통한 정답 라벨(Y) 맵핑 시작...")
        labels_gdf = ensure_crs(labels_gdf, grid_features.crs)
            
        merged_gdf = gpd.sjoin(grid_features, labels_gdf, how='left', predicate='contains')
        
        # 중복 제거 (한 격자에 쓰레기 점이 여러 개 들어가도 1개로 취급)
        merged_gdf = merged_gdf[~merged_gdf.index.duplicated(keep='first')]
        merged_gdf['is_trash'] = merged_gdf['is_trash'].fillna(0).astype(int)
        
        if 'index_right' in merged_gdf.columns:
            merged_gdf = merged_gdf.drop(columns=['index_right'])
            
        trash_count = merged_gdf['is_trash'].sum()
        total_count = len(merged_gdf)
        ratio = (trash_count / total_count) * 100
        print(f"🔥 쓰레기 투기 위험 구역(핫스팟) 격자 수: {trash_count:,}개")
        print(f"🧊 안전 구역 격자 수: {total_count - trash_count:,}개")
        print(f"⚖️ 클래스 불균형 비율: {ratio:.4f}%")

        # 5. 최종 데이터셋 저장
        suffix = f"{self.view_type_name}_{self.feature_type.replace(',', '_').replace(' ', '')}"
        output_filename = get_standard_filename("dataset", self.region, self.grid_size, self.buffer_size, suffix=suffix)
        output_path = self.processed_dir / output_filename
        print(f"💾 최종 학습 데이터셋 저장 중... -> {output_filename}")
        merged_gdf.to_file(output_path, driver='GPKG', layer='dataset')
        print(f"🚀 [Phase 4 완료] 최종 데이터셋 생성됨 (소요시간: {time.time()-t0:.2f}초) -> {output_path}")
