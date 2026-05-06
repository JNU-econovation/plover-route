import pytest
from typer.testing import CliRunner
import geopandas as gpd
from shapely.geometry import Point

from main import app

runner = CliRunner()

@pytest.fixture
def dummy_result_gdf():
    """가짜 추론 결과 데이터"""
    return gpd.GeoDataFrame({
        'grid_id': [0, 1],
        'trash_score': [0.1, 0.9]
    }, geometry=[Point(0,0), Point(1,1)], crs="EPSG:5179")

def test_infer_hotspot_without_push(mocker, dummy_result_gdf):
    """
    [TDD] --push 옵션이 없을 때: 
    로컬에 파일만 저장하고 DB 엔진(sqlalchemy)이 절대 호출되지 않아야 합니다.
    """
    # 1. 의존성 Mocking (실제 모델 파일 로드 차단)
    mock_predictor_class = mocker.patch('main.HotspotPredictor')
    mock_predictor_instance = mock_predictor_class.return_value
    mock_predictor_instance.predict.return_value = dummy_result_gdf
    
    # 2. 파일 I/O 및 DB 접속 차단
    mocker.patch('geopandas.GeoDataFrame.to_file')
    mock_engine = mocker.patch('sqlalchemy.create_engine')

    # 3. CLI 실행 (옵션 없음)
    result = runner.invoke(app, [
        "infer-hotspot", 
        "--train-region", "Test", 
        "--target-region", "Test"
    ])
    
    # 4. 검증
    assert result.exit_code == 0
    assert "로컬 백업 저장 완료" in result.stdout
    assert "PostGIS DB 적재" not in result.stdout
    mock_engine.assert_not_called()  # 핵심: DB 접속이 일어나면 안 됨!

def test_infer_hotspot_with_push(mocker, monkeypatch, dummy_result_gdf):
    """
    [TDD] --push 옵션이 있을 때: 
    DB 주소를 읽어와 sqlalchemy 엔진을 생성하고 to_postgis가 호출되어야 합니다.
    """
    # 1. 가짜 DB 환경변수 주입
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    
    # 2. 의존성 Mocking
    mock_predictor_class = mocker.patch('main.HotspotPredictor')
    mock_predictor_instance = mock_predictor_class.return_value
    mock_predictor_instance.predict.return_value = dummy_result_gdf
    
    mocker.patch('geopandas.GeoDataFrame.to_file')
    mock_engine = mocker.patch('sqlalchemy.create_engine')
    mock_to_postgis = mocker.patch('geopandas.GeoDataFrame.to_postgis')

    # 3. CLI 실행 (--push 옵션 추가)
    result = runner.invoke(app, [
        "infer-hotspot", 
        "--train-region", "Test", 
        "--target-region", "Test",
        "--push"
    ])
    
    # 4. 검증
    assert result.exit_code == 0
    assert "PostGIS DB 적재 완료" in result.stdout
    
    # 핵심: 엔진이 생성되고, DB 밀어넣기 메서드가 정확히 1번 호출되어야 함
    mock_engine.assert_called_once()
    mock_to_postgis.assert_called_once()
