import os
import requests
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

class DongguramiFetcher:
    def __init__(self):
        self.db_url = os.environ.get('DATABASE_URL')
        if not self.db_url:
            raise ValueError(" .env 파일에 DATABASE_URL이 설정되지 않았습니다.")
        self.engine = create_engine(self.db_url)
        self.api_url = "https://donggurami.kr/api/comap/mapping/get-mapping-list-all"
        
    def fetch_data(self) -> gpd.GeoDataFrame:
        print(f"동구라미 API 호출 중... ({self.api_url})")
        response = requests.get(self.api_url)
        
        if response.status_code != 200:
            raise ConnectionError(f"API 호출 실패: 상태 코드 {response.status_code}")
            
        data = response.json()
        mapping_list = data.get('mappingList', [])
        print(f"API 호출 완료. 총 {len(mapping_list)}개의 제보 데이터를 가져왔습니다.")
        
        df = pd.DataFrame(mapping_list)
        
        df['source_id'] = 'donggurami_' + df['cmUid'].astype(str)
        df['provider'] = 'donggurami'
        df['reported_at'] = pd.to_datetime(df['crtDt'], errors='coerce')
        
        df = df.dropna(subset=['cntrLng', 'cntrLat'])
        
        geometry = [Point(xy) for xy in zip(df['cntrLng'], df['cntrLat'])]
        gdf = gpd.GeoDataFrame(
            df[['source_id', 'provider', 'reported_at']], 
            geometry=geometry, 
            crs="EPSG:4326"
        )
        return gdf

    def _get_existing_ids(self) -> set:
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT source_id FROM raw_trash_reports"))
                return set(row[0] for row in result)
        except Exception:
            return set()

    def load_to_db(self, gdf: gpd.GeoDataFrame):
        existing_ids = self._get_existing_ids()
        print(f"현재 DB에 저장된 기존 데이터 개수: {len(existing_ids)}개")
        
        new_gdf = gdf[~gdf['source_id'].isin(existing_ids)]
        print(f"중복 제거 후 이번에 새로 Insert 할 신규 데이터 개수: {len(new_gdf)}개")
        
        if len(new_gdf) > 0:
            with self.engine.connect() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
                conn.commit()
                
            new_gdf.to_postgis(
                name='raw_trash_reports',
                con=self.engine,
                if_exists='append',
                index=False
            )
            print("성공적으로 PostGIS DB에 신규 데이터를 적재했습니다!")
        else:
            print("이미 모든 데이터가 최신 상태입니다. (중복 적재 방지 완료)")

    def execute(self):
        gdf = self.fetch_data()
        self.load_to_db(gdf)
