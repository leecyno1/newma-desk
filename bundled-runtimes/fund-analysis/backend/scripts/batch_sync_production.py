#!/usr/bin/env python3
"""
生产环境批量数据同步脚本
同步所有基金和基金经理的完整数据到 PostgreSQL

功能：
- 获取所有基金（~2,500+）
- 并行同步每只基金的完整数据（基本信息、净值、持仓、业绩、风险）
- Token Bucket 限流器（120次/分钟）
- 自动降速重试（触发限流时）
- 进度跟踪与断点续传
- 错误处理与重试

使用方法：
    python scripts/batch_sync_production.py --sync-funds
    python scripts/batch_sync_production.py --sync-managers
    python scripts/batch_sync_production.py --sync-all
"""

import os
import sys
import time
import json
import logging
import argparse
import threading
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Any, Optional

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.tushare_service import TushareDataService
from services.fund_classification_ingestion_service import FundClassificationIngestionService
from services.fund_nav_evidence_service import FundNavDataEnrichmentService
from repositories import get_fund_repo, get_manager_repo, get_nav_repo, get_holding_repo
from service_registry import init_services

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("batch_sync.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class TokenBucketRateLimiter:
    """Token Bucket 限流器 - 控制 API 调用速率"""

    def __init__(self, rate=120, per=60):
        """
        Args:
            rate: 令牌数量（默认 120）
            per: 时间窗口秒数（默认 60 秒）
        """
        self.rate = rate
        self.per = per
        self.tokens = float(rate)
        self.last_update = time.time()
        self.lock = threading.Lock()
        self.slowdown_factor = 1.0  # 降速因子

    def acquire(self, tokens=1):
        """获取令牌，如果不足则等待"""
        with self.lock:
            now = time.time()
            elapsed = now - self.last_update

            # 补充令牌
            self.tokens = min(
                self.rate,
                self.tokens + elapsed * (self.rate / self.per) * self.slowdown_factor
            )
            self.last_update = now

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            else:
                # 需要等待
                sleep_time = (tokens - self.tokens) * (self.per / self.rate) / self.slowdown_factor
                time.sleep(sleep_time)
                self.tokens = 0
                return True

    def slow_down(self, factor=0.5):
        """降速"""
        with self.lock:
            self.slowdown_factor *= factor
            logger.warning(f"Rate limiter slowed down to {self.slowdown_factor * 100:.1f}% speed")


class ProgressTracker:
    """进度跟踪器 - 支持断点续传"""

    def __init__(self, checkpoint_file="sync_progress.json"):
        self.checkpoint_file = checkpoint_file
        self.progress = self.load_checkpoint()
        self.lock = threading.Lock()

    def load_checkpoint(self) -> Dict:
        """加载检查点"""
        if os.path.exists(self.checkpoint_file):
            try:
                with open(self.checkpoint_file) as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load checkpoint: {e}")

        return {
            "completed": [],
            "failed": [],
            "start_time": datetime.now().isoformat(),
            "last_update": datetime.now().isoformat(),
        }

    def save_checkpoint(self):
        """保存检查点"""
        with self.lock:
            self.progress["last_update"] = datetime.now().isoformat()
            try:
                with open(self.checkpoint_file, 'w') as f:
                    json.dump(self.progress, f, indent=2)
            except Exception as e:
                logger.error(f"Failed to save checkpoint: {e}")

    def mark_completed(self, item_id: str):
        """标记为已完成"""
        with self.lock:
            if item_id not in self.progress["completed"]:
                self.progress["completed"].append(item_id)

            # 每 50 个保存一次
            if len(self.progress["completed"]) % 50 == 0:
                self.save_checkpoint()

    def mark_failed(self, item_id: str, error: str):
        """标记为失败"""
        with self.lock:
            self.progress["failed"].append({"id": item_id, "error": str(error), "time": datetime.now().isoformat()})

    def is_completed(self, item_id: str) -> bool:
        """检查是否已完成"""
        return item_id in self.progress["completed"]

    def get_stats(self) -> Dict:
        """获取统计信息"""
        with self.lock:
            return {
                "completed": len(self.progress["completed"]),
                "failed": len(self.progress["failed"]),
                "start_time": self.progress.get("start_time"),
                "last_update": self.progress.get("last_update"),
            }


class BatchSyncOrchestrator:
    """批量同步编排器"""

    def __init__(self, max_workers=8):
        self.data_svc = TushareDataService(strict_no_mock=True)
        self.fund_repo = get_fund_repo()
        self.manager_repo = get_manager_repo()
        self.nav_repo = get_nav_repo()
        self.holding_repo = get_holding_repo()

        self.rate_limiter = TokenBucketRateLimiter(rate=120, per=60)
        self.tracker = ProgressTracker()
        self.max_workers = max_workers

    def sync_single_fund(self, wind_code: str) -> bool:
        """同步单只基金的完整数据"""
        try:
            # 1. 基本信息
            self.rate_limiter.acquire()
            info = self.data_svc.get_fund_info(wind_code)
            ingestion_service = FundClassificationIngestionService()
            ingestion_plan = ingestion_service.build_plan([{**info, "wind_code": wind_code}])
            if ingestion_plan.get("groups"):
                ingestion_service.apply_plan(ingestion_plan)

            # 2. 净值序列（最近1年）
            self.rate_limiter.acquire()
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
            end_date = datetime.now().strftime("%Y-%m-%d")
            nav_data = self.data_svc.get_fund_nav(wind_code, start_date=start_date, end_date=end_date)
            nav_enrichment = FundNavDataEnrichmentService(self.data_svc).enrich(
                wind_code=wind_code,
                fund_type=info.get("type"),
                nav_series=nav_data,
                start_date=start_date,
                end_date=end_date,
            )
            nav_data = nav_enrichment["nav_series"]
            if nav_enrichment.get("nav_data_status") != "valid":
                raise ValueError(f"净值质量门禁未通过：{nav_enrichment.get('nav_validation')}")

            # 3. 业绩指标
            self.rate_limiter.acquire()
            perf = self.data_svc.get_fund_performance(wind_code)
            perf.update(nav_enrichment.get("performance_facts") or {})

            # 4. 风险指标
            self.rate_limiter.acquire()
            risk = self.data_svc.get_fund_risk_metrics(wind_code)

            # 5. 持仓数据（最新季度）
            self.rate_limiter.acquire()
            try:
                holdings = self.data_svc.get_fund_holdings(wind_code)
            except Exception:
                holdings = []

            # 6. 保存到数据库；分类内评价由统一评价服务读取已持久化事实后执行。
            fund_data = {
                **info,
                "performance_data": perf,
                "risk_metrics": risk,
                "raw_data": {
                    "source": "tushare",
                    "synced_at": datetime.now().isoformat(),
                    "info": info,
                    "nav_evidence": {
                        "benchmark_code": nav_enrichment.get("benchmark_code"),
                        "benchmark_source": nav_enrichment.get("benchmark_source"),
                        "benchmark_data_status": nav_enrichment.get("benchmark_data_status"),
                        "benchmark_data_kind": nav_enrichment.get("benchmark_data_kind"),
                        "benchmark_observations": nav_enrichment.get("benchmark_observations", 0),
                        "benchmark_nav_observations": nav_enrichment.get("benchmark_nav_observations", 0),
                        "benchmark_rate_observations": nav_enrichment.get("benchmark_rate_observations", 0),
                        "money_market_metric_status": nav_enrichment.get("money_market_metric_status"),
                        "nav_data_status": nav_enrichment.get("nav_data_status"),
                        "nav_validation": nav_enrichment.get("nav_validation"),
                    },
                },
            }
            self.fund_repo.upsert_fund(wind_code, fund_data)

            # 7. 保存净值序列
            if nav_data:
                self.nav_repo.upsert_nav_series(wind_code, nav_data, replace_range=True)

            # 8. 保存持仓
            if holdings:
                quarter = datetime.now().strftime("%YQ%m")
                self.holding_repo.upsert_holdings(wind_code, quarter, holdings)

            logger.info(f"✓ Synced {wind_code}: {info.get('name', 'N/A')}")
            return True

        except Exception as e:
            logger.error(f"✗ Failed to sync {wind_code}: {e}")
            # 检查是否是限流错误
            if "频率" in str(e) or "limit" in str(e).lower():
                self.rate_limiter.slow_down(0.5)
                time.sleep(60)  # 等待1分钟
            return False

    def sync_all_funds(self):
        """同步所有基金"""
        logger.info("=" * 60)
        logger.info("开始批量同步基金数据")
        logger.info("=" * 60)

        # 1. 获取所有基金
        logger.info("正在获取基金列表...")
        all_funds = self.data_svc.get_all_funds()
        logger.info(f"共获取 {len(all_funds)} 只基金")

        # 2. 过滤已完成的
        remaining = [f for f in all_funds if not self.tracker.is_completed(f['wind_code'])]
        logger.info(f"待同步: {len(remaining)} 只（已完成: {len(all_funds) - len(remaining)}）")

        if not remaining:
            logger.info("所有基金已同步完成！")
            return

        # 3. 并行同步
        logger.info(f"开始并行同步（{self.max_workers} 个工作线程）...")

        try:
            from tqdm import tqdm
            use_tqdm = True
        except ImportError:
            use_tqdm = False
            logger.warning("tqdm not installed, progress bar disabled")

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self.sync_with_retry, f['wind_code']): f
                for f in remaining
            }

            if use_tqdm:
                pbar = tqdm(total=len(remaining), desc="同步进度")

            for future in as_completed(futures):
                fund = futures[future]
                wind_code = fund['wind_code']

                try:
                    success = future.result()
                    if success:
                        self.tracker.mark_completed(wind_code)
                    else:
                        self.tracker.mark_failed(wind_code, "Sync failed after retries")
                except Exception as e:
                    logger.error(f"Unexpected error for {wind_code}: {e}")
                    self.tracker.mark_failed(wind_code, str(e))

                if use_tqdm:
                    pbar.update(1)

            if use_tqdm:
                pbar.close()

        # 4. 保存最终结果
        self.tracker.save_checkpoint()
        stats = self.tracker.get_stats()

        logger.info("=" * 60)
        logger.info("同步完成！")
        logger.info(f"成功: {stats['completed']}")
        logger.info(f"失败: {stats['failed']}")
        logger.info(f"开始时间: {stats['start_time']}")
        logger.info(f"结束时间: {stats['last_update']}")
        logger.info("=" * 60)

    def sync_with_retry(self, wind_code: str, max_retries=3) -> bool:
        """带重试的同步"""
        for attempt in range(max_retries):
            try:
                return self.sync_single_fund(wind_code)
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"Failed after {max_retries} attempts: {wind_code}")
                    return False

                # 指数退避
                wait_time = 2 ** attempt
                logger.warning(f"Retry {attempt + 1}/{max_retries} for {wind_code} after {wait_time}s")
                time.sleep(wait_time)

        return False


def main():
    parser = argparse.ArgumentParser(description="批量同步基金数据到生产环境")
    parser.add_argument("--sync-funds", action="store_true", help="同步所有基金")
    parser.add_argument("--sync-managers", action="store_true", help="同步所有基金经理")
    parser.add_argument("--sync-all", action="store_true", help="同步所有数据")
    parser.add_argument("--workers", type=int, default=8, help="并行工作线程数（默认8）")
    parser.add_argument("--reset", action="store_true", help="重置进度，从头开始")

    args = parser.parse_args()

    if args.reset:
        if os.path.exists("sync_progress.json"):
            os.remove("sync_progress.json")
            logger.info("进度已重置")

    # 初始化服务
    logger.info("初始化服务...")
    tushare_svc = TushareDataService()
    scoring_eng = FundScoringEngine()
    init_services(tushare_svc=tushare_svc, scoring_eng=scoring_eng)

    orchestrator = BatchSyncOrchestrator(max_workers=args.workers)

    if args.sync_funds or args.sync_all:
        orchestrator.sync_all_funds()

    if args.sync_managers or args.sync_all:
        logger.info("基金经理同步功能待实现")

    if not (args.sync_funds or args.sync_managers or args.sync_all):
        parser.print_help()


if __name__ == "__main__":
    main()
