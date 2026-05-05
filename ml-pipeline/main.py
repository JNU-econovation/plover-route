import os
import typer
from typing import Optional

# 기존 파이프라인 모듈들
from src.grid_maker import generate_grid
from src.feature_engineering import FeatureOrchestrator
from src.dataset_builder import DatasetBuilder
from src.model_trainer import ModelTrainer
from src.predictor import HotspotPredictor
from src.utils import load_config

# Typer 앱 초기화
app = typer.Typer(help="GeoAI Plogging ML Pipeline Orchestrator (CLI)")

# 전역 설정 로드
config = load_config()

@app.command()
def add_grid(
    region: Optional[str] = typer.Option(None, help="타겟 지역명 (설정하지 않으면 config.yaml 값을 따릅니다)"),
    grid_size: Optional[int] = typer.Option(None, help="격자 1칸의 크기(m)"),
    buffer: Optional[int] = typer.Option(None, help="도로 중심선(엣지) 기준 마스킹 버퍼 반경(m)"),
    force_download: bool = typer.Option(False, help="기존 로컬 캐시 무시 및 OSM API에서 재다운로드")
):
    """[Phase 1-2] 원본 도로망(OSMnx) 추출 및 10m 정방형 그리드를 마스킹합니다."""
    _region = region if region else config['spatial']['target_region']
    _grid_size = grid_size if grid_size else config['spatial']['grid_size_meters']
    _buffer = buffer if buffer is not None else config['spatial']['buffer_size_meters']
    
    generate_grid(region=_region, grid_size=_grid_size, buffer_size=_buffer, force_download=force_download)

@app.command()
def add_features(
    region: Optional[str] = typer.Option(None, help="타겟 지역명"),
    grid_size: Optional[int] = typer.Option(None, help="격자 1칸의 크기(m)"),
    buffer: Optional[int] = typer.Option(None, help="마스킹 확장 버퍼 반경(m)"),
    feature_type: Optional[str] = typer.Option(None, help="추가할 피처 종류 (예: poi, pop, cctv 등)")
):
    """[Phase 3] 원본 그리드 위에 다중 버퍼 특정 피처를 계산하여 추가합니다."""
    _region = region if region else config['spatial']['target_region']
    _grid_size = grid_size if grid_size else config['spatial']['grid_size_meters']
    _buffer = buffer if buffer is not None else config['spatial']['buffer_size_meters']
    _feature_type = feature_type if feature_type else config['pipeline']['default_feature_type']
    
    orchestrator = FeatureOrchestrator(region=_region, grid_size=_grid_size, buffer_size=_buffer)
    orchestrator.run(feature_type=_feature_type)

@app.command()
def make_dataset(
    region: Optional[str] = typer.Option(None, help="타겟 지역명"),
    grid_size: Optional[int] = typer.Option(None, help="격자 1칸의 크기(m)"),
    buffer: Optional[int] = typer.Option(None, help="마스킹 확장 버퍼 반경(m)"),
    view_type: Optional[str] = typer.Option(None, help="DB에서 불러올 정답지(View) 형태 전략")
):
    """[Phase 4] PostGIS DB에서 정답(Y) View를 불러와 정적 피처(Grid)와 병합합니다."""
    _region = region if region else config['spatial']['target_region']
    _grid_size = grid_size if grid_size else config['spatial']['grid_size_meters']
    _buffer = buffer if buffer is not None else config['spatial']['buffer_size_meters']
    _view_type = view_type if view_type else config['pipeline']['default_view_type']
    
    builder = DatasetBuilder(region=_region, grid_size=_grid_size, buffer_size=_buffer, view_type=_view_type)
    builder.build()

@app.command()
def train_model(
    dataset: str = typer.Option(..., help="학습에 사용할 대상 데이터셋 파일 경로 (.gpkg)"),
    model_out: str = typer.Option("./models/pu_xgboost_model.pkl", help="학습된 모델을 저장할 경로 (.pkl)")
):
    """[Phase 5] 만들어진 데이터셋(GPKG)으로 PU-XGBoost 모델을 학습시킵니다."""
    trainer = ModelTrainer(data_path=dataset, model_save_path=model_out, config=config)
    trainer.train()

@app.command()
def infer_hotspot(
    dataset: str = typer.Option(..., help="추론할 대상 지역의 데이터 파일 경로 (.gpkg)"),
    output_path: str = typer.Option(..., help="추론 결과가 추가된 데이터를 저장할 경로 (.gpkg)"),
    model_path: str = typer.Option("./models/pu_xgboost_model.pkl", help="불러올 모델 파일 경로 (.pkl)")
):
    """[Phase 6] 타겟 지역에 대해 학습된 모델로 핫스팟 확률(trash_score)을 추론합니다."""
    predictor = HotspotPredictor(model_path=model_path)
    gdf_result = predictor.predict(target_data_path=dataset)
    
    # 디렉토리 자동 생성 및 저장 (PostGIS DB 업데이트 전 로컬 검증용)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    gdf_result.to_file(output_path, driver="GPKG")
    typer.secho(f"🎉 최종 추론 결과 저장 완료: {output_path}", fg=typer.colors.GREEN)

if __name__ == "__main__":
    app()
