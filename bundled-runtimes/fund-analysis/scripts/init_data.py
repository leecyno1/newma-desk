"""
数据初始化脚本 - 从 Tushare 拉取并填充 PostgreSQL 数据库
使用方法: python scripts/init_data.py
"""
import os
import sys
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main():
    logger.info("=" * 60)
    logger.info("基金分析系统 - 数据初始化 (Tushare -> PostgreSQL)")
    logger.info("=" * 60)

    # 1. 初始化数据库表
    logger.info("\n[1/4] 初始化数据库表...")
    try:
        from database import init_database
        if init_database():
            logger.info("数据库表创建成功")
        else:
            logger.error("数据库表创建失败")
    except Exception as e:
        logger.error(f"数据库初始化异常: {e}")
        return

    # 2. 填充基金数据
    logger.info("\n[2/4] 从 Tushare 拉取基金数据...")
    try:
        from services.tushare_service import TushareDataService
        from repositories import get_fund_repo, get_fund_repo
        from services.scoring_engine import FundScoringEngine

        data_svc = TushareDataService()
        fund_repo = get_fund_repo()
        scoring_engine = FundScoringEngine()

        # 主流权益基金列表
        seed_codes = [
            ("000001.OF", "平安策略先锋混合"),
            ("110011.OF", "易方达中小盘混合"),
            ("110022.OF", "易方达消费行业股票"),
            ("161725.OF", "招商中证白酒指数(LOF)"),
            ("163402.OF", "兴全趋势投资混合(LOF)"),
            ("163406.OF", "兴全合润混合(LOF)"),
            ("260101.OF", "景顺长城新兴成长混合"),
            ("270008.OF", "广发核心精选混合"),
            ("320013.OF", "国泰纳斯达克100ETF联接"),
            ("340006.OF", "兴全商业模式优选混合"),
            ("519697.OF", "万家行业优选混合(LOF)"),
            ("540006.OF", "汇添富大盘核心资产混合"),
            ("000961.OF", "天弘沪深300ETF联接A"),
            ("001717.OF", "工银文体产业股票A"),
            ("002407.OF", "工银前沿医疗股票A"),
            ("003096.OF", "中欧医疗健康混合A"),
            ("005827.OF", "易方达蓝筹精选混合"),
            ("006328.OF", "中泰星盈灵活配置混合A"),
            ("007994.OF", "华夏消费升级灵活配置"),
            ("008086.OF", "华夏5GETF联接A"),
            ("008303.OF", "富国创新科技混合"),
            ("009714.OF", "易方达信息行业精选股票"),
            ("010326.OF", "汇添富消费升级混合"),
            ("011612.OF", "富国质量成长6个月混合"),
            ("012363.OF", "广发医疗保健股票A"),
            ("013203.OF", "中欧创新成长混合"),
            ("110015.OF", "易方达行业领先企业混合"),
            ("260108.OF", "景顺长城新兴成长混合"),
            ("270041.OF", "广发主题领先混合"),
            ("320007.OF", "国泰中小盘成长混合(LOF)"),
            ("519066.OF", "汇添富价值精选混合"),
            ("040004.OF", "华安动态灵活配置混合A"),
            ("050025.OF", "博时标普500ETF联接A"),
            ("100056.OF", "富国低碳环保混合"),
        ]

        logger.info(f"开始填充 {len(seed_codes)} 只基金...")
        seeded = 0

        for wind_code, name in seed_codes:
            try:
                info = data_svc.get_fund_info(wind_code)
                perf = data_svc.get_fund_performance(wind_code)
                risk = data_svc.get_fund_risk_metrics(wind_code)
                style = data_svc.get_fund_style(wind_code)
                score = scoring_engine.score_fund(perf, risk, style)

                fund_data = {
                    **info,
                    "performance": perf,
                    "risk_metrics": risk,
                }

                if fund_repo.upsert_fund(wind_code, fund_data):
                    fund_repo.save_score(wind_code, score)
                    seeded += 1
                    if seeded % 5 == 0:
                        logger.info(f"  已填充 {seeded}/{len(seed_codes)}...")
            except Exception as e:
                logger.error(f"  填充失败 {wind_code}: {e}")

        logger.info(f"基金数据填充完成: {seeded}/{len(seed_codes)}")
    except Exception as e:
        logger.error(f"基金数据填充异常: {e}")

    # 3. 填充基金经理数据
    logger.info("\n[3/4] 填充基金经理数据...")
    try:
        from repositories import get_manager_repo

        manager_repo = get_manager_repo()

        managers = [
            ("M001", {"name": "张坤", "company": "易方达基金管理有限公司", "experience_years": 17}),
            ("M002", {"name": "刘彦春", "company": "景顺长城基金管理有限公司", "experience_years": 15}),
            ("M003", {"name": "葛兰", "company": "中欧基金管理有限公司", "experience_years": 10}),
            ("M004", {"name": "周蔚文", "company": "中欧基金管理有限公司", "experience_years": 22}),
            ("M005", {"name": "谢治宇", "company": "兴证全球基金管理有限公司", "experience_years": 15}),
            ("M006", {"name": "董承菲", "company": "兴证全球基金管理有限公司", "experience_years": 18}),
            ("M007", {"name": "刘格菘", "company": "广发基金管理有限公司", "experience_years": 14}),
            ("M008", {"name": "胡昕炜", "company": "汇添富基金管理有限公司", "experience_years": 12}),
            ("M009", {"name": "赵蓓", "company": "工银瑞信基金管理有限公司", "experience_years": 11}),
            ("M010", {"name": "萧楠", "company": "易方达基金管理有限公司", "experience_years": 14}),
        ]

        for mid, data in managers:
            manager_repo.upsert_manager(mid, data)

        logger.info(f"基金经理数据填充完成: {len(managers)}")
    except Exception as e:
        logger.error(f"基金经理数据填充异常: {e}")

    # 4. 验证数据
    logger.info("\n[4/4] 验证数据...")
    try:
        from repositories import get_fund_repo, get_manager_repo
        fund_repo = get_fund_repo()
        manager_repo = get_manager_repo()

        funds_result = fund_repo.list_funds(page=1, page_size=5)
        managers_result = manager_repo.list_managers(page=1, page_size=5)

        logger.info(f"  数据库中的基金数量: {funds_result.get('total', 0)}")
        logger.info(f"  数据库中的经理数量: {managers_result.get('total', 0)}")
        logger.info(f"  前5只基金: {[f['wind_code'] for f in funds_result.get('funds', [])]}")
    except Exception as e:
        logger.warning(f"数据验证异常: {e}")

    logger.info("\n" + "=" * 60)
    logger.info("初始化完成!")
    logger.info("=" * 60)
    logger.info("\n下一步:")
    logger.info("  1. 启动后端: cd backend && python main.py")
    logger.info("  2. 启动正式前端: 在项目根目录运行 npm run dev")
    logger.info("  3. 访问: http://localhost:3000")


if __name__ == "__main__":
    main()
