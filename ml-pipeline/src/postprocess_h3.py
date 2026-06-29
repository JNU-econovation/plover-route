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


def aggregate_predicted_hotspots_to_geojson(db_url: str, resolution: int, output_path: str):
    """
    Reads prediction grid centroids from PostGIS in memory-bounded chunks, 
    maps them to H3 cells, aggregates metrics in a memory-efficient structure, 
    and writes them directly as a GeoJSON stream to output_path.
    """
    import json
    import sys
    engine = sqlalchemy.create_engine(db_url)
    
    # Query total row count for progress logging
    print(f" -> [H3 Res {resolution}] Querying total row count for progress tracking...")
    sys.stdout.flush()
    with engine.connect() as conn:
        total_rows = conn.execute(sqlalchemy.text("SELECT COUNT(*) FROM predicted_hotspots WHERE trash_score IS NOT NULL")).scalar()
    print(f" -> [H3 Res {resolution}] Total rows to process: {total_rows:,}")
    sys.stdout.flush()
    
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
    chunk_size = 200000
    h3_accumulator = {}
    processed_rows = 0
    
    try:
        with Timer(f"Nationwide-scale streaming H3 aggregation (Res {resolution})"):
            for chunk in pd.read_sql_query(query, con=conn, chunksize=chunk_size):
                if chunk.empty:
                    continue
                    
                chunk_len = len(chunk)
                processed_rows += chunk_len
                
                lats = chunk['lat'].to_numpy()
                lons = chunk['lon'].to_numpy()
                scores = chunk['trash_score'].to_numpy()
                
                h3_cells = [h3.latlng_to_cell(lat, lon, resolution) for lat, lon in zip(lats, lons)]
                
                for cell, score in zip(h3_cells, scores):
                    if cell in h3_accumulator:
                        s_sum, s_max, s_cnt = h3_accumulator[cell]
                        h3_accumulator[cell] = (s_sum + score, max(s_max, score), s_cnt + 1)
                    else:
                        h3_accumulator[cell] = (score, score, 1)
                
                percent = (processed_rows / total_rows) * 100
                print(f"  -> [H3 Res {resolution}] {processed_rows:,} / {total_rows:,}행 완료 ({percent:.2f}%) | 고유 셀: {len(h3_accumulator):,}개")
                sys.stdout.flush()
    finally:
        conn.close()
                 
    if not h3_accumulator:
        raise ValueError("No valid prediction data found in database.")
        
    with Timer(f"Streaming H3 Res {resolution} hexagons to GeoJSON"):
        with open(output_path, "w", encoding="utf-8") as f:
            f.write('{"type": "FeatureCollection", "features": [\n')
            first = True
            for cell, (s_sum, s_max, s_cnt) in h3_accumulator.items():
                if not first:
                    f.write(",\n")
                first = False
                
                avg_score = min(max(s_sum / s_cnt, 0.0), 1.0)
                max_score = min(max(s_max, 0.0), 1.0)
                
                boundary = h3.cell_to_boundary(cell)
                coords = [[lng, lat] for lat, lng in boundary]
                # Close the polygon loop for valid GeoJSON
                coords.append(coords[0])
                
                feature = {
                    "type": "Feature",
                    "properties": {
                        "h3_cell": cell,
                        "trash_score_avg": avg_score,
                        "trash_score_max": max_score,
                        "cell_count": s_cnt
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [coords]
                    }
                }
                f.write(json.dumps(feature))
            f.write("\n]}")
            
    print(f"H3 spatial aggregation completed: Res {resolution} -> Written {len(h3_accumulator)} hexagons to {output_path}")
    sys.stdout.flush()

