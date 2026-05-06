import geopandas as gpd
import matplotlib.pyplot as plt
from pathlib import Path
from abc import ABC, abstractmethod

class BaseVisualizer(ABC):
    """
    [Rule 6 준수] OCP를 위한 시각화 추상 클래스
    새로운 형태의 시각화 기법(Interactive Map 등) 추가 시 이 클래스를 상속합니다.
    """
    def __init__(self, data_path: str, output_path: str):
        self.data_path = Path(data_path)
        self.output_path = Path(output_path)
        
    @abstractmethod
    def render(self):
        pass

class StaticMapVisualizer(BaseVisualizer):
    """정적 고해상도 이미지(PNG) 맵 렌더러"""
    def render(self):
        if not self.data_path.exists():
            raise FileNotFoundError(f"🚨 추론 결과 파일이 존재하지 않습니다: {self.data_path}")
            
        print(f"🎨 시각화 준비 중... ({self.data_path.name})")
        gdf = gpd.read_file(self.data_path)
        
        if 'trash_score' not in gdf.columns:
            raise ValueError("🚨 데이터셋에 핫스팟 확률 'trash_score' 컬럼이 존재하지 않습니다. 먼저 infer-hotspot 명령어를 실행하세요.")
            
        # Matplotlib 설정
        fig, ax = plt.subplots(1, 1, figsize=(15, 15), dpi=300)
        
        # 배경을 어둡게 처리하여 핫스팟이 잘 보이도록 설정
        ax.set_facecolor('#1a1a1a')
        fig.patch.set_facecolor('#1a1a1a')
        
        # 도로 등 베이스맵이 있다면 여기에 추가할 수 있습니다.
        # 현재는 격자 자체가 연속된 도화지이므로 바로 렌더링합니다.
        print("🗺️ 히트맵 렌더링 중...")
        gdf.plot(
            column='trash_score',
            ax=ax,
            cmap='YlOrRd',  # 노랑(안전) -> 빨강(위험)
            legend=True,
            legend_kwds={
                'label': "Hotspot Probability (Trash Score)",
                'orientation': "horizontal",
                'shrink': 0.5,
                'pad': 0.05
            },
            edgecolor='none',  # 격자 선 안 보이게 처리
            alpha=0.9
        )
        
        # 축 눈금 제거 및 타이틀 설정
        ax.axis('off')
        plt.title('GeoAI Plogging: Trash Hotspot Prediction Map', color='white', fontsize=20, pad=20)
        
        # 이미지 저장
        print(f"💾 시각화 이미지 저장 중... -> {self.output_path.name}")
        plt.tight_layout()
        plt.savefig(self.output_path, facecolor=fig.get_facecolor(), bbox_inches='tight')
        plt.close()
        
        print(f"🚀 [Phase 7 완료] 시각화 이미지 생성됨 -> {self.output_path}")

class VisualizerFactory:
    """시각화 방식(map_type)에 따라 적절한 시각화 객체를 반환합니다."""
    @staticmethod
    def get_visualizer(map_type: str, data_path: str, output_path: str) -> BaseVisualizer:
        if map_type == "static":
            return StaticMapVisualizer(data_path, output_path)
        # elif map_type == "interactive":
        #     return InteractiveMapVisualizer(data_path, output_path)
        else:
            raise ValueError(f"🚨 지원하지 않는 시각화 타입입니다: {map_type}")
