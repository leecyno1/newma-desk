"""
经济周期分析器

实现基于多维度指标的经济周期判断和分析。
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import warnings
warnings.filterwarnings('ignore')

from loguru import logger
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
from scipy import stats
from scipy.signal import find_peaks

try:
    from ..config.settings import settings
    from ..config.indicators_config import indicators_config, IndicatorDimension, IndicatorType
    from ..data_collection.akshare_collector import AKShareCollector
except ImportError:
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent))
    from config.settings import settings
    from config.indicators_config import indicators_config, IndicatorDimension, IndicatorType
    from data_collection.akshare_collector import AKShareCollector


class CyclePhase(Enum):
    """经济周期阶段"""
    EXPANSION = "扩张期"
    PEAK = "繁荣期"
    CONTRACTION = "收缩期"
    TROUGH = "萧条期"
    RECOVERY = "复苏期"


class CycleType(Enum):
    """周期类型"""
    KONDRATIEFF = "康波周期"  # 50-60年
    REAL_ESTATE = "地产周期"  # 18-20年
    CAPITAL = "资本开支周期"  # 9-10年
    KITCHIN = "基钦周期"  # 3-4年
    CREDIT = "信用周期"  # 7-11年
    ANNUAL = "年度周期"  # 1年


@dataclass
class CycleAnalysisResult:
    """周期分析结果"""
    cycle_type: CycleType
    current_phase: CyclePhase
    phase_confidence: float  # 0-1
    phase_duration: int  # 当前阶段持续月数
    next_phase_probability: Dict[CyclePhase, float]
    key_indicators: List[str]  # 关键指标
    analysis_date: datetime
    detailed_scores: Dict[str, float]  # 各维度得分
    historical_position: float  # 历史位置 0-1
    trend_direction: str  # "上升", "下降", "平稳"
    risk_level: str  # "低", "中", "高"


class CycleAnalyzer:
    """经济周期分析器"""
    
    def __init__(self):
        self.collector = AKShareCollector()
        self.scaler = StandardScaler()
        self.pca = PCA(n_components=0.95)  # 保留95%的方差
        
        # 周期阶段判断阈值
        self.phase_thresholds = {
            CyclePhase.TROUGH: (-2.0, -1.0),      # 萧条期
            CyclePhase.RECOVERY: (-1.0, -0.3),    # 复苏期
            CyclePhase.EXPANSION: (-0.3, 0.8),    # 扩张期
            CyclePhase.PEAK: (0.8, 1.5),          # 繁荣期
            CyclePhase.CONTRACTION: (1.5, 2.0)    # 收缩期（过热后的调整）
        }
        
        # 各维度权重
        self.dimension_weights = {
            IndicatorDimension.OVERSEAS: 0.15,      # 海外面
            IndicatorDimension.MONETARY: 0.25,      # 资金面
            IndicatorDimension.FUNDAMENTAL: 0.35,   # 基本面
            IndicatorDimension.POLICY: 0.15,        # 政策面
            IndicatorDimension.SENTIMENT: 0.10      # 情绪面
        }
    
    def _preprocess_data(self, data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """
        预处理数据，统一时间序列格式
        
        Args:
            data: 原始指标数据
            
        Returns:
            pd.DataFrame: 预处理后的数据
        """
        processed_data = []
        
        for indicator_name, df in data.items():
            if df.empty:
                continue
                
            try:
                # 获取指标配置
                config = indicators_config.get_indicator(indicator_name)
                
                # 提取时间和数值列
                time_col = None
                value_col = None
                
                # 寻找时间列
                for col in df.columns:
                    if any(keyword in col.lower() for keyword in ['日期', 'date', '时间', 'time', '月份']):
                        time_col = col
                        break
                
                # 寻找数值列
                for col in df.columns:
                    if col not in ['data_source', 'function_name', 'fetch_time', 
                                 'indicator_name', 'dimension', 'indicator_type', 'weight']:
                        if df[col].dtype in ['float64', 'int64'] or col in ['今值', '最新价', '指数', '制造业-指数']:
                            value_col = col
                            break
                
                if time_col is None or value_col is None:
                    logger.warning(f"无法找到时间或数值列: {indicator_name}")
                    continue
                
                # 创建标准化的数据格式
                temp_df = df[[time_col, value_col]].copy()
                temp_df.columns = ['date', 'value']
                temp_df['indicator'] = indicator_name
                temp_df['dimension'] = config.dimension.value
                temp_df['weight'] = config.weight
                
                # 转换日期格式
                if temp_df['date'].dtype == 'object':
                    # 处理中文日期格式
                    if '年' in str(temp_df['date'].iloc[0]):
                        temp_df['date'] = pd.to_datetime(temp_df['date'].str.replace('年', '-').str.replace('月份', ''), errors='coerce')
                    else:
                        temp_df['date'] = pd.to_datetime(temp_df['date'], errors='coerce')
                
                # 去除无效数据
                temp_df = temp_df.dropna()
                
                if len(temp_df) > 0:
                    processed_data.append(temp_df)
                    
            except Exception as e:
                logger.error(f"预处理指标数据失败: {indicator_name}, 错误: {str(e)}")
        
        if not processed_data:
            return pd.DataFrame()
        
        # 合并所有数据
        combined_df = pd.concat(processed_data, ignore_index=True)
        
        # 按日期排序
        combined_df = combined_df.sort_values('date')
        
        return combined_df
    
    def _calculate_dimension_scores(self, data: pd.DataFrame) -> Dict[str, float]:
        """
        计算各维度得分
        
        Args:
            data: 预处理后的数据
            
        Returns:
            Dict[str, float]: 各维度得分
        """
        dimension_scores = {}
        
        # 获取最近3个月的数据
        recent_date = data['date'].max()
        three_months_ago = recent_date - timedelta(days=90)
        recent_data = data[data['date'] >= three_months_ago]
        
        for dimension in IndicatorDimension:
            dimension_data = recent_data[recent_data['dimension'] == dimension.value]
            
            if dimension_data.empty:
                dimension_scores[dimension.value] = 0.0
                continue
            
            # 计算标准化得分
            scores = []
            for indicator in dimension_data['indicator'].unique():
                indicator_data = dimension_data[dimension_data['indicator'] == indicator]
                
                if len(indicator_data) < 2:
                    continue
                
                # 计算趋势得分
                values = indicator_data['value'].values
                if len(values) >= 3:
                    # 使用线性回归计算趋势
                    x = np.arange(len(values))
                    slope, _, r_value, _, _ = stats.linregress(x, values)
                    trend_score = slope * r_value  # 趋势强度 * 相关性
                else:
                    trend_score = 0
                
                # 计算相对位置得分
                if len(values) >= 12:  # 至少需要一年数据
                    current_value = values[-1]
                    historical_mean = np.mean(values[:-3])  # 排除最近3个月
                    historical_std = np.std(values[:-3])
                    
                    if historical_std > 0:
                        position_score = (current_value - historical_mean) / historical_std
                    else:
                        position_score = 0
                else:
                    position_score = 0
                
                # 综合得分
                weight = indicator_data['weight'].iloc[0]
                combined_score = (trend_score * 0.6 + position_score * 0.4) * weight
                scores.append(combined_score)
            
            # 维度总得分
            if scores:
                dimension_scores[dimension.value] = np.mean(scores)
            else:
                dimension_scores[dimension.value] = 0.0
        
        return dimension_scores
    
    def _determine_cycle_phase(self, dimension_scores: Dict[str, float]) -> Tuple[CyclePhase, float]:
        """
        判断当前经济周期阶段
        
        Args:
            dimension_scores: 各维度得分
            
        Returns:
            Tuple[CyclePhase, float]: 周期阶段和置信度
        """
        # 计算综合得分
        total_score = 0
        for dimension, score in dimension_scores.items():
            weight = self.dimension_weights.get(
                IndicatorDimension(dimension), 0.2
            )
            total_score += score * weight
        
        # 根据得分判断阶段
        phase = CyclePhase.EXPANSION  # 默认
        confidence = 0.5
        
        for phase_candidate, (min_score, max_score) in self.phase_thresholds.items():
            if min_score <= total_score < max_score:
                phase = phase_candidate
                # 计算置信度（距离阈值边界的远近）
                range_size = max_score - min_score
                distance_from_center = abs(total_score - (min_score + max_score) / 2)
                confidence = max(0.5, 1 - (distance_from_center / (range_size / 2)))
                break
        
        return phase, confidence
    
    def _predict_next_phase(self, current_phase: CyclePhase, dimension_scores: Dict[str, float]) -> Dict[CyclePhase, float]:
        """
        预测下一阶段概率
        
        Args:
            current_phase: 当前阶段
            dimension_scores: 各维度得分
            
        Returns:
            Dict[CyclePhase, float]: 各阶段概率
        """
        # 周期转换概率矩阵
        transition_matrix = {
            CyclePhase.TROUGH: {
                CyclePhase.TROUGH: 0.3,
                CyclePhase.RECOVERY: 0.6,
                CyclePhase.EXPANSION: 0.1
            },
            CyclePhase.RECOVERY: {
                CyclePhase.RECOVERY: 0.4,
                CyclePhase.EXPANSION: 0.5,
                CyclePhase.PEAK: 0.1
            },
            CyclePhase.EXPANSION: {
                CyclePhase.EXPANSION: 0.5,
                CyclePhase.PEAK: 0.3,
                CyclePhase.CONTRACTION: 0.2
            },
            CyclePhase.PEAK: {
                CyclePhase.PEAK: 0.2,
                CyclePhase.CONTRACTION: 0.7,
                CyclePhase.EXPANSION: 0.1
            },
            CyclePhase.CONTRACTION: {
                CyclePhase.CONTRACTION: 0.4,
                CyclePhase.TROUGH: 0.4,
                CyclePhase.RECOVERY: 0.2
            }
        }
        
        base_probabilities = transition_matrix.get(current_phase, {})
        
        # 根据当前指标状态调整概率
        # 这里可以根据具体的经济指标状态进一步调整概率
        
        return base_probabilities
    
    def _identify_key_indicators(self, data: pd.DataFrame, dimension_scores: Dict[str, float]) -> List[str]:
        """
        识别关键指标
        
        Args:
            data: 预处理后的数据
            dimension_scores: 各维度得分
            
        Returns:
            List[str]: 关键指标列表
        """
        # 计算各指标的重要性
        indicator_importance = {}
        
        recent_date = data['date'].max()
        three_months_ago = recent_date - timedelta(days=90)
        recent_data = data[data['date'] >= three_months_ago]
        
        for indicator in recent_data['indicator'].unique():
            indicator_data = recent_data[recent_data['indicator'] == indicator]
            
            if len(indicator_data) < 2:
                continue
            
            # 计算指标的变化幅度
            values = indicator_data['value'].values
            if len(values) >= 2:
                change_rate = abs((values[-1] - values[0]) / values[0]) if values[0] != 0 else 0
                weight = indicator_data['weight'].iloc[0]
                importance = change_rate * weight
                indicator_importance[indicator] = importance
        
        # 选择前5个最重要的指标
        sorted_indicators = sorted(
            indicator_importance.items(), 
            key=lambda x: x[1], 
            reverse=True
        )
        
        return [indicator for indicator, _ in sorted_indicators[:5]]
    
    def _calculate_risk_level(self, dimension_scores: Dict[str, float], current_phase: CyclePhase) -> str:
        """
        计算风险水平
        
        Args:
            dimension_scores: 各维度得分
            current_phase: 当前阶段
            
        Returns:
            str: 风险水平
        """
        # 基于阶段的基础风险
        phase_risk = {
            CyclePhase.TROUGH: 0.3,      # 萧条期风险较低
            CyclePhase.RECOVERY: 0.2,    # 复苏期风险最低
            CyclePhase.EXPANSION: 0.4,   # 扩张期风险中等
            CyclePhase.PEAK: 0.8,        # 繁荣期风险较高
            CyclePhase.CONTRACTION: 0.9  # 收缩期风险最高
        }
        
        base_risk = phase_risk.get(current_phase, 0.5)
        
        # 根据各维度得分调整风险
        score_volatility = np.std(list(dimension_scores.values()))
        risk_adjustment = min(0.3, score_volatility * 0.5)
        
        total_risk = base_risk + risk_adjustment
        
        if total_risk < 0.4:
            return "低"
        elif total_risk < 0.7:
            return "中"
        else:
            return "高"
    
    def analyze_cycle(self, cycle_type: CycleType = CycleType.KITCHIN) -> CycleAnalysisResult:
        """
        分析经济周期
        
        Args:
            cycle_type: 周期类型
            
        Returns:
            CycleAnalysisResult: 分析结果
        """
        try:
            logger.info(f"开始分析{cycle_type.value}")
            
            # 获取所有指标数据
            logger.info("正在获取指标数据...")
            raw_data = self.collector.fetch_all_indicators()
            
            # 预处理数据
            logger.info("正在预处理数据...")
            processed_data = self._preprocess_data(raw_data)
            
            if processed_data.empty:
                raise ValueError("没有可用的数据进行分析")
            
            # 计算各维度得分
            logger.info("正在计算维度得分...")
            dimension_scores = self._calculate_dimension_scores(processed_data)
            
            # 判断当前周期阶段
            logger.info("正在判断周期阶段...")
            current_phase, confidence = self._determine_cycle_phase(dimension_scores)
            
            # 预测下一阶段概率
            next_phase_prob = self._predict_next_phase(current_phase, dimension_scores)
            
            # 识别关键指标
            key_indicators = self._identify_key_indicators(processed_data, dimension_scores)
            
            # 计算历史位置
            total_score = sum(
                score * self.dimension_weights.get(IndicatorDimension(dim), 0.2)
                for dim, score in dimension_scores.items()
            )
            historical_position = max(0, min(1, (total_score + 2) / 4))  # 标准化到0-1
            
            # 判断趋势方向
            recent_scores = list(dimension_scores.values())
            if np.mean(recent_scores) > 0.2:
                trend_direction = "上升"
            elif np.mean(recent_scores) < -0.2:
                trend_direction = "下降"
            else:
                trend_direction = "平稳"
            
            # 计算风险水平
            risk_level = self._calculate_risk_level(dimension_scores, current_phase)
            
            # 创建分析结果
            result = CycleAnalysisResult(
                cycle_type=cycle_type,
                current_phase=current_phase,
                phase_confidence=confidence,
                phase_duration=0,  # 需要历史数据计算
                next_phase_probability=next_phase_prob,
                key_indicators=key_indicators,
                analysis_date=datetime.now(),
                detailed_scores=dimension_scores,
                historical_position=historical_position,
                trend_direction=trend_direction,
                risk_level=risk_level
            )
            
            logger.info(f"周期分析完成: {current_phase.value}, 置信度: {confidence:.2f}")
            return result
            
        except Exception as e:
            logger.error(f"周期分析失败: {str(e)}")
            raise
    
    def get_cycle_summary(self) -> Dict[str, Any]:
        """
        获取所有周期类型的分析摘要
        
        Returns:
            Dict[str, Any]: 周期分析摘要
        """
        summary = {}
        
        for cycle_type in CycleType:
            try:
                result = self.analyze_cycle(cycle_type)
                summary[cycle_type.value] = {
                    'current_phase': result.current_phase.value,
                    'confidence': result.phase_confidence,
                    'risk_level': result.risk_level,
                    'trend_direction': result.trend_direction,
                    'historical_position': result.historical_position
                }
            except Exception as e:
                logger.error(f"分析{cycle_type.value}失败: {str(e)}")
                summary[cycle_type.value] = {
                    'current_phase': '未知',
                    'confidence': 0.0,
                    'risk_level': '未知',
                    'trend_direction': '未知',
                    'historical_position': 0.5
                }
        
        return summary 