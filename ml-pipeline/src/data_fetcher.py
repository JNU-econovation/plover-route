import os
import requests
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

class DongguramiFetcher:
    """
    [Phase 0] 광주 동구라미 API에서 쓰레기 무단투기 제보 데이터를 추출하여(Extract)
    PostGIS에 적재하는(Load) ETL 파이프라인 클래스.
    """
    def __init__(self):
        self.db_url = os.environ.get('DATABASE_URL')
        if not self.db_url:
            raise ValueError("🚨 .env 파일에 DATABASE_URL이 설정되지 않았습니다.")
        self.engine = create_engine(self.db_url)
        self.api_url = "https://donggurami.kr/api/comap/mapping/get-mapping-list-all"
        
    def fetch_data(self) -> gpd.GeoDataFrame:
        """API를 호출하여 Raw Data를 가져오고 GeoDataFrame으로 변환합니다."""
        print(f"🌐 동구라미 API 호출 중... ({self.api_url})")
        response = requests.get(self.api_url)
        
        if response.status_code != 200:
            raise ConnectionError(f"❌ API 호출 실패: 상태 코드 {response.status_code}")
            
        data = response.json()
        mapping_list = data.get('mappingList', [])
        print(f"✅ API 호출 성공! 총 {len(mapping_list)}개의 제보 데이터를 가져왔습니다.")
        
        df = pd.DataFrame(mapping_list)
        
        # 통합 스키마 규격에 맞게 정제
        df['source_id'] = 'donggurami_' + df['cmUid'].astype(str)
        df['provider'] = 'donggurami'
        df['reported_at'] = pd.to_datetime(df['crtDt'], errors='coerce')
        
        # 좌표가 없는 불량 데이터 제거
        df = df.dropna(subset=['cntrLng', 'cntrLat'])
        
        # GeoDataFrame 변환 (Rule 5 준수: EPSG:4326 유지)
        geometry = [Point(xy) for xy in zip(df['cntrLng'], df['cntrLat'])]
        gdf = gpd.GeoDataFrame(
            df[['source_id', 'provider', 'reported_at']], 
            geometry=geometry, 
            crs="EPSG:4326"
        )
        return gdf

    def _get_existing_ids(self) -> set:
        """DB에 이미 저장된 source_id 목록을 가져옵니다."""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT source_id FROM raw_trash_reports"))
                return set(row[0] for row in result)
        except Exception:
            # 테이블이 아직 없는 경우
            return set()

    def load_to_db(self, gdf: gpd.GeoDataFrame):
        """중복을 제거한 신규 데이터만 PostGIS에 적재합니다."""
        existing_ids = self._get_existing_ids()
        print(f"📦 현재 DB에 저장된 기존 데이터 개수: {len(existing_ids)}개")
        
        # 신규 데이터 필터링
        new_gdf = gdf[~gdf['source_id'].isin(existing_ids)]
        print(f"✨ 중복 제거 후 이번에 새로 Insert 할 신규 데이터 개수: {len(new_gdf)}개")
        
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
            print("🚀 성공적으로 PostGIS DB에 신규 데이터를 적재했습니다!")
        else:
            print("✅ 이미 모든 데이터가 최신 상태입니다. (중복 적재 방지 완료)")

    def execute(self):
        """전체 ETL 파이프라인을 실행합니다."""
        gdf = self.fetch_data()
        self.load_to_db(gdf)
