import os
import subprocess
import boto3
from pathlib import Path
from dotenv import load_dotenv
from src.postprocess_h3 import aggregate_predicted_hotspots
from src.utils import get_data_dirs

class TilePipelineBuilder:
    def __init__(self, config: dict, bucket: str = None):
        self.config = config
        self.bucket = bucket
        load_dotenv()
        
    def execute(self):
        db_url = os.environ.get("DATABASE_URL")
        if not db_url:
            raise ValueError("DATABASE_URL is not set in environment variables.")
            
        s3_bucket = self.bucket or os.environ.get("AWS_S3_BUCKET")
        
        h3_gdf_res7 = aggregate_predicted_hotspots(db_url, 7)
        h3_gdf_res9 = aggregate_predicted_hotspots(db_url, 9)
        h3_gdf_res11 = aggregate_predicted_hotspots(db_url, 11)
        
        _, processed_dir = get_data_dirs(self.config)
        geojson_path_res7 = processed_dir / "hotspots_res7.geojson"
        geojson_path_res9 = processed_dir / "hotspots_res9.geojson"
        geojson_path_res11 = processed_dir / "hotspots_res11.geojson"
        
        h3_gdf_res7.to_file(geojson_path_res7, driver="GeoJSON")
        h3_gdf_res9.to_file(geojson_path_res9, driver="GeoJSON")
        h3_gdf_res11.to_file(geojson_path_res11, driver="GeoJSON")
        
        mbtiles_name = "hotspots.mbtiles"
        pmtiles_name = "hotspots.pmtiles"
        mbtiles_path = processed_dir / mbtiles_name
        pmtiles_path = processed_dir / pmtiles_name
        
        res7_mbtiles_path = processed_dir / "res7.mbtiles"
        res9_mbtiles_path = processed_dir / "res9.mbtiles"
        res11_mbtiles_path = processed_dir / "res11.mbtiles"
        
        for path in [mbtiles_path, pmtiles_path, res7_mbtiles_path, res9_mbtiles_path, res11_mbtiles_path]:
            if path.exists():
                path.unlink()
                
        res7_cmd = [
            "docker", "run", "--entrypoint", "", "--rm",
            "-v", f"{processed_dir}:/data",
            "jskeates/tippecanoe:latest",
            "tippecanoe",
            "-f",
            "-o", "/data/res7.mbtiles",
            "-Z4", "-z13",
            "--layer=hotspots_res7", "/data/hotspots_res7.geojson"
        ]
        
        res9_cmd = [
            "docker", "run", "--entrypoint", "", "--rm",
            "-v", f"{processed_dir}:/data",
            "jskeates/tippecanoe:latest",
            "tippecanoe",
            "-f",
            "-o", "/data/res9.mbtiles",
            "-Z8", "-z17",
            "--layer=hotspots_res9", "/data/hotspots_res9.geojson"
        ]
        
        res11_cmd = [
            "docker", "run", "--entrypoint", "", "--rm",
            "-v", f"{processed_dir}:/data",
            "jskeates/tippecanoe:latest",
            "tippecanoe",
            "-f",
            "-pf",
            "-pk",
            "--drop-rate=0",
            "-o", "/data/res11.mbtiles",
            "-Z16", "-z17",
            "--layer=hotspots_res11", "/data/hotspots_res11.geojson"
        ]
        
        tile_join_cmd = [
            "docker", "run", "--entrypoint", "", "--rm",
            "-v", f"{processed_dir}:/data",
            "jskeates/tippecanoe:latest",
            "tile-join",
            "-f",
            "-o", f"/data/{mbtiles_name}",
            "/data/res7.mbtiles",
            "/data/res9.mbtiles",
            "/data/res11.mbtiles"
        ]
        
        try:
            print("1/4 Compiling H3 Res 7 tiles (Z4-Z13)...")
            subprocess.run(res7_cmd, check=True)
            
            print("2/4 Compiling H3 Res 9 tiles (Z8-Z17)...")
            subprocess.run(res9_cmd, check=True)
            
            print("3/4 Compiling H3 Res 11 ultra-fine tiles (Z16-Z17)...")
            subprocess.run(res11_cmd, check=True)
            
            print("4/4 Merging layers using tile-join...")
            subprocess.run(tile_join_cmd, check=True)
        except subprocess.CalledProcessError as e:
            self._cleanup_temp_files(
                geojson_path_res7, geojson_path_res9, geojson_path_res11,
                res7_mbtiles_path, res9_mbtiles_path, res11_mbtiles_path, mbtiles_path
            )
            raise RuntimeError(f"Tippecanoe or tile-join compilation failed: {e}")
            
        convert_cmd = [
            "docker", "run", "--rm",
            "-v", f"{processed_dir}:/data",
            "protomaps/go-pmtiles:latest",
            "convert",
            f"/data/{mbtiles_name}",
            f"/data/{pmtiles_name}"
        ]
        
        print("Converting compiled MBTiles to PMTiles format...")
        try:
            subprocess.run(convert_cmd, check=True)
            print("Successfully compiled hybrid 3-stage PMTiles.")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"go-pmtiles conversion failed: {e}")
        finally:
            self._cleanup_temp_files(
                geojson_path_res7, geojson_path_res9, geojson_path_res11,
                res7_mbtiles_path, res9_mbtiles_path, res11_mbtiles_path, mbtiles_path
            )
            
        if not s3_bucket:
            print("AWS_S3_BUCKET is not configured. Skipping S3 upload.")
            print(f"Local PMTiles path: {pmtiles_path}")
            return
            
        aws_access = os.environ.get("AWS_ACCESS_KEY_ID")
        aws_secret = os.environ.get("AWS_SECRET_ACCESS_KEY")
        aws_region = os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION") or "ap-northeast-2"
        
        if not aws_access or not aws_secret:
            print("AWS credentials are not configured. Skipping S3 upload.")
            print(f"Local PMTiles path: {pmtiles_path}")
            return
            
        print(f"Uploading pmtiles to AWS S3 bucket: {s3_bucket}...")
        try:
            s3 = boto3.client(
                "s3",
                aws_access_key_id=aws_access,
                aws_secret_access_key=aws_secret,
                region_name=aws_region
            )
            s3.upload_file(
                Filename=str(pmtiles_path),
                Bucket=s3_bucket,
                Key=pmtiles_name,
                ExtraArgs={"ACL": "public-read", "ContentType": "application/octet-stream"}
            )
            s3_url = f"https://{s3_bucket}.s3.{aws_region}.amazonaws.com/{pmtiles_name}"
            print(f"S3 upload completed. Public URL: {s3_url}")
        except Exception as e:
            print(f"Failed to upload to S3: {e}")
            print(f"Local PMTiles remains available at: {pmtiles_path}")

    def _cleanup_temp_files(self, *paths):
        for path in paths:
            if path.exists():
                path.unlink()
