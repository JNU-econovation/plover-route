import time
import yaml
import geopandas as gpd
from pathlib import Path
from typing import Tuple

def get_safe_region_name(region: str) -> str:
    return "_".join(region.lower().replace(",", "").split())

def load_config() -> dict:
    src_dir = Path(__file__).parent.resolve()
    project_root = src_dir.parent
    config_path = project_root / 'config.yaml'
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def get_data_dirs(config: dict) -> Tuple[Path, Path]:
    src_dir = Path(__file__).parent.resolve()
    project_root = src_dir.parent
    raw_dir = (project_root / config['data']['paths']['raw']).resolve()
    processed_dir = (project_root / config['data']['paths']['processed']).resolve()
    
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir, processed_dir

def get_standard_filename(prefix: str, region: str, grid_size: int, buffer_size: int, suffix: str = "", ext: str = ".gpkg") -> str:
    safe_region = get_safe_region_name(region)
    base = f"{prefix}_{safe_region}_{grid_size}m_buf{buffer_size}m"
    if suffix:
        safe_suffix = suffix.replace(",", "_").replace(" ", "")
        base += f"_{safe_suffix}"
    return f"{base}{ext}"

def ensure_crs(gdf: gpd.GeoDataFrame, target_crs: str) -> gpd.GeoDataFrame:
    if gdf.crs is None:
        raise ValueError(" 데이터 프레임에 CRS 정보가 없습니다.")
    if not gdf.crs.equals(target_crs):
        print(f"CRS 변환 중: {gdf.crs} -> {target_crs}")
        return gdf.to_crs(target_crs)
    return gdf

class Timer:
    def __init__(self, description: str):
        self.description = description
        
    def __enter__(self):
        self.start = time.time()
        print(f"{self.description} 시작...")
        return self
        
    def __exit__(self, *args):
        elapsed = time.time() - self.start
        print(f"  -> 완료 (소요시간: {elapsed:.2f}초)")

def get_pipeline_paths(config: dict, region: str, grid_size: int, buffer_size: int, view_type: str, feature_type: str) -> dict:
    _, processed_dir = get_data_dirs(config)
    
    src_dir = Path(__file__).parent.resolve()
    project_root = src_dir.parent
    models_dir = (project_root / config['data']['paths']['models']).resolve()
    models_dir.mkdir(parents=True, exist_ok=True)
    
    safe_view = view_type.replace(",", "_").replace(" ", "")
    safe_feature = feature_type.replace(",", "_").replace(" ", "")
    
    dataset_name = get_standard_filename("dataset", region, grid_size, buffer_size, f"{safe_view}_{safe_feature}")
    features_name = get_standard_filename("features", region, grid_size, buffer_size, feature_type)
    
    safe_region = get_safe_region_name(region)
    model_name = f"pu_xgboost_{safe_region}_{grid_size}m_buf{buffer_size}m_{safe_view}_{safe_feature}.pkl"
    
    result_name = get_standard_filename("result_hotspot", region, grid_size, buffer_size, feature_type)
    map_name = get_standard_filename("map_hotspot", region, grid_size, buffer_size, feature_type, ext=".png")
    
    return {
        "dataset": processed_dir / dataset_name,
        "features": processed_dir / features_name,
        "model": models_dir / model_name,
        "result": processed_dir / result_name,
        "map": processed_dir / map_name
    }

def upsert_geodataframe_to_postgis(gdf: gpd.GeoDataFrame, table_name: str, engine, unique_col: str = "grid_id"):
    import sqlalchemy
    from sqlalchemy import text
    
    gdf = ensure_crs(gdf, "EPSG:4326")
    
    inspector = sqlalchemy.inspect(engine)
    if not inspector.has_table(table_name):
        print(f"본 테이블('{table_name}')이 존재하지 않아 최초 생성합니다.")
        gdf.to_postgis(table_name, engine, if_exists="replace", index=False)
        with engine.begin() as conn:
            conn.execute(text(f'ALTER TABLE "{table_name}" ADD PRIMARY KEY ("{unique_col}");'))
    else:
        temp_table = f"{table_name}_temp"
        print(f"임시 테이블('{temp_table}')에 데이터 삽입 중...")
        gdf.to_postgis(temp_table, engine, if_exists="replace", index=False)
        
        print(f"본 테이블('{table_name}')에 Upsert 병합을 시작합니다...")
        columns = [col for col in gdf.columns if col != unique_col]
        set_clause = ", ".join([f'"{col}" = EXCLUDED."{col}"' for col in columns])
        
        upsert_sql = text(f"""
            INSERT INTO "{table_name}"
            SELECT * FROM "{temp_table}"
            ON CONFLICT ("{unique_col}")
            DO UPDATE SET
                {set_clause};
        """)
        
        with engine.begin() as conn:
            conn.execute(upsert_sql)
            print(f"임시 테이블('{temp_table}') 정리 중...")
            conn.execute(text(f'DROP TABLE "{temp_table}";'))
