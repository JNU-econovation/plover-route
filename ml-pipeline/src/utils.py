import time
import yaml
import geopandas as gpd
from pathlib import Path
from typing import Tuple

def get_safe_region_name(region: str) -> str:
    """지역명(Region)을 파일 시스템에서 안전하게 사용할 수 있는 이름으로 변환합니다."""
    return "_".join(region.lower().replace(",", "").split())

def load_config() -> dict:
    """프로젝트 루트를 찾아 config.yaml을 로드합니다."""
    src_dir = Path(__file__).parent.resolve()
    project_root = src_dir.parent
    config_path = project_root / 'config.yaml'
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def get_data_dirs(config: dict) -> Tuple[Path, Path]:
    """config 정보를 바탕으로 raw 및 processed 디렉터리를 반환하고, 없으면 생성합니다."""
    src_dir = Path(__file__).parent.resolve()
    project_root = src_dir.parent
    raw_dir = (project_root / config['data']['paths']['raw']).resolve()
    processed_dir = (project_root / config['data']['paths']['processed']).resolve()
    
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir, processed_dir

def get_standard_filename(prefix: str, region: str, grid_size: int, buffer_size: int, suffix: str = "", ext: str = ".gpkg") -> str:
    """파이프라인 표준 네이밍 룰에 맞춘 파일명을 생성합니다."""
    safe_region = get_safe_region_name(region)
    base = f"{prefix}_{safe_region}_{grid_size}m_buf{buffer_size}m"
    if suffix:
        # 콤마(,) 등 파일명에 부적합한 문자를 언더스코어(_)로 치환하여 안전하게 만듭니다.
        safe_suffix = suffix.replace(",", "_").replace(" ", "")
        base += f"_{safe_suffix}"
    return f"{base}{ext}"

def ensure_crs(gdf: gpd.GeoDataFrame, target_crs: str) -> gpd.GeoDataFrame:
    """[Rule 1, Rule 5 준수] 현재 CRS를 확인하고 다르면 타겟 CRS로 변환합니다."""
    if gdf.crs is None:
        raise ValueError("🚨 데이터 프레임에 CRS 정보가 없습니다.")
    if not gdf.crs.equals(target_crs):
        print(f"🔄 CRS 변환 중: {gdf.crs} -> {target_crs}")
        return gdf.to_crs(target_crs)
    return gdf

class Timer:
    """실행 시간을 측정하고 출력하는 컨텍스트 매니저 (with 구문용)"""
    def __init__(self, description: str):
        self.description = description
        
    def __enter__(self):
        self.start = time.time()
        print(f"▶️ {self.description} 시작...")
        return self
        
    def __exit__(self, *args):
        elapsed = time.time() - self.start
        print(f"   -> 완료 (소요시간: {elapsed:.2f}초)")

def get_pipeline_paths(config: dict, region: str, grid_size: int, buffer_size: int, view_type: str, feature_type: str) -> dict:
    """단일 책임 원칙(SRP)에 따라 파이프라인 전체의 파일 입출력 경로 계산을 전담합니다."""
    _, processed_dir = get_data_dirs(config)
    
    # 모델 디렉토리 확보
    src_dir = Path(__file__).parent.resolve()
    project_root = src_dir.parent
    models_dir = (project_root / config['data']['paths']['models']).resolve()
    models_dir.mkdir(parents=True, exist_ok=True)
    
    # 태그를 안전하게 변환
    safe_view = view_type.replace(",", "_").replace(" ", "")
    safe_feature = feature_type.replace(",", "_").replace(" ", "")
    
    # 표준 네이밍 룰에 맞춘 파일명 생성
    dataset_name = get_standard_filename("dataset", region, grid_size, buffer_size, f"{safe_view}_{safe_feature}")
    features_name = get_standard_filename("features", region, grid_size, buffer_size, feature_type)
    
    # 모델명에도 모든 태그(view, feature)를 포함하여 덮어쓰기 방지 및 A/B 테스트 가능하도록 수정
    safe_region = get_safe_region_name(region)
    model_name = f"pu_xgboost_{safe_region}_{grid_size}m_buf{buffer_size}m_{safe_view}_{safe_feature}.pkl"
    
    result_name = get_standard_filename("result_hotspot", region, grid_size, buffer_size, feature_type)
    map_name = get_standard_filename("map_hotspot", region, grid_size, buffer_size, feature_type, ext=".png")
    
    # 최종 절대경로 딕셔너리 반환
    return {
        "dataset": processed_dir / dataset_name,
        "features": processed_dir / features_name,
        "model": models_dir / model_name,
        "result": processed_dir / result_name,
        "map": processed_dir / map_name
    }
