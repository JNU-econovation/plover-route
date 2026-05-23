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
    push: bool = typer.Option(False, "--push", help="추론 결과를 PostGIS DB에 업로드합니다 (배포 시 필수)")
):
    model_paths = get_pipeline_paths(config, train_region, grid_size, buffer, config['pipeline']['default_view_type'], feature_type)
    
    target_paths = get_pipeline_paths(config, target_region, grid_size, buffer, config['pipeline']['default_view_type'], feature_type)
    
    predictor = HotspotPredictor(model_path=str(model_paths["model"]))
    gdf_result = predictor.predict(target_data_path=str(target_paths["features"]))
    
    gdf_result.to_file(str(target_paths["result"]), driver="GPKG")
    typer.secho(f"로컬 백업 저장 완료: {target_paths['result']}", fg=typer.colors.GREEN)
    
    if push:
        db_url = os.environ.get('DATABASE_URL')
        if not db_url:
            typer.secho(".env 파일에 DATABASE_URL이 설정되지 않아 DB 업로드를 취소합니다.", fg=typer.colors.RED)
            raise typer.Exit(code=1)
            
        predictor.push_to_db(gdf_result, db_url)

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
    resolution: int = typer.Option(9, help="H3 공간 압축 집계 해상도 (기본 Res 9 ~100m)"),
    bucket: str = typer.Option(None, help="AWS S3 버킷명 (생략 시 .env의 AWS_S3_BUCKET 사용)")
):
    import subprocess
    import os
    import boto3
    from src.postprocess_h3 import aggregate_predicted_hotspots
    from dotenv import load_dotenv
    from src.utils import get_data_dirs
    
    load_dotenv()
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        typer.secho("DATABASE_URL이 .env 파일에 설정되지 않았습니다.", fg=typer.colors.RED)
        raise typer.Exit(code=1)
        
    s3_bucket = bucket or os.environ.get('AWS_S3_BUCKET')
    
    try:
        typer.secho("H3 집계 변환 시작...", fg=typer.colors.CYAN)
        h3_gdf = aggregate_predicted_hotspots(db_url, resolution)
    except Exception as e:
        typer.secho(f"H3 집계 중 에러 발생: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
        
    _, processed_dir = get_data_dirs(config)
    geojson_path = processed_dir / "hotspots.geojson"
    
    typer.secho(f"임시 GeoJSON 저장 중: {geojson_path}", fg=typer.colors.CYAN)
    h3_gdf.to_file(geojson_path, driver='GeoJSON')
    
    mbtiles_name = "hotspots.mbtiles"
    pmtiles_name = "hotspots.pmtiles"
    mbtiles_path = processed_dir / mbtiles_name
    pmtiles_path = processed_dir / pmtiles_name
    
    if mbtiles_path.exists():
        mbtiles_path.unlink()
    if pmtiles_path.exists():
        pmtiles_path.unlink()
        
    # Step 1: jskeates/tippecanoe를 사용하여 GeoJSON -> MBTiles 컴파일
    tippecanoe_cmd = [
        "docker", "run", "--entrypoint", "", "--rm",
        "-v", f"{processed_dir}:/data",
        "jskeates/tippecanoe:latest",
        "tippecanoe",
        "-f",
        "-Z4",
        "-z15",
        "-o", f"/data/{mbtiles_name}",
        "-l", "hotspots",
        "/data/hotspots.geojson"
    ]
    
    typer.secho("Tippecanoe Docker로 hotspots.mbtiles 1차 컴파일 중...", fg=typer.colors.CYAN)
    try:
        res = subprocess.run(tippecanoe_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.stdout:
            typer.secho(res.stdout, fg=typer.colors.GREEN)
        if res.stderr:
            typer.secho(res.stderr, fg=typer.colors.YELLOW)
    except Exception as e:
        typer.secho(f"Tippecanoe 1차 컴파일 중 에러 발생: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
        
    # Step 2: protomaps/go-pmtiles를 사용하여 MBTiles -> PMTiles 고속 변환
    convert_cmd = [
        "docker", "run", "--rm",
        "-v", f"{processed_dir}:/data",
        "protomaps/go-pmtiles:latest",
        "convert",
        f"/data/{mbtiles_name}",
        f"/data/{pmtiles_name}"
    ]
    
    typer.secho("go-pmtiles Docker로 hotspots.pmtiles 최종 변환 중...", fg=typer.colors.CYAN)
    try:
        res = subprocess.run(convert_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.stdout:
            typer.secho(res.stdout, fg=typer.colors.GREEN)
        if res.stderr:
            typer.secho(res.stderr, fg=typer.colors.YELLOW)
        typer.secho("PMTiles 최종 컴파일 성공! 🎉", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"go-pmtiles 변환 중 에러 발생: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    finally:
        if geojson_path.exists():
            geojson_path.unlink()
        if mbtiles_path.exists():
            mbtiles_path.unlink()
            
    if not s3_bucket:
        typer.secho("AWS_S3_BUCKET이 설정되지 않아 S3 업로드를 스킵하고 로컬 파일 컴파일로 성공 처리합니다.", fg=typer.colors.YELLOW)
        typer.secho(f"로컬 파일 위치: {pmtiles_path}", fg=typer.colors.GREEN)
        return
        
    aws_access_key = os.environ.get('AWS_ACCESS_KEY_ID')
    aws_secret_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    aws_region = os.environ.get('AWS_DEFAULT_REGION') or os.environ.get('AWS_REGION') or 'ap-northeast-2'
    
    if not aws_access_key or not aws_secret_key:
        typer.secho("AWS 자격 증명(AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)이 존재하지 않아 S3 업로드를 스킵합니다.", fg=typer.colors.YELLOW)
        typer.secho(f"로컬 파일 위치: {pmtiles_path}", fg=typer.colors.GREEN)
        return
        
    typer.secho(f"AWS S3 버킷 '{s3_bucket}'에 pmtiles 파일 배포 중...", fg=typer.colors.CYAN)
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=aws_region
        )
        
        s3_client.upload_file(
            Filename=str(pmtiles_path),
            Bucket=s3_bucket,
            Key=pmtiles_name,
            ExtraArgs={'ACL': 'public-read', 'ContentType': 'application/octet-stream'}
        )
        
        s3_url = f"https://{s3_bucket}.s3.{aws_region}.amazonaws.com/{pmtiles_name}"
        typer.secho(f"S3 업로드 및 배포 완료! 🚀", fg=typer.colors.GREEN)
        typer.secho(f"공개 타일셋 URL: {s3_url}", fg=typer.colors.GREEN)
    except Exception as e:
        typer.secho(f"S3 업로드 중 에러 발생: {e}", fg=typer.colors.RED)
        typer.secho("업로드는 실패했으나 로컬 PMTiles 파일은 성공적으로 확보되었습니다.", fg=typer.colors.YELLOW)
        typer.secho(f"로컬 파일 위치: {pmtiles_path}", fg=typer.colors.GREEN)

if __name__ == "__main__":
    app()
