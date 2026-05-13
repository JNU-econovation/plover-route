import geopandas as gpd
import matplotlib.pyplot as plt
from pathlib import Path
from abc import ABC, abstractmethod

class BaseVisualizer(ABC):
    def __init__(self, data_path: str, output_path: str):
        self.data_path = Path(data_path)
        self.output_path = Path(output_path)
        
    @abstractmethod
    def render(self):
        pass

class StaticMapVisualizer(BaseVisualizer):
    def render(self):
        if not self.data_path.exists():
            raise FileNotFoundError(f" 추론 결과 파일이 존재하지 않습니다: {self.data_path}")
            
        print(f"시각화 준비 중... ({self.data_path.name})")
        gdf = gpd.read_file(self.data_path)
        
        if 'trash_score' not in gdf.columns:
            raise ValueError(" 데이터셋에 핫스팟 확률 'trash_score' 컬럼이 존재하지 않습니다. 먼저 infer-hotspot 명령어를 실행하세요.")
            
        fig, ax = plt.subplots(1, 1, figsize=(15, 15), dpi=300)
        
        ax.set_facecolor('#1a1a1a')
        fig.patch.set_facecolor('#1a1a1a')
        
        print("히트맵 렌더링 중...")
        gdf.plot(
            column='trash_score',
            ax=ax,
            cmap='YlOrRd',
            legend=True,
            legend_kwds={
                'label': "Hotspot Probability (Trash Score)",
                'orientation': "horizontal",
                'shrink': 0.5,
                'pad': 0.05
            },
            edgecolor='none',
            alpha=0.9
        )
        
        ax.axis('off')
        plt.title('GeoAI Plogging: Trash Hotspot Prediction Map', color='white', fontsize=20, pad=20)
        
        print(f"시각화 이미지 저장 중... -> {self.output_path.name}")
        plt.tight_layout()
        plt.savefig(self.output_path, facecolor=fig.get_facecolor(), bbox_inches='tight')
        plt.close()
        
        print(f"시각화 이미지 생성됨 -> {self.output_path}")

class VisualizerFactory:
    @staticmethod
    def get_visualizer(map_type: str, data_path: str, output_path: str) -> BaseVisualizer:
        if map_type == "static":
            return StaticMapVisualizer(data_path, output_path)
        else:
            raise ValueError(f" 지원하지 않는 시각화 타입입니다: {map_type}")
