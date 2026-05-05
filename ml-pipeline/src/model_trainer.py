import joblib
import pandas as pd
import geopandas as gpd
from pathlib import Path
from typing import List, Tuple, Dict
from sklearn.model_selection import train_test_split
import logging

# 앞서 작성한 핵심 모듈들을 불러옵니다.
from src.models.pu_xgboost import PUBaggingXGBoost
from src.evaluator import evaluate_pu_model

logger = logging.getLogger(__name__)

class ModelTrainer:
    """
    GeoAI 플로깅 쓰레기 핫스팟 탐지 모델의 학습 워크플로우를 통제하는 클래스입니다.
    단일 책임 원칙(SRP)에 따라 데이터 로드, 훈련 통제, 저장만을 담당합니다.
    """
    def __init__(self, data_path: str, model_save_path: str, config: Dict):
        self.data_path = Path(data_path)
        self.model_save_path = Path(model_save_path)
        self.config = config

    def _extract_features_and_target(self, gdf: gpd.GeoDataFrame) -> Tuple[pd.DataFrame, pd.Series]:
        """
        공간 데이터프레임에서 동적으로 피처(독립변수)와 타겟(종속변수)을 분리합니다.
        
        Args:
            gdf (gpd.GeoDataFrame): 원본 공간 데이터프레임
            
        Returns:
            Tuple[pd.DataFrame, pd.Series]: 피처 데이터프레임(X)과 타겟 시리즈(y)
        """
        # [클린 코드 - 개선안] OCP 진정한 준수: 특정 문자열(_count_)에 의존하지 않습니다.
        # 인구수 밀도, 도로까지의 거리 등 다양한 피처가 추가될 것을 대비하여, 
        # '머신러닝에 쓰면 안 되는 컬럼(정답지, 공간좌표, ID 등)'만 리스트로 만들어 제외(Exclude)시킵니다.
        exclude_cols = ['is_hotspot', 'geometry', 'grid_id', 'index_right']
        
        if 'is_hotspot' not in gdf.columns:
            raise ValueError("데이터셋에 정답지인 'is_hotspot' 컬럼이 존재하지 않습니다.")

        # 제외 리스트에 없는 모든 컬럼을 피처(X)로 사용합니다.
        feature_cols = [col for col in gdf.columns if col not in exclude_cols]
        
        if not feature_cols:
            raise ValueError(f"학습에 사용할 피처(독립변수)가 데이터셋에 존재하지 않습니다: {self.data_path}")

        X = gdf[feature_cols]
        y = gdf['is_hotspot']
        return X, y

    def train(self) -> Dict[str, float]:
        """
        데이터 분할, 모델 학습, 평가 및 저장을 한 번에 수행하는 메인 함수입니다.
        """
        print(f"📦 데이터셋 로드 중... ({self.data_path})")
        gdf: gpd.GeoDataFrame = gpd.read_file(self.data_path)
        
        X, y = self._extract_features_and_target(gdf)
        
        # config.yaml 설정값 동적 로드
        train_cfg = self.config.get('model', {}).get('training', {})
        xgb_cfg = self.config.get('model', {}).get('xgboost', {})
        
        test_size = train_cfg.get('test_size', 0.2)
        random_seed = train_cfg.get('random_seed', 42)
        n_estimators = xgb_cfg.get('n_estimators', 10)
        
        # XGBoost 전용 파라미터 분리 (n_estimators 제외)
        base_params = {k: v for k, v in xgb_cfg.items() if k != 'n_estimators'}
        
        # [과적합 방지] 데이터를 설정 파일의 비율로 나누어 객관성을 확보합니다.
        # stratify=y 를 주어, 극도로 적은 Positive(1) 라벨이 한쪽에 몰리지 않게 골고루 분배합니다.
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_seed, stratify=y
        )
        
        print("🏋️‍♂️ PUBaggingXGBoost 모델 학습 시작...")
        model = PUBaggingXGBoost(
            n_estimators=n_estimators, 
            random_state=random_seed,
            base_params=base_params if base_params else None
        )
        model.fit(X_train, y_train.values)
        
        print("📊 테스트 데이터 벤치마크 평가 중...")
        # 훈련에 참여하지 않은 Test 데이터로 순수하게 모델의 실력을 평가합니다.
        y_pred_proba = model.predict_proba(X_test)
        metrics: Dict[str, float] = evaluate_pu_model(y_test.values, y_pred_proba)
        
        print(f"✨ 평가 완료! 결과: {metrics}")
        
        # 직렬화(Serialize)하여 모델을 디스크에 물리적 파일(.pkl)로 영구 저장합니다.
        self.model_save_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, self.model_save_path)
        print(f"💾 모델 저장 완료: {self.model_save_path}")
        
        return metrics
