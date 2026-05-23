import h3
import geopandas as gpd
import pandas as pd
import sqlalchemy
from shapely.geometry import Polygon
from collections import defaultdict
from src.utils import ensure_crs, Timer

def aggregate_predicted_hotspots(db_url: str, resolution: int = 9) -> gpd.GeoDataFrame:
    """
    Reads prediction grid centroids from PostGIS in memory-bounded chunks, 
    maps them to H3 cells, and aggregates metrics streaming-style to support nationwide scales.
    """
    engine = sqlalchemy.create_engine(db_url)
    
    # Enable server-side streaming cursor to guarantee driver-level bounded memory footprint.
    conn = engine.connect().execution_options(stream_results=True)
    
    # Select only Float coordinates instead of heavy Geometry polygons to save 90% memory.
    query = """
        SELECT ST_X(ST_Centroid(geometry)) AS lon, 
               ST_Y(ST_Centroid(geometry)) AS lat, 
               trash_score 
        FROM predicted_hotspots 
        WHERE trash_score IS NOT NULL
    """
    
    # Use streaming accumulator to bound memory usage to O(H3 cells) instead of O(Input Grids)
    chunk_size = 200000
    h3_accumulator = defaultdict(lambda: {"sum": 0.0, "max": 0.0, "count": 0})
    
    try:
        with Timer("Nationwide-scale streaming H3 aggregation"):
            for chunk in pd.read_sql_query(query, con=conn, chunksize=chunk_size):
                if chunk.empty:
                    continue
                    
                h3_cells = [h3.latlng_to_cell(lat, lon, resolution) for lat, lon in zip(chunk['lat'], chunk['lon'])]
                chunk['h3_cell'] = h3_cells
                
                for cell, score in zip(chunk['h3_cell'], chunk['trash_score']):
                    cell_data = h3_accumulator[cell]
                    cell_data["sum"] += score
                    cell_data["max"] = max(cell_data["max"], score)
                    cell_data["count"] += 1
    finally:
        conn.close()
                
    if not h3_accumulator:
        raise ValueError("No valid prediction data found in database.")
        
    with Timer("Reconstructing unified H3 GeoDataFrame"):
        rows = []
        for cell, metrics in h3_accumulator.items():
            avg_score = min(max(metrics["sum"] / metrics["count"], 0.0), 1.0)
            max_score = min(max(metrics["max"], 0.0), 1.0)
            
            boundary = h3.cell_to_boundary(cell)
            coords = [(lng, lat) for lat, lng in boundary]
            
            rows.append({
                "h3_cell": cell,
                "trash_score_avg": avg_score,
                "trash_score_max": max_score,
                "cell_count": metrics["count"],
                "geometry": Polygon(coords)
            })
            
        h3_gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
        
    print(f"H3 spatial aggregation completed: Streaming -> {len(h3_gdf)} hexagons")
    return h3_gdf
