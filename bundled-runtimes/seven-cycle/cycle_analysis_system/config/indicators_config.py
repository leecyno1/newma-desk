"""
指标配置

定义五大维度指标体系的配置，包括先行、同步、滞后指标的分类和权重。
根据最新AKShare文档更新函数名和参数。
"""

from typing import Dict, List, Any, Optional
from enum import Enum
from dataclasses import dataclass, field


class IndicatorDimension(Enum):
    """指标维度枚举"""
    OVERSEAS = "海外面"
    MONETARY = "资金面"
    FUNDAMENTAL = "基本面"
    POLICY = "政策面"
    SENTIMENT = "情绪面"


class IndicatorType(Enum):
    """指标类型枚举"""
    LEADING = "先行指标"
    SYNCHRONOUS = "同步指标"
    LAGGING = "滞后指标"


@dataclass
class IndicatorConfig:
    """单个指标配置"""
    name: str
    akshare_function: str
    dimension: IndicatorDimension
    indicator_type: IndicatorType
    weight: float
    frequency: str  # daily, weekly, monthly, quarterly, yearly
    lag_months: int  # 相对于经济周期的滞后月数
    data_source: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    transformation: Optional[str] = None  # log, diff, pct_change, etc.
    
    def __post_init__(self):
        """验证配置参数"""
        if not (0 <= self.weight <= 1):
            raise ValueError(f"权重 {self.weight} 必须在 [0, 1] 范围内")
        # 允许负数表示先行性（提前几个月反映变化）
        if self.lag_months < -12 or self.lag_months > 12:
            raise ValueError(f"滞后月数 {self.lag_months} 必须在 [-12, 12] 范围内")


class IndicatorsConfig:
    """指标配置管理类"""
    
    def __init__(self):
        self._indicators = self._initialize_indicators()
        self._validate_configuration()
    
    def _initialize_indicators(self) -> Dict[str, IndicatorConfig]:
        """初始化指标配置 - 根据最新AKShare文档更新"""
        indicators = {}
        
        # 海外面指标
        overseas_indicators = [
            # 先行指标
            IndicatorConfig(
                name="美元指数",
                akshare_function="index_global_hist_em",
                dimension=IndicatorDimension.OVERSEAS,
                indicator_type=IndicatorType.LEADING,
                weight=0.15,
                frequency="daily",
                lag_months=-3,
                data_source="akshare",
                description="美元相对其他主要货币的强弱指标",
                parameters={"symbol": "美元指数"}
            ),
            IndicatorConfig(
                name="美国失业率",
                akshare_function="macro_usa_unemployment_rate",
                dimension=IndicatorDimension.OVERSEAS,
                indicator_type=IndicatorType.LEADING,
                weight=0.12,
                frequency="monthly",
                lag_months=-2,
                data_source="akshare",
                description="美国就业市场状况"
            ),
            IndicatorConfig(
                name="波罗的海干散货指数",
                akshare_function="macro_shipping_bdi",
                dimension=IndicatorDimension.OVERSEAS,
                indicator_type=IndicatorType.LEADING,
                weight=0.10,
                frequency="daily",
                lag_months=-1,
                data_source="akshare",
                description="全球贸易活跃度指标"
            ),
            # 同步指标
            IndicatorConfig(
                name="美国CPI月率",
                akshare_function="macro_usa_cpi_monthly",
                dimension=IndicatorDimension.OVERSEAS,
                indicator_type=IndicatorType.SYNCHRONOUS,
                weight=0.08,
                frequency="monthly",
                lag_months=0,
                data_source="akshare",
                description="美国通胀水平指标"
            ),
            IndicatorConfig(
                name="美国制造业PMI",
                akshare_function="macro_usa_pmi",
                dimension=IndicatorDimension.OVERSEAS,
                indicator_type=IndicatorType.SYNCHRONOUS,
                weight=0.06,
                frequency="monthly",
                lag_months=0,
                data_source="akshare",
                description="美国制造业景气度指标"
            ),
            # 滞后指标
            IndicatorConfig(
                name="美国工业生产",
                akshare_function="macro_usa_industrial_production",
                dimension=IndicatorDimension.OVERSEAS,
                indicator_type=IndicatorType.LAGGING,
                weight=0.05,
                frequency="monthly",
                lag_months=2,
                data_source="akshare",
                description="美国工业生产月率"
            )
        ]
        
        # 资金面指标
        monetary_indicators = [
            # 先行指标
            IndicatorConfig(
                name="美联储利率决议",
                akshare_function="macro_bank_usa_interest_rate",
                dimension=IndicatorDimension.MONETARY,
                indicator_type=IndicatorType.LEADING,
                weight=0.12,
                frequency="irregular",
                lag_months=-2,
                data_source="akshare",
                description="美联储基准利率"
            ),
            IndicatorConfig(
                name="欧央行利率决议",
                akshare_function="macro_bank_euro_interest_rate",
                dimension=IndicatorDimension.MONETARY,
                indicator_type=IndicatorType.LEADING,
                weight=0.10,
                frequency="irregular",
                lag_months=-1,
                data_source="akshare",
                description="欧洲央行基准利率"
            ),
            # 同步指标
            IndicatorConfig(
                name="中国M2货币供应量",
                akshare_function="macro_china_m2_yearly",
                dimension=IndicatorDimension.MONETARY,
                indicator_type=IndicatorType.SYNCHRONOUS,
                weight=0.08,
                frequency="monthly",
                lag_months=0,
                data_source="akshare",
                description="中国广义货币供应量年率"
            ),
            IndicatorConfig(
                name="新增人民币贷款",
                akshare_function="macro_rmb_loan",
                dimension=IndicatorDimension.MONETARY,
                indicator_type=IndicatorType.SYNCHRONOUS,
                weight=0.06,
                frequency="monthly",
                lag_months=0,
                data_source="akshare",
                description="银行信贷投放量"
            ),
            # 滞后指标
            IndicatorConfig(
                name="央行利率决议",
                akshare_function="macro_bank_china_interest_rate",
                dimension=IndicatorDimension.MONETARY,
                indicator_type=IndicatorType.LAGGING,
                weight=0.04,
                frequency="irregular",
                lag_months=3,
                data_source="akshare",
                description="中国人民银行基准利率"
            )
        ]
        
        # 基本面指标
        fundamental_indicators = [
            # 先行指标
            IndicatorConfig(
                name="中国制造业PMI",
                akshare_function="macro_china_pmi",
                dimension=IndicatorDimension.FUNDAMENTAL,
                indicator_type=IndicatorType.LEADING,
                weight=0.12,
                frequency="monthly",
                lag_months=-1,
                data_source="akshare",
                description="中国制造业采购经理指数"
            ),
            IndicatorConfig(
                name="中国非制造业PMI",
                akshare_function="macro_china_non_man_pmi",
                dimension=IndicatorDimension.FUNDAMENTAL,
                indicator_type=IndicatorType.LEADING,
                weight=0.08,
                frequency="monthly",
                lag_months=-1,
                data_source="akshare",
                description="中国非制造业采购经理指数"
            ),
            # 同步指标
            IndicatorConfig(
                name="中国GDP年率",
                akshare_function="macro_china_gdp_yearly",
                dimension=IndicatorDimension.FUNDAMENTAL,
                indicator_type=IndicatorType.SYNCHRONOUS,
                weight=0.15,
                frequency="quarterly",
                lag_months=0,
                data_source="akshare",
                description="中国国内生产总值年率"
            ),
            IndicatorConfig(
                name="中国GDP",
                akshare_function="macro_china_gdp",
                dimension=IndicatorDimension.FUNDAMENTAL,
                indicator_type=IndicatorType.SYNCHRONOUS,
                weight=0.10,
                frequency="quarterly",
                lag_months=0,
                data_source="akshare",
                description="中国国内生产总值"
            ),
            IndicatorConfig(
                name="中国外商直接投资",
                akshare_function="macro_china_fdi",
                dimension=IndicatorDimension.FUNDAMENTAL,
                indicator_type=IndicatorType.SYNCHRONOUS,
                weight=0.08,
                frequency="monthly",
                lag_months=0,
                data_source="akshare",
                description="中国外商直接投资"
            ),
            # 滞后指标
            IndicatorConfig(
                name="中国CPI月率",
                akshare_function="macro_china_cpi_monthly",
                dimension=IndicatorDimension.FUNDAMENTAL,
                indicator_type=IndicatorType.LAGGING,
                weight=0.06,
                frequency="monthly",
                lag_months=2,
                data_source="akshare",
                description="中国消费者价格指数月率"
            ),
            IndicatorConfig(
                name="中国PPI年率",
                akshare_function="macro_china_ppi",
                dimension=IndicatorDimension.FUNDAMENTAL,
                indicator_type=IndicatorType.LAGGING,
                weight=0.05,
                frequency="monthly",
                lag_months=1,
                data_source="akshare",
                description="中国生产者价格指数年率"
            )
        ]
        
        # 政策面指标
        policy_indicators = [
            # 先行指标
            IndicatorConfig(
                name="中国新增信贷",
                akshare_function="macro_china_new_financial_credit",
                dimension=IndicatorDimension.POLICY,
                indicator_type=IndicatorType.LEADING,
                weight=0.08,
                frequency="monthly",
                lag_months=-1,
                data_source="akshare",
                description="中国新增金融机构信贷"
            ),
            # 同步指标
            IndicatorConfig(
                name="中国消费品零售",
                akshare_function="macro_china_consumer_goods_retail",
                dimension=IndicatorDimension.POLICY,
                indicator_type=IndicatorType.SYNCHRONOUS,
                weight=0.06,
                frequency="monthly",
                lag_months=0,
                data_source="akshare",
                description="中国社会消费品零售总额"
            ),
            # 滞后指标
            IndicatorConfig(
                name="中国企业景气指数",
                akshare_function="macro_china_enterprise_boom_index",
                dimension=IndicatorDimension.POLICY,
                indicator_type=IndicatorType.LAGGING,
                weight=0.04,
                frequency="quarterly",
                lag_months=2,
                data_source="akshare",
                description="中国企业景气指数"
            )
        ]
        
        # 情绪面指标
        sentiment_indicators = [
            # 先行指标
            IndicatorConfig(
                name="全球指数实时行情",
                akshare_function="index_global_spot_em",
                dimension=IndicatorDimension.SENTIMENT,
                indicator_type=IndicatorType.LEADING,
                weight=0.06,
                frequency="daily",
                lag_months=-1,
                data_source="akshare",
                description="全球主要股指实时行情"
            ),
            # 同步指标
            IndicatorConfig(
                name="中国贸易差额",
                akshare_function="macro_china_trade_balance",
                dimension=IndicatorDimension.SENTIMENT,
                indicator_type=IndicatorType.SYNCHRONOUS,
                weight=0.05,
                frequency="monthly",
                lag_months=0,
                data_source="akshare",
                description="中国贸易差额"
            ),
            # 滞后指标
            IndicatorConfig(
                name="中国CPI年率",
                akshare_function="macro_china_cpi_yearly",
                dimension=IndicatorDimension.SENTIMENT,
                indicator_type=IndicatorType.LAGGING,
                weight=0.03,
                frequency="monthly",
                lag_months=1,
                data_source="akshare",
                description="中国消费者价格指数年率"
            )
        ]
        
        # 合并所有指标
        all_indicators = (overseas_indicators + monetary_indicators + 
                         fundamental_indicators + policy_indicators + 
                         sentiment_indicators)
        
        # 转换为字典
        for indicator in all_indicators:
            indicators[indicator.name] = indicator
        
        return indicators
    
    def _validate_configuration(self) -> None:
        """验证配置的有效性"""
        # 计算权重总和并标准化
        total_weight = sum(indicator.weight for indicator in self._indicators.values())
        
        # 如果权重总和不等于1.0，进行标准化
        if abs(total_weight - 1.0) > 1e-6:
            print(f"警告: 指标权重总和为 {total_weight:.6f}，正在进行标准化...")
            for indicator in self._indicators.values():
                indicator.weight = indicator.weight / total_weight
            
            # 验证标准化后的权重
            new_total = sum(indicator.weight for indicator in self._indicators.values())
            print(f"标准化后权重总和: {new_total:.6f}")
        
        # 验证每个维度都有指标
        dimensions = set(indicator.dimension for indicator in self._indicators.values())
        expected_dimensions = set(IndicatorDimension)
        if dimensions != expected_dimensions:
            missing = expected_dimensions - dimensions
            raise ValueError(f"缺少维度的指标: {missing}")
        
        # 验证每个维度都有三类指标
        for dimension in IndicatorDimension:
            dimension_indicators = [
                indicator for indicator in self._indicators.values()
                if indicator.dimension == dimension
            ]
            types = set(indicator.indicator_type for indicator in dimension_indicators)
            expected_types = set(IndicatorType)
            if types != expected_types:
                missing_types = expected_types - types
                print(f"警告: 维度 {dimension.value} 缺少指标类型: {[t.value for t in missing_types]}")
    
    def get_indicator(self, name: str) -> IndicatorConfig:
        """获取指定名称的指标配置"""
        if name not in self._indicators:
            raise KeyError(f"未找到指标: {name}")
        return self._indicators[name]
    
    def get_indicators_by_dimension(self, dimension: IndicatorDimension) -> List[IndicatorConfig]:
        """获取指定维度的所有指标"""
        return [
            indicator for indicator in self._indicators.values()
            if indicator.dimension == dimension
        ]
    
    def get_indicators_by_type(self, indicator_type: IndicatorType) -> List[IndicatorConfig]:
        """获取指定类型的所有指标"""
        return [
            indicator for indicator in self._indicators.values()
            if indicator.indicator_type == indicator_type
        ]
    
    def get_all_indicators(self) -> Dict[str, IndicatorConfig]:
        """获取所有指标配置"""
        return self._indicators.copy()
    
    def get_indicator_names(self) -> List[str]:
        """获取所有指标名称"""
        return list(self._indicators.keys())
    
    def get_akshare_functions(self) -> Dict[str, str]:
        """获取所有AKShare函数映射"""
        return {
            name: indicator.akshare_function 
            for name, indicator in self._indicators.items()
        }
    
    def get_dimension_weights(self) -> Dict[str, float]:
        """获取各维度的权重分布"""
        dimension_weights = {}
        for dimension in IndicatorDimension:
            total_weight = sum(
                indicator.weight for indicator in self._indicators.values()
                if indicator.dimension == dimension
            )
            dimension_weights[dimension.value] = total_weight
        return dimension_weights
    
    def get_type_weights(self) -> Dict[str, float]:
        """获取各类型的权重分布"""
        type_weights = {}
        for indicator_type in IndicatorType:
            total_weight = sum(
                indicator.weight for indicator in self._indicators.values()
                if indicator.indicator_type == indicator_type
            )
            type_weights[indicator_type.value] = total_weight
        return type_weights
    
    def update_indicator_weight(self, name: str, new_weight: float) -> None:
        """更新指标权重"""
        if name not in self._indicators:
            raise KeyError(f"未找到指标: {name}")
        
        if not (0 <= new_weight <= 1):
            raise ValueError(f"权重 {new_weight} 必须在 [0, 1] 范围内")
        
        self._indicators[name].weight = new_weight
        
        # 重新验证配置
        self._validate_configuration()
    
    def get_summary(self) -> Dict[str, Any]:
        """获取配置摘要"""
        return {
            "total_indicators": len(self._indicators),
            "dimension_distribution": self.get_dimension_weights(),
            "type_distribution": self.get_type_weights(),
            "akshare_functions": len(set(
                indicator.akshare_function for indicator in self._indicators.values()
            )),
            "data_sources": list(set(
                indicator.data_source for indicator in self._indicators.values()
            ))
        }


# 创建全局配置实例
indicators_config = IndicatorsConfig() 