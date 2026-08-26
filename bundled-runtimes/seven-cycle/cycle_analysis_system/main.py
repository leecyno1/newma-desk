"""
周期判断系统主程序

系统的主入口，提供命令行界面和基本功能演示。
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
from loguru import logger

# 添加项目根目录到Python路径
sys.path.append(str(Path(__file__).parent))

from config.settings import settings
from config.cycles_config import cycles_config, CycleType
from config.indicators_config import indicators_config, IndicatorDimension
from data_collection.akshare_collector import AKShareCollector


def setup_logging():
    """设置日志配置"""
    logger.remove()  # 移除默认处理器
    
    # 添加控制台输出
    logger.add(
        sys.stdout,
        level=settings.LOG_LEVEL,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <level>{message}</level>"
    )
    
    # 添加文件输出
    log_file = settings.LOG_DIR / "cycle_analysis.log"
    logger.add(
        log_file,
        level=settings.LOG_LEVEL,
        rotation=settings.LOG_ROTATION,
        retention=settings.LOG_RETENTION,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}"
    )


def show_system_info():
    """显示系统信息"""
    logger.info("=" * 60)
    logger.info(f"🎯 {settings.PROJECT_NAME} v{settings.VERSION}")
    logger.info("=" * 60)
    
    # 显示配置信息
    logger.info("📋 系统配置:")
    logger.info(f"  - 调试模式: {settings.DEBUG}")
    logger.info(f"  - 数据目录: {settings.DATA_DIR}")
    logger.info(f"  - 日志级别: {settings.LOG_LEVEL}")
    logger.info(f"  - 并发请求数: {settings.MAX_CONCURRENT_REQUESTS}")
    
    # 显示周期配置
    logger.info("\n🔄 周期配置:")
    for cycle_type, cycle_config in cycles_config.get_all_cycles().items():
        logger.info(f"  - {cycle_config.name}: {cycle_config.length_months}个月 (权重: {cycle_config.weight})")
    
    # 显示指标配置
    logger.info("\n📊 指标配置:")
    dimension_weights = indicators_config.get_dimension_weights()
    for dimension, weight in dimension_weights.items():
        logger.info(f"  - {dimension}: {weight:.3f}")
    
    logger.info(f"\n📈 总指标数量: {len(indicators_config.get_indicator_names())}")


def test_data_collection():
    """测试数据采集功能"""
    logger.info("\n🔍 开始测试数据采集...")
    
    collector = AKShareCollector()
    
    # 获取数据摘要
    logger.info("📋 获取指标摘要...")
    summary = collector.get_data_summary()
    
    logger.info(f"📊 指标摘要:")
    logger.info(f"  - 总指标数: {len(summary)}")
    logger.info(f"  - 可用指标数: {summary['data_available'].sum()}")
    logger.info(f"  - 不可用指标数: {(~summary['data_available']).sum()}")
    
    # 显示各维度指标数量
    dimension_counts = summary.groupby('dimension').size()
    logger.info(f"\n📈 各维度指标数量:")
    for dimension, count in dimension_counts.items():
        logger.info(f"  - {dimension}: {count}")
    
    # 测试获取单个指标数据
    logger.info("\n🧪 测试获取单个指标数据...")
    test_indicators = ["制造业PMI", "M2货币供应量", "美元指数"]
    
    for indicator_name in test_indicators:
        try:
            logger.info(f"正在测试: {indicator_name}")
            data = collector.get_latest_data(indicator_name)
            
            if not data.empty:
                logger.info(f"✅ {indicator_name}: 成功获取 {len(data)} 条数据")
                logger.info(f"   数据列: {list(data.columns)}")
            else:
                logger.warning(f"⚠️ {indicator_name}: 未获取到数据")
                
        except Exception as e:
            logger.error(f"❌ {indicator_name}: 获取失败 - {str(e)}")
    
    return summary


def show_cycle_analysis_demo():
    """演示周期分析功能"""
    logger.info("\n🔄 周期分析演示...")
    
    # 显示周期配置详情
    for cycle_type in CycleType:
        cycle_config = cycles_config.get_cycle(cycle_type)
        filter_params = cycles_config.get_filter_parameters(cycle_type)
        
        logger.info(f"\n📊 {cycle_config.name}:")
        logger.info(f"  - 周期长度: {cycle_config.length_months} 个月")
        logger.info(f"  - 范围: {cycle_config.min_length}-{cycle_config.max_length} 个月")
        logger.info(f"  - 权重: {cycle_config.weight}")
        logger.info(f"  - 检测方法: {cycle_config.detection_method}")
        logger.info(f"  - 滤波类型: {cycle_config.filter_type}")
        logger.info(f"  - 描述: {cycle_config.description}")
    
    # 演示周期阶段分类
    logger.info("\n🎯 周期阶段分类演示:")
    test_positions = [0.1, 0.3, 0.6, 0.8]
    
    for position in test_positions:
        phase = cycles_config.classify_cycle_phase(position)
        logger.info(f"  - 位置 {position:.1f}: {phase.value}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="周期判断系统")
    parser.add_argument(
        "--mode", 
        choices=["info", "test", "demo", "collect"],
        default="info",
        help="运行模式"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="启用调试模式"
    )
    
    args = parser.parse_args()
    
    # 设置调试模式
    if args.debug:
        settings.DEBUG = True
        settings.LOG_LEVEL = "DEBUG"
    
    # 设置日志
    setup_logging()
    
    try:
        if args.mode == "info":
            show_system_info()
            
        elif args.mode == "test":
            show_system_info()
            test_data_collection()
            
        elif args.mode == "demo":
            show_system_info()
            show_cycle_analysis_demo()
            
        elif args.mode == "collect":
            show_system_info()
            summary = test_data_collection()
            
            # 保存摘要到文件
            output_file = settings.DATA_DIR / f"indicators_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            summary.to_csv(output_file, index=False, encoding='utf-8-sig')
            logger.info(f"📁 摘要已保存到: {output_file}")
            
    except KeyboardInterrupt:
        logger.info("\n👋 程序被用户中断")
    except Exception as e:
        logger.error(f"❌ 程序执行出错: {str(e)}")
        if settings.DEBUG:
            raise
    finally:
        logger.info("🏁 程序结束")


if __name__ == "__main__":
    main() 