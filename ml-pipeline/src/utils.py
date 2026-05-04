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

def get_standard_filename(prefix: str, region: str, grid_size: int, buffer_size: int, suffix: str = "") -> str:
    """파이프라인 표준 네이밍 룰에 맞춘 파일명을 생성합니다."""
    safe_region = get_safe_region_name(region)
    base = f"{prefix}_{safe_region}_{grid_size}m_buf{buffer_size}m"
    if suffix:
        base += f"_{suffix}"
    return f"{base}.gpkg"

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
