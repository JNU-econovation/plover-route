import numpy as np
import pandas as pd
import geopandas as gpd
import joblib
from pathlib import Path
import logging
import time

from src.models.pu_xgboost import PUBaggingXGBoost

logger = logging.getLogger(__name__)

class HotspotPredictor:
    def __init__(self, model_path: str):
        self.model_path = Path(model_path)
        self.model: PUBaggingXGBoost = self._load_model()
        
    def _load_model(self) -> PUBaggingXGBoost:
        if not self.model_path.exists():
            raise FileNotFoundError(f"[Predictor] Model file not found: {self.model_path}")
        return joblib.load(self.model_path)

    def predict_legacy(self, target_data_path: str) -> gpd.GeoDataFrame:
        """Legacy single-prediction API for backward compatibility."""
        print(f"[Warning] legacy predict loaded for: {target_data_path}")
        gdf: gpd.GeoDataFrame = gpd.read_file(target_data_path)
        raw_scores: np.ndarray = self.model.predict_proba(gdf)
        safe_scores: np.ndarray = np.nan_to_num(raw_scores, nan=0.0)
        safe_scores = np.clip(safe_scores, 0.0, 1.0)
        gdf['trash_score'] = safe_scores
        return gdf

    def is_cache_valid(self, target_data_path: str, result_path: str) -> bool:
        """Verifies prediction cache validity by checking timestamps and row counts."""
        import pyogrio
        result_path_obj = Path(result_path)
        if not result_path_obj.exists():
            return False
            
        try:
            info_feat = pyogrio.read_info(str(target_data_path))
            info_res = pyogrio.read_info(str(result_path))
            total_rows = info_feat['features']
            result_rows = info_res['features']
            
            res_mtime = result_path_obj.stat().st_mtime
            feat_mtime = Path(target_data_path).stat().st_mtime
            model_mtime = self.model_path.stat().st_mtime
            
            is_row_matched = (result_rows == total_rows)
            is_feat_older = (res_mtime > feat_mtime)
            is_model_older = (res_mtime > model_mtime)
            
            if is_row_matched and is_feat_older and is_model_older:
                print(f"[Predictor] Inference cache is valid and up-to-date ({result_rows:,} cells).")
                return True
                
        except Exception as e:
            print(f"[Predictor] Cache validation check failed: {e}")
            
        return False

    def predict(self, target_data_path: str, result_path: str, force_infer: bool = False):
        """Runs batch model prediction and saves output locally."""
        import pyogrio
        import gc

        info = pyogrio.read_info(target_data_path)
        total_rows = info['features']
        
        if not force_infer and self.is_cache_valid(target_data_path, result_path):
            print("[Predictor] Skipping heavy model inference step.")
            return

        print(f"[Predictor] Starting model prediction: {Path(target_data_path).name}")
        print(f"[Predictor] Total cells to predict: {total_rows:,}")

        grid_chunk_size = 3000000
        total_chunks = int(np.ceil(total_rows / grid_chunk_size))
        
        result_path_obj = Path(result_path)
        if result_path_obj.exists():
            result_path_obj.unlink()

        for idx, i in enumerate(range(0, total_rows, grid_chunk_size)):
            t_chunk = time.time()
            start_row = i
            end_row = min(i + grid_chunk_size, total_rows)
            print(f"[Predictor] [Chunk {idx+1}/{total_chunks}] Running inference for cells {start_row:,} ~ {end_row:,}...")
            
            chunk_gdf = gpd.read_file(target_data_path, rows=slice(start_row, end_row))
            
            try:
                raw_scores = self.model.predict_proba(chunk_gdf)
            except KeyError as e:
                print("[Predictor] Feature mismatch between training and target dataset.")
                raise e
            
            safe_scores = np.nan_to_num(raw_scores, nan=0.0)
            safe_scores = np.clip(safe_scores, 0.0, 1.0)
            chunk_gdf['trash_score'] = safe_scores
            
            mode = 'w' if idx == 0 else 'a'
            chunk_gdf.to_file(result_path, driver='GPKG', layer='predicted_hotspots', mode=mode)
            
            print(f"[Predictor] [Chunk {idx+1}/{total_chunks}] Chunk complete ({time.time()-t_chunk:.2f}s)")
            del chunk_gdf
            gc.collect()

        print(f"[Predictor] Model inference complete. Output: {result_path}")
