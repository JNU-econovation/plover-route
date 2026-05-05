import numpy as np
from sklearn.metrics import recall_score, roc_auc_score
from typing import Dict

def calculate_puf_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """
    PU-Learning 모델 성능 평가를 위한 PUF-Score를 계산합니다. (Lee and Liu, 2003)
    
    극단적인 불균형(Class Imbalance) 및 Unlabeled 데이터 환경에서 
    왜곡되는 F1-Score를 대체하기 위해 고안된 수학적 벤치마크 지표입니다.
    
    Args:
        y_true (np.ndarray): 실제 정답 배열 (1: Positive/Hotspot, 0: Unlabeled).
        y_pred (np.ndarray): 모델의 이진 예측값 배열 (1: 예측 Hotspot, 0: 예측 아님).
        
    Returns:
        float: 계산된 PUF-Score. 모델이 단 하나의 Positive도 예측하지 않아 
               비율이 0이 될 경우 0.0을 반환합니다.
    """
    # 1. Recall(재현율) 계산: 실제 핫스팟 중 모델이 찾아낸 핫스팟의 비율 (공식의 'r')
    # zero_division=0을 주어, 혹시 모를 에러를 방지합니다.
    recall: float = float(recall_score(y_true, y_pred, zero_division=0))
    
    # 2. P[f(x)=1] 계산: 전체 지도 격자 중 모델이 핫스팟으로 '예측'한 비율
    # y_pred는 0과 1로만 이루어져 있으므로, 평균(mean)을 구하면 자연스럽게 1(Positive)의 비율이 나옵니다.
    prob_positive: float = float(y_pred.mean())
    
    # 3. 방어적 프로그래밍 (Defensive Programming)
    # 모델이 "광주시에 핫스팟이 단 하나도 없다"고 예측해버리면 prob_positive가 0이 됩니다.
    # 이때 0으로 나누기(ZeroDivisionError)가 발생해 서버가 다운되는 것을 막기 위한 예외 처리입니다.
    if prob_positive <= 0.0:
        return 0.0
        
    # 4. PUF-Score 공식: (r^2) / P[f(x)=1]
    puf_score: float = (recall ** 2) / prob_positive
    
    return puf_score


def evaluate_pu_model(y_true: np.ndarray, y_pred_proba: np.ndarray, threshold: float = 0.5) -> Dict[str, float]:
    """
    PU-Learning 모델의 종합적인 벤치마크 지표를 계산하여 딕셔너리로 반환합니다.
    
    Args:
        y_true (np.ndarray): 실제 정답 배열.
        y_pred_proba (np.ndarray): 모델이 예측한 Positive 확률 배열 (0.0 ~ 1.0).
        threshold (float): 확률을 0과 1로 나눌 기준선 (기본값 0.5).
        
    Returns:
        Dict[str, float]: 가독성 좋게 소수점 4자리로 반올림된 주요 평가 지표 모음.
    """
    # 확률 값(0.0~1.0)을 threshold(0.5) 기준으로 잘라 0과 1의 정수 배열로 변환합니다.
    y_pred: np.ndarray = (y_pred_proba > threshold).astype(int)
    
    # 종합 지표 계산
    recall: float = float(recall_score(y_true, y_pred, zero_division=0))
    prob_positive: float = float(y_pred.mean())
    puf_score: float = calculate_puf_score(y_true, y_pred)
    roc_auc: float = float(roc_auc_score(y_true, y_pred_proba))
    
    # 딕셔너리 형태로 묶어서 반환 (다른 모듈에서 사용하기 편하도록 포장)
    return {
        "recall": round(recall, 4),
        "prob_positive": round(prob_positive, 4),
        "puf_score": round(puf_score, 4),
        "roc_auc": round(roc_auc, 4)
    }
