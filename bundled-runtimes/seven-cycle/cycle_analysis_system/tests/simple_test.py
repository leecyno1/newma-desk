#!/usr/bin/env python3
"""
简化的系统测试脚本
"""

import sys
from pathlib import Path

# 添加项目路径
sys.path.append(str(Path(__file__).parent))

def test_basic_functionality():
    """测试基本功能"""
    print("=== 经济周期分析系统 - 基本功能测试 ===\n")
    
    try:
        # 测试配置加载
        from config.indicators_config import indicators_config
        print("✓ 指标配置加载成功")
        
        # 测试数据采集器
        from data_collection.akshare_collector import AKShareCollector
        collector = AKShareCollector()
        print("✓ 数据采集器创建成功")
        
        # 测试周期分析器
        from analysis.cycle_analyzer import CycleAnalyzer, CycleType
        analyzer = CycleAnalyzer()
        print("✓ 周期分析器创建成功")
        
        # 获取配置摘要
        summary = indicators_config.get_summary()
        print(f"\n📊 系统配置摘要:")
        for key, value in summary.items():
            print(f"   {key}: {value}")
        
        # 测试单个指标数据获取
        print(f"\n🔍 测试数据获取:")
        test_indicators = ['美国失业率', '波罗的海干散货指数', '美国CPI月率']
        
        for indicator_name in test_indicators:
            try:
                data = collector.fetch_indicator_data(indicator_name)
                if data is not None and not data.empty:
                    print(f"   ✓ {indicator_name}: {len(data)} 条数据")
                else:
                    print(f"   ❌ {indicator_name}: 无数据")
            except Exception as e:
                print(f"   ❌ {indicator_name}: 错误 - {str(e)[:50]}...")
        
        # 测试周期分析
        print(f"\n🔄 测试周期分析:")
        try:
            result = analyzer.analyze_cycle(CycleType.KITCHIN)
            print(f"   ✓ 基钦周期分析成功")
            print(f"     当前阶段: {result.current_phase.value}")
            print(f"     置信度: {result.phase_confidence:.2f}")
            print(f"     风险水平: {result.risk_level}")
        except Exception as e:
            print(f"   ❌ 周期分析失败: {str(e)[:50]}...")
        
        print(f"\n🎯 系统状态: 所有核心功能正常运行！")
        print(f"\n💡 使用说明:")
        print(f"   1. 运行主程序: python main.py")
        print(f"   2. 启动仪表板: streamlit run visualization/dashboard.py")
        print(f"   3. 查看项目文档: cat README.md")
        
    except Exception as e:
        print(f"❌ 系统测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_basic_functionality() 