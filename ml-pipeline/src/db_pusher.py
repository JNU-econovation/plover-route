import time
import gc
import numpy as np
import geopandas as gpd
import pyogrio
import sqlalchemy
from pathlib import Path
from src.utils import upsert_geodataframe_to_postgis

def push_gpkg_to_postgis(gpkg_path: str, db_url: str, table_name: str = "predicted_hotspots"):
    """Ingests local GPKG predictions into PostGIS database using optimized batches."""
    gpkg_path_obj = Path(gpkg_path)
    if not gpkg_path_obj.exists():
        raise FileNotFoundError(f"[Database] Target GPKG file not found: {gpkg_path}")
        
    t_start = time.time()
    
    info = pyogrio.read_info(str(gpkg_path))
    total_rows = info['features']
    print(f"[Database] Starting GPKG Ingestion: {gpkg_path_obj.name}")
    print(f"[Database] Total grid cells: {total_rows:,}")
    
    grid_chunk_size = 100000
    total_chunks = int(np.ceil(total_rows / grid_chunk_size))
    engine = sqlalchemy.create_engine(db_url)
    
    for idx, i in enumerate(range(0, total_rows, grid_chunk_size)):
        t_chunk = time.time()
        start_row = i
        end_row = min(i + grid_chunk_size, total_rows)
        print(f"[Database] [Batch {idx+1}/{total_chunks}] Processing cells {start_row:,} ~ {end_row:,}...")
        
        chunk_gdf = gpd.read_file(str(gpkg_path), rows=slice(start_row, end_row))
        
        essential_cols = ['grid_id', 'geometry', 'trash_score']
        essential_gdf = chunk_gdf[essential_cols].copy()
        
        essential_gdf = essential_gdf.drop_duplicates(subset=["grid_id"], keep="first")
        
        upsert_geodataframe_to_postgis(essential_gdf, table_name, engine, unique_col="grid_id")
        
        print(f"[Database] [Batch {idx+1}/{total_chunks}] Batch complete ({time.time()-t_chunk:.2f}s)")
        del chunk_gdf, essential_gdf
        gc.collect()
        
    print(f"[Database] GPKG Ingestion completed (Total Duration: {time.time()-t_start:.2f}s)")
