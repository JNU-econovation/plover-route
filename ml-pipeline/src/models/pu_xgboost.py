import numpy as np
import pandas as pd
import xgboost as xgb
from typing import List, Optional, Dict, Any

class PUBaggingXGBoost:
    """
    Positive-Unlabeled (PU) Learning을 위한 Bagging 앙상블 XGBoost 분류기.
    
    극단적으로 불균형한 데이터셋(Positive가 매우 적고 대부분이 Unlabeled인 상황)에서
    Positive 데이터와 동일한 비율로 Unlabeled 데이터를 반복 샘플링하여 
    다수의 XGBoost 모델을 학습시키고 그 결과의 평균을 내어 안정적인 확률을 산출합니다.
    """

    def __init__(self,
                 n_estimators: int = 10,
                 random_state: int = 42,
                 base_params: Optional[Dict[str, Any]] = None) -> None:
        """
        초기화 메서드.

        Args:
            n_estimators (int): 앙상블할 XGBoost 개별 모델의 개수.
            random_state (int): 난수 생성기 제어를 위한 시드 값 (재현성 보장).
            base_params (Optional[Dict[str, Any]]): 개별 모델에 주입할 하이퍼파라미터 딕셔너리.
        """
        self.n_estimators: int = n_estimators
        self.random_state: int = random_state
        self.models: List[xgb.XGBClassifier] = []
        
        # Effective Python: 가변 객체(딕셔너리)를 함수의 기본 인자로 사용하지 않고 None으로 받아 내부에서 할당
        self.base_params: Dict[str, Any] = base_params if base_params is not None else {
            'n_estimators': 100,
            'max_depth': 6,
            'n_jobs': -1,
            'eval_metric': 'logloss'
        }
        
        # 훈련 시점의 피처 순서를 저장하기 위한 상태 변수
        self.feature_names_: Optional[List[str]] = None

    def fit(self, X_df: pd.DataFrame, y: np.ndarray) -> "PUBaggingXGBoost":
        """
        PU-Learning Bagging 방식으로 앙상블 모델을 학습합니다.

        Args:
            X_df (pd.DataFrame): 독립변수(피처)가 포함된 입력 데이터 프레임.
            y (np.ndarray): 종속변수 배열 (1: Positive, 0: Unlabeled).

        Returns:
            PUBaggingXGBoost: 학습이 완료된 모델 객체 자기 자신 (Method Chaining 지원).
        """
        # 추론 시 피처 순서 꼬임을 방지하기 위해 훈련 시점의 컬럼명과 순서를 리스트로 영구 보존
        self.feature_names_ = list(X_df.columns)
        
        X: np.ndarray = X_df.values
        p_idx: np.ndarray = np.where(y == 1)[0]
        u_idx: np.ndarray = np.where(y == 0)[0]
        
        # 전역 시드 오염을 방지하는 로컬 난수 생성기 (Numpy Best Practice)
        rng = np.random.default_rng(self.random_state)
        
        for i in range(self.n_estimators):
            # Unlabeled(0) 데이터 중 Positive(1) 개수만큼 추출
            sampled_u_idx: np.ndarray = rng.choice(u_idx, size=len(p_idx), replace=True)
            
            # 훈련용 데이터 병합
            train_idx: np.ndarray = np.concatenate([p_idx, sampled_u_idx])
            X_train: np.ndarray = X[train_idx]
            
            # 명시적인 int 타입 변환으로 데이터 타입 안정성 확보
            y_train: np.ndarray = np.concatenate([
                np.ones(len(p_idx), dtype=int), 
                np.zeros(len(sampled_u_idx), dtype=int)
            ])
            
            # 개별 모델 초기화 및 학습 (각 모델마다 시드를 다르게 주어 앙상블 다양성 확보)
            model = xgb.XGBClassifier(random_state=self.random_state + i, **self.base_params)
            model.fit(X_train, y_train)
            
            self.models.append(model)
            
        return self

    def predict_proba(self, X_df: pd.DataFrame) -> np.ndarray:
        """
        모든 앙상블 모델의 예측 확률 평균을 계산하여 반환합니다.

        Args:
            X_df (pd.DataFrame): 예측을 수행할 데이터 프레임.

        Raises:
            ValueError: 모델이 학습되지 않은 상태에서 호출될 경우.
            KeyError: 훈련 시 사용된 피처가 추론 데이터셋에 누락되었을 경우.

        Returns:
            np.ndarray: 각 행이 Positive(1) 클래스에 속할 확률 배열 (1D Array).
        """
        if not self.models or self.feature_names_ is None:
            raise ValueError("모델이 아직 학습되지 않았습니다. predict_proba를 호출하기 전에 fit을 먼저 수행하세요.")

        # 훈련 당시의 피처 순서대로 데이터 재배열 (Silent Bug 원천 차단 로직)
        try:
            X: np.ndarray = X_df[self.feature_names_].values
        except KeyError as e:
            missing_cols = set(self.feature_names_) - set(X_df.columns)
            raise KeyError(f"입력 데이터에 훈련 시 사용된 필수 피처가 누락되었습니다: {missing_cols}") from e

        # List Comprehension을 활용한 파이썬 다운(Pythonic) 코드 작성
        # 각 모델의 클래스 1(Positive) 확률만 추출하여 numpy 배열로 변환
        probas: np.ndarray = np.array([model.predict_proba(X)[:, 1] for model in self.models])
        
        # (n_estimators, n_samples) 형태의 행렬을 열 기준으로 평균 내어 1D 배열로 반환
        return probas.mean(axis=0)
