import os
import typer

# 기존 파이프라인 모듈들
from src.grid_maker import generate_grid
from src.feature_engineering import FeatureOrchestrator
from src.dataset_builder import DatasetBuilder
from src.model_trainer import ModelTrainer
from src.predictor import HotspotPredictor
from src.visualizer import VisualizerFactory
from src.utils import load_config, get_pipeline_paths
from pathlib import Path

# 전역 설정 로드 (함수 정의 시점에 typer.Option의 기본값으로 주입하기 위함)
config = load_config()

# Typer 앱 초기화
app = typer.Typer(help="GeoAI Plogging ML Pipeline Orchestrator (CLI)")

@app.command()
def add_grid(
    region: str = typer.Option(config['spatial']['target_region'], help="타겟 지역명"),
    grid_size: int = typer.Option(config['spatial']['grid_size_meters'], help="격자 1칸의 크기(m)"),
    buffer: int = typer.Option(config['spatial']['buffer_size_meters'], help="도로 중심선(엣지) 기준 마스킹 버퍼 반경(m)"),
    force_download: bool = typer.Option(False, help="기존 로컬 캐시 무시 및 OSM API에서 재다운로드")
):
    """[Phase 1-2] 원본 도로망(OSMnx) 추출 및 10m 정방형 그리드를 마스킹합니다."""
    generate_grid(region=region, grid_size=grid_size, buffer_size=buffer, force_download=force_download)

@app.command()
def add_features(
    region: str = typer.Option(config['spatial']['target_region'], help="타겟 지역명"),
    grid_size: int = typer.Option(config['spatial']['grid_size_meters'], help="격자 1칸의 크기(m)"),
    buffer: int = typer.Option(config['spatial']['buffer_size_meters'], help="마스킹 확장 버퍼 반경(m)"),
    feature_type: str = typer.Option(config['pipeline']['default_feature_type'], help="추가할 피처 종류 (예: poi, pop, cctv 등)")
):
    """[Phase 3] 원본 그리드 위에 다중 버퍼 특정 피처를 계산하여 추가합니다."""
    orchestrator = FeatureOrchestrator(region=region, grid_size=grid_size, buffer_size=buffer)
    orchestrator.run(feature_type=feature_type)

@app.command()
def make_dataset(
    region: str = typer.Option(config['spatial']['target_region'], help="타겟 지역명"),
    grid_size: int = typer.Option(config['spatial']['grid_size_meters'], help="격자 1칸의 크기(m)"),
    buffer: int = typer.Option(config['spatial']['buffer_size_meters'], help="마스킹 확장 버퍼 반경(m)"),
    view_type: str = typer.Option(config['pipeline']['default_view_type'], help="DB에서 불러올 정답지(View) 형태 전략"),
    feature_type: str = typer.Option(config['pipeline']['default_feature_type'], help="학습에 포함된 피처 종류")
):
    """[Phase 4] PostGIS DB에서 정답(Y) View를 불러와 정적 피처(Grid)와 병합합니다."""
    builder = DatasetBuilder(region=region, grid_size=grid_size, buffer_size=buffer, view_type=view_type, feature_type=feature_type)
    builder.build()

@app.command()
def train_model(
    region: str = typer.Option(config['spatial']['target_region'], help="타겟 지역명"),
    grid_size: int = typer.Option(config['spatial']['grid_size_meters'], help="격자 크기(m)"),
    buffer: int = typer.Option(config['spatial']['buffer_size_meters'], help="마스킹 확장 버퍼 반경(m)"),
    view_type: str = typer.Option(config['pipeline']['default_view_type'], help="학습에 사용된 정답지(View) 형태 전략")
):
    """[Phase 5] 만들어진 데이터셋(GPKG)으로 PU-XGBoost 모델을 학습시킵니다."""
    paths = get_pipeline_paths(config, region, grid_size, buffer, view_type, config['pipeline']['default_feature_type'])
    
    trainer = ModelTrainer(data_path=str(paths["dataset"]), model_save_path=str(paths["model"]), config=config)
    trainer.train()

@app.command()
def infer_hotspot(
    target_region: str = typer.Option(config['spatial']['target_region'], help="추론을 진행할 타겟 지역명 (예: 광주 전체)"),
    train_region: str = typer.Option(config['spatial']['target_region'], help="모델을 학습시킨 지역명 (예: 광주 동구)"),
    grid_size: int = typer.Option(config['spatial']['grid_size_meters'], help="격자 크기(m)"),
    buffer: int = typer.Option(config['spatial']['buffer_size_meters'], help="마스킹 확장 버퍼 반경(m)"),
    feature_type: str = typer.Option(config['pipeline']['default_feature_type'], help="추론 대상 피처 종류")
):
    """[Phase 6] 타겟 지역에 대해 학습된 모델로 핫스팟 확률(trash_score)을 추론합니다. (공간 전이 학습 지원)"""
    # 1. 모델이 있는 경로 (train_region 기준)
    model_paths = get_pipeline_paths(config, train_region, grid_size, buffer, config['pipeline']['default_view_type'], feature_type)
    
    # 2. 추론할 피처와 결과물을 저장할 경로 (target_region 기준)
    target_paths = get_pipeline_paths(config, target_region, grid_size, buffer, config['pipeline']['default_view_type'], feature_type)
    
    predictor = HotspotPredictor(model_path=str(model_paths["model"]))
    gdf_result = predictor.predict(target_data_path=str(target_paths["features"]))
    
    gdf_result.to_file(str(target_paths["result"]), driver="GPKG")
    typer.secho(f"🎉 최종 추론 결과 저장 완료: {target_paths['result']}", fg=typer.colors.GREEN)

@app.command()
def visualize_hotspot(
    target_region: str = typer.Option(config['spatial']['target_region'], help="시각화할 타겟 지역명 (예: 광주 전체)"),
    grid_size: int = typer.Option(config['spatial']['grid_size_meters'], help="격자 1칸의 크기(m)"),
    buffer: int = typer.Option(config['spatial']['buffer_size_meters'], help="마스킹 확장 버퍼 반경(m)"),
    feature_type: str = typer.Option(config['pipeline']['default_feature_type'], help="추론에 사용된 피처 종류"),
    map_type: str = typer.Option("static", help="생성할 지도 종류 (static)")
):
    """[Phase 7] 추론된 핫스팟 확률 지도를 시각화 이미지로 저장합니다."""
    target_paths = get_pipeline_paths(config, target_region, grid_size, buffer, config['pipeline']['default_view_type'], feature_type)
    
    visualizer = VisualizerFactory.get_visualizer(
        map_type=map_type,
        data_path=str(target_paths["result"]),
        output_path=str(target_paths["map"])
    )
    visualizer.render()

if __name__ == "__main__":
    app()
