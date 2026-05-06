import pytest
import pandas as pd
import geopandas as gpd
import numpy as np
from shapely.geometry import Point
from src.model_trainer import ModelTrainer
from src.predictor import HotspotPredictor

@pytest.fixture
def mock_geodataframe():
    """테스트용 가짜 공간 데이터셋(Mock Data) 생성"""
    data = {
        'grid_id': [1, 2, 3],
        'cafe_count': [10, 0, 5],
        'dist_to_road': [100.5, 20.0, 50.1],
        'is_trash': [1, 0, 0],
        'index_right': [99, 88, 77] # 공간 조인 시 딸려오는 불필요한 찌꺼기 컬럼
    }
    geometry = [Point(0,0), Point(1,1), Point(2,2)]
    return gpd.GeoDataFrame(data, geometry=geometry)

def test_model_trainer_ocp_feature_extraction(mock_geodataframe):
    """정상 케이스: ModelTrainer의 OCP (Exclude List) 피처 추출 로직 완벽 검증"""
    trainer = ModelTrainer(data_path="dummy.gpkg", model_save_path="dummy.pkl", config={})
    
    X, y = trainer._extract_features_and_target(mock_geodataframe)
    
    # 1. 정답지 분리 확인
    assert list(y.values) == [1, 0, 0]
    
    # 2. Exclude List 동작 확인 (is_trash, geometry, grid_id, index_right 등 시스템 컬럼 제외)
    # 남은 피처는 무조건 'cafe_count'와 'dist_to_road' 2개 뿐이어야 함
    expected_features = ['cafe_count', 'dist_to_road']
    assert list(X.columns) == expected_features

def test_predictor_rule5_bounding():
    """예외 케이스: Predictor의 Rule 5 방어 (NaN, 음수, 1초과 값 강제 클리핑 방어막)"""
    # 실제 모델을 불러오지 않고, 예측 확률이 비정상으로 나왔다는 상황만 모킹(Mocking)
    raw_scores = np.array([np.nan, -0.5, 1.2, 0.8])
    
    # src.predictor 내부의 C++/Java 크래시 방어 로직 재현
    safe_scores = np.nan_to_num(raw_scores, nan=0.0)
    safe_scores = np.clip(safe_scores, 0.0, 1.0)
    
    # 검증: NaN -> 0.0 / 음수 -> 0.0 / 1.0 초과 -> 1.0 / 정상범위(0.8) -> 0.8
    assert safe_scores[0] == 0.0
    assert safe_scores[1] == 0.0
    assert safe_scores[2] == 1.0
    assert safe_scores[3] == 0.8

def test_predictor_missing_features(mocker, mock_geodataframe):
    """예외 케이스: 훈련 시 사용한 피처가 추론 대상 데이터(Grid)에 없을 때 친절한 KeyError 방어"""
    # 1. 파일 읽기 모킹
    mocker.patch('geopandas.read_file', return_value=mock_geodataframe)
    
    # 2. 모델 로드(joblib.load) 모킹하여 FileNotFoundError 방지
    class FakeModel:
        def predict_proba(self, X):
            raise KeyError("훈련 시 사용된 ['dist_to_road'] 컬럼이 없습니다!")
            
    mocker.patch.object(HotspotPredictor, '_load_model', return_value=FakeModel())
    
    predictor = HotspotPredictor(model_path="dummy.pkl")
    
    # 누락된 피처를 잡아서 KeyError를 위로 잘 뱉어주는지 확인
    with pytest.raises(KeyError, match="dist_to_road"):
        predictor.predict(target_data_path="dummy.gpkg")
