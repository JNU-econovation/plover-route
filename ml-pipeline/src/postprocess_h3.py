import h3
import geopandas as gpd
import pandas as pd
import sqlalchemy
from shapely.geometry import Polygon
from src.utils import ensure_crs, Timer

def aggregate_predicted_hotspots(db_url: str, resolution: int = 9) -> gpd.GeoDataFrame:
    """
    PostGIS DB에서 10m 격자 예측 결과(predicted_hotspots)를 읽어와 
    H3 육각형 격자로 공간 집계(Aggregation)를 수행합니다.
    """
    engine = sqlalchemy.create_engine(db_url)
    
    with Timer("PostGIS 데이터 로딩 및 검증"):
        query = "SELECT grid_id, geometry, trash_score FROM predicted_hotspots"
        gdf = gpd.read_postgis(query, con=engine, geom_col="geometry")
        
        gdf = ensure_crs(gdf, "EPSG:4326")
        gdf = gdf.dropna(subset=['trash_score'])
        
        if len(gdf) == 0:
            raise ValueError("DB에 유효한 예측 데이터가 존재하지 않습니다.")
            
    with Timer("H3 공간 인덱스 매핑"):
        # 중심점 산출을 위해 일시적으로 투영 좌표계(EPSG:3857) 변환
        gdf_proj = gdf.to_crs("EPSG:3857")
        centroids_proj = gdf_proj.geometry.centroid
        centroids = centroids_proj.to_crs("EPSG:4326")
        
        gdf['h3_cell'] = [h3.latlng_to_cell(c.y, c.x, resolution) for c in centroids]

    with Timer("H3 그룹별 집계 연산"):
        agg = gdf.groupby('h3_cell').agg(
            trash_score_avg=('trash_score', 'mean'),
            trash_score_max=('trash_score', 'max'),
            cell_count=('grid_id', 'count')
        ).reset_index()

        agg['trash_score_avg'] = agg['trash_score_avg'].clip(0.0, 1.0)
        agg['trash_score_max'] = agg['trash_score_max'].clip(0.0, 1.0)

    with Timer("H3 육각형 Polygon 복원"):
        def cell_to_polygon(cell_id: str) -> Polygon:
            boundary = h3.cell_to_boundary(cell_id)
            # H3 (lat, lng) 경계를 Shapely (lng, lat)로 스왑
            coords = [(lng, lat) for lat, lng in boundary]
            return Polygon(coords)

        agg['geometry'] = agg['h3_cell'].apply(cell_to_polygon)
        h3_gdf = gpd.GeoDataFrame(agg, geometry='geometry', crs="EPSG:4326")
        
    print(f"H3 공간 압축 집계 완료: 원본 {len(gdf)}개 격자 -> H3 {len(h3_gdf)}개 헥사곤")
    return h3_gdf

