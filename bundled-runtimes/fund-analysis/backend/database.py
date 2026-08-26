"""
PostgreSQL 数据库访问层
使用 SQLAlchemy 管理基金核心数据的持久化

Prisma schema 参考：仓库根目录 `prisma/schema.prisma`
"""
import os
import logging
from typing import Optional, List, Dict, Any, TypeVar, Type
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Lazy initialization
_engine = None
_SessionLocal = None
_initialized_database_url = None


def normalize_database_url(database_url: str) -> str:
    """兼容托管平台常见的 postgres:// 写法，SQLAlchemy 需要 postgresql://。"""
    if database_url.startswith("postgres://"):
        return f"postgresql://{database_url[len('postgres://'):]}"
    return database_url


def get_database_url(default: str = "postgresql://postgres@localhost:5432/fund_analysis") -> str:
    return normalize_database_url(os.environ.get("DATABASE_URL", default))


def get_engine():
    """获取 SQLAlchemy 引擎"""
    global _engine
    if _engine is None:
        from sqlalchemy import create_engine
        pg_url = get_database_url()
        _engine = create_engine(
            pg_url,
            pool_pre_ping=True,
            pool_size=20,
            max_overflow=30,
            pool_recycle=3600,
            pool_timeout=30,
        )
        logger.info(f"PostgreSQL engine created: {pg_url.split('@')[1] if '@' in pg_url else 'localhost'}")
    return _engine


def check_database_health(min_fund_count: int = 1) -> Dict[str, Any]:
    """检查基金研究数据库是否真的可用于本地研究。

    健康检查不打印连接串或密钥，只返回可操作的状态和计数。
    """
    from sqlalchemy import text

    health: Dict[str, Any] = {
        "connected": False,
        "funds_table": False,
        "fund_count": 0,
        "minimum_fund_count": min_fund_count,
        "status": "database_unavailable",
    }

    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            health["connected"] = True
            table_exists = conn.execute(
                text("SELECT to_regclass('public.funds') IS NOT NULL AS exists")
            ).scalar()
            health["funds_table"] = bool(table_exists)
            if table_exists:
                fund_count = conn.execute(text("SELECT COUNT(*) FROM funds")).scalar()
                health["fund_count"] = int(fund_count or 0)

        if not health["funds_table"]:
            health["status"] = "schema_missing"
        elif int(health["fund_count"] or 0) < min_fund_count:
            health["status"] = "fund_universe_empty"
        else:
            health["status"] = "ok"
        return health
    except Exception as exc:
        health["error"] = exc.__class__.__name__
        health["detail"] = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
        return health


def get_session():
    """获取数据库会话工厂"""
    global _SessionLocal
    if _SessionLocal is None:
        from sqlalchemy.orm import sessionmaker
        engine = get_engine()
        _SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return _SessionLocal


@contextmanager
def db_session():
    """数据库会话上下文管理器"""
    Session = get_session()
    session = Session()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()


def init_database():
    """初始化数据库表结构"""
    global _initialized_database_url

    from sqlalchemy import text
    database_url = get_database_url()
    if _initialized_database_url == database_url:
        return True

    engine = get_engine()

    tables = [
        # 基金表
        """CREATE TABLE IF NOT EXISTS funds (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            wind_code VARCHAR(20) UNIQUE NOT NULL,
            name VARCHAR(200) NOT NULL,
            type VARCHAR(50),
            manager_ids TEXT[],
            nav DECIMAL(10, 4),
            nav_date DATE,
            total_asset DECIMAL(15, 2),
            establishment_date DATE,
            performance_data JSONB,
            risk_metrics JSONB,
            raw_data JSONB,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )""",
        # 基金研究画像表：基准、同类池、风格标签与数据可信补充
        """CREATE TABLE IF NOT EXISTS fund_research_profiles (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            wind_code VARCHAR(20) UNIQUE NOT NULL REFERENCES funds(wind_code) ON DELETE CASCADE,
            primary_benchmark VARCHAR(100) NOT NULL,
            secondary_benchmark VARCHAR(100),
            peer_group VARCHAR(100) NOT NULL,
            style_label VARCHAR(100) NOT NULL,
            strategy_tags TEXT[],
            manager_tenure_start DATE,
            capacity_notes TEXT,
            data_quality_notes TEXT,
            evidence JSONB,
            updated_by VARCHAR(100),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )""",
        # 标准化基金分类：目录、实体、份额、同类组与基准映射
        """CREATE TABLE IF NOT EXISTS strategy_families (
            id TEXT PRIMARY KEY,
            key TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            asset_class TEXT,
            active_passive TEXT,
            style_tags TEXT[],
            benchmark_policy JSONB,
            peer_policy JSONB,
            source TEXT NOT NULL DEFAULT 'methodology_config',
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS fund_entities (
            id TEXT PRIMARY KEY,
            canonical_code TEXT UNIQUE NOT NULL,
            canonical_name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            company_id TEXT,
            product_line_id TEXT,
            strategy_family_id TEXT,
            asset_class TEXT,
            active_passive TEXT,
            lifecycle_stage TEXT NOT NULL DEFAULT 'active',
            established_at DATE,
            terminated_at DATE,
            source TEXT NOT NULL DEFAULT 'entity_standardization',
            source_updated_at DATE,
            raw_data JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS fund_share_classes (
            id TEXT PRIMARY KEY,
            entity_id TEXT NOT NULL,
            fund_id TEXT,
            wind_code TEXT UNIQUE NOT NULL,
            share_class TEXT,
            fee_class TEXT,
            currency TEXT DEFAULT 'CNY',
            is_primary BOOLEAN NOT NULL DEFAULT FALSE,
            status TEXT NOT NULL DEFAULT 'active',
            source TEXT NOT NULL DEFAULT 'share_class_normalizer',
            source_updated_at DATE,
            raw_data JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS peer_groups (
            id TEXT PRIMARY KEY,
            key TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            strategy_family_id TEXT,
            asset_class TEXT NOT NULL,
            active_passive TEXT NOT NULL,
            benchmark_code TEXT,
            benchmark_name TEXT,
            inclusion_rules JSONB NOT NULL,
            exclusion_rules JSONB,
            minimum_peer_count INTEGER NOT NULL DEFAULT 10,
            source TEXT NOT NULL DEFAULT 'peer_group_policy',
            source_updated_at DATE,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        )""",
        """CREATE TABLE IF NOT EXISTS peer_group_members (
            id TEXT PRIMARY KEY,
            peer_group_id TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'member',
            matched_rules JSONB NOT NULL,
            excluded_rules JSONB,
            sample_as_of_date DATE,
            confidence NUMERIC(5,2),
            source TEXT NOT NULL DEFAULT 'peer_group_builder',
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE (peer_group_id, entity_id)
        )""",
        """CREATE TABLE IF NOT EXISTS benchmark_mappings (
            id TEXT PRIMARY KEY,
            entity_id TEXT NOT NULL,
            peer_group_id TEXT,
            benchmark_code TEXT NOT NULL,
            benchmark_name TEXT NOT NULL,
            benchmark_type TEXT NOT NULL,
            mapping_method TEXT NOT NULL,
            confidence NUMERIC(5,2),
            rationale TEXT NOT NULL,
            evidence_refs JSONB,
            effective_from DATE,
            effective_to DATE,
            status TEXT NOT NULL DEFAULT 'active',
            source TEXT NOT NULL DEFAULT 'benchmark_mapping_policy',
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE (entity_id, benchmark_code, effective_from)
        )""",
        """CREATE TABLE IF NOT EXISTS attribution_explanations (
            id TEXT PRIMARY KEY,
            entity_id TEXT NOT NULL,
            benchmark_mapping_id TEXT,
            period_start DATE NOT NULL,
            period_end DATE NOT NULL,
            total_return NUMERIC(10,4),
            benchmark_return NUMERIC(10,4),
            excess_return NUMERIC(10,4),
            allocation_effect NUMERIC(10,4),
            selection_effect NUMERIC(10,4),
            interaction_effect NUMERIC(10,4),
            style_contribution JSONB,
            industry_contribution JSONB,
            asset_allocation JSONB,
            residual_explanation TEXT,
            evidence_refs JSONB,
            quality_status TEXT NOT NULL DEFAULT 'draft',
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE (entity_id, period_start, period_end, benchmark_mapping_id)
        )""",
        # 销售规则/材料证据表：基金研究门禁会直接读取，不能只依赖前端懒创建
        """CREATE TABLE IF NOT EXISTS fund_sales_rules (
            wind_code TEXT NOT NULL,
            platform TEXT NOT NULL DEFAULT 'manual',
            purchase_status TEXT NOT NULL DEFAULT 'unknown',
            purchase_status_label TEXT NOT NULL DEFAULT '申购待核',
            min_purchase_amount NUMERIC,
            min_sip_amount NUMERIC,
            daily_limit_amount NUMERIC,
            purchase_fee_rate NUMERIC,
            redemption_fee_rules JSONB NOT NULL DEFAULT '[]'::jsonb,
            sales_service_fee_rate NUMERIC,
            risk_level TEXT,
            supports_sip BOOLEAN,
            source_url TEXT,
            source_updated_at DATE,
            notes TEXT,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
            PRIMARY KEY (wind_code, platform)
        )""",
        # 基金经理表
        """CREATE TABLE IF NOT EXISTS managers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            wind_code VARCHAR(50) UNIQUE,
            name VARCHAR(100) NOT NULL,
            company VARCHAR(200),
            education VARCHAR(50),
            work_years INTEGER,
            management_years DECIMAL(5, 2),
            current_funds TEXT[],
            historical_performance JSONB,
            style_analysis JSONB,
            raw_data JSONB,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )""",
        # 基金经理完整任职关系：现任与历史产品统一留存
        """CREATE TABLE IF NOT EXISTS manager_fund_tenures (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            manager_id VARCHAR(50) NOT NULL REFERENCES managers(wind_code) ON DELETE CASCADE,
            fund_code VARCHAR(20) NOT NULL REFERENCES funds(wind_code) ON DELETE CASCADE,
            fund_name VARCHAR(200),
            start_date DATE NOT NULL,
            end_date DATE,
            is_current BOOLEAN NOT NULL DEFAULT FALSE,
            performance_snapshot JSONB,
            source VARCHAR(100) NOT NULL DEFAULT 'tushare.fund_manager',
            raw_data JSONB,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(manager_id, fund_code, start_date)
        )""",
        # 基金净值表
        """CREATE TABLE IF NOT EXISTS fund_nav (
            id SERIAL PRIMARY KEY,
            wind_code VARCHAR(20) NOT NULL,
            trade_date DATE NOT NULL,
            nav DECIMAL(10, 4),
            unit_nav DECIMAL(10, 4),
            accum_nav DECIMAL(10, 4),
            daily_return DECIMAL(12, 8),
            benchmark_nav DECIMAL(10, 4),
            discount_rate DECIMAL(12, 8),
            UNIQUE(wind_code, trade_date)
        )""",
        # 基金评分表
        """CREATE TABLE IF NOT EXISTS scores (
            id SERIAL PRIMARY KEY,
            target_type VARCHAR(20) NOT NULL,
            target_id VARCHAR(50) NOT NULL,
            dimension VARCHAR(50),
            score DECIMAL(5, 2),
            weight DECIMAL(3, 2),
            calculation_method VARCHAR(50),
            details JSONB,
            scored_at TIMESTAMP DEFAULT NOW(),
            created_at TIMESTAMP DEFAULT NOW()
        )""",
        # 用户主动保存的专业评价历史快照
        """CREATE TABLE IF NOT EXISTS fund_evaluation_snapshots (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            wind_code VARCHAR(20) NOT NULL REFERENCES funds(wind_code) ON DELETE CASCADE,
            evaluation_window VARCHAR(10) NOT NULL,
            as_of_date DATE,
            status VARCHAR(30) NOT NULL,
            methodology_version VARCHAR(100) NOT NULL,
            calculation_method VARCHAR(200),
            peer_group_id TEXT,
            peer_group_name TEXT,
            overall_score DECIMAL(5, 2),
            overall_grade VARCHAR(30),
            peer_rank INTEGER,
            peer_count INTEGER,
            peer_percentile DECIMAL(8, 4),
            dimension_scores JSONB NOT NULL DEFAULT '{}'::jsonb,
            peer_metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
            data_quality JSONB NOT NULL DEFAULT '{}'::jsonb,
            missing_items JSONB NOT NULL DEFAULT '[]'::jsonb,
            source_snapshot_ids TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
            snapshot JSONB NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        )""",
        # 基金持仓表
        """CREATE TABLE IF NOT EXISTS holdings (
            id SERIAL PRIMARY KEY,
            wind_code VARCHAR(20) NOT NULL,
            quarter VARCHAR(10) NOT NULL,
            stock_code VARCHAR(20) NOT NULL,
            stock_name VARCHAR(200),
            industry VARCHAR(50),
            sub_industry VARCHAR(50),
            weight DECIMAL(8, 4),
            shares BIGINT,
            market_cap VARCHAR(20),
            pe_ratio DECIMAL(10, 2),
            pb_ratio DECIMAL(10, 2),
            roe DECIMAL(8, 4),
            revenue_growth DECIMAL(10, 4),
            dividend_yield DECIMAL(8, 4),
            market_cap_value DECIMAL(15, 2),
            equity_portfolio_weight DECIMAL(8, 4),
            weight_basis VARCHAR(30),
            weight_validation_status VARCHAR(30),
            source VARCHAR(100),
            weight_source VARCHAR(100),
            weight_source_url TEXT,
            fund_net_asset DECIMAL(24, 4),
            fund_net_asset_basis VARCHAR(100),
            fund_net_asset_date DATE,
            announcement_date DATE,
            report_date DATE,
            synced_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE(wind_code, quarter, stock_code)
        )""",
        # 基金定期报告资产配置历史
        """CREATE TABLE IF NOT EXISTS fund_asset_allocations (
            wind_code VARCHAR(20) NOT NULL REFERENCES funds(wind_code) ON DELETE CASCADE,
            report_date DATE NOT NULL,
            stock_ratio DECIMAL(10, 8),
            bond_ratio DECIMAL(10, 8),
            cash_ratio DECIMAL(10, 8),
            net_asset_yi DECIMAL(15, 4),
            source TEXT NOT NULL,
            source_url TEXT,
            fetched_at TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (wind_code, report_date)
        )""",
        # 基金半年报、年报披露的持有人结构历史
        """CREATE TABLE IF NOT EXISTS fund_holder_structures (
            wind_code VARCHAR(20) NOT NULL REFERENCES funds(wind_code) ON DELETE CASCADE,
            report_date DATE NOT NULL,
            institution_ratio DECIMAL(10, 8),
            individual_ratio DECIMAL(10, 8),
            internal_ratio DECIMAL(10, 8),
            total_shares_yi DECIMAL(15, 4),
            source TEXT NOT NULL,
            source_url TEXT,
            fetched_at TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (wind_code, report_date)
        )""",
        # 基金定期报告公开展示的重仓债券，不代表完整债券组合
        """CREATE TABLE IF NOT EXISTS fund_bond_holdings (
            wind_code VARCHAR(20) NOT NULL REFERENCES funds(wind_code) ON DELETE CASCADE,
            report_date DATE NOT NULL,
            sequence INTEGER NOT NULL,
            bond_code VARCHAR(30) NOT NULL,
            bond_name VARCHAR(200) NOT NULL,
            bond_type VARCHAR(50) NOT NULL,
            nav_ratio DECIMAL(10, 8),
            market_value_wan DECIMAL(18, 2),
            classification_basis TEXT,
            issuer VARCHAR(300),
            security_bond_type VARCHAR(100),
            credit_rating VARCHAR(30),
            rating_type VARCHAR(30),
            maturity_date DATE,
            coupon_rate DECIMAL(10, 8),
            metadata_source TEXT,
            metadata_url TEXT,
            metadata_status VARCHAR(30) NOT NULL DEFAULT 'unavailable',
            source TEXT NOT NULL,
            source_url TEXT,
            fetched_at TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (wind_code, report_date, bond_code)
        )""",
        # FOF 定期报告公开展示的底层基金，不代表完整组合
        """CREATE TABLE IF NOT EXISTS fund_underlying_holdings (
            wind_code VARCHAR(20) NOT NULL REFERENCES funds(wind_code) ON DELETE CASCADE,
            report_date DATE NOT NULL,
            sequence INTEGER NOT NULL,
            underlying_fund_code VARCHAR(20) NOT NULL,
            underlying_fund_name VARCHAR(200) NOT NULL,
            nav_ratio DECIMAL(10, 8),
            daily_return DECIMAL(10, 8),
            source TEXT NOT NULL,
            source_url TEXT,
            fetched_at TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (wind_code, report_date, underlying_fund_code)
        )""",
        # 中债分期限指数序列；用于债基净值回归久期，不参与基金评分
        """CREATE TABLE IF NOT EXISTS bond_index_series (
            series_key VARCHAR(100) NOT NULL,
            index_group VARCHAR(50) NOT NULL,
            index_name VARCHAR(200) NOT NULL,
            index_id VARCHAR(64) NOT NULL,
            period_code VARCHAR(10) NOT NULL,
            period_label VARCHAR(30) NOT NULL,
            indicator VARCHAR(30) NOT NULL,
            trade_date DATE NOT NULL,
            value DECIMAL(18, 8) NOT NULL,
            source TEXT NOT NULL,
            source_url TEXT NOT NULL,
            fetched_at TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (series_key, indicator, trade_date)
        )""",
        # Sharpe 收益率风格回归得到的债基估算久期
        """CREATE TABLE IF NOT EXISTS fund_bond_duration_estimates (
            wind_code VARCHAR(20) NOT NULL REFERENCES funds(wind_code) ON DELETE CASCADE,
            as_of_date DATE NOT NULL,
            window_weeks INTEGER NOT NULL,
            data_start DATE,
            data_end DATE,
            observations INTEGER NOT NULL DEFAULT 0,
            estimated_duration DECIMAL(10, 6),
            duration_bucket VARCHAR(50),
            r_squared DECIMAL(10, 8),
            tracking_error DECIMAL(10, 8),
            selected_series JSONB NOT NULL DEFAULT '[]'::jsonb,
            weights JSONB NOT NULL DEFAULT '[]'::jsonb,
            group_diagnostics JSONB NOT NULL DEFAULT '[]'::jsonb,
            methodology_version VARCHAR(80) NOT NULL,
            status VARCHAR(30) NOT NULL,
            source TEXT NOT NULL,
            missing_items JSONB NOT NULL DEFAULT '[]'::jsonb,
            calculated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (wind_code, as_of_date, window_weeks)
        )""",
        # Barra 因子暴露表
        """CREATE TABLE IF NOT EXISTS factor_exposures (
            id SERIAL PRIMARY KEY,
            wind_code VARCHAR(20) NOT NULL,
            quarter VARCHAR(10) NOT NULL,
            factor_name VARCHAR(50) NOT NULL,
            exposure DECIMAL(10, 4),
            factor_return DECIMAL(10, 4),
            risk_contribution DECIMAL(8, 4),
            UNIQUE(wind_code, quarter, factor_name)
        )""",
        # 公开持仓风格描述子；与正式 Barra 因子暴露分表保存
        """CREATE TABLE IF NOT EXISTS holding_style_snapshots (
            wind_code VARCHAR(20) NOT NULL,
            quarter VARCHAR(10) NOT NULL,
            peer_group_id TEXT,
            peer_group_key TEXT,
            peer_group_name TEXT,
            descriptors JSONB NOT NULL DEFAULT '[]'::jsonb,
            peer_percentiles JSONB NOT NULL DEFAULT '[]'::jsonb,
            style_labels TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
            peer_sample_size INTEGER NOT NULL DEFAULT 0,
            minimum_peer_count INTEGER NOT NULL DEFAULT 5,
            holdings_disclosed_weight DECIMAL(8, 6),
            source TEXT NOT NULL,
            status VARCHAR(30) NOT NULL,
            missing_items JSONB NOT NULL DEFAULT '[]'::jsonb,
            calculated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (wind_code, quarter)
        )""",
        # 市场指数成分的时点快照；历史归因只能使用区间开始日之前的快照
        """CREATE TABLE IF NOT EXISTS market_index_constituent_snapshots (
            index_code VARCHAR(30) NOT NULL,
            as_of_date DATE NOT NULL,
            constituent_code VARCHAR(20) NOT NULL,
            constituent_name VARCHAR(200),
            weight DECIMAL(12, 10),
            industry VARCHAR(100),
            source TEXT NOT NULL,
            evidence_url TEXT,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (index_code, as_of_date, constituent_code)
        )""",
        # Brinson 归因表
        """CREATE TABLE IF NOT EXISTS performance_attributions (
            id SERIAL PRIMARY KEY,
            wind_code VARCHAR(20) NOT NULL,
            benchmark_id VARCHAR(20) NOT NULL,
            quarter VARCHAR(10) NOT NULL,
            total_return DECIMAL(10, 4),
            benchmark_return DECIMAL(10, 4),
            active_return DECIMAL(10, 4),
            allocation_effect DECIMAL(10, 4),
            selection_effect DECIMAL(10, 4),
            interaction_effect DECIMAL(10, 4),
            industry_allocation DECIMAL(10, 4),
            stock_selection DECIMAL(10, 4),
            residual DECIMAL(10, 4),
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(wind_code, quarter)
        )""",
        # 基金经理画像表
        """CREATE TABLE IF NOT EXISTS manager_profiles (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            manager_id VARCHAR(50) UNIQUE NOT NULL,
            product_positioning TEXT,
            investment_objective TEXT,
            investment_method TEXT,
            core_philosophy TEXT,
            stock_selection_logic TEXT,
            risk_philosophy TEXT,
            focus_industries TEXT[],
            competence_advantages TEXT,
            competence_boundaries TEXT,
            style_label VARCHAR(50),
            concentration TEXT,
            turnover TEXT,
            excess_return_source TEXT,
            holding_style TEXT,
            style_stability INTEGER,
            philosophy_score INTEGER,
            competence_score INTEGER,
            style_score INTEGER,
            overall_quality_score INTEGER,
            philosophy_behavior_consistency DECIMAL(5, 2),
            valuation_consistency INTEGER,
            quality_consistency INTEGER,
            industry_consistency INTEGER,
            key_insights TEXT[],
            red_flags TEXT[],
            interviews_analyzed INTEGER DEFAULT 0,
            last_interview_date DATE,
            evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_by VARCHAR(100),
            last_updated TIMESTAMP DEFAULT NOW()
        )""",
        # 本地调研纪要文件夹
        """CREATE TABLE IF NOT EXISTS local_research_folders (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            path TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ready',
            last_scan_at TIMESTAMPTZ,
            last_scan_counts JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )""",
        # 调研报告表
        """CREATE TABLE IF NOT EXISTS research_reports (
            id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            manager_id VARCHAR(50),
            manager_name VARCHAR(100),
            fund_ids TEXT[],
            title VARCHAR(500) NOT NULL,
            report_date DATE,
            report_date_source VARCHAR(30),
            report_date_precision VARCHAR(20),
            source VARCHAR(200),
            content TEXT,
            summary TEXT,
            key_points JSONB,
            tags TEXT[],
            viewpoint_topics TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
            research_domains TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
            classifications TEXT[],
            style_labels TEXT[],
            review_proposals JSONB NOT NULL DEFAULT '[]'::jsonb,
            review_status TEXT,
            local_folder_id UUID REFERENCES local_research_folders(id) ON DELETE SET NULL,
            local_relative_path TEXT,
            local_source_path TEXT,
            source_hash TEXT,
            extraction_status TEXT,
            extraction_provider TEXT,
            extraction_model TEXT,
            llm_extraction_status TEXT,
            llm_extraction_error TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )""",
        # 一篇纪要可关联多位经理；旧 manager_id 字段仅保留单经理兼容。
        """CREATE TABLE IF NOT EXISTS research_report_managers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            report_id TEXT NOT NULL REFERENCES research_reports(id) ON DELETE CASCADE,
            manager_id VARCHAR(50) NOT NULL REFERENCES managers(wind_code) ON DELETE CASCADE,
            manager_name VARCHAR(100) NOT NULL,
            source VARCHAR(100) NOT NULL DEFAULT 'research_memo_review',
            confirmed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(report_id, manager_id)
        )""",
        """CREATE TABLE IF NOT EXISTS local_research_documents (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            folder_id UUID NOT NULL REFERENCES local_research_folders(id) ON DELETE CASCADE,
            relative_path TEXT NOT NULL,
            source_path TEXT NOT NULL,
            size BIGINT,
            mtime_ns BIGINT,
            content_hash TEXT,
            report_id TEXT REFERENCES research_reports(id) ON DELETE SET NULL,
            index_status TEXT NOT NULL,
            error TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(folder_id, relative_path)
        )""",
        # 调研报告切片表（RAG 证据链）
        """CREATE TABLE IF NOT EXISTS research_report_chunks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            report_id TEXT NOT NULL REFERENCES research_reports(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            token_count INTEGER,
            embedding_id VARCHAR(200),
            entities JSONB,
            metadata JSONB,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(report_id, chunk_index)
        )""",
        # 筛选条件表
        """CREATE TABLE IF NOT EXISTS screening_criteria (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(200) NOT NULL,
            description TEXT,
            criteria JSONB NOT NULL,
            created_by VARCHAR(100),
            is_public BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )""",
        # AI 分析报告表
        """CREATE TABLE IF NOT EXISTS ai_analysis_reports (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            target_type VARCHAR(20) NOT NULL,
            target_id VARCHAR(50) NOT NULL,
            report_type VARCHAR(100),
            content TEXT,
            data_sources JSONB,
            research_reports_used TEXT[],
            generation_params JSONB,
            created_at TIMESTAMP DEFAULT NOW()
        )""",
        # 基金池表
        """CREATE TABLE IF NOT EXISTS fund_pools (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(200) NOT NULL,
            description TEXT,
            created_by VARCHAR(100),
            is_default BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )""",
        # 基金池成员表
        """CREATE TABLE IF NOT EXISTS pool_members (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            pool_id UUID NOT NULL REFERENCES fund_pools(id) ON DELETE CASCADE,
            fund_id VARCHAR(100) NOT NULL,
            status VARCHAR(30) NOT NULL,
            reason TEXT,
            latest_conclusion TEXT,
            evidence JSONB,
            risk_notes TEXT,
            next_review_date DATE,
            created_by VARCHAR(100),
            updated_by VARCHAR(100),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(pool_id, fund_id)
        )""",
        # 投资决策留痕表
        """CREATE TABLE IF NOT EXISTS investment_decisions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            pool_id UUID REFERENCES fund_pools(id) ON DELETE SET NULL,
            target_type VARCHAR(30) NOT NULL,
            target_id VARCHAR(100) NOT NULL,
            decision_type VARCHAR(50) NOT NULL,
            decision_status VARCHAR(30) NOT NULL,
            rationale TEXT,
            evidence JSONB,
            memo_snapshot JSONB,
            suitability_profile JSONB,
            suitability_result JSONB,
            model_version VARCHAR(200),
            created_by VARCHAR(100),
            updated_by VARCHAR(100),
            reviewed_by VARCHAR(100),
            review_notes TEXT,
            reviewed_at TIMESTAMP,
            approved_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )""",
        # 决策审计事件表
        """CREATE TABLE IF NOT EXISTS decision_audit_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            decision_id UUID NOT NULL REFERENCES investment_decisions(id) ON DELETE CASCADE,
            event_type VARCHAR(80) NOT NULL,
            actor VARCHAR(100),
            from_status VARCHAR(30),
            to_status VARCHAR(30),
            payload JSONB,
            created_at TIMESTAMP DEFAULT NOW()
        )""",
        # 数据源快照表
        """CREATE TABLE IF NOT EXISTS data_source_snapshots (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source VARCHAR(100) NOT NULL,
            dataset VARCHAR(100) NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'running',
            started_at TIMESTAMP DEFAULT NOW(),
            finished_at TIMESTAMP,
            coverage_start DATE,
            coverage_end DATE,
            record_count INTEGER,
            error_message TEXT,
            metadata JSONB,
            created_at TIMESTAMP DEFAULT NOW()
        )""",
        # 指标快照表
        """CREATE TABLE IF NOT EXISTS metric_snapshots (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            target_type VARCHAR(30) NOT NULL,
            target_id VARCHAR(100) NOT NULL,
            as_of_date DATE NOT NULL,
            metric_name VARCHAR(100) NOT NULL,
            metric_value DECIMAL(20, 8) NOT NULL,
            metric_unit VARCHAR(30),
            metric_window VARCHAR(30),
            benchmark_code VARCHAR(50),
            peer_group_key VARCHAR(100),
            source_snapshot_id UUID REFERENCES data_source_snapshots(id) ON DELETE SET NULL,
            details JSONB,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            CONSTRAINT metric_snapshots_unique_key UNIQUE (
                target_type, target_id, as_of_date, metric_name, metric_window, benchmark_code, peer_group_key
            )
        )""",
        # 预警规则表
        """CREATE TABLE IF NOT EXISTS alert_rules (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(200) NOT NULL,
            rule_type VARCHAR(50) NOT NULL,
            scope_type VARCHAR(50) NOT NULL,
            scope_id VARCHAR(100),
            threshold JSONB,
            enabled BOOLEAN DEFAULT TRUE,
            created_by VARCHAR(100),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )""",
        # 预警事件表
        """CREATE TABLE IF NOT EXISTS alert_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            rule_id UUID REFERENCES alert_rules(id) ON DELETE SET NULL,
            fund_id VARCHAR(100),
            pool_member_id VARCHAR(100),
            event_type VARCHAR(50) NOT NULL,
            severity VARCHAR(20) NOT NULL,
            title VARCHAR(200) NOT NULL,
            message TEXT NOT NULL,
            status VARCHAR(30) NOT NULL,
            triggered_at TIMESTAMP DEFAULT NOW(),
            resolved_at TIMESTAMP,
            details JSONB,
            created_at TIMESTAMP DEFAULT NOW()
        )""",
    ]

    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_funds_wind_code ON funds(wind_code)",
        "CREATE INDEX IF NOT EXISTS idx_funds_name ON funds(name)",
        "CREATE INDEX IF NOT EXISTS idx_funds_type ON funds(type)",
        "CREATE INDEX IF NOT EXISTS idx_research_profiles_peer ON fund_research_profiles(peer_group)",
        "CREATE INDEX IF NOT EXISTS idx_research_profiles_style ON fund_research_profiles(style_label)",
        "CREATE INDEX IF NOT EXISTS idx_research_profiles_benchmark ON fund_research_profiles(primary_benchmark)",
        "CREATE INDEX IF NOT EXISTS strategy_families_asset_class_idx ON strategy_families(asset_class)",
        "CREATE INDEX IF NOT EXISTS strategy_families_active_passive_idx ON strategy_families(active_passive)",
        "CREATE INDEX IF NOT EXISTS fund_entities_normalized_name_idx ON fund_entities(normalized_name)",
        "CREATE INDEX IF NOT EXISTS fund_entities_strategy_family_id_idx ON fund_entities(strategy_family_id)",
        "CREATE INDEX IF NOT EXISTS fund_entities_asset_class_idx ON fund_entities(asset_class)",
        "CREATE INDEX IF NOT EXISTS fund_entities_lifecycle_stage_idx ON fund_entities(lifecycle_stage)",
        "CREATE INDEX IF NOT EXISTS fund_share_classes_entity_id_idx ON fund_share_classes(entity_id)",
        "CREATE INDEX IF NOT EXISTS fund_share_classes_fund_id_idx ON fund_share_classes(fund_id)",
        "CREATE INDEX IF NOT EXISTS fund_share_classes_share_class_idx ON fund_share_classes(share_class)",
        "CREATE INDEX IF NOT EXISTS fund_share_classes_status_idx ON fund_share_classes(status)",
        "CREATE INDEX IF NOT EXISTS peer_groups_strategy_family_id_idx ON peer_groups(strategy_family_id)",
        "CREATE INDEX IF NOT EXISTS peer_groups_asset_class_idx ON peer_groups(asset_class)",
        "CREATE INDEX IF NOT EXISTS peer_groups_active_passive_idx ON peer_groups(active_passive)",
        "CREATE INDEX IF NOT EXISTS peer_groups_benchmark_code_idx ON peer_groups(benchmark_code)",
        "CREATE INDEX IF NOT EXISTS peer_group_members_peer_group_id_idx ON peer_group_members(peer_group_id)",
        "CREATE INDEX IF NOT EXISTS peer_group_members_entity_id_idx ON peer_group_members(entity_id)",
        "CREATE INDEX IF NOT EXISTS peer_group_members_role_idx ON peer_group_members(role)",
        "CREATE INDEX IF NOT EXISTS benchmark_mappings_entity_id_idx ON benchmark_mappings(entity_id)",
        "CREATE INDEX IF NOT EXISTS benchmark_mappings_peer_group_id_idx ON benchmark_mappings(peer_group_id)",
        "CREATE INDEX IF NOT EXISTS benchmark_mappings_benchmark_code_idx ON benchmark_mappings(benchmark_code)",
        "CREATE INDEX IF NOT EXISTS benchmark_mappings_status_idx ON benchmark_mappings(status)",
        "CREATE INDEX IF NOT EXISTS attribution_explanations_entity_id_period_end_idx ON attribution_explanations(entity_id, period_end)",
        "CREATE INDEX IF NOT EXISTS attribution_explanations_benchmark_mapping_id_idx ON attribution_explanations(benchmark_mapping_id)",
        "CREATE INDEX IF NOT EXISTS attribution_explanations_quality_status_idx ON attribution_explanations(quality_status)",
        "CREATE INDEX IF NOT EXISTS fund_sales_rules_wind_code_idx ON fund_sales_rules(wind_code)",
        "CREATE INDEX IF NOT EXISTS idx_nav_wind_code ON fund_nav(wind_code)",
        "CREATE INDEX IF NOT EXISTS idx_nav_date ON fund_nav(trade_date)",
        "CREATE INDEX IF NOT EXISTS idx_nav_wind_code_trade_date ON fund_nav(wind_code, trade_date)",
        "CREATE INDEX IF NOT EXISTS idx_scores_target ON scores(target_type, target_id)",
        "CREATE INDEX IF NOT EXISTS idx_scores_dimension ON scores(dimension)",
        "CREATE INDEX IF NOT EXISTS idx_fund_evaluation_history ON fund_evaluation_snapshots(wind_code, evaluation_window, created_at DESC)",
        "CREATE UNIQUE INDEX IF NOT EXISTS holdings_wind_code_quarter_stock_code_key ON holdings(wind_code, quarter, stock_code)",
        "CREATE INDEX IF NOT EXISTS idx_holdings_wind_code ON holdings(wind_code)",
        "CREATE INDEX IF NOT EXISTS idx_holdings_quarter ON holdings(quarter)",
        "CREATE INDEX IF NOT EXISTS idx_holdings_industry ON holdings(industry)",
        "CREATE INDEX IF NOT EXISTS idx_fund_asset_allocations_report_date ON fund_asset_allocations(report_date)",
        "CREATE INDEX IF NOT EXISTS idx_fund_holder_structures_report_date ON fund_holder_structures(report_date)",
        "CREATE INDEX IF NOT EXISTS idx_fund_bond_holdings_report_date ON fund_bond_holdings(report_date)",
        "CREATE INDEX IF NOT EXISTS idx_fund_bond_holdings_code ON fund_bond_holdings(bond_code)",
        "CREATE INDEX IF NOT EXISTS idx_fund_bond_holdings_type ON fund_bond_holdings(bond_type)",
        "CREATE INDEX IF NOT EXISTS idx_fund_underlying_holdings_report_date ON fund_underlying_holdings(report_date)",
        "CREATE INDEX IF NOT EXISTS idx_fund_underlying_holdings_code ON fund_underlying_holdings(underlying_fund_code)",
        "CREATE INDEX IF NOT EXISTS idx_bond_index_series_group_date ON bond_index_series(index_group, trade_date)",
        "CREATE INDEX IF NOT EXISTS idx_bond_index_series_indicator_date ON bond_index_series(indicator, trade_date)",
        "CREATE INDEX IF NOT EXISTS idx_fund_bond_duration_latest ON fund_bond_duration_estimates(wind_code, as_of_date DESC)",
        "CREATE UNIQUE INDEX IF NOT EXISTS factor_exposures_wind_code_quarter_factor_name_key ON factor_exposures(wind_code, quarter, factor_name)",
        "CREATE INDEX IF NOT EXISTS idx_exposures_wind_code ON factor_exposures(wind_code)",
        "CREATE INDEX IF NOT EXISTS idx_exposures_quarter ON factor_exposures(quarter)",
        "CREATE INDEX IF NOT EXISTS idx_holding_style_snapshots_peer ON holding_style_snapshots(peer_group_id, quarter)",
        "CREATE UNIQUE INDEX IF NOT EXISTS performance_attributions_wind_code_quarter_key ON performance_attributions(wind_code, quarter)",
        "CREATE INDEX IF NOT EXISTS idx_attributions_wind_code ON performance_attributions(wind_code)",
        "CREATE INDEX IF NOT EXISTS idx_managers_name ON managers(name)",
        "CREATE INDEX IF NOT EXISTS idx_manager_fund_tenures_manager ON manager_fund_tenures(manager_id, is_current)",
        "CREATE INDEX IF NOT EXISTS idx_manager_fund_tenures_fund ON manager_fund_tenures(fund_code)",
        "CREATE INDEX IF NOT EXISTS idx_reports_manager ON research_reports(manager_id)",
        "CREATE INDEX IF NOT EXISTS idx_reports_date ON research_reports(report_date)",
        "CREATE INDEX IF NOT EXISTS idx_reports_fund_ids ON research_reports USING GIN(fund_ids)",
        "CREATE INDEX IF NOT EXISTS idx_reports_viewpoint_topics ON research_reports USING GIN(viewpoint_topics)",
        "CREATE INDEX IF NOT EXISTS idx_reports_research_domains ON research_reports USING GIN(research_domains)",
        "CREATE INDEX IF NOT EXISTS idx_reports_local_folder ON research_reports(local_folder_id)",
        "CREATE INDEX IF NOT EXISTS idx_report_managers_manager ON research_report_managers(manager_id, confirmed_at)",
        "CREATE INDEX IF NOT EXISTS idx_report_managers_report ON research_report_managers(report_id)",
        "CREATE INDEX IF NOT EXISTS idx_local_research_documents_hash ON local_research_documents(content_hash)",
        "CREATE INDEX IF NOT EXISTS idx_local_research_documents_report ON local_research_documents(report_id)",
        "CREATE INDEX IF NOT EXISTS idx_report_chunks_report ON research_report_chunks(report_id)",
        "CREATE INDEX IF NOT EXISTS idx_report_chunks_embedding ON research_report_chunks(embedding_id)",
        "CREATE INDEX IF NOT EXISTS idx_market_index_snapshot_date ON market_index_constituent_snapshots(index_code, as_of_date DESC)",
        "CREATE INDEX IF NOT EXISTS idx_data_snapshots_source ON data_source_snapshots(source)",
        "CREATE INDEX IF NOT EXISTS idx_data_snapshots_dataset ON data_source_snapshots(dataset)",
        "CREATE INDEX IF NOT EXISTS idx_data_snapshots_status ON data_source_snapshots(status)",
        "CREATE INDEX IF NOT EXISTS idx_data_snapshots_started ON data_source_snapshots(started_at)",
        "CREATE INDEX IF NOT EXISTS idx_metric_snapshots_target ON metric_snapshots(target_type, target_id, as_of_date)",
        "CREATE INDEX IF NOT EXISTS idx_metric_snapshots_name ON metric_snapshots(metric_name)",
        "CREATE INDEX IF NOT EXISTS idx_metric_snapshots_source ON metric_snapshots(source_snapshot_id)",
        "CREATE INDEX IF NOT EXISTS idx_fund_pools_name ON fund_pools(name)",
        "CREATE INDEX IF NOT EXISTS idx_fund_pools_default ON fund_pools(is_default)",
        "CREATE INDEX IF NOT EXISTS idx_pool_members_pool ON pool_members(pool_id)",
        "CREATE INDEX IF NOT EXISTS idx_pool_members_fund ON pool_members(fund_id)",
        "CREATE INDEX IF NOT EXISTS idx_pool_members_status ON pool_members(status)",
        "CREATE INDEX IF NOT EXISTS idx_pool_members_next_review ON pool_members(next_review_date)",
        "CREATE INDEX IF NOT EXISTS idx_alert_rules_type ON alert_rules(rule_type)",
        "CREATE INDEX IF NOT EXISTS idx_alert_rules_scope ON alert_rules(scope_type, scope_id)",
        "CREATE INDEX IF NOT EXISTS idx_alert_rules_enabled ON alert_rules(enabled)",
        "CREATE INDEX IF NOT EXISTS idx_alert_events_rule ON alert_events(rule_id)",
        "CREATE INDEX IF NOT EXISTS idx_alert_events_fund ON alert_events(fund_id)",
        "CREATE INDEX IF NOT EXISTS idx_alert_events_pool_member ON alert_events(pool_member_id)",
        "CREATE INDEX IF NOT EXISTS idx_alert_events_status ON alert_events(status)",
        "CREATE INDEX IF NOT EXISTS idx_alert_events_severity ON alert_events(severity)",
        "CREATE INDEX IF NOT EXISTS idx_alert_events_triggered ON alert_events(triggered_at)",
        "CREATE INDEX IF NOT EXISTS idx_investment_decisions_target ON investment_decisions(target_type, target_id)",
        "CREATE INDEX IF NOT EXISTS idx_investment_decisions_pool ON investment_decisions(pool_id)",
        "CREATE INDEX IF NOT EXISTS idx_investment_decisions_status ON investment_decisions(decision_status)",
        "CREATE INDEX IF NOT EXISTS idx_decision_audit_events_decision ON decision_audit_events(decision_id)",
        "CREATE INDEX IF NOT EXISTS idx_decision_audit_events_type ON decision_audit_events(event_type)",
    ]

    migrations = [
        "ALTER TABLE fund_nav ADD COLUMN IF NOT EXISTS unit_nav DECIMAL(10, 4)",
        "ALTER TABLE fund_nav ADD COLUMN IF NOT EXISTS daily_return DECIMAL(12, 8)",
        "ALTER TABLE fund_nav ADD COLUMN IF NOT EXISTS benchmark_nav DECIMAL(10, 4)",
        "ALTER TABLE fund_nav ADD COLUMN IF NOT EXISTS discount_rate DECIMAL(12, 8)",
        "UPDATE fund_nav SET unit_nav = nav WHERE unit_nav IS NULL AND nav IS NOT NULL",
        "ALTER TABLE holdings ADD COLUMN IF NOT EXISTS wind_code VARCHAR(20)",
        "ALTER TABLE holdings ADD COLUMN IF NOT EXISTS fund_id TEXT",
        "ALTER TABLE holdings ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT NOW()",
        "UPDATE holdings SET wind_code = funds.wind_code FROM funds WHERE holdings.wind_code IS NULL AND holdings.fund_id = funds.id::text",
        "UPDATE holdings SET fund_id = funds.id::text FROM funds WHERE holdings.fund_id IS NULL AND holdings.wind_code = funds.wind_code",
        "ALTER TABLE holdings ADD COLUMN IF NOT EXISTS equity_portfolio_weight DECIMAL(8, 4)",
        "ALTER TABLE holdings ADD COLUMN IF NOT EXISTS weight_basis VARCHAR(30)",
        "ALTER TABLE holdings ADD COLUMN IF NOT EXISTS weight_validation_status VARCHAR(30)",
        "ALTER TABLE holdings ADD COLUMN IF NOT EXISTS source VARCHAR(100)",
        "ALTER TABLE holdings ADD COLUMN IF NOT EXISTS weight_source VARCHAR(100)",
        "ALTER TABLE holdings ADD COLUMN IF NOT EXISTS weight_source_url TEXT",
        "ALTER TABLE holdings ADD COLUMN IF NOT EXISTS fund_net_asset DECIMAL(24, 4)",
        "ALTER TABLE holdings ADD COLUMN IF NOT EXISTS fund_net_asset_basis VARCHAR(100)",
        "ALTER TABLE holdings ADD COLUMN IF NOT EXISTS fund_net_asset_date DATE",
        "ALTER TABLE holdings ADD COLUMN IF NOT EXISTS announcement_date DATE",
        "ALTER TABLE holdings ADD COLUMN IF NOT EXISTS report_date DATE",
        "ALTER TABLE holdings ADD COLUMN IF NOT EXISTS synced_at TIMESTAMP NOT NULL DEFAULT NOW()",
        "ALTER TABLE factor_exposures ADD COLUMN IF NOT EXISTS wind_code VARCHAR(20)",
        "ALTER TABLE factor_exposures ADD COLUMN IF NOT EXISTS fund_id TEXT",
        "UPDATE factor_exposures SET wind_code = funds.wind_code FROM funds WHERE factor_exposures.wind_code IS NULL AND factor_exposures.fund_id = funds.id::text",
        "UPDATE factor_exposures SET fund_id = funds.id::text FROM funds WHERE factor_exposures.fund_id IS NULL AND factor_exposures.wind_code = funds.wind_code",
        "ALTER TABLE performance_attributions ADD COLUMN IF NOT EXISTS wind_code VARCHAR(20)",
        "ALTER TABLE performance_attributions ADD COLUMN IF NOT EXISTS fund_id TEXT",
        "UPDATE performance_attributions SET wind_code = funds.wind_code FROM funds WHERE performance_attributions.wind_code IS NULL AND performance_attributions.fund_id = funds.id::text",
        "UPDATE performance_attributions SET fund_id = funds.id::text FROM funds WHERE performance_attributions.fund_id IS NULL AND performance_attributions.wind_code = funds.wind_code",
        "ALTER TABLE performance_attributions ADD COLUMN IF NOT EXISTS holding_quarter VARCHAR(10)",
        "ALTER TABLE performance_attributions ADD COLUMN IF NOT EXISTS status VARCHAR(30)",
        "ALTER TABLE performance_attributions ADD COLUMN IF NOT EXISTS evidence JSONB",
        "ALTER TABLE performance_attributions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW()",
        "ALTER TABLE research_reports ADD COLUMN IF NOT EXISTS manager_name VARCHAR(100)",
        "ALTER TABLE research_reports ADD COLUMN IF NOT EXISTS report_date_source VARCHAR(30)",
        "ALTER TABLE research_reports ADD COLUMN IF NOT EXISTS report_date_precision VARCHAR(20)",
        "ALTER TABLE research_reports ADD COLUMN IF NOT EXISTS viewpoint_topics TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]",
        "ALTER TABLE research_reports ADD COLUMN IF NOT EXISTS research_domains TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[]",
        "ALTER TABLE research_reports ADD COLUMN IF NOT EXISTS classifications TEXT[]",
        "ALTER TABLE research_reports ADD COLUMN IF NOT EXISTS style_labels TEXT[]",
        "ALTER TABLE research_reports ADD COLUMN IF NOT EXISTS review_proposals JSONB NOT NULL DEFAULT '[]'::jsonb",
        "ALTER TABLE research_reports ADD COLUMN IF NOT EXISTS review_status TEXT",
        "ALTER TABLE research_reports ADD COLUMN IF NOT EXISTS local_folder_id UUID REFERENCES local_research_folders(id) ON DELETE SET NULL",
        "ALTER TABLE research_reports ADD COLUMN IF NOT EXISTS local_relative_path TEXT",
        "ALTER TABLE research_reports ADD COLUMN IF NOT EXISTS local_source_path TEXT",
        "ALTER TABLE research_reports ADD COLUMN IF NOT EXISTS source_hash TEXT",
        "ALTER TABLE research_reports ADD COLUMN IF NOT EXISTS extraction_status TEXT",
        "ALTER TABLE research_reports ADD COLUMN IF NOT EXISTS extraction_provider TEXT",
        "ALTER TABLE research_reports ADD COLUMN IF NOT EXISTS extraction_model TEXT",
        "ALTER TABLE research_reports ADD COLUMN IF NOT EXISTS llm_extraction_status TEXT",
        "ALTER TABLE research_reports ADD COLUMN IF NOT EXISTS llm_extraction_error TEXT",
        "ALTER TABLE managers ALTER COLUMN updated_at SET DEFAULT NOW()",
        "ALTER TABLE manager_profiles ADD COLUMN IF NOT EXISTS evidence JSONB NOT NULL DEFAULT '{}'::jsonb",
        "ALTER TABLE manager_profiles ADD COLUMN IF NOT EXISTS updated_by VARCHAR(100)",
        "ALTER TABLE manager_profiles ADD COLUMN IF NOT EXISTS excess_return_source TEXT",
        "ALTER TABLE manager_profiles ADD COLUMN IF NOT EXISTS holding_style TEXT",
        "ALTER TABLE manager_profiles ADD COLUMN IF NOT EXISTS product_positioning TEXT",
        "ALTER TABLE manager_profiles ADD COLUMN IF NOT EXISTS investment_objective TEXT",
        "ALTER TABLE manager_profiles ADD COLUMN IF NOT EXISTS investment_method TEXT",
        "ALTER TABLE manager_profiles ALTER COLUMN concentration TYPE TEXT",
        "ALTER TABLE manager_profiles ALTER COLUMN turnover TYPE TEXT",
        "ALTER TABLE manager_fund_tenures ADD COLUMN IF NOT EXISTS performance_snapshot JSONB",
        "ALTER TABLE fund_bond_holdings ADD COLUMN IF NOT EXISTS issuer VARCHAR(300)",
        "ALTER TABLE fund_bond_holdings ADD COLUMN IF NOT EXISTS security_bond_type VARCHAR(100)",
        "ALTER TABLE fund_bond_holdings ADD COLUMN IF NOT EXISTS credit_rating VARCHAR(30)",
        "ALTER TABLE fund_bond_holdings ADD COLUMN IF NOT EXISTS rating_type VARCHAR(30)",
        "ALTER TABLE fund_bond_holdings ADD COLUMN IF NOT EXISTS maturity_date DATE",
        "ALTER TABLE fund_bond_holdings ADD COLUMN IF NOT EXISTS coupon_rate DECIMAL(10, 8)",
        "ALTER TABLE fund_bond_holdings ADD COLUMN IF NOT EXISTS metadata_source TEXT",
        "ALTER TABLE fund_bond_holdings ADD COLUMN IF NOT EXISTS metadata_url TEXT",
        "ALTER TABLE fund_bond_holdings ADD COLUMN IF NOT EXISTS metadata_status VARCHAR(30) NOT NULL DEFAULT 'unavailable'",
        """INSERT INTO research_report_managers (
                report_id, manager_id, manager_name, source, confirmed_at
            )
            SELECT
                report.id,
                report.manager_id,
                COALESCE(NULLIF(report.manager_name, ''), manager.name),
                'legacy_research_reports.manager_id',
                COALESCE(report.updated_at, report.created_at, NOW())
            FROM research_reports report
            JOIN managers manager ON manager.wind_code = report.manager_id
            WHERE NULLIF(report.manager_id, '') IS NOT NULL
            ON CONFLICT (report_id, manager_id) DO NOTHING""",
    ]

    try:
        with engine.connect() as conn:
            for sql in tables:
                conn.execute(text(sql))
            for sql in migrations:
                conn.execute(text(sql))
            for sql in indexes:
                conn.execute(text(sql))
            conn.commit()
        logger.info(f"Database tables initialized: {len(tables)} tables, {len(indexes)} indexes")
        _initialized_database_url = database_url
        return True
    except Exception as e:
        logger.error(f"Database init failed: {e}")
        return False
