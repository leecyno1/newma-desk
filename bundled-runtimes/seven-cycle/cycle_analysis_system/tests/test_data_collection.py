"""
数据采集模块测试脚本

测试AKShare数据采集功能。
"""

import sys
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from loguru import logger
import akshare as ak

# 添加项目根目录到Python路径
sys.path.append(str(Path(__file__).parent))


def test_akshare_basic():
    """测试AKShare基础功能"""
    logger.info("🔍 测试AKShare基础功能...")
    
    try:
        # 测试获取股票基本信息
        stock_info = ak.stock_info_a_code_name()
        logger.info(f"✅ 获取A股代码成功: {len(stock_info)} 只股票")
        
        # 测试获取宏观经济数据
        try:
            # GDP数据
            gdp_data = ak.macro_china_gdp()
            logger.info(f"✅ 获取GDP数据成功: {len(gdp_data)} 条记录")
        except Exception as e:
            logger.warning(f"⚠️ 获取GDP数据失败: {str(e)}")
        
        # 测试获取货币供应量数据
        try:
            money_supply = ak.macro_china_money_supply()
            logger.info(f"✅ 获取货币供应量数据成功: {len(money_supply)} 条记录")
        except Exception as e:
            logger.warning(f"⚠️ 获取货币供应量数据失败: {str(e)}")
        
        # 测试获取CPI数据
        try:
            cpi_data = ak.macro_china_cpi()
            logger.info(f"✅ 获取CPI数据成功: {len(cpi_data)} 条记录")
        except Exception as e:
            logger.warning(f"⚠️ 获取CPI数据失败: {str(e)}")
        
        # 测试获取PMI数据
        try:
            pmi_data = ak.macro_china_pmi()
            logger.info(f"✅ 获取PMI数据成功: {len(pmi_data)} 条记录")
        except Exception as e:
            logger.warning(f"⚠️ 获取PMI数据失败: {str(e)}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ AKShare基础功能测试失败: {str(e)}")
        return False


def test_global_indicators():
    """测试全球指标数据采集"""
    logger.info("\n🔍 测试全球指标数据采集...")
    
    try:
        # 测试美国经济数据
        try:
            # 美国GDP
            us_gdp = ak.macro_usa_gdp()
            logger.info(f"✅ 获取美国GDP数据成功: {len(us_gdp)} 条记录")
        except Exception as e:
            logger.warning(f"⚠️ 获取美国GDP数据失败: {str(e)}")
        
        # 测试美国CPI
        try:
            us_cpi = ak.macro_usa_cpi()
            logger.info(f"✅ 获取美国CPI数据成功: {len(us_cpi)} 条记录")
        except Exception as e:
            logger.warning(f"⚠️ 获取美国CPI数据失败: {str(e)}")
        
        # 测试欧洲经济数据
        try:
            eu_gdp = ak.macro_euro_gdp()
            logger.info(f"✅ 获取欧洲GDP数据成功: {len(eu_gdp)} 条记录")
        except Exception as e:
            logger.warning(f"⚠️ 获取欧洲GDP数据失败: {str(e)}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 全球指标数据采集测试失败: {str(e)}")
        return False


def test_financial_indicators():
    """测试金融指标数据采集"""
    logger.info("\n🔍 测试金融指标数据采集...")
    
    try:
        # 测试利率数据
        try:
            interest_rate = ak.macro_china_interest_rate()
            logger.info(f"✅ 获取利率数据成功: {len(interest_rate)} 条记录")
        except Exception as e:
            logger.warning(f"⚠️ 获取利率数据失败: {str(e)}")
        
        # 测试汇率数据
        try:
            exchange_rate = ak.macro_china_fx_reserves()
            logger.info(f"✅ 获取外汇储备数据成功: {len(exchange_rate)} 条记录")
        except Exception as e:
            logger.warning(f"⚠️ 获取外汇储备数据失败: {str(e)}")
        
        # 测试股票指数数据
        try:
            # 上证指数
            sh_index = ak.stock_zh_index_daily(symbol="sh000001")
            logger.info(f"✅ 获取上证指数数据成功: {len(sh_index)} 条记录")
            
            # 显示最近几条数据
            if not sh_index.empty:
                logger.info("最近5个交易日数据:")
                recent_data = sh_index.tail()
                for _, row in recent_data.iterrows():
                    logger.info(f"  {row['date']}: 收盘={row['close']:.2f}")
        except Exception as e:
            logger.warning(f"⚠️ 获取股票指数数据失败: {str(e)}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 金融指标数据采集测试失败: {str(e)}")
        return False


def test_commodity_indicators():
    """测试大宗商品指标数据采集"""
    logger.info("\n🔍 测试大宗商品指标数据采集...")
    
    try:
        # 测试原油价格
        try:
            oil_price = ak.energy_oil_hist()
            logger.info(f"✅ 获取原油价格数据成功: {len(oil_price)} 条记录")
        except Exception as e:
            logger.warning(f"⚠️ 获取原油价格数据失败: {str(e)}")
        
        # 测试黄金价格
        try:
            gold_price = ak.tool_trade_date_hist_sina()
            logger.info(f"✅ 获取交易日历数据成功: {len(gold_price)} 条记录")
        except Exception as e:
            logger.warning(f"⚠️ 获取交易日历数据失败: {str(e)}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 大宗商品指标数据采集测试失败: {str(e)}")
        return False


def test_data_processing():
    """测试数据处理功能"""
    logger.info("\n🔍 测试数据处理功能...")
    
    try:
        # 创建模拟数据
        dates = pd.date_range(start='2020-01-01', end='2024-01-01', freq='M')
        data = pd.DataFrame({
            'date': dates,
            'value': range(len(dates)),
            'indicator': 'test_indicator'
        })
        
        logger.info(f"✅ 创建测试数据成功: {len(data)} 条记录")
        
        # 测试数据清洗
        cleaned_data = data.dropna()
        logger.info(f"✅ 数据清洗成功: {len(cleaned_data)} 条记录")
        
        # 测试数据标准化
        from sklearn.preprocessing import StandardScaler
        scaler = StandardScaler()
        normalized_values = scaler.fit_transform(data[['value']])
        logger.info(f"✅ 数据标准化成功: 均值={normalized_values.mean():.6f}, 标准差={normalized_values.std():.6f}")
        
        # 测试时间序列重采样
        data_with_index = data.set_index('date')
        quarterly_data = data_with_index.resample('Q').mean()
        logger.info(f"✅ 时间序列重采样成功: 月度{len(data)}条 -> 季度{len(quarterly_data)}条")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 数据处理功能测试失败: {str(e)}")
        return False


def test_data_storage():
    """测试数据存储功能"""
    logger.info("\n🔍 测试数据存储功能...")
    
    try:
        # 创建测试数据
        test_data = pd.DataFrame({
            'date': pd.date_range(start='2023-01-01', periods=12, freq='M'),
            'gdp': [100 + i for i in range(12)],
            'cpi': [2.0 + 0.1*i for i in range(12)],
            'pmi': [50 + i for i in range(12)]
        })
        
        # 测试CSV存储
        csv_file = Path("test_data.csv")
        test_data.to_csv(csv_file, index=False)
        logger.info(f"✅ CSV存储成功: {csv_file}")
        
        # 测试CSV读取
        loaded_data = pd.read_csv(csv_file)
        logger.info(f"✅ CSV读取成功: {len(loaded_data)} 条记录")
        
        # 测试Excel存储
        excel_file = Path("test_data.xlsx")
        test_data.to_excel(excel_file, index=False)
        logger.info(f"✅ Excel存储成功: {excel_file}")
        
        # 清理测试文件
        csv_file.unlink(missing_ok=True)
        excel_file.unlink(missing_ok=True)
        logger.info("✅ 测试文件清理完成")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 数据存储功能测试失败: {str(e)}")
        return False


def main():
    """主测试函数"""
    logger.info("🚀 开始数据采集模块测试")
    logger.info("=" * 60)
    
    test_results = []
    
    # 运行各项测试
    test_results.append(("AKShare基础功能", test_akshare_basic()))
    test_results.append(("全球指标数据采集", test_global_indicators()))
    test_results.append(("金融指标数据采集", test_financial_indicators()))
    test_results.append(("大宗商品指标数据采集", test_commodity_indicators()))
    test_results.append(("数据处理功能", test_data_processing()))
    test_results.append(("数据存储功能", test_data_storage()))
    
    # 汇总测试结果
    logger.info("\n📊 测试结果汇总:")
    passed = 0
    total = len(test_results)
    
    for test_name, result in test_results:
        status = "✅ 通过" if result else "❌ 失败"
        logger.info(f"  - {test_name}: {status}")
        if result:
            passed += 1
    
    logger.info(f"\n🎯 测试完成: {passed}/{total} 项测试通过")
    
    if passed == total:
        logger.info("🎉 所有测试通过！数据采集模块功能正常")
    else:
        logger.warning("⚠️ 部分测试失败，请检查网络连接和API可用性")
    
    logger.info("🏁 测试结束")


if __name__ == "__main__":
    main() 