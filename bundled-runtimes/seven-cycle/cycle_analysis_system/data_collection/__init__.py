"""
数据采集模块

提供从AKShare等数据源采集全球经济指标数据的功能。
"""

from .akshare_collector import AKShareCollector

__all__ = ['AKShareCollector'] 