import os
import sys
import time
import pyogrio
import geopandas as gpd
import sqlalchemy
import gc
from pathlib import Path

# 현재 경로를 sys.path에 추가하여 src 모듈 임포트 가능하도록 설정
sys.path.append(str(Path(__file__).resolve().parents[1]))
from src.utils import load_config, get_data_dirs, upsert_geodataframe_to_postgis

def push_gpkg_to_db(gpkg_path: Path, db_url: str, table_name: str = "predicted_hotspots"):
    print(f"\n==================================================")
    print(f"🚀 GPKG 직적재 프로세스 시작: {gpkg_path.name}")
    print(f"==================================================")
    
    t_start = time.time()
    try:
        info = pyogrio.read_info(str(gpkg_path))
    except Exception as e:
        print(f"❌ GPKG 정보 조회 실패 ({gpkg_path.name}): {e}")
        return
        
    total_rows = info['features']
    print(f"  -> 총 행(격자) 수: {total_rows:,}")
    
    grid_chunk_size = 1000000
    total_chunks = int((total_rows + grid_chunk_size - 1) // grid_chunk_size)
    engine = sqlalchemy.create_engine(db_url)
    
    for idx in range(total_chunks):
        t_chunk = time.time()
        start_row = idx * grid_chunk_size
        end_row = min(start_row + grid_chunk_size, total_rows)
        print(f"  -> [청크 {idx+1}/{total_chunks}] {start_row:,} ~ {end_row:,} 행 로딩 중...")
        
        try:
            # pyogrio 기반 슬라이싱 로딩
            chunk_gdf = gpd.read_file(str(gpkg_path), rows=slice(start_row, end_row))
        except Exception as e:
            print(f"❌ {idx+1}번째 청크 로딩 중 오류 발생: {e}")
            continue
        
        # 필수 컬럼만 추출
        essential_cols = ['grid_id', 'geometry', 'trash_score']
        # 만약 컬럼이 없으면 에러가 나므로 확인 후 필터링
        available_cols = [col for col in essential_cols if col in chunk_gdf.columns]
        essential_gdf = chunk_gdf[available_cols].copy()
        
        if 'grid_id' not in essential_gdf.columns or 'geometry' not in essential_gdf.columns or 'trash_score' not in essential_gdf.columns:
            print(f"❌ 필수 컬럼('grid_id', 'geometry', 'trash_score') 중 일부가 존재하지 않습니다: {essential_gdf.columns}")
            del chunk_gdf, essential_gdf
            gc.collect()
            continue
            
        # 중복 제거
        essential_gdf = essential_gdf.drop_duplicates(subset=["grid_id"], keep="first")
        
        # DB 적재
        print(f"     -> [DB Upsert 적재] {idx+1}/{total_chunks} 시작...")
        try:
            upsert_geodataframe_to_postgis(essential_gdf, table_name, engine, unique_col="grid_id")
        except Exception as e:
            print(f"❌ DB Upsert 중 오류 발생: {e}")
            del chunk_gdf, essential_gdf
            gc.collect()
            continue
        
        print(f"     -> [청크 완착] 소요시간: {time.time()-t_chunk:.2f}초 | 메모리 반환 중...")
        del chunk_gdf, essential_gdf
        gc.collect()
        
    print(f"✔ {gpkg_path.name} 적재 완료! 총 소요시간: {time.time()-t_start:.2f}초")

def main():
    config = load_config()
    _, processed_dir = get_data_dirs(config)
    
    # DB URL 설정
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        # env 파일에서 로드 시도
        env_path = Path(__file__).resolve().parents[2] / 'scripts' / '.env'
        if env_path.exists():
            print(f"scripts/.env 파일 발견. DATABASE_URL 로딩 중...")
            with open(env_path) as f:
                for line in f:
                    if line.strip().startswith('DATABASE_URL='):
                        db_url = line.strip().split('=', 1)[1].strip('"\'')
                        break
        if not db_url:
            # ml-pipeline/.env 파일에서 로드 시도
            env_ml_path = Path(__file__).resolve().parents[1] / '.env'
            if env_ml_path.exists():
                print(f"ml-pipeline/.env 파일 발견. DATABASE_URL 로딩 중...")
                with open(env_ml_path) as f:
                    for line in f:
                        if line.strip().startswith('DATABASE_URL='):
                            db_url = line.strip().split('=', 1)[1].strip('"\'')
                            break
                            
    if not db_url:
        print("❌ DATABASE_URL 환경변수가 존재하지 않습니다.")
        sys.exit(1)
            
    print(f"DATABASE_URL: {db_url.split('@')[-1]}") # 보안상 뒤쪽 호스트 정보만 노출
    
    # sys.argv로 특정 지역 필터 전달 가능하도록 설정 (예: uv run fast_db_pusher.py jeju)
    filter_word = sys.argv[1].lower() if len(sys.argv) > 1 else None
    
    # processed_dir에서 result_hotspot_*.gpkg 파일 매칭
    gpkg_files = list(processed_dir.glob("result_hotspot_*.gpkg"))
    if not gpkg_files:
        print(f"❌ 적재할 result_hotspot_*.gpkg 파일이 존재하지 않습니다. (경로: {processed_dir})")
        sys.exit(1)
        
    if filter_word:
        gpkg_files = [f for f in gpkg_files if filter_word in f.name.lower()]
        print(f"💡 필터 단어 '{filter_word}'에 매칭된 GPKG 파일 목록:")
    else:
        # 강원도는 미완성 상태이므로 기본 전체 적재에서는 안전하게 배제
        gpkg_files = [f for f in gpkg_files if "gangwon" not in f.name.lower()]
        print(f"💡 발견된 {len(gpkg_files)}개 GPKG 파일 전체 적재를 순차 개시합니다. (미완성 강원 스킵 완료)")
        
    for f in sorted(gpkg_files, key=lambda x: x.stat().st_size):
        print(f" - {f.name} ({f.stat().st_size / 1024 / 1024:.2f} MB)")
        
    for f in sorted(gpkg_files, key=lambda x: x.stat().st_size):
        # 🌟 [크로스 격자 매칭 검증 가드]
        # 결과 GPKG의 격자 개수와 원본 grid GPKG의 격자 개수를 1:1 대조하여 손상 감지
        region_sig = f.name.replace("result_hotspot_", "").replace("_10m_buf10m_poi_road.gpkg", "")
        grid_file = processed_dir / f"grid_{region_sig}_10m_buf10m.gpkg"
        
        print(f"\n🔍 [격자 검증] {f.name} 유효성 교차 검증 중...")
        if not grid_file.exists():
            print(f" ⚠ 원본 그리드 파일이 존재하지 않습니다: {grid_file.name}. 안전을 위해 신규 빌드 대상 처리.")
            sys.exit(2)
            
        try:
            info_res = pyogrio.read_info(str(f))
            info_grid = pyogrio.read_info(str(grid_file))
            rows_res = info_res['features']
            rows_grid = info_grid['features']
            
            if rows_res != rows_grid:
                print(f" 🚨 [손상 파일 포착] 결과 격자수({rows_res:,})가 원본 그리드 격자수({rows_grid:,})와 불일치합니다!")
                print(f"  -> {f.name}은(는) 불완전하게 잘린 손상 파일로 진단되었습니다. 고속 복구를 기각합니다.")
                sys.exit(2)
            else:
                print(f" ✔ [검증 완벽] 결과 격자수와 원본 격자수가 정확히 일치합니다 ({rows_res:,}행). 청정 파일 인가!")
        except Exception as ve:
            print(f" 🚨 [검증 실패] 파일 구조 판독 불능 (손상 의심): {ve}")
            sys.exit(2)
            
        push_gpkg_to_db(f, db_url)

if __name__ == "__main__":
    main()
