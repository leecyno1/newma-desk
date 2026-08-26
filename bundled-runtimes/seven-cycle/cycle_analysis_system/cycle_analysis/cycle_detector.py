"""
周期检测器

实现周期识别、峰谷检测、转折点识别等功能。
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Union
from scipy.signal import find_peaks, argrelextrema
from scipy.stats import zscore
from sklearn.cluster import KMeans
from loguru import logger

from ..config.cycles_config import cycles_config, CycleType, CyclePhase
from .cycle_filter import CycleFilter


class CycleDetector:
    """周期检测器类"""
    
    def __init__(self):
        self.cycles_config = cycles_config
        self.filter = CycleFilter()
        
    def find_peaks_valleys(
        self,
        data: pd.Series,
        prominence: float = 0.1,
        distance: int = 6
    ) -> Tuple[List[int], List[int]]:
        """
        寻找峰值和谷值
        
        Args:
            data: 时间序列数据
            prominence: 峰值显著性阈值
            distance: 峰值间最小距离
            
        Returns:
            Tuple[List[int], List[int]]: (峰值索引, 谷值索引)
        """
        try:
            clean_data = data.dropna()
            if len(clean_data) < 10:
                return [], []
            
            # 标准化数据
            normalized_data = zscore(clean_data.values)
            
            # 寻找峰值
            peaks, _ = find_peaks(
                normalized_data,
                prominence=prominence,
                distance=distance
            )
            
            # 寻找谷值（负峰值）
            valleys, _ = find_peaks(
                -normalized_data,
                prominence=prominence,
                distance=distance
            )
            
            # 转换为原始索引
            peak_indices = [clean_data.index[i] for i in peaks]
            valley_indices = [clean_data.index[i] for i in valleys]
            
            logger.info(f"检测到 {len(peak_indices)} 个峰值, {len(valley_indices)} 个谷值")
            return peak_indices, valley_indices
            
        except Exception as e:
            logger.error(f"峰谷检测失败: {str(e)}")
            return [], []
    
    def detect_turning_points(
        self,
        data: pd.Series,
        window: int = 5,
        threshold: float = 0.05
    ) -> List[Tuple[int, str]]:
        """
        检测转折点
        
        Args:
            data: 时间序列数据
            window: 滑动窗口大小
            threshold: 变化阈值
            
        Returns:
            List[Tuple[int, str]]: 转折点列表 (索引, 类型)
        """
        try:
            clean_data = data.dropna()
            if len(clean_data) < window * 2:
                return []
            
            turning_points = []
            
            # 计算滑动平均的斜率
            rolling_mean = clean_data.rolling(window=window, center=True).mean()
            slopes = rolling_mean.diff()
            
            # 检测斜率变化
            for i in range(window, len(slopes) - window):
                prev_slope = slopes.iloc[i-1]
                curr_slope = slopes.iloc[i]
                
                # 从上升转为下降
                if prev_slope > threshold and curr_slope < -threshold:
                    turning_points.append((clean_data.index[i], 'peak'))
                
                # 从下降转为上升
                elif prev_slope < -threshold and curr_slope > threshold:
                    turning_points.append((clean_data.index[i], 'trough'))
            
            logger.info(f"检测到 {len(turning_points)} 个转折点")
            return turning_points
            
        except Exception as e:
            logger.error(f"转折点检测失败: {str(e)}")
            return []
    
    def calculate_cycle_length(
        self,
        peaks: List[int],
        valleys: List[int]
    ) -> Dict[str, float]:
        """
        计算周期长度
        
        Args:
            peaks: 峰值索引列表
            valleys: 谷值索引列表
            
        Returns:
            Dict[str, float]: 周期长度统计
        """
        try:
            # 合并并排序所有转折点
            all_points = [(p, 'peak') for p in peaks] + [(v, 'valley') for v in valleys]
            all_points.sort(key=lambda x: x[0])
            
            if len(all_points) < 4:
                return {'mean_length': 0, 'std_length': 0, 'count': 0}
            
            # 计算完整周期长度（峰-谷-峰 或 谷-峰-谷）
            cycle_lengths = []
            
            for i in range(len(all_points) - 2):
                point1 = all_points[i]
                point2 = all_points[i + 1]
                point3 = all_points[i + 2]
                
                # 检查是否为完整周期
                if (point1[1] == point3[1] and point1[1] != point2[1]):
                    if isinstance(point1[0], pd.Timestamp) and isinstance(point3[0], pd.Timestamp):
                        # 时间索引，计算月份差
                        months_diff = (point3[0] - point1[0]).days / 30.44
                        cycle_lengths.append(months_diff)
                    else:
                        # 数值索引
                        cycle_lengths.append(point3[0] - point1[0])
            
            if not cycle_lengths:
                return {'mean_length': 0, 'std_length': 0, 'count': 0}
            
            return {
                'mean_length': np.mean(cycle_lengths),
                'std_length': np.std(cycle_lengths),
                'count': len(cycle_lengths),
                'min_length': np.min(cycle_lengths),
                'max_length': np.max(cycle_lengths)
            }
            
        except Exception as e:
            logger.error(f"计算周期长度失败: {str(e)}")
            return {'mean_length': 0, 'std_length': 0, 'count': 0}
    
    def identify_cycle_type(
        self,
        cycle_length: float,
        tolerance: float = 0.3
    ) -> Optional[CycleType]:
        """
        根据周期长度识别周期类型
        
        Args:
            cycle_length: 周期长度（月）
            tolerance: 容忍度
            
        Returns:
            Optional[CycleType]: 识别的周期类型
        """
        try:
            best_match = None
            min_distance = float('inf')
            
            for cycle_type in CycleType:
                cycle_config = self.cycles_config.get_cycle(cycle_type)
                expected_length = cycle_config.length_months
                
                # 计算相对距离
                relative_distance = abs(cycle_length - expected_length) / expected_length
                
                if relative_distance <= tolerance and relative_distance < min_distance:
                    min_distance = relative_distance
                    best_match = cycle_type
            
            if best_match:
                logger.info(f"识别周期类型: {cycle_length:.1f}个月 -> {best_match.value}")
            
            return best_match
            
        except Exception as e:
            logger.error(f"识别周期类型失败: {str(e)}")
            return None
    
    def detect_cycles_in_data(
        self,
        data: pd.Series,
        min_cycle_length: int = 6,
        max_cycle_length: int = 720
    ) -> Dict[str, Dict]:
        """
        在数据中检测所有周期
        
        Args:
            data: 时间序列数据
            min_cycle_length: 最小周期长度
            max_cycle_length: 最大周期长度
            
        Returns:
            Dict[str, Dict]: 检测结果
        """
        try:
            results = {}
            
            # 寻找峰谷
            peaks, valleys = self.find_peaks_valleys(data)
            
            if not peaks and not valleys:
                logger.warning("未检测到明显的峰谷")
                return results
            
            # 计算周期长度
            cycle_stats = self.calculate_cycle_length(peaks, valleys)
            
            if cycle_stats['count'] == 0:
                logger.warning("未检测到完整周期")
                return results
            
            # 识别主要周期类型
            main_cycle_length = cycle_stats['mean_length']
            cycle_type = self.identify_cycle_type(main_cycle_length)
            
            results['main_cycle'] = {
                'type': cycle_type.value if cycle_type else 'Unknown',
                'length': main_cycle_length,
                'statistics': cycle_stats,
                'peaks': peaks,
                'valleys': valleys
            }
            
            # 尝试识别其他周期成分
            for target_cycle in CycleType:
                try:
                    # 提取特定周期成分
                    cycle_component = self.filter.extract_cycle_component(data, target_cycle)
                    
                    if not cycle_component.empty:
                        # 在周期成分中寻找峰谷
                        comp_peaks, comp_valleys = self.find_peaks_valleys(cycle_component)
                        comp_stats = self.calculate_cycle_length(comp_peaks, comp_valleys)
                        
                        # 计算周期强度
                        amplitude = self.filter.calculate_cycle_amplitude(cycle_component)
                        phase_data = self.filter.calculate_cycle_phase(cycle_component)
                        current_phase = phase_data.iloc[-1] if not phase_data.empty else 0.0
                        
                        cycle_config = self.cycles_config.get_cycle(target_cycle)
                        results[cycle_config.name] = {
                            'type': target_cycle.value,
                            'expected_length': cycle_config.length_months,
                            'detected_length': comp_stats.get('mean_length', 0),
                            'amplitude': amplitude,
                            'current_phase': current_phase,
                            'phase_category': self.cycles_config.classify_cycle_phase(current_phase).value,
                            'peaks': comp_peaks,
                            'valleys': comp_valleys,
                            'statistics': comp_stats
                        }
                
                except Exception as e:
                    logger.error(f"分析{target_cycle.value}失败: {str(e)}")
            
            return results
            
        except Exception as e:
            logger.error(f"周期检测失败: {str(e)}")
            return {}
    
    def calculate_cycle_position(
        self,
        data: pd.Series,
        cycle_type: CycleType
    ) -> float:
        """
        计算当前在周期中的位置
        
        Args:
            data: 时间序列数据
            cycle_type: 周期类型
            
        Returns:
            float: 周期位置 (0-1)
        """
        try:
            # 提取周期成分
            cycle_component = self.filter.extract_cycle_component(data, cycle_type)
            
            if cycle_component.empty:
                return 0.0
            
            # 计算相位
            phase_data = self.filter.calculate_cycle_phase(cycle_component)
            
            if phase_data.empty:
                return 0.0
            
            # 返回最新的相位位置
            current_position = phase_data.iloc[-1]
            
            # 确保在0-1范围内
            current_position = max(0.0, min(1.0, current_position))
            
            logger.info(f"{cycle_type.value}当前位置: {current_position:.3f}")
            return current_position
            
        except Exception as e:
            logger.error(f"计算周期位置失败: {str(e)}")
            return 0.0
    
    def get_cycle_status(
        self,
        data: pd.Series
    ) -> Dict[str, Dict[str, Union[float, str]]]:
        """
        获取所有周期的当前状态
        
        Args:
            data: 时间序列数据
            
        Returns:
            Dict[str, Dict[str, Union[float, str]]]: 周期状态
        """
        status = {}
        
        for cycle_type in CycleType:
            try:
                cycle_config = self.cycles_config.get_cycle(cycle_type)
                
                # 计算周期位置
                position = self.calculate_cycle_position(data, cycle_type)
                
                # 分类周期阶段
                phase = self.cycles_config.classify_cycle_phase(position)
                
                # 提取周期成分并计算振幅
                cycle_component = self.filter.extract_cycle_component(data, cycle_type)
                amplitude = self.filter.calculate_cycle_amplitude(cycle_component)
                
                # 计算趋势方向
                if not cycle_component.empty and len(cycle_component) >= 2:
                    recent_trend = cycle_component.iloc[-1] - cycle_component.iloc[-2]
                    trend_direction = "上升" if recent_trend > 0 else "下降"
                else:
                    trend_direction = "未知"
                
                status[cycle_config.name] = {
                    'position': position,
                    'phase': phase.value,
                    'amplitude': amplitude,
                    'trend_direction': trend_direction,
                    'weight': cycle_config.weight,
                    'expected_length': cycle_config.length_months
                }
                
            except Exception as e:
                logger.error(f"获取{cycle_type.value}状态失败: {str(e)}")
                status[cycle_type.value] = {
                    'position': 0.0,
                    'phase': '未知',
                    'amplitude': 0.0,
                    'trend_direction': '未知',
                    'weight': 0.0,
                    'expected_length': 0
                }
        
        return status
    
    def calculate_composite_cycle_score(
        self,
        data: pd.Series
    ) -> Dict[str, float]:
        """
        计算复合周期得分
        
        Args:
            data: 时间序列数据
            
        Returns:
            Dict[str, float]: 复合得分
        """
        try:
            cycle_status = self.get_cycle_status(data)
            
            # 计算加权位置
            weighted_position = 0.0
            total_weight = 0.0
            
            expansion_score = 0.0
            contraction_score = 0.0
            
            for cycle_name, status in cycle_status.items():
                weight = status['weight']
                position = status['position']
                
                weighted_position += position * weight
                total_weight += weight
                
                # 根据周期阶段计算扩张/收缩得分
                if status['phase'] in ['扩张前期', '扩张后期']:
                    expansion_score += weight
                elif status['phase'] in ['收缩前期', '收缩后期']:
                    contraction_score += weight
            
            # 标准化
            if total_weight > 0:
                weighted_position /= total_weight
                expansion_score /= total_weight
                contraction_score /= total_weight
            
            return {
                'composite_position': weighted_position,
                'expansion_score': expansion_score,
                'contraction_score': contraction_score,
                'cycle_strength': expansion_score - contraction_score
            }
            
        except Exception as e:
            logger.error(f"计算复合周期得分失败: {str(e)}")
            return {
                'composite_position': 0.0,
                'expansion_score': 0.0,
                'contraction_score': 0.0,
                'cycle_strength': 0.0
            } 