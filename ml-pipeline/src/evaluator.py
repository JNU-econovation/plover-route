import numpy as np
from sklearn.metrics import recall_score, roc_auc_score
from typing import Dict

def calculate_puf_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    recall: float = float(recall_score(y_true, y_pred, zero_division=0))
    
    prob_positive: float = float(y_pred.mean())
    
    if prob_positive <= 0.0:
        return 0.0
        
    puf_score: float = (recall ** 2) / prob_positive
    
    return puf_score

def evaluate_pu_model(y_true: np.ndarray, y_pred_proba: np.ndarray, threshold: float = 0.5) -> Dict[str, float]:
    y_pred: np.ndarray = (y_pred_proba > threshold).astype(int)
    
    recall: float = float(recall_score(y_true, y_pred, zero_division=0))
    prob_positive: float = float(y_pred.mean())
    puf_score: float = calculate_puf_score(y_true, y_pred)
    roc_auc: float = float(roc_auc_score(y_true, y_pred_proba))
    
    return {
        "recall": round(recall, 4),
        "prob_positive": round(prob_positive, 4),
        "puf_score": round(puf_score, 4),
        "roc_auc": round(roc_auc, 4)
    }
