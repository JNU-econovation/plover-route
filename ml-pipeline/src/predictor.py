import numpy as np
import pandas as pd
import geopandas as gpd
import joblib
from pathlib import Path
import logging

from src.models.pu_xgboost import PUBaggingXGBoost

logger = logging.getLogger(__name__)

class HotspotPredictor:
    def __init__(self, model_path: str):
        self.model_path = Path(model_path)
        self.model: PUBaggingXGBoost = self._load_model()
        
    def _load_model(self) -> PUBaggingXGBoost:
        if not self.model_path.exists():
            raise FileNotFoundError(f"모델 파일을 찾을 수 없습니다: {self.model_path}")
        return joblib.load(self.model_path)

    def predict(self, target_data_path: str) -> gpd.GeoDataFrame:
        print(f"타겟 공간 데이터 로드 중... ({target_data_path})")
        gdf: gpd.GeoDataFrame = gpd.read_file(target_data_path)
        
        print("trash_score 추론 중...")
        try:
            raw_scores: np.ndarray = self.model.predict_proba(gdf)
        except KeyError as e:
            print("입력 데이터에 훈련 시 사용된 피처가 누락되었습니다.")
            raise e
        
        safe_scores: np.ndarray = np.nan_to_num(raw_scores, nan=0.0)
        safe_scores = np.clip(safe_scores, 0.0, 1.0)
        
        gdf['trash_score'] = safe_scores
        
        print("추론 완료. 'trash_score' 컬럼이 추가되었습니다.")
        return gdf

    def push_to_db(self, gdf: gpd.GeoDataFrame, db_url: str, table_name: str = "predicted_hotspots"):
        import sqlalchemy
        import time
        from src.utils import upsert_geodataframe_to_postgis
        
        print("PostGIS DB에 추론 결과 적재(Upsert)를 시작합니다...")
        start_time = time.time()
        engine = sqlalchemy.create_engine(db_url)
        
        upsert_geodataframe_to_postgis(gdf, table_name, engine, unique_col="grid_id")
        
        elapsed = time.time() - start_time
        print(f"PostGIS DB 적재 완료. ({elapsed:.2f}초 소요)")
