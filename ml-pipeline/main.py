import os
import typer

from src.grid_maker import generate_grid
from src.feature_engineering import FeatureOrchestrator
from src.data_fetcher import DongguramiFetcher
from src.dataset_builder import DatasetBuilder
from src.model_trainer import ModelTrainer
from src.predictor import HotspotPredictor
from src.visualizer import VisualizerFactory
from src.utils import load_config, get_pipeline_paths
from pathlib import Path

config = load_config()

app = typer.Typer(help="GeoAI Plogging ML Pipeline Orchestrator (CLI)")

@app.command()
def fetch_raw_data():
    fetcher = DongguramiFetcher()
    fetcher.execute()

@app.command()
def add_grid(
    region: str = typer.Option(config['spatial']['target_region'], help="타겟 지역명"),
    grid_size: int = typer.Option(config['spatial']['grid_size_meters'], help="격자 1칸의 크기(m)"),
    buffer: int = typer.Option(config['spatial']['buffer_size_meters'], help="도로 중심선(엣지) 기준 마스킹 버퍼 반경(m)"),
    force_download: bool = typer.Option(False, help="기존 로컬 캐시 무시 및 OSM API에서 재다운로드")
):
    generate_grid(region=region, grid_size=grid_size, buffer_size=buffer, force_download=force_download)

@app.command()
def add_features(
    region: str = typer.Option(config['spatial']['target_region'], help="타겟 지역명"),
    grid_size: int = typer.Option(config['spatial']['grid_size_meters'], help="격자 1칸의 크기(m)"),
    buffer: int = typer.Option(config['spatial']['buffer_size_meters'], help="마스킹 확장 버퍼 반경(m)"),
    feature_type: str = typer.Option(config['pipeline']['default_feature_type'], help="추가할 피처 종류 (예: poi, pop, cctv 등)")
):
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
    builder = DatasetBuilder(region=region, grid_size=grid_size, buffer_size=buffer, view_type=view_type, feature_type=feature_type)
    builder.build()

@app.command()
def train_model(
    region: str = typer.Option(config['spatial']['target_region'], help="타겟 지역명"),
    grid_size: int = typer.Option(config['spatial']['grid_size_meters'], help="격자 크기(m)"),
    buffer: int = typer.Option(config['spatial']['buffer_size_meters'], help="마스킹 확장 버퍼 반경(m)"),
    view_type: str = typer.Option(config['pipeline']['default_view_type'], help="학습에 사용된 정답지(View) 형태 전략")
):
    paths = get_pipeline_paths(config, region, grid_size, buffer, view_type, config['pipeline']['default_feature_type'])
    
    trainer = ModelTrainer(data_path=str(paths["dataset"]), model_save_path=str(paths["model"]), config=config)
    trainer.train()

@app.command()
def infer_hotspot(
    target_region: str = typer.Option(config['spatial']['target_region'], help="추론을 진행할 타겟 지역명 (예: 광주 전체)"),
    train_region: str = typer.Option(config['spatial']['target_region'], help="모델을 학습시킨 지역명 (예: 광주 동구)"),
    grid_size: int = typer.Option(config['spatial']['grid_size_meters'], help="격자 크기(m)"),
    buffer: int = typer.Option(config['spatial']['buffer_size_meters'], help="마스킹 확장 버퍼 반경(m)"),
    feature_type: str = typer.Option(config['pipeline']['default_feature_type'], help="추론 대상 피처 종류"),
    push: bool = typer.Option(False, "--push", help="추론 결과를 PostGIS DB에 업로드합니다 (배포 시 필수)"),
    force_infer: bool = typer.Option(False, "--force-infer", help="기존 로컬 추론 결과 무시 및 강제 재추론 수행")
):
    model_paths = get_pipeline_paths(config, train_region, grid_size, buffer, config['pipeline']['default_view_type'], feature_type)
    target_paths = get_pipeline_paths(config, target_region, grid_size, buffer, config['pipeline']['default_view_type'], feature_type)
    
    db_url = os.environ.get('DATABASE_URL')
    if push and not db_url:
        typer.secho(".env 파일에 DATABASE_URL이 설정되지 않아 DB 업로드를 취소합니다.", fg=typer.colors.RED)
        raise typer.Exit(code=1)
        
    predictor = HotspotPredictor(model_path=str(model_paths["model"]))
    predictor.predict(
        target_data_path=str(target_paths["features"]),
        result_path=str(target_paths["result"]),
        force_infer=force_infer
    )
    
    if push:
        from src.db_pusher import push_gpkg_to_postgis
        push_gpkg_to_postgis(
            gpkg_path=str(target_paths["result"]),
            db_url=db_url
        )

@app.command()
def push_hotspot(
    gpkg_path: str = typer.Option(..., "--gpkg-path", help="Path to GPKG prediction file"),
    table_name: str = typer.Option("predicted_hotspots", "--table", help="Target database table name")
):
    """Directly ingests an existing GPKG prediction file into the PostGIS database."""
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        typer.secho("DATABASE_URL environment variable is not set.", fg=typer.colors.RED)
        raise typer.Exit(code=1)
        
    from src.db_pusher import push_gpkg_to_postgis
    push_gpkg_to_postgis(
        gpkg_path=gpkg_path,
        db_url=db_url,
        table_name=table_name
    )

@app.command()
def visualize_hotspot(
    target_region: str = typer.Option(config['spatial']['target_region'], help="시각화할 타겟 지역명 (예: 광주 전체)"),
    grid_size: int = typer.Option(config['spatial']['grid_size_meters'], help="격자 1칸의 크기(m)"),
    buffer: int = typer.Option(config['spatial']['buffer_size_meters'], help="마스킹 확장 버퍼 반경(m)"),
    feature_type: str = typer.Option(config['pipeline']['default_feature_type'], help="추론에 사용된 피처 종류"),
    map_type: str = typer.Option("static", help="생성할 지도 종류 (static)")
):
    target_paths = get_pipeline_paths(config, target_region, grid_size, buffer, config['pipeline']['default_view_type'], feature_type)
    
    visualizer = VisualizerFactory.get_visualizer(
        map_type=map_type,
        data_path=str(target_paths["result"]),
        output_path=str(target_paths["map"])
    )
    visualizer.render()

@app.command()
def build_tiles(
    bucket: str = typer.Option(None, help="AWS S3 버킷명 (생략 시 .env의 AWS_S3_BUCKET 사용)")
):
    from src.tile_builder import TilePipelineBuilder
    
    try:
        builder = TilePipelineBuilder(config=config, bucket=bucket)
        builder.execute()
        typer.secho("PMTiles compilation and deployment successfully completed.", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"Error during tile build pipeline: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()

