"""
周期滤波器

实现各种周期滤波方法，包括HP滤波、带通滤波、高斯滤波等。
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Union
from scipy import signal
from scipy.signal import butter, filtfilt, hilbert
from statsmodels.tsa.filters.hp_filter import hpfilter
from statsmodels.tsa.seasonal import seasonal_decompose
from loguru import logger

from ..config.cycles_config import cycles_config, CycleType, CycleConfig


class CycleFilter:
    """周期滤波器类"""
    
    def __init__(self):
        self.cycles_config = cycles_config
        
    def hp_filter(
        self, 
        data: pd.Series, 
        lambda_param: float = 129600,
        two_sided: bool = True
    ) -> Tuple[pd.Series, pd.Series]:
        """
        Hodrick-Prescott滤波
        
        Args:
            data: 时间序列数据
            lambda_param: 平滑参数
            two_sided: 是否使用双边滤波
            
        Returns:
            Tuple[pd.Series, pd.Series]: (趋势, 周期)
        """
        try:
            # 处理缺失值
            clean_data = data.dropna()
            if len(clean_data) < 10:
                raise ValueError("数据点太少，无法进行HP滤波")
            
            # 执行HP滤波
            cycle, trend = hpfilter(clean_data, lamb=lambda_param)
            
            # 转换为Series并保持原始索引
            trend_series = pd.Series(trend, index=clean_data.index, name=f"{data.name}_trend")
            cycle_series = pd.Series(cycle, index=clean_data.index, name=f"{data.name}_cycle")
            
            logger.info(f"HP滤波完成: {data.name}, λ={lambda_param}")
            return trend_series, cycle_series
            
        except Exception as e:
            logger.error(f"HP滤波失败: {str(e)}")
            raise
    
    def bandpass_filter(
        self,
        data: pd.Series,
        low_freq: float,
        high_freq: float,
        order: int = 4,
        filter_type: str = 'butterworth'
    ) -> pd.Series:
        """
        带通滤波器
        
        Args:
            data: 时间序列数据
            low_freq: 低频截止频率
            high_freq: 高频截止频率
            order: 滤波器阶数
            filter_type: 滤波器类型
            
        Returns:
            pd.Series: 滤波后的数据
        """
        try:
            # 处理缺失值
            clean_data = data.dropna()
            if len(clean_data) < order * 6:
                raise ValueError(f"数据点太少，无法进行{order}阶滤波")
            
            # 设计带通滤波器
            nyquist = 0.5  # 假设采样频率为1（月度数据）
            low = low_freq / nyquist
            high = high_freq / nyquist
            
            if filter_type == 'butterworth':
                b, a = butter(order, [low, high], btype='band')
            else:
                raise ValueError(f"不支持的滤波器类型: {filter_type}")
            
            # 应用滤波器
            filtered_data = filtfilt(b, a, clean_data.values)
            
            # 转换为Series
            result = pd.Series(
                filtered_data, 
                index=clean_data.index, 
                name=f"{data.name}_bandpass"
            )
            
            logger.info(f"带通滤波完成: {data.name}, 频率范围: [{low_freq:.4f}, {high_freq:.4f}]")
            return result
            
        except Exception as e:
            logger.error(f"带通滤波失败: {str(e)}")
            raise
    
    def gaussian_filter(
        self,
        data: pd.Series,
        sigma: float = 2.0
    ) -> pd.Series:
        """
        高斯滤波
        
        Args:
            data: 时间序列数据
            sigma: 高斯核标准差
            
        Returns:
            pd.Series: 滤波后的数据
        """
        try:
            from scipy.ndimage import gaussian_filter1d
            
            # 处理缺失值
            clean_data = data.dropna()
            if len(clean_data) < 10:
                raise ValueError("数据点太少，无法进行高斯滤波")
            
            # 应用高斯滤波
            filtered_data = gaussian_filter1d(clean_data.values, sigma=sigma)
            
            # 转换为Series
            result = pd.Series(
                filtered_data,
                index=clean_data.index,
                name=f"{data.name}_gaussian"
            )
            
            logger.info(f"高斯滤波完成: {data.name}, σ={sigma}")
            return result
            
        except Exception as e:
            logger.error(f"高斯滤波失败: {str(e)}")
            raise
    
    def seasonal_decompose_filter(
        self,
        data: pd.Series,
        period: int = 12,
        model: str = 'additive'
    ) -> Dict[str, pd.Series]:
        """
        季节性分解
        
        Args:
            data: 时间序列数据
            period: 季节周期
            model: 分解模型 ('additive' 或 'multiplicative')
            
        Returns:
            Dict[str, pd.Series]: 分解结果
        """
        try:
            # 处理缺失值
            clean_data = data.dropna()
            if len(clean_data) < period * 2:
                raise ValueError(f"数据点太少，无法进行周期为{period}的季节性分解")
            
            # 执行季节性分解
            decomposition = seasonal_decompose(
                clean_data, 
                model=model, 
                period=period,
                extrapolate_trend='freq'
            )
            
            # 提取各组件
            result = {
                'trend': decomposition.trend,
                'seasonal': decomposition.seasonal,
                'residual': decomposition.resid,
                'observed': decomposition.observed
            }
            
            # 重命名Series
            for key, series in result.items():
                series.name = f"{data.name}_{key}"
            
            logger.info(f"季节性分解完成: {data.name}, 周期={period}, 模型={model}")
            return result
            
        except Exception as e:
            logger.error(f"季节性分解失败: {str(e)}")
            raise
    
    def extract_cycle_component(
        self,
        data: pd.Series,
        cycle_type: CycleType
    ) -> pd.Series:
        """
        提取特定周期成分
        
        Args:
            data: 时间序列数据
            cycle_type: 周期类型
            
        Returns:
            pd.Series: 周期成分
        """
        try:
            # 获取周期配置
            cycle_config = self.cycles_config.get_cycle(cycle_type)
            filter_params = self.cycles_config.get_filter_parameters(cycle_type)
            
            logger.info(f"提取{cycle_config.name}成分: {data.name}")
            
            # 根据检测方法选择滤波器
            if cycle_config.detection_method == "hp_filter":
                trend, cycle = self.hp_filter(
                    data, 
                    lambda_param=filter_params.get('lambda', 129600),
                    two_sided=filter_params.get('two_sided', True)
                )
                return cycle
                
            elif cycle_config.detection_method == "bandpass_filter":
                return self.bandpass_filter(
                    data,
                    low_freq=filter_params['low_freq'],
                    high_freq=filter_params['high_freq'],
                    order=filter_params.get('order', 4),
                    filter_type=filter_params.get('filter_type', 'butterworth')
                )
                
            elif cycle_config.detection_method == "seasonal_decompose":
                decomp_result = self.seasonal_decompose_filter(
                    data,
                    period=cycle_config.length_months,
                    model=filter_params.get('model', 'additive')
                )
                return decomp_result['seasonal']
                
            else:
                raise ValueError(f"不支持的检测方法: {cycle_config.detection_method}")
                
        except Exception as e:
            logger.error(f"提取周期成分失败: {str(e)}")
            raise
    
    def extract_all_cycles(
        self,
        data: pd.Series
    ) -> Dict[str, pd.Series]:
        """
        提取所有周期成分
        
        Args:
            data: 时间序列数据
            
        Returns:
            Dict[str, pd.Series]: 所有周期成分
        """
        results = {}
        
        for cycle_type in CycleType:
            try:
                cycle_component = self.extract_cycle_component(data, cycle_type)
                cycle_config = self.cycles_config.get_cycle(cycle_type)
                results[cycle_config.name] = cycle_component
                
            except Exception as e:
                logger.error(f"提取{cycle_type.value}失败: {str(e)}")
                # 创建空的Series作为占位符
                results[cycle_type.value] = pd.Series(
                    dtype=float, 
                    name=f"{data.name}_{cycle_type.value}"
                )
        
        return results
    
    def calculate_cycle_amplitude(self, cycle_data: pd.Series) -> float:
        """
        计算周期振幅
        
        Args:
            cycle_data: 周期数据
            
        Returns:
            float: 振幅
        """
        try:
            clean_data = cycle_data.dropna()
            if len(clean_data) == 0:
                return 0.0
            
            # 使用标准差作为振幅度量
            amplitude = clean_data.std()
            return amplitude
            
        except Exception as e:
            logger.error(f"计算周期振幅失败: {str(e)}")
            return 0.0
    
    def calculate_cycle_phase(self, cycle_data: pd.Series) -> pd.Series:
        """
        计算周期相位
        
        Args:
            cycle_data: 周期数据
            
        Returns:
            pd.Series: 相位数据
        """
        try:
            clean_data = cycle_data.dropna()
            if len(clean_data) < 10:
                return pd.Series(dtype=float)
            
            # 使用Hilbert变换计算瞬时相位
            analytic_signal = hilbert(clean_data.values)
            phase = np.angle(analytic_signal)
            
            # 转换为0-1范围
            normalized_phase = (phase + np.pi) / (2 * np.pi)
            
            result = pd.Series(
                normalized_phase,
                index=clean_data.index,
                name=f"{cycle_data.name}_phase"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"计算周期相位失败: {str(e)}")
            return pd.Series(dtype=float)
    
    def filter_multiple_series(
        self,
        data_dict: Dict[str, pd.Series],
        cycle_type: CycleType
    ) -> Dict[str, pd.Series]:
        """
        对多个时间序列进行周期滤波
        
        Args:
            data_dict: 时间序列数据字典
            cycle_type: 周期类型
            
        Returns:
            Dict[str, pd.Series]: 滤波结果
        """
        results = {}
        
        for name, data in data_dict.items():
            try:
                cycle_component = self.extract_cycle_component(data, cycle_type)
                results[name] = cycle_component
                
            except Exception as e:
                logger.error(f"滤波失败 {name}: {str(e)}")
                results[name] = pd.Series(dtype=float, name=f"{name}_filtered")
        
        return results
    
    def get_filter_summary(self, data: pd.Series) -> Dict[str, Dict[str, float]]:
        """
        获取所有周期的滤波摘要
        
        Args:
            data: 时间序列数据
            
        Returns:
            Dict[str, Dict[str, float]]: 滤波摘要
        """
        summary = {}
        
        # 提取所有周期成分
        all_cycles = self.extract_all_cycles(data)
        
        for cycle_name, cycle_data in all_cycles.items():
            if not cycle_data.empty:
                amplitude = self.calculate_cycle_amplitude(cycle_data)
                phase_data = self.calculate_cycle_phase(cycle_data)
                current_phase = phase_data.iloc[-1] if not phase_data.empty else 0.0
                
                summary[cycle_name] = {
                    'amplitude': amplitude,
                    'current_phase': current_phase,
                    'data_points': len(cycle_data.dropna()),
                    'variance': cycle_data.var() if len(cycle_data.dropna()) > 1 else 0.0
                }
            else:
                summary[cycle_name] = {
                    'amplitude': 0.0,
                    'current_phase': 0.0,
                    'data_points': 0,
                    'variance': 0.0
                }
        
        return summary 