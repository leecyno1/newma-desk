#!/usr/bin/env python3
"""
测试仪表板功能

验证可视化组件是否正常工作。
"""

import sys
from pathlib import Path

# 添加项目路径
sys.path.append(str(Path(__file__).parent))

from visualization.dashboard import CycleDashboard
from analysis.cycle_analyzer import CycleAnalyzer, CycleType

def test_dashboard_components():
    """测试仪表板组件"""
    print("=== 测试仪表板组件 ===\n")
    
    try:
        # 创建仪表板实例
        dashboard = CycleDashboard()
        print("✓ 仪表板实例创建成功")
        
        # 测试分析器
        analyzer = CycleAnalyzer()
        print("✓ 分析器创建成功")
        
        # 获取测试数据
        print("\n正在获取测试数据...")
        summary = analyzer.get_cycle_summary()
        print(f"✓ 获取周期摘要成功: {len(summary)} 个周期")
        
        # 测试单一周期分析
        result = analyzer.analyze_cycle(CycleType.KITCHIN)
        print(f"✓ 基钦周期分析成功: {result.current_phase.value}")
        
        # 测试图表创建
        print("\n正在测试图表创建...")
        
        # 1. 测试概览图表
        try:
            overview_fig = dashboard.create_cycle_overview_chart(summary)
            print("✓ 概览图表创建成功")
        except Exception as e:
            print(f"✗ 概览图表创建失败: {str(e)}")
        
        # 2. 测试雷达图
        try:
            radar_fig = dashboard.create_dimension_radar_chart(result.detailed_scores)
            print("✓ 雷达图创建成功")
        except Exception as e:
            print(f"✗ 雷达图创建失败: {str(e)}")
        
        # 3. 测试转换概率图
        try:
            transition_fig = dashboard.create_phase_transition_chart(result.next_phase_probability)
            print("✓ 转换概率图创建成功")
        except Exception as e:
            print(f"✗ 转换概率图创建失败: {str(e)}")
        
        # 4. 测试风险评估图
        try:
            risk_fig = dashboard.create_risk_assessment_chart(summary)
            print("✓ 风险评估图创建成功")
        except Exception as e:
            print(f"✗ 风险评估图创建失败: {str(e)}")
        
        print("\n=== 测试完成 ===")
        print("✅ 所有核心组件测试通过！")
        print("\n💡 启动仪表板命令:")
        print("   python run_dashboard.py")
        print("   或者: streamlit run visualization/dashboard.py")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        return False

def main():
    """主函数"""
    success = test_dashboard_components()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main()) 