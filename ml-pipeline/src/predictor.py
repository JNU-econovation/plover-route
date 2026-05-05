import numpy as np
import pandas as pd
import geopandas as gpd
import joblib
from pathlib import Path
import logging

from src.models.pu_xgboost import PUBaggingXGBoost

logger = logging.getLogger(__name__)

class HotspotPredictor:
    """
    학습이 완료되어 저장된 PU-XGBoost 모델을 불러와 
    타겟 지역(10m 격자)에 대해 쓰레기 핫스팟 확률(trash_score)을 추론하는 클래스입니다.
    """
    def __init__(self, model_path: str):
        self.model_path = Path(model_path)
        self.model: PUBaggingXGBoost = self._load_model()
        
    def _load_model(self) -> PUBaggingXGBoost:
        """저장된 모델(.pkl)을 메모리로 불러옵니다."""
        if not self.model_path.exists():
            raise FileNotFoundError(f"모델 파일을 찾을 수 없습니다: {self.model_path}")
        return joblib.load(self.model_path)

    def predict(self, target_data_path: str) -> gpd.GeoDataFrame:
        """
        타겟 지역 공간 데이터를 읽어 추론을 수행하고, 결과를 포함한 GeoDataFrame을 반환합니다.
        
        Args:
            target_data_path (str): 추론할 대상 공간 데이터 경로 (.gpkg)
            
        Returns:
            gpd.GeoDataFrame: 'trash_score' 컬럼이 추가된 원본 공간 데이터 (향후 DB UPDATE 용도)
        """
        print(f"🗺️ 타겟 공간 데이터 로드 중... ({target_data_path})")
        gdf: gpd.GeoDataFrame = gpd.read_file(target_data_path)
        
        print("🧠 핫스팟 확률(trash_score) 추론 중...")
        # 모델 내부에 저장된 feature_names_가 알아서 컬럼 순서를 맞춰주므로, 
        # 원본 gdf를 통째로 던져도 안전합니다.
        try:
            raw_scores: np.ndarray = self.model.predict_proba(gdf)
        except KeyError as e:
            print("❌ 입력 데이터에 훈련 시 사용된 피처가 누락되었습니다.")
            raise e
        
        # [Rule 5 준수] 방어적 프로그래밍 (NaN 및 범위를 벗어난 값 처리)
        # GraphHopper 엔진이 0.0 미만이거나 1.0 초과인 가중치, 혹은 NaN을 받으면 
        # C++ / Java 레벨에서 치명적인 크래시(Crash)가 날 수 있습니다.
        safe_scores: np.ndarray = np.nan_to_num(raw_scores, nan=0.0)
        safe_scores = np.clip(safe_scores, 0.0, 1.0)
        
        # 원본 공간 데이터에 추론 결과(안전한 점수)를 컬럼으로 추가
        # 이 반환된 gdf를 쪼개서 그대로 PostGIS DB에 UPDATE 쿼리로 날리면 됩니다.
        gdf['trash_score'] = safe_scores
        
        print("✅ 추론 완료! 'trash_score' 컬럼이 추가되었습니다.")
        return gdf
