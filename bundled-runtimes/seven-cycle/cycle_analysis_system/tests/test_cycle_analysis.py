#!/usr/bin/env python3
"""
测试周期分析功能
"""

from analysis.cycle_analyzer import CycleAnalyzer, CycleType
import json
from datetime import datetime

def main():
    print("=== 经济周期分析系统测试 ===\n")
    
    # 创建分析器
    analyzer = CycleAnalyzer()
    
    # 测试基钦周期分析
    print("1. 测试基钦周期分析...")
    try:
        result = analyzer.analyze_cycle(CycleType.KITCHIN)
        
        print(f"✓ 分析完成")
        print(f"  周期类型: {result.cycle_type.value}")
        print(f"  当前阶段: {result.current_phase.value}")
        print(f"  置信度: {result.phase_confidence:.2f}")
        print(f"  风险水平: {result.risk_level}")
        print(f"  趋势方向: {result.trend_direction}")
        print(f"  历史位置: {result.historical_position:.2f}")
        print(f"  关键指标: {', '.join(result.key_indicators[:3])}")
        
        print(f"\n  各维度得分:")
        for dimension, score in result.detailed_scores.items():
            print(f"    {dimension}: {score:.3f}")
        
        print(f"\n  下一阶段概率:")
        for phase, prob in result.next_phase_probability.items():
            print(f"    {phase.value}: {prob:.1%}")
            
    except Exception as e:
        print(f"✗ 基钦周期分析失败: {str(e)}")
    
    print("\n" + "="*50 + "\n")
    
    # 测试所有周期类型摘要
    print("2. 测试所有周期类型分析摘要...")
    try:
        summary = analyzer.get_cycle_summary()
        
        print("✓ 摘要生成完成\n")
        
        for cycle_type, info in summary.items():
            print(f"【{cycle_type}】")
            print(f"  当前阶段: {info['current_phase']}")
            print(f"  置信度: {info['confidence']:.2f}")
            print(f"  风险水平: {info['risk_level']}")
            print(f"  趋势方向: {info['trend_direction']}")
            print(f"  历史位置: {info['historical_position']:.2f}")
            print()
            
    except Exception as e:
        print(f"✗ 周期摘要生成失败: {str(e)}")
    
    print("="*50)
    print("测试完成！")

if __name__ == "__main__":
    main() 