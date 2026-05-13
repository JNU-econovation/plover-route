import numpy as np
import pandas as pd
import xgboost as xgb
from typing import List, Optional, Dict, Any

class PUBaggingXGBoost:

    def __init__(self,
                 n_estimators: int = 10,
                 random_state: int = 42,
                 base_params: Optional[Dict[str, Any]] = None) -> None:
        self.n_estimators: int = n_estimators
        self.random_state: int = random_state
        self.models: List[xgb.XGBClassifier] = []
        
        self.base_params: Dict[str, Any] = base_params if base_params is not None else {
            'n_estimators': 100,
            'max_depth': 6,
            'n_jobs': -1,
            'eval_metric': 'logloss'
        }
        
        self.feature_names_: Optional[List[str]] = None

    def fit(self, X_df: pd.DataFrame, y: np.ndarray) -> "PUBaggingXGBoost":
        if len(X_df) != len(y):
            raise ValueError(f"데이터 개수 불일치: X는 {len(X_df)}개, y는 {len(y)}개입니다.")

        self.feature_names_ = list(X_df.columns)
        
        X: np.ndarray = X_df.values
        p_idx: np.ndarray = np.where(y == 1)[0]
        u_idx: np.ndarray = np.where(y == 0)[0]
        
        if len(p_idx) == 0:
            raise ValueError("Positive 샘플이 단 하나도 존재하지 않아 PU-Learning이 불가능합니다.")
            
        rng = np.random.default_rng(self.random_state)
        
        for i in range(self.n_estimators):
            sampled_u_idx: np.ndarray = rng.choice(u_idx, size=len(p_idx), replace=False)
            
            train_idx: np.ndarray = np.concatenate([p_idx, sampled_u_idx])
            X_train: np.ndarray = X[train_idx]
            
            y_train: np.ndarray = np.concatenate([
                np.ones(len(p_idx), dtype=int), 
                np.zeros(len(sampled_u_idx), dtype=int)
            ])
            
            model = xgb.XGBClassifier(random_state=self.random_state + i, **self.base_params)
            model.fit(X_train, y_train)
            
            self.models.append(model)
            
        return self

    def predict_proba(self, X_df: pd.DataFrame) -> np.ndarray:
        if not self.models or self.feature_names_ is None:
            raise ValueError("모델이 아직 학습되지 않았습니다. predict_proba를 호출하기 전에 fit을 먼저 수행하세요.")

        try:
            X: np.ndarray = X_df[self.feature_names_].values
        except KeyError as e:
            missing_cols = set(self.feature_names_) - set(X_df.columns)
            raise KeyError(f"입력 데이터에 훈련 시 사용된 필수 피처가 누락되었습니다: {missing_cols}") from e

        probas: np.ndarray = np.array([model.predict_proba(X)[:, 1] for model in self.models])
        
        return probas.mean(axis=0)
