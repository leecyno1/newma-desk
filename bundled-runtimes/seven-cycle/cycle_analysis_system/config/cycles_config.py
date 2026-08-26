"""
周期配置

定义六大周期的参数配置，包括周期长度、权重、检测方法等。
"""

from typing import Dict, List, Any
from enum import Enum
from dataclasses import dataclass


class CycleType(Enum):
    """周期类型枚举"""
    KONDRATIEFF = "康波周期"      # 600个月
    REAL_ESTATE = "地产周期"      # 200个月  
    CAPITAL = "资本周期"          # 100个月（朱格拉周期）
    KITCHIN = "基钦周期"          # 42个月
    CREDIT = "信用周期"           # 20个月
    ANNUAL = "年度周期"           # 12个月


class CyclePhase(Enum):
    """周期阶段枚举"""
    EXPANSION_EARLY = "扩张前期"
    EXPANSION_LATE = "扩张后期"
    CONTRACTION_EARLY = "收缩前期"
    CONTRACTION_LATE = "收缩后期"


@dataclass
class CycleConfig:
    """单个周期配置"""
    name: str
    length_months: int
    min_length: int
    max_length: int
    weight: float
    detection_method: str
    filter_type: str
    description: str
    
    def __post_init__(self):
        """验证配置参数"""
        if not (self.min_length <= self.length_months <= self.max_length):
            raise ValueError(f"周期长度 {self.length_months} 不在有效范围 [{self.min_length}, {self.max_length}] 内")
        if not (0 <= self.weight <= 1):
            raise ValueError(f"权重 {self.weight} 必须在 [0, 1] 范围内")


class CyclesConfig:
    """周期配置管理类"""
    
    def __init__(self):
        self._cycles = self._initialize_cycles()
        self._validate_weights()
    
    def _initialize_cycles(self) -> Dict[CycleType, CycleConfig]:
        """初始化六大周期配置"""
        return {
            CycleType.KONDRATIEFF: CycleConfig(
                name="康波周期",
                length_months=600,
                min_length=480,
                max_length=720,
                weight=0.25,
                detection_method="hp_filter",
                filter_type="gaussian",
                description="技术革命驱动的长期周期，约50年"
            ),
            CycleType.REAL_ESTATE: CycleConfig(
                name="地产周期",
                length_months=200,
                min_length=150,
                max_length=250,
                weight=0.20,
                detection_method="bandpass_filter",
                filter_type="butterworth",
                description="房地产投资周期，约16-17年"
            ),
            CycleType.CAPITAL: CycleConfig(
                name="资本周期",
                length_months=100,
                min_length=80,
                max_length=120,
                weight=0.20,
                detection_method="bandpass_filter",
                filter_type="butterworth",
                description="设备投资周期（朱格拉周期），约8-10年"
            ),
            CycleType.KITCHIN: CycleConfig(
                name="基钦周期",
                length_months=42,
                min_length=30,
                max_length=54,
                weight=0.15,
                detection_method="bandpass_filter",
                filter_type="butterworth",
                description="库存周期，约3-4年"
            ),
            CycleType.CREDIT: CycleConfig(
                name="信用周期",
                length_months=20,
                min_length=15,
                max_length=30,
                weight=0.10,
                detection_method="bandpass_filter",
                filter_type="butterworth",
                description="货币信贷周期，约1.5-2.5年"
            ),
            CycleType.ANNUAL: CycleConfig(
                name="年度周期",
                length_months=12,
                min_length=10,
                max_length=14,
                weight=0.10,
                detection_method="seasonal_decompose",
                filter_type="moving_average",
                description="季节性周期，1年"
            )
        }
    
    def _validate_weights(self) -> None:
        """验证权重总和"""
        total_weight = sum(cycle.weight for cycle in self._cycles.values())
        if abs(total_weight - 1.0) > 1e-6:
            raise ValueError(f"周期权重总和 {total_weight} 不等于 1.0")
    
    def get_cycle(self, cycle_type: CycleType) -> CycleConfig:
        """获取指定周期配置"""
        return self._cycles[cycle_type]
    
    def get_all_cycles(self) -> Dict[CycleType, CycleConfig]:
        """获取所有周期配置"""
        return self._cycles.copy()
    
    def get_cycle_names(self) -> List[str]:
        """获取所有周期名称"""
        return [cycle.name for cycle in self._cycles.values()]
    
    def get_cycle_lengths(self) -> Dict[str, int]:
        """获取周期长度映射"""
        return {cycle.name: cycle.length_months for cycle in self._cycles.values()}
    
    def get_cycle_weights(self) -> Dict[str, float]:
        """获取周期权重映射"""
        return {cycle.name: cycle.weight for cycle in self._cycles.values()}
    
    def update_cycle_weight(self, cycle_type: CycleType, new_weight: float) -> None:
        """更新周期权重"""
        if not (0 <= new_weight <= 1):
            raise ValueError(f"权重 {new_weight} 必须在 [0, 1] 范围内")
        
        old_weight = self._cycles[cycle_type].weight
        self._cycles[cycle_type].weight = new_weight
        
        # 重新验证权重总和
        try:
            self._validate_weights()
        except ValueError:
            # 如果验证失败，恢复原权重
            self._cycles[cycle_type].weight = old_weight
            raise ValueError("更新权重后总和不等于1.0，请调整其他周期权重")
    
    def get_phase_thresholds(self) -> Dict[str, float]:
        """获取周期阶段阈值"""
        return {
            "expansion_early": 0.0,    # 0-25%
            "expansion_late": 0.25,    # 25-50%
            "contraction_early": 0.5,  # 50-75%
            "contraction_late": 0.75   # 75-100%
        }
    
    def classify_cycle_phase(self, cycle_position: float) -> CyclePhase:
        """根据周期位置分类周期阶段
        
        Args:
            cycle_position: 周期位置，范围 [0, 1]
            
        Returns:
            CyclePhase: 周期阶段
        """
        if not (0 <= cycle_position <= 1):
            raise ValueError(f"周期位置 {cycle_position} 必须在 [0, 1] 范围内")
        
        thresholds = self.get_phase_thresholds()
        
        if cycle_position < thresholds["expansion_late"]:
            return CyclePhase.EXPANSION_EARLY
        elif cycle_position < thresholds["contraction_early"]:
            return CyclePhase.EXPANSION_LATE
        elif cycle_position < thresholds["contraction_late"]:
            return CyclePhase.CONTRACTION_EARLY
        else:
            return CyclePhase.CONTRACTION_LATE
    
    def get_filter_parameters(self, cycle_type: CycleType) -> Dict[str, Any]:
        """获取滤波器参数"""
        cycle = self.get_cycle(cycle_type)
        
        base_params = {
            "cycle_length": cycle.length_months,
            "min_length": cycle.min_length,
            "max_length": cycle.max_length,
            "filter_type": cycle.filter_type
        }
        
        # 根据检测方法添加特定参数
        if cycle.detection_method == "hp_filter":
            base_params.update({
                "lambda": 129600,  # HP滤波参数
                "two_sided": True
            })
        elif cycle.detection_method == "bandpass_filter":
            base_params.update({
                "low_freq": 1 / cycle.max_length,
                "high_freq": 1 / cycle.min_length,
                "order": 4
            })
        elif cycle.detection_method == "seasonal_decompose":
            base_params.update({
                "model": "additive",
                "extrapolate_trend": "freq"
            })
        
        return base_params


# 全局周期配置实例
cycles_config = CyclesConfig() 