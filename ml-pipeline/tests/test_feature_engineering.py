import pytest
import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString
from src.feature_engineering import POIFeatureExtractor, RoadFeatureExtractor

def test_categorize_poi():
    """상권 분류 로직이 규칙에 맞게 편의점을 포함한 6개 카테고리로 매핑하는지 검증합니다."""
    test_cases = [
        ({'상권업종대분류명': '음식', '상권업종중분류명': '주점'}, 'nightlife'),
        ({'상권업종대분류명': '음식', '상권업종중분류명': '비알코올'}, 'cafe'),
        ({'상권업종대분류명': '음식', '상권업종중분류명': '기타 간이'}, 'cafe'),
        ({'상권업종대분류명': '음식', '상권업종중분류명': '한식'}, 'food'),
        ({'상권업종대분류명': '소매', '상권업종중분류명': '종합소매점'}, 'retail'),
        ({'상권업종대분류명': '관광/여가/오락', '상권업종중분류명': '무도/유흥/가무'}, 'service'),
        ({'상권업종대분류명': '소매', '상권업종중분류명': '종합 소매', '상권업종소분류명': '편의점'}, 'convenience'),
    ]
    
    for row, expected in test_cases:
        assert POIFeatureExtractor._categorize_poi(row) == expected

def test_poi_spatial_join(mocker, dummy_config, dummy_grid_gdf, dummy_poi_df, tmp_path):
    """실제 파일을 읽지 않고, 가짜 데이터(Fixture)를 주입(Mock)하여 버퍼 연산과 카운팅 로직을 검증합니다."""
    mocker.patch('pathlib.Path.exists', return_value=True)
    
    extended_poi_df = dummy_poi_df.copy()
    extended_poi_df['상권업종소분류명'] = ''
    extended_poi_df = pd.concat([extended_poi_df, pd.DataFrame([{
        '상권업종대분류명': '소매',
        '상권업종중분류명': '종합 소매',
        '상권업종소분류명': '편의점',
        '경도': 126.94,
        '위도': 37.54
    }])], ignore_index=True)
    
    mocker.patch('pandas.read_csv', return_value=extended_poi_df)
    
    extractor = POIFeatureExtractor(dummy_config, "Test Region", tmp_path)
    
    result_gdf = extractor.extract(dummy_grid_gdf)
    
    expected_columns = [
        'food_count_30m', 'food_count_50m', 'food_count_100m',
        'retail_count_30m', 'retail_count_50m', 'retail_count_100m',
        'nightlife_count_30m', 'nightlife_count_50m', 'nightlife_count_100m',
        'service_count_30m', 'service_count_50m', 'service_count_100m',
        'convenience_count_30m', 'convenience_count_50m', 'convenience_count_100m'
    ]
    
    for col in expected_columns:
        assert col in result_gdf.columns, f"{col} 피처가 생성되지 않았습니다."
        
    assert not result_gdf['food_count_30m'].isnull().any()

def test_road_spatial_join(mocker, dummy_config, dummy_grid_gdf, tmp_path):
    """RoadFeatureExtractor의 도로 세그먼트 공간 조인 및 밀도 집계 로직을 검증합니다."""
    mocker.patch('pathlib.Path.exists', return_value=True)
    mocker.patch('osmnx.load_graphml', return_value=object())
    
    dummy_edges = gpd.GeoDataFrame({
        'highway': ['residential', 'primary', 'service'],
        'geometry': [
            LineString([(1, 1), (5, 5)]),
            LineString([(12, 1), (15, 5)]),
            LineString([(2, 2), (8, 8)])
        ]
    }, crs='EPSG:5179')
    
    mocker.patch('osmnx.graph_to_gdfs', return_value=(None, dummy_edges))
    
    extractor = RoadFeatureExtractor(dummy_config, "Test Region", tmp_path)
    result_gdf = extractor.extract(dummy_grid_gdf)
    
    assert 'road_density_alleyway' in result_gdf.columns
    assert 'road_density_major' in result_gdf.columns
    assert result_gdf.loc[0, 'road_density_alleyway'] == 2  # residential + service in grid 0
    assert result_gdf.loc[1, 'road_density_major'] == 1  # primary in grid 1
