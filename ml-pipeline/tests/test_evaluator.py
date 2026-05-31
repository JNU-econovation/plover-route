import pytest
import numpy as np
from src.evaluator import calculate_puf_score, evaluate_pu_model

def test_calculate_puf_score_normal():
    """정상 케이스: 수작업 공식과 파이썬 함수의 결과값이 정확히 일치하는지 확인"""
    y_true = np.array([1, 1, 1, 1, 0, 0, 0, 0, 0, 0])
    
    y_pred = np.array([1, 1, 0, 0, 1, 1, 0, 0, 0, 0])
    
    expected_score = 0.625
    actual_score = calculate_puf_score(y_true, y_pred)
    assert actual_score == expected_score

def test_calculate_puf_score_zero_division():
    """예외(엣지) 케이스: 모델이 단 하나도 핫스팟을 찾지 못했을 때 서버 크래시(ZeroDivision) 방어"""
    y_true = np.array([1, 1, 0, 0])
    y_pred = np.array([0, 0, 0, 0])

    score = calculate_puf_score(y_true, y_pred)
    assert score == 0.0

def test_evaluate_pu_model_dictionary():
    """정상 케이스: 딕셔너리로 주요 지표들이 가독성 좋게 포장되는지 확인"""
    y_true = np.array([1, 1, 0, 0])
    y_pred_proba = np.array([0.9, 0.4, 0.6, 0.1]) 
    
    metrics = evaluate_pu_model(y_true, y_pred_proba, threshold=0.5)
    
    assert "puf_score" in metrics
    assert "recall" in metrics
    assert "roc_auc" in metrics
    assert "pr_auc" in metrics
    assert isinstance(metrics["puf_score"], float)
    assert isinstance(metrics["pr_auc"], float)
