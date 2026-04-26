import argparse
import sys
from src.grid_maker import generate_grid
import yaml
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="GeoAI Plogging ML Pipeline Orchestrator (CLI)")
    subparsers = parser.add_subparsers(dest="command", help="사용 가능한 파이프라인 명령어 목록")
    
    # 'add-grid' 서브옵션 설정
    grid_parser = subparsers.add_parser("add-grid", help="[Phase 1-2] 원본 도로망(OSMnx) 추출 및 10m 정방형 그리드를 마스킹합니다.")
    grid_parser.add_argument("--region", type=str, default=None,
                             help="타겟 지역명 (설정하지 않으면 config.yaml의 값을 따릅니다.)")
    grid_parser.add_argument("--grid-size", type=int, default=None,
                             help="격자 1칸의 크기(m) (설정하지 않으면 config.yaml 값을 따릅니다.)")
    grid_parser.add_argument("--buffer", type=int, default=10,
                             help="도로 중심선(엣지) 기준 마스킹 확장 버퍼 반경(m) (기본값: 10m)")
    grid_parser.add_argument("--force-download", action="store_true",
                             help="기존 로컬 캐시 데이터(.graphml)를 무시하고 OSM API로 서버에서 재다운로드합니다.")
    
    # 인자 파싱
    args = parser.parse_args()
    
    # 명령어가 제공되지 않은 경우
    if args.command is None:
        parser.print_help()
        sys.exit(1)
        
    if args.command == "add-grid":
        # config.yaml에서 기본값 가져오기
        config_path = Path(__file__).parent / 'config.yaml'
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            
        region = args.region if args.region else config['spatial']['target_region']
        grid_size = args.grid_size if args.grid_size else config['spatial']['grid_size_meters']
        buffer_size = args.buffer
        force_download = args.force_download
        
        generate_grid(
            region=region,
            grid_size=grid_size,
            buffer_size=buffer_size,
            force_download=force_download
        )

if __name__ == "__main__":
    main()
