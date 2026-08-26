"""
AKShare数据采集器

负责从AKShare接口采集各类经济指标数据。
"""

import asyncio
import time
import inspect
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta
import pandas as pd
import akshare as ak
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

try:
    from ..config.settings import settings
    from ..config.indicators_config import indicators_config, IndicatorConfig
except ImportError:
    # 当直接运行时的导入方式
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent))
    from config.settings import settings
    from config.indicators_config import indicators_config, IndicatorConfig


class AKShareCollector:
    """AKShare数据采集器"""
    
    def __init__(self):
        self.timeout = settings.AKSHARE_TIMEOUT
        self.request_delay = settings.REQUEST_DELAY
        self.max_concurrent = settings.MAX_CONCURRENT_REQUESTS
        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        
    def _get_function_parameters(self, function_name: str) -> List[str]:
        """获取AKShare函数支持的参数列表"""
        try:
            if not hasattr(ak, function_name):
                return []
            
            func = getattr(ak, function_name)
            sig = inspect.signature(func)
            return list(sig.parameters.keys())
        except Exception as e:
            logger.warning(f"无法获取函数 {function_name} 的参数列表: {str(e)}")
            return []
    
    def _filter_parameters(self, function_name: str, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """过滤掉函数不支持的参数"""
        supported_params = self._get_function_parameters(function_name)
        
        if not supported_params:
            # 如果无法获取参数列表，只保留基本参数
            basic_params = ['symbol', 'period', 'indicator']
            filtered_kwargs = {k: v for k, v in kwargs.items() if k in basic_params}
        else:
            # 只保留函数支持的参数
            filtered_kwargs = {k: v for k, v in kwargs.items() if k in supported_params}
        
        # 记录被过滤掉的参数
        filtered_out = set(kwargs.keys()) - set(filtered_kwargs.keys())
        if filtered_out:
            logger.debug(f"函数 {function_name} 不支持参数: {filtered_out}")
        
        return filtered_kwargs
        
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    def _fetch_data(self, function_name: str, **kwargs) -> pd.DataFrame:
        """
        获取单个指标数据
        
        Args:
            function_name: AKShare函数名
            **kwargs: 函数参数
            
        Returns:
            pd.DataFrame: 数据
        """
        try:
            # 获取AKShare函数
            if not hasattr(ak, function_name):
                raise ValueError(f"AKShare中不存在函数: {function_name}")
            
            func = getattr(ak, function_name)
            
            # 过滤不支持的参数
            filtered_kwargs = self._filter_parameters(function_name, kwargs)
            
            # 调用函数获取数据
            logger.info(f"正在获取数据: {function_name}({filtered_kwargs})")
            data = func(**filtered_kwargs)
            
            if data is None or data.empty:
                logger.warning(f"获取到空数据: {function_name}")
                return pd.DataFrame()
            
            # 添加数据源信息
            data['data_source'] = 'akshare'
            data['function_name'] = function_name
            data['fetch_time'] = datetime.now()
            
            logger.info(f"成功获取数据: {function_name}, 行数: {len(data)}")
            return data
            
        except Exception as e:
            logger.error(f"获取数据失败: {function_name}, 错误: {str(e)}")
            raise
    
    async def _fetch_data_async(self, function_name: str, **kwargs) -> pd.DataFrame:
        """异步获取数据"""
        async with self._semaphore:
            # 在线程池中执行同步函数
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, self._fetch_data, function_name, **kwargs
            )
            
            # 添加请求延迟
            await asyncio.sleep(self.request_delay)
            return result
    
    def fetch_indicator_data(
        self, 
        indicator_name: str, 
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        获取单个指标数据
        
        Args:
            indicator_name: 指标名称
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            
        Returns:
            pd.DataFrame: 指标数据
        """
        try:
            # 获取指标配置
            indicator_config = indicators_config.get_indicator(indicator_name)
            
            # 准备函数参数
            kwargs = indicator_config.parameters.copy()
            
            # 尝试添加日期参数（如果函数支持）
            if start_date or end_date:
                date_params = {}
                if start_date:
                    date_params.update({
                        'start_date': start_date,
                        'start_time': start_date,
                        'begin_date': start_date
                    })
                
                if end_date:
                    date_params.update({
                        'end_date': end_date,
                        'end_time': end_date,
                        'finish_date': end_date
                    })
                
                # 合并日期参数
                kwargs.update(date_params)
            
            # 获取数据
            data = self._fetch_data(indicator_config.akshare_function, **kwargs)
            
            if not data.empty:
                # 添加指标元信息
                data['indicator_name'] = indicator_name
                data['dimension'] = indicator_config.dimension.value
                data['indicator_type'] = indicator_config.indicator_type.value
                data['weight'] = indicator_config.weight
            
            return data
            
        except Exception as e:
            logger.error(f"获取指标数据失败: {indicator_name}, 错误: {str(e)}")
            return pd.DataFrame()
    
    async def fetch_multiple_indicators(
        self,
        indicator_names: List[str],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        并发获取多个指标数据
        
        Args:
            indicator_names: 指标名称列表
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            Dict[str, pd.DataFrame]: 指标数据字典
        """
        tasks = []
        
        for indicator_name in indicator_names:
            try:
                # 获取指标配置
                indicator_config = indicators_config.get_indicator(indicator_name)
                
                # 准备函数参数
                kwargs = indicator_config.parameters.copy()
                
                # 尝试添加日期参数
                if start_date or end_date:
                    date_params = {}
                    if start_date:
                        date_params.update({
                            'start_date': start_date,
                            'start_time': start_date,
                            'begin_date': start_date
                        })
                    
                    if end_date:
                        date_params.update({
                            'end_date': end_date,
                            'end_time': end_date,
                            'finish_date': end_date
                        })
                    
                    kwargs.update(date_params)
                
                # 创建异步任务
                task = self._fetch_data_async(
                    indicator_config.akshare_function, **kwargs
                )
                tasks.append((indicator_name, task))
                
            except Exception as e:
                logger.error(f"创建任务失败: {indicator_name}, 错误: {str(e)}")
        
        # 执行所有任务
        results = {}
        completed_tasks = await asyncio.gather(
            *[task for _, task in tasks], 
            return_exceptions=True
        )
        
        # 处理结果
        for (indicator_name, _), result in zip(tasks, completed_tasks):
            if isinstance(result, Exception):
                logger.error(f"获取数据失败: {indicator_name}, 错误: {str(result)}")
                results[indicator_name] = pd.DataFrame()
            else:
                if not result.empty:
                    # 添加指标元信息
                    indicator_config = indicators_config.get_indicator(indicator_name)
                    result['indicator_name'] = indicator_name
                    result['dimension'] = indicator_config.dimension.value
                    result['indicator_type'] = indicator_config.indicator_type.value
                    result['weight'] = indicator_config.weight
                
                results[indicator_name] = result
        
        return results
    
    def fetch_all_indicators(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        获取所有配置的指标数据
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            Dict[str, pd.DataFrame]: 所有指标数据
        """
        indicator_names = indicators_config.get_indicator_names()
        
        # 使用异步方法获取数据
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            results = loop.run_until_complete(
                self.fetch_multiple_indicators(
                    indicator_names, start_date, end_date
                )
            )
            return results
        finally:
            loop.close()
    
    def get_latest_data(self, indicator_name: str) -> pd.DataFrame:
        """
        获取指标的最新数据（不传递日期参数）
        
        Args:
            indicator_name: 指标名称
            
        Returns:
            pd.DataFrame: 最新数据
        """
        return self.fetch_indicator_data(indicator_name)
    
    def get_historical_data(
        self,
        indicator_name: str,
        years: int = 20
    ) -> pd.DataFrame:
        """
        获取指标的历史数据
        
        Args:
            indicator_name: 指标名称
            years: 历史年数
            
        Returns:
            pd.DataFrame: 历史数据
        """
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=years*365)).strftime('%Y-%m-%d')
        
        return self.fetch_indicator_data(indicator_name, start_date, end_date)
    
    def validate_data_availability(self) -> Dict[str, bool]:
        """
        验证所有指标的数据可用性（不传递日期参数）
        
        Returns:
            Dict[str, bool]: 指标可用性状态
        """
        availability = {}
        
        for indicator_name in indicators_config.get_indicator_names():
            try:
                # 尝试获取最新数据（不传递日期参数）
                data = self.get_latest_data(indicator_name)
                availability[indicator_name] = not data.empty
                
                if data.empty:
                    logger.warning(f"指标数据不可用: {indicator_name}")
                else:
                    logger.info(f"指标数据可用: {indicator_name}, 最新数据行数: {len(data)}")
                    
            except Exception as e:
                logger.error(f"验证指标失败: {indicator_name}, 错误: {str(e)}")
                availability[indicator_name] = False
        
        return availability
    
    def get_data_summary(self) -> pd.DataFrame:
        """
        获取所有指标的数据摘要
        
        Returns:
            pd.DataFrame: 数据摘要
        """
        summary_data = []
        
        for indicator_name in indicators_config.get_indicator_names():
            try:
                indicator_config = indicators_config.get_indicator(indicator_name)
                
                # 尝试获取最新数据
                data = self.get_latest_data(indicator_name)
                
                summary_data.append({
                    'indicator_name': indicator_name,
                    'dimension': indicator_config.dimension.value,
                    'indicator_type': indicator_config.indicator_type.value,
                    'weight': indicator_config.weight,
                    'frequency': indicator_config.frequency,
                    'akshare_function': indicator_config.akshare_function,
                    'data_available': not data.empty,
                    'latest_data_count': len(data) if not data.empty else 0,
                    'description': indicator_config.description
                })
                
            except Exception as e:
                logger.error(f"获取指标摘要失败: {indicator_name}, 错误: {str(e)}")
                summary_data.append({
                    'indicator_name': indicator_name,
                    'dimension': 'Unknown',
                    'indicator_type': 'Unknown',
                    'weight': 0,
                    'frequency': 'Unknown',
                    'akshare_function': 'Unknown',
                    'data_available': False,
                    'latest_data_count': 0,
                    'description': 'Error'
                })
        
        return pd.DataFrame(summary_data) 