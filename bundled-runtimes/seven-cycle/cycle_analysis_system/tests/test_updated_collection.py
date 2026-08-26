#!/usr/bin/env python3
"""
测试更新后的数据采集功能
"""

from data_collection.akshare_collector import AKShareCollector
from config.indicators_config import indicators_config

def main():
    # 创建采集器
    collector = AKShareCollector()

    # 获取配置摘要
    summary = indicators_config.get_summary()
    print('=== 配置摘要 ===')
    for key, value in summary.items():
        print(f'{key}: {value}')

    print('\n=== 指标列表 ===')
    for name in indicators_config.get_indicator_names():
        indicator = indicators_config.get_indicator(name)
        print(f'{name}: {indicator.akshare_function} ({indicator.dimension.value})')

    print('\n=== 测试数据采集 ===')
    # 测试几个关键指标
    test_indicators = ['美元指数', '中国制造业PMI', '中国GDP年率']
    
    for indicator_name in test_indicators:
        try:
            print(f'\n正在测试: {indicator_name}')
            data = collector.fetch_indicator_data(indicator_name)
            if not data.empty:
                print(f'✓ 成功获取数据，行数: {len(data)}')
                print(f'  列名: {list(data.columns)}')
                if len(data) > 0:
                    print(f'  数据样例: {data.head(2).to_dict()}')
            else:
                print(f'✗ 获取到空数据')
        except Exception as e:
            print(f'✗ 获取失败: {str(e)}')

    print('\n=== 验证数据可用性 ===')
    availability = collector.validate_data_availability()
    
    available_count = sum(availability.values())
    total_count = len(availability)
    
    print(f'数据可用性统计: {available_count}/{total_count} ({available_count/total_count*100:.1f}%)')
    
    print('\n可用指标:')
    for name, available in availability.items():
        status = '✓' if available else '✗'
        print(f'  {status} {name}')

if __name__ == "__main__":
    main() 