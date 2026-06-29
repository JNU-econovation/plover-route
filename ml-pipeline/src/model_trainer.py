import joblib
import pandas as pd
import geopandas as gpd
from pathlib import Path
from typing import List, Tuple, Dict
from sklearn.model_selection import train_test_split
import logging

from src.models.pu_xgboost import PUBaggingXGBoost
from src.evaluator import evaluate_pu_model

logger = logging.getLogger(__name__)

class ModelTrainer:
    def __init__(self, data_path: str, model_save_path: str, config: Dict):
        self.data_path = Path(data_path)
        self.model_save_path = Path(model_save_path)
        self.config = config

    def _extract_features_and_target(self, gdf: gpd.GeoDataFrame) -> Tuple[pd.DataFrame, pd.Series]:
        exclude_cols = ['is_trash', 'geometry', 'grid_id', 'index_right', 'trash_count']
        
        if 'is_trash' not in gdf.columns:
            raise ValueError("데이터셋에 정답지인 'is_trash' 컬럼이 존재하지 않습니다.")

        feature_cols = [col for col in gdf.columns if col not in exclude_cols]
        
        if not feature_cols:
            raise ValueError(f"학습에 사용할 독립변수가 데이터셋에 존재하지 않습니다: {self.data_path}")

        X = gdf[feature_cols]
        y = gdf['is_trash']
        return X, y

    def train(self) -> Dict[str, float]:
        print(f"데이터셋 로드 중... ({self.data_path})")
        gdf: gpd.GeoDataFrame = gpd.read_file(self.data_path)
        
        X, y = self._extract_features_and_target(gdf)
        
        train_cfg = self.config.get('model', {}).get('training', {})
        xgb_cfg = self.config.get('model', {}).get('xgboost', {})
        
        test_size = train_cfg.get('test_size', 0.2)
        random_seed = train_cfg.get('random_seed', 42)
        n_estimators = xgb_cfg.get('n_estimators', 10)
        
        base_params = {k: v for k, v in xgb_cfg.items() if k != 'n_estimators'}
        
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_seed, stratify=y
        )
        
        print("PUBaggingXGBoost 모델 학습 시작...")
        model = PUBaggingXGBoost(
            n_estimators=n_estimators, 
            random_state=random_seed,
            base_params=base_params if base_params else None
        )
        model.fit(X_train, y_train.values)
        
        print("테스트 데이터 벤치마크 평가 중...")
        y_pred_proba = model.predict_proba(X_test)
        metrics: Dict[str, float] = evaluate_pu_model(y_test.values, y_pred_proba)
        
        print(f"평가 완료. 결과: {metrics}")
        
        self.model_save_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, self.model_save_path)
        print(f"모델 저장 완료: {self.model_save_path}")
        
        return metrics
