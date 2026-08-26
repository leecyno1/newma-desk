"""基金分类目录 Module。

集中定义策略族谱、同类组和可核验的指数别名；不包含任何演示基金。
"""
import re
from typing import Any, Dict, List, Optional


class FundClassificationCatalog:
    """标准分类定义的唯一来源。"""

    VERSION = "fund_classification_catalog_v14"

    STRATEGY_FAMILIES: List[Dict[str, Any]] = [
        {
            "id": "strategy-family-active-equity-core",
            "key": "active_equity_core",
            "name": "主动权益-宽基参考",
            "asset_class": "equity",
            "active_passive": "active",
            "evaluation_profile_key": "active_equity",
            "compatible_fund_types": ["stock", "股票型", "普通股票型"],
            "style_tags": ["主动权益", "宽基参考"],
        },
        {
            "id": "strategy-family-active-equity-sector",
            "key": "active_equity_sector",
            "name": "主动权益-行业/主题",
            "asset_class": "equity",
            "active_passive": "active",
            "evaluation_profile_key": "active_equity",
            "compatible_fund_types": ["stock", "股票型", "普通股票型", "hybrid", "偏股混合型", "偏股混合"],
            "style_tags": ["主动权益", "行业", "主题"],
        },
        {
            "id": "strategy-family-active-equity-cross-market",
            "key": "active_equity_cross_market",
            "name": "主动权益-沪港深",
            "asset_class": "equity",
            "active_passive": "active",
            "evaluation_profile_key": "active_equity",
            "compatible_fund_types": ["stock", "股票型", "普通股票型"],
            "style_tags": ["主动权益", "沪港深", "跨市场"],
        },
        {
            "id": "strategy-family-fixed-income-credit",
            "key": "fixed_income_credit",
            "name": "固收-信用债/产业债",
            "asset_class": "fixed_income",
            "active_passive": "active",
            "evaluation_profile_key": "fixed_income",
            "compatible_fund_types": ["bond", "债券型", "中长期纯债型", "短期纯债型", "混合债券型", "纯债"],
            "style_tags": ["固收", "信用债", "产业债"],
        },
        {
            "id": "strategy-family-fixed-income-general",
            "key": "fixed_income_general",
            "name": "固收-综合债券",
            "asset_class": "fixed_income",
            "active_passive": "active",
            "evaluation_profile_key": "fixed_income",
            "compatible_fund_types": ["bond", "债券型", "中长期纯债型", "短期纯债型", "混合债券型", "纯债"],
            "style_tags": ["固收", "纯债", "综合债券"],
        },
        {
            "id": "strategy-family-fixed-income-equity-allocation",
            "key": "fixed_income_equity_allocation",
            "name": "债券型-含权益配置",
            "asset_class": "fixed_income",
            "active_passive": "active",
            "evaluation_profile_key": "fixed_income_plus",
            "compatible_fund_types": ["bond", "债券型", "混合债券型", "强化收益型", "稳健增长型"],
            "style_tags": ["固收", "含权益配置", "收益增强"],
        },
        {
            "id": "strategy-family-index-broad",
            "key": "index_broad",
            "name": "指数-权益宽基",
            "asset_class": "index",
            "active_passive": "passive",
            "evaluation_profile_key": "index_fund",
            "compatible_fund_types": ["index", "指数型", "被动指数型", "ETF", "ETF联接"],
            "style_tags": ["指数", "宽基", "被动"],
        },
        {
            "id": "strategy-family-index-sector",
            "key": "index_sector",
            "name": "指数-行业/主题",
            "asset_class": "index",
            "active_passive": "passive",
            "evaluation_profile_key": "index_fund",
            "compatible_fund_types": ["index", "指数型", "被动指数型", "ETF", "ETF联接"],
            "style_tags": ["指数", "行业", "主题", "被动"],
        },
        {
            "id": "strategy-family-index-fixed-income",
            "key": "index_fixed_income",
            "name": "指数-固定收益",
            "asset_class": "fixed_income",
            "active_passive": "passive",
            "evaluation_profile_key": "index_fund",
            "compatible_fund_types": ["指数型", "被动指数型", "债券指数", "同业存单指数"],
            "style_tags": ["指数", "固定收益", "被动"],
        },
        {
            "id": "strategy-family-index-enhanced",
            "key": "index_enhanced",
            "name": "指数-增强",
            "asset_class": "index",
            "active_passive": "active",
            "evaluation_profile_key": "index_enhanced",
            "compatible_fund_types": ["index", "指数型", "增强指数型", "指数增强"],
            "style_tags": ["指数", "增强", "主动"],
        },
        {
            "id": "strategy-family-qdii-equity",
            "key": "qdii_equity",
            "name": "QDII-主动权益",
            "asset_class": "global",
            "active_passive": "active",
            "evaluation_profile_key": "qdii_equity",
            "compatible_fund_types": ["qdii", "QDII", "国际(QDII)", "海外基金"],
            "style_tags": ["QDII", "海外权益", "主动管理", "汇率"],
        },
        {
            "id": "strategy-family-qdii-bond",
            "key": "qdii_bond",
            "name": "QDII-债券",
            "asset_class": "global",
            "active_passive": "active",
            "evaluation_profile_key": "qdii_bond",
            "compatible_fund_types": ["qdii", "QDII", "国际(QDII)", "海外基金"],
            "style_tags": ["QDII", "海外债券", "主动管理", "汇率"],
        },
        {
            "id": "strategy-family-qdii-multi-asset",
            "key": "qdii_multi_asset",
            "name": "QDII-多资产",
            "asset_class": "global",
            "active_passive": "active",
            "evaluation_profile_key": "qdii_multi_asset",
            "compatible_fund_types": ["qdii", "QDII", "国际(QDII)", "海外基金"],
            "style_tags": ["QDII", "海外多资产", "配置", "汇率"],
        },
        {
            "id": "strategy-family-qdii-index",
            "key": "qdii_index",
            "name": "QDII-被动指数",
            "asset_class": "global",
            "active_passive": "passive",
            "evaluation_profile_key": "qdii_index",
            "compatible_fund_types": ["qdii", "QDII", "国际(QDII)", "海外基金"],
            "style_tags": ["QDII", "海外指数", "被动", "人民币计价", "汇率"],
        },
        {
            "id": "strategy-family-cash-management",
            "key": "cash_management",
            "name": "货币-现金管理",
            "asset_class": "money_market",
            "active_passive": "active",
            "evaluation_profile_key": "money_market",
            "compatible_fund_types": ["money", "货币型", "货币基金", "现金管理"],
            "style_tags": ["货币", "现金管理", "流动性"],
        },
        {
            "id": "strategy-family-multi-asset-allocation",
            "key": "multi_asset_allocation",
            "name": "多资产-配置",
            "asset_class": "multi_asset",
            "active_passive": "active",
            "evaluation_profile_key": "multi_asset",
            "compatible_fund_types": ["hybrid", "混合型", "灵活配置型", "平衡混合型"],
            "style_tags": ["多资产", "配置", "平衡"],
        },
        {
            "id": "strategy-family-mixed-equity-allocation",
            "key": "mixed_equity_allocation",
            "name": "混合型-偏股配置",
            "asset_class": "multi_asset",
            "active_passive": "active",
            "evaluation_profile_key": "multi_asset_equity",
            "compatible_fund_types": ["hybrid", "混合型", "灵活配置型", "偏股混合型"],
            "style_tags": ["混合型", "偏股", "权益配置"],
        },
        {
            "id": "strategy-family-mixed-balanced-allocation",
            "key": "mixed_balanced_allocation",
            "name": "混合型-平衡配置",
            "asset_class": "multi_asset",
            "active_passive": "active",
            "evaluation_profile_key": "multi_asset_balanced",
            "compatible_fund_types": ["hybrid", "混合型", "灵活配置型", "平衡混合型"],
            "style_tags": ["混合型", "平衡", "股债配置"],
        },
        {
            "id": "strategy-family-mixed-bond-allocation",
            "key": "mixed_bond_allocation",
            "name": "混合型-偏债配置",
            "asset_class": "multi_asset",
            "active_passive": "active",
            "evaluation_profile_key": "multi_asset_bond",
            "compatible_fund_types": ["hybrid", "混合型", "灵活配置型", "偏债混合型"],
            "style_tags": ["混合型", "偏债", "稳健配置"],
        },
        {
            "id": "strategy-family-fof-equity-allocation",
            "key": "fof_equity_allocation",
            "name": "FOF-偏股配置",
            "asset_class": "fof",
            "active_passive": "active",
            "evaluation_profile_key": "fof_equity",
            "compatible_fund_types": ["FOF", "基金中基金", "混合型"],
            "style_tags": ["FOF", "偏股配置", "底层基金穿透"],
        },
        {
            "id": "strategy-family-fof-balanced-allocation",
            "key": "fof_balanced_allocation",
            "name": "FOF-平衡配置",
            "asset_class": "fof",
            "active_passive": "active",
            "evaluation_profile_key": "fof_balanced",
            "compatible_fund_types": ["FOF", "基金中基金", "混合型"],
            "style_tags": ["FOF", "平衡配置", "底层基金穿透"],
        },
        {
            "id": "strategy-family-fof-bond-allocation",
            "key": "fof_bond_allocation",
            "name": "FOF-偏债配置",
            "asset_class": "fof",
            "active_passive": "active",
            "evaluation_profile_key": "fof_bond",
            "compatible_fund_types": ["FOF", "基金中基金", "混合型"],
            "style_tags": ["FOF", "偏债配置", "底层基金穿透"],
        },
    ]

    TRACKED_INDEX_RULES: List[Dict[str, Any]] = [
        {
            "aliases": ["沪深300指数"],
            "benchmark_code": "000300.SH",
            "benchmark_name": "沪深300",
            "peer_group_key": "peer-index-hs300",
            "strategy_family_key": "index_broad",
            "asset_class": "index",
        },
        {
            "aliases": ["中证500指数", "中证小盘500指数"],
            "benchmark_code": "000905.SH",
            "benchmark_name": "中证500",
            "peer_group_key": "peer-index-csi500",
            "strategy_family_key": "index_broad",
            "asset_class": "index",
        },
        {
            "aliases": ["中证A500指数"],
            "benchmark_code": "000510.SH",
            "benchmark_name": "中证A500",
            "peer_group_key": "peer-index-csi-a500",
            "strategy_family_key": "index_broad",
            "asset_class": "index",
        },
        {
            "aliases": ["中证1000指数"],
            "benchmark_code": "000852.SH",
            "benchmark_name": "中证1000",
            "peer_group_key": "peer-index-csi1000",
            "strategy_family_key": "index_broad",
            "asset_class": "index",
        },
        {
            "aliases": ["中证2000指数"],
            "benchmark_code": "932000.CSI",
            "benchmark_name": "中证2000",
            "peer_group_key": "peer-index-csi2000",
            "strategy_family_key": "index_broad",
            "asset_class": "index",
        },
        {
            "aliases": ["中证800指数"],
            "benchmark_code": "000906.SH",
            "benchmark_name": "中证800",
            "peer_group_key": "peer-index-csi800",
            "strategy_family_key": "index_broad",
            "asset_class": "index",
        },
        {
            "aliases": ["中证A50指数"],
            "benchmark_code": "930050.CSI",
            "benchmark_name": "中证A50",
            "peer_group_key": "peer-index-csi-a50",
            "strategy_family_key": "index_broad",
            "asset_class": "index",
        },
        {
            "aliases": ["创业板指数", "创业板指"],
            "benchmark_code": "399006.SZ",
            "benchmark_name": "创业板指",
            "peer_group_key": "peer-index-chinext",
            "strategy_family_key": "index_broad",
            "asset_class": "index",
        },
        {
            "aliases": ["上证科创板50成份指数", "科创50指数"],
            "benchmark_code": "000688.SH",
            "benchmark_name": "科创50",
            "peer_group_key": "peer-index-star50",
            "strategy_family_key": "index_broad",
            "asset_class": "index",
        },
        {
            "aliases": ["上证180指数", "上海证券交易所180指数"],
            "benchmark_code": "000010.SH",
            "benchmark_name": "上证180",
            "peer_group_key": "peer-index-sse180",
            "strategy_family_key": "index_broad",
            "asset_class": "index",
        },
        {
            "aliases": ["上证50指数", "上海证券交易所50成份指数"],
            "benchmark_code": "000016.SH",
            "benchmark_name": "上证50",
            "peer_group_key": "peer-index-sse50",
            "strategy_family_key": "index_broad",
            "asset_class": "index",
        },
        {
            "aliases": ["沪深300医药卫生指数", "300医药指数"],
            "benchmark_code": "000913.SH",
            "benchmark_name": "沪深300医药卫生",
            "peer_group_key": "peer-index-hs300-health-care",
            "strategy_family_key": "index_sector",
            "asset_class": "index",
        },
        {
            "aliases": ["中证环保产业指数"],
            "benchmark_code": "000827.SH",
            "benchmark_name": "中证环保产业",
            "peer_group_key": "peer-index-csi-environmental-protection",
            "strategy_family_key": "index_sector",
            "asset_class": "index",
        },
        {
            "aliases": ["中证医药卫生指数"],
            "benchmark_code": "000933.SH",
            "benchmark_name": "中证医药卫生",
            "peer_group_key": "peer-index-csi-health-care",
            "strategy_family_key": "index_sector",
            "asset_class": "index",
        },
        {
            "aliases": ["中证新能源汽车指数"],
            "benchmark_code": "399976.SZ",
            "benchmark_name": "中证新能源汽车",
            "peer_group_key": "peer-index-csi-new-energy-vehicle",
            "strategy_family_key": "index_sector",
            "asset_class": "index",
        },
        {
            "aliases": ["中证新兴产业指数"],
            "benchmark_code": "000964.CSI",
            "benchmark_name": "中证新兴产业",
            "peer_group_key": "peer-index-csi-emerging-industry",
            "strategy_family_key": "index_sector",
            "asset_class": "index",
        },
        {
            "aliases": ["中证服务业指数"],
            "benchmark_code": "H30074.CSI",
            "benchmark_name": "中证服务业",
            "peer_group_key": "peer-index-csi-service-industry",
            "strategy_family_key": "index_sector",
            "asset_class": "index",
        },
        {
            "aliases": ["沪深300金融地产指数"],
            "benchmark_code": "000914.SH",
            "benchmark_name": "沪深300金融地产",
            "peer_group_key": "peer-index-hs300-financial-real-estate",
            "strategy_family_key": "index_sector",
            "asset_class": "index",
        },
        {
            "aliases": ["中国战略新兴产业成份指数"],
            "benchmark_code": "000171.CSI",
            "benchmark_name": "中国战略新兴产业成份",
            "peer_group_key": "peer-index-china-strategic-emerging",
            "strategy_family_key": "index_sector",
            "asset_class": "index",
        },
        {
            "aliases": ["中证全指信息技术指数"],
            "benchmark_code": "000993.SH",
            "benchmark_name": "中证全指信息技术",
            "peer_group_key": "peer-index-csi-all-share-information-technology",
            "strategy_family_key": "index_sector",
            "asset_class": "index",
        },
        {
            "aliases": ["中证TMT产业主题指数"],
            "benchmark_code": "000998.CSI",
            "benchmark_name": "中证TMT产业主题",
            "peer_group_key": "peer-index-csi-tmt-industry",
            "strategy_family_key": "index_sector",
            "asset_class": "index",
        },
        {
            "aliases": ["上证高端装备制造60指数"],
            "benchmark_code": "000097.SH",
            "benchmark_name": "上证高端装备制造60",
            "peer_group_key": "peer-index-sse-high-end-equipment",
            "strategy_family_key": "index_sector",
            "asset_class": "index",
        },
        {
            "aliases": ["国证航天军工指数"],
            "benchmark_code": "399368.SZ",
            "benchmark_name": "国证航天军工",
            "peer_group_key": "peer-index-cninfo-aerospace-defense",
            "strategy_family_key": "index_sector",
            "asset_class": "index",
        },
        {
            "aliases": ["中证国有企业改革指数"],
            "benchmark_code": "399974.SZ",
            "benchmark_name": "中证国有企业改革",
            "peer_group_key": "peer-index-csi-soe-reform",
            "strategy_family_key": "index_sector",
            "asset_class": "index",
        },
        {
            "aliases": ["中证800成长指数"],
            "benchmark_code": "H30355.CSI",
            "benchmark_name": "中证800成长",
            "peer_group_key": "peer-index-csi800-growth",
            "strategy_family_key": "index_sector",
            "asset_class": "index",
        },
        {
            "aliases": ["中证内地消费主题指数"],
            "benchmark_code": "000942.CSI",
            "benchmark_name": "中证内地消费主题",
            "peer_group_key": "peer-index-csi-mainland-consumption",
            "strategy_family_key": "index_sector",
            "asset_class": "index",
        },
        {
            "aliases": ["中证可选消费指数"],
            "benchmark_code": "000931.CSI",
            "benchmark_name": "中证可选消费",
            "peer_group_key": "peer-index-csi-consumer-discretionary",
            "strategy_family_key": "index_sector",
            "asset_class": "index",
        },
        {
            "aliases": ["中证主要消费指数"],
            "benchmark_code": "000932.SH",
            "benchmark_name": "中证主要消费",
            "peer_group_key": "peer-index-csi-consumer-staples",
            "strategy_family_key": "index_sector",
            "asset_class": "index",
        },
        {
            "aliases": ["中证移动互联网指数"],
            "benchmark_code": "399970.SZ",
            "benchmark_name": "中证移动互联网",
            "peer_group_key": "peer-index-csi-mobile-internet",
            "strategy_family_key": "index_sector",
            "asset_class": "index",
        },
        {
            "aliases": ["中证周期100指数"],
            "benchmark_code": "931355.CSI",
            "benchmark_name": "中证周期100",
            "peer_group_key": "peer-index-csi-cyclical-100",
            "strategy_family_key": "index_sector",
            "asset_class": "index",
        },
        {
            "aliases": ["中证科技100指数"],
            "benchmark_code": "931187.CSI",
            "benchmark_name": "中证科技100",
            "peer_group_key": "peer-index-csi-technology-100",
            "strategy_family_key": "index_sector",
            "asset_class": "index",
        },
        {
            "aliases": ["中证沪港深高股息精选指数"],
            "benchmark_code": "930836.CSI",
            "benchmark_name": "中证沪港深高股息精选",
            "peer_group_key": "peer-index-csi-shs-high-dividend",
            "strategy_family_key": "index_sector",
            "asset_class": "index",
        },
        {
            "aliases": ["中证港股通综合指数"],
            "benchmark_code": "930930.CSI",
            "benchmark_name": "中证港股通综合",
            "peer_group_key": "peer-index-csi-hk-connect-composite",
            "strategy_family_key": "index_sector",
            "asset_class": "index",
        },
        {
            "aliases": ["中证国有企业综合指数"],
            "benchmark_code": "000955.CSI",
            "benchmark_name": "中证国有企业综合",
            "peer_group_key": "peer-index-csi-state-owned-enterprises",
            "strategy_family_key": "index_sector",
            "asset_class": "index",
        },
        {
            "aliases": ["中证国新央企综合指数"],
            "benchmark_code": "932004.CSI",
            "benchmark_name": "中证国新央企综合",
            "peer_group_key": "peer-index-csi-central-enterprises",
            "strategy_family_key": "index_sector",
            "asset_class": "index",
        },
        {
            "aliases": ["中证上游资源产业指数"],
            "benchmark_code": "000961.CSI",
            "benchmark_name": "中证上游资源产业",
            "peer_group_key": "peer-index-csi-upstream-resources",
            "strategy_family_key": "index_sector",
            "asset_class": "index",
        },
        {
            "aliases": ["中证同业存单AAA指数"],
            "benchmark_code": "931059.CSI",
            "benchmark_name": "中证同业存单AAA",
            "peer_group_key": "peer-index-cd-aaa",
            "strategy_family_key": "index_fixed_income",
            "asset_class": "fixed_income",
            "required_contract_term": "债券",
        },
    ]

    QDII_INDEX_RULES: List[Dict[str, Any]] = [
        {
            "aliases": ["纳斯达克100指数"],
            "benchmark_code": "NDX.CNY",
            "benchmark_name": "人民币计价纳斯达克100指数",
            "peer_group_key": "peer-qdii-index-ndx-cny",
            "strategy_family_key": "qdii_index",
            "asset_class": "global",
            "required_weight": 100.0,
            "currency_basis_terms": ["汇率调整", "汇率折算", "人民币计价"],
        },
    ]

    ENHANCED_INDEX_RULES: List[Dict[str, Any]] = [
        {
            "aliases": list(rule["aliases"]),
            "benchmark_code": rule["benchmark_code"],
            "benchmark_name": rule["benchmark_name"],
            "peer_group_key": f"peer-index-enhanced-{rule['peer_group_key'].removeprefix('peer-index-')}",
        }
        for rule in TRACKED_INDEX_RULES
        if rule.get("strategy_family_key") == "index_broad"
        and rule["benchmark_code"] in {
            "000300.SH",
            "000905.SH",
            "000510.SH",
            "000852.SH",
            "000906.SH",
            "932000.CSI",
            "930050.CSI",
            "399006.SZ",
            "000688.SH",
            "000016.SH",
        }
    ]

    ACTIVE_EQUITY_REFERENCE_RULES: List[Dict[str, Any]] = [
        {
            "aliases": ["沪深300指数"],
            "benchmark_code": "000300.SH",
            "benchmark_name": "沪深300",
            "peer_group_key": "peer-active-equity-stock-hs300",
        },
        {
            "aliases": ["中证500指数", "中证小盘500指数"],
            "benchmark_code": "000905.SH",
            "benchmark_name": "中证500",
            "peer_group_key": "peer-active-equity-stock-csi500",
        },
        {
            "aliases": ["中证800指数"],
            "benchmark_code": "000906.SH",
            "benchmark_name": "中证800",
            "peer_group_key": "peer-active-equity-stock-csi800",
        },
        {
            "aliases": ["中证1000指数"],
            "benchmark_code": "000852.SH",
            "benchmark_name": "中证1000",
            "peer_group_key": "peer-active-equity-stock-csi1000",
        },
    ]

    ACTIVE_EQUITY_SECTOR_RULES: List[Dict[str, Any]] = [
        {
            "aliases": ["中证上游资源产业指数"],
            "benchmark_code": "SECTOR-RESOURCE",
            "benchmark_name": "资源产业",
            "peer_group_key": "peer-active-equity-sector-resource",
        },
        {
            "aliases": ["中证全指信息技术指数", "中证全指电信业务指数"],
            "benchmark_code": "SECTOR-TECH-MEDIA",
            "benchmark_name": "信息技术/传媒",
            "peer_group_key": "peer-active-equity-sector-tech-media",
        },
        {
            "aliases": ["中证内地消费主题指数"],
            "benchmark_code": "SECTOR-CONSUMPTION",
            "benchmark_name": "消费主题",
            "peer_group_key": "peer-active-equity-sector-consumption",
        },
        {
            "aliases": ["中证新能源指数", "中证新能源汽车指数", "中证港股通能源综合指数"],
            "benchmark_code": "SECTOR-NEW-ENERGY",
            "benchmark_name": "新能源",
            "peer_group_key": "peer-active-equity-sector-new-energy",
        },
    ]

    CHINABOND_CONTRACT_BASES: Dict[str, str] = {
        "composite": "中债综合指数",
        "new_composite": "中债新综合指数",
        "total": "中债总指数",
    }
    CHINABOND_CONTRACT_PRICE_RETURNS: Dict[str, str] = {
        "full_price": "全价",
        "wealth": "财富",
        "total_wealth": "总财富合同写法",
        "unspecified": "价格口径未注明",
    }
    CHINABOND_CONTRACT_TENORS: Dict[str, str] = {
        "all": "全期限",
        "under_1y": "1年以下",
        "1_3y": "1—3年",
        "0_3y": "0—3年",
        "0_5y": "0—5年",
        "3_5y": "3—5年",
        "1_5y": "1—5年",
        "3_7y": "3—7年",
        "5_10y": "5—10年",
        "7_10y": "7—10年",
        "over_10y": "10年以上",
    }
    CHINABOND_CONTRACT_BUCKETS = (
        ("composite", "full_price", "all"),
        ("composite", "unspecified", "all"),
        ("composite", "wealth", "all"),
        ("composite", "total_wealth", "all"),
        ("composite", "full_price", "under_1y"),
        ("composite", "wealth", "under_1y"),
        ("composite", "unspecified", "under_1y"),
        ("composite", "full_price", "1_3y"),
        ("composite", "wealth", "1_3y"),
        ("composite", "wealth", "0_3y"),
        ("composite", "wealth", "0_5y"),
        ("composite", "wealth", "1_5y"),
        ("composite", "full_price", "3_5y"),
        ("composite", "wealth", "3_5y"),
        ("new_composite", "full_price", "all"),
        ("new_composite", "wealth", "all"),
        ("new_composite", "unspecified", "all"),
        ("new_composite", "full_price", "under_1y"),
        ("new_composite", "full_price", "1_3y"),
        ("new_composite", "wealth", "1_3y"),
        ("new_composite", "wealth", "3_5y"),
        ("total", "full_price", "all"),
        ("total", "wealth", "all"),
        ("total", "unspecified", "all"),
        ("total", "full_price", "1_3y"),
        ("total", "wealth", "1_3y"),
        ("total", "unspecified", "1_3y"),
    )

    @classmethod
    def _chinabond_contract_rule(
        cls,
        base_key: str,
        price_return_key: str,
        tenor_key: str,
    ) -> Dict[str, Any]:
        legacy_bucket = (base_key, price_return_key, tenor_key) == (
            "composite",
            "full_price",
            "all",
        )
        slug = f"{base_key.replace('_', '-')}-{price_return_key.replace('_', '-')}-{tenor_key.replace('_', '-')}"
        benchmark_code = (
            "CONTRACT-CBA-COMPOSITE-FULL-PRICE"
            if legacy_bucket
            else f"CONTRACT-CBA-{slug.upper()}"
        )
        peer_group_key = (
            "peer-fixed-income-chinabond-composite-full-price"
            if legacy_bucket
            else f"peer-fixed-income-chinabond-{slug}"
        )
        benchmark_name = "·".join((
            cls.CHINABOND_CONTRACT_BASES[base_key],
            cls.CHINABOND_CONTRACT_PRICE_RETURNS[price_return_key],
            cls.CHINABOND_CONTRACT_TENORS[tenor_key],
        ))
        return {
            "benchmark_code": benchmark_code,
            "benchmark_name": benchmark_name,
            "benchmark_type": "contract_benchmark_bucket",
            "peer_group_key": peer_group_key,
            "contract_dimensions": {
                "base_index": base_key,
                "price_return": price_return_key,
                "tenor": tenor_key,
            },
        }

    CHINABOND_CONTRACT_REFERENCE_RULES: List[Dict[str, Any]] = []

    ACTIVE_FIXED_INCOME_REFERENCE_RULES: List[Dict[str, Any]] = [
        {
            "aliases": ["中证全债指数"],
            "benchmark_code": "H11001.CSI",
            "benchmark_name": "中证全债",
            "peer_group_key": "peer-fixed-income-csi-total-bond",
        },
        {
            "aliases": ["中证综合债指数", "中证综合债券指数"],
            "benchmark_code": "H11009.CSI",
            "benchmark_name": "中证综合债",
            "peer_group_key": "peer-fixed-income-csi-composite-bond",
        },
        {
            "aliases": ["上证国债指数", "上海证券交易所国债指数", "中国国债指数"],
            "benchmark_code": "000012.SH",
            "benchmark_name": "上证国债",
            "peer_group_key": "peer-fixed-income-sse-treasury",
        },
    ]

    @classmethod
    def resolve_declared_equity_benchmark(cls, declared_benchmark: str) -> Optional[Dict[str, Any]]:
        """从合同复合基准中提取可核验的权益指数成分，供行业归因使用。"""
        text = str(declared_benchmark or "").strip()
        if not text:
            return None

        matches = []
        for rule in cls.TRACKED_INDEX_RULES:
            if rule.get("asset_class") != "index":
                continue
            matched_alias = next((alias for alias in rule.get("aliases", []) if alias in text), None)
            if not matched_alias:
                continue
            weight_match = re.search(
                rf"{re.escape(matched_alias)}(?:[（(][^）)]*[）)])?(?:收益率)?\s*[×xX*]\s*(\d+(?:\.\d+)?)\s*%",
                text,
            )
            matches.append({
                "benchmark_code": rule["benchmark_code"],
                "benchmark_name": rule["benchmark_name"],
                "declared_weight": float(weight_match.group(1)) / 100 if weight_match else None,
                "declared_benchmark": text,
            })

        unique = {item["benchmark_code"]: item for item in matches}
        if len(unique) == 1:
            return next(iter(unique.values()))
        if len(unique) > 1 and all(item.get("declared_weight") is not None for item in unique.values()):
            components = list(unique.values())
            return {
                "benchmark_code": components[0]["benchmark_code"],
                "benchmark_name": "合同权益指数复合参照",
                "declared_weight": round(sum(float(item["declared_weight"]) for item in components), 6),
                "declared_benchmark": text,
                "benchmark_basis": "contract_equity_composite",
                "equity_components": [
                    {
                        "code": item["benchmark_code"],
                        "name": item["benchmark_name"],
                        "weight": item["declared_weight"],
                    }
                    for item in components
                ],
            }
        return None

    @classmethod
    def family_meta(cls) -> Dict[str, Dict[str, Any]]:
        return {
            item["key"]: {
                "asset_class": item["asset_class"],
                "active_passive": item["active_passive"],
                "evaluation_profile_key": item["evaluation_profile_key"],
                "compatible_fund_types": list(item["compatible_fund_types"]),
            }
            for item in cls.STRATEGY_FAMILIES
        }

    @classmethod
    def peer_groups(cls) -> List[Dict[str, Any]]:
        groups = [
            {
                "id": "peer-money-cash-management",
                "key": "peer-money-cash-management",
                "name": "货币-现金管理",
                "strategy_family_key": "cash_management",
                "asset_class": "money_market",
                "active_passive": "active",
                "benchmark_code": "DR007",
                "benchmark_name": "DR007",
                "inclusion_rules": {"legalType": "money_market", "currency": "CNY"},
                "exclusion_rules": {"exclude": ["非货币基金"]},
                "minimum_peer_count": 5,
            }
        ]
        groups.extend([
            {
                "id": "peer-qdii-equity",
                "key": "peer-qdii-equity",
                "name": "QDII-主动权益",
                "strategy_family_key": "qdii_equity",
                "asset_class": "global",
                "active_passive": "active",
                "benchmark_code": "QDII-ACTIVE-EQUITY",
                "benchmark_name": "QDII 主动权益同类组",
                "inclusion_rules": {
                    "legalType": "QDII",
                    "investmentType": "股票型",
                    "contractType": "股票型",
                    "declaredBenchmarkRequired": True,
                },
                "exclusion_rules": {"exclude": ["被动指数型", "增强指数型", "其他型", "合同基准缺失"]},
                "minimum_peer_count": 5,
            },
            {
                "id": "peer-qdii-bond",
                "key": "peer-qdii-bond",
                "name": "QDII-债券",
                "strategy_family_key": "qdii_bond",
                "asset_class": "global",
                "active_passive": "active",
                "benchmark_code": "QDII-ACTIVE-BOND",
                "benchmark_name": "QDII 债券同类组",
                "inclusion_rules": {
                    "legalType": "QDII",
                    "investmentType": "债券型",
                    "contractType": "债券型",
                    "declaredBenchmarkRequired": True,
                },
                "exclusion_rules": {"exclude": ["股票型", "混合型", "其他型", "合同基准缺失"]},
                "minimum_peer_count": 5,
            },
            {
                "id": "peer-qdii-multi-asset",
                "key": "peer-qdii-multi-asset",
                "name": "QDII-多资产",
                "strategy_family_key": "qdii_multi_asset",
                "asset_class": "global",
                "active_passive": "active",
                "benchmark_code": "QDII-ACTIVE-MULTI-ASSET",
                "benchmark_name": "QDII 多资产同类组",
                "inclusion_rules": {
                    "legalType": "QDII",
                    "investmentType": ["混合型", "灵活配置型"],
                    "contractType": "混合型",
                    "declaredBenchmarkRequired": True,
                },
                "exclusion_rules": {"exclude": ["股票型", "债券型", "其他型", "合同基准缺失"]},
                "minimum_peer_count": 5,
            },
            {
                "id": "peer-qdii-index-ndx-cny",
                "key": "peer-qdii-index-ndx-cny",
                "name": "QDII-人民币计价纳斯达克100指数",
                "strategy_family_key": "qdii_index",
                "asset_class": "global",
                "active_passive": "passive",
                "benchmark_code": "NDX.CNY",
                "benchmark_name": "人民币计价纳斯达克100指数",
                "inclusion_rules": {
                    "legalType": "QDII",
                    "investmentType": "被动指数型",
                    "contractType": "股票型",
                    "trackedIndex": "纳斯达克100指数",
                    "trackedIndexWeight": 100,
                    "currencyBasis": "CNY",
                    "declaredBenchmarkRequired": True,
                },
                "exclusion_rules": {
                    "exclude": ["指数权重不是100%", "汇率口径未声明", "指数增强", "非纳斯达克100"],
                },
                "minimum_peer_count": 5,
            },
            {
                "id": "peer-active-equity-cross-market-cn-hk",
                "key": "peer-active-equity-cross-market-cn-hk",
                "name": "主动权益-沪港深",
                "strategy_family_key": "active_equity_cross_market",
                "asset_class": "equity",
                "active_passive": "active",
                "benchmark_code": "CONTRACT-CN-HK-EQUITY",
                "benchmark_name": "合同沪港深复合基准",
                "inclusion_rules": {
                    "legalType": "股票型",
                    "minimumMainlandEquityWeight": 20,
                    "minimumHongKongEquityWeight": 20,
                    "minimumTotalEquityWeight": 80,
                    "maximumDefensiveWeight": 20,
                    "declaredBenchmarkRequired": True,
                },
                "exclusion_rules": {
                    "exclude": ["单一市场基准", "权益权重不足", "合同权重不完整", "未登记指数成分"],
                },
                "minimum_peer_count": 5,
            },
            {
                "id": "peer-fixed-income-equity-allocation",
                "key": "peer-fixed-income-equity-allocation",
                "name": "债券型-含权益配置",
                "strategy_family_key": "fixed_income_equity_allocation",
                "asset_class": "fixed_income",
                "active_passive": "active",
                "benchmark_code": "FIXED-INCOME-EQUITY-20",
                "benchmark_name": "合同基准权益权重>0%且≤20%",
                "inclusion_rules": {"legalType": "债券型", "equityBenchmarkWeightRange": [0, 20], "declaredBenchmarkRequired": True},
                "exclusion_rules": {"exclude": ["可转债主题", "权重不完整", "无法识别资产类别"]},
                "minimum_peer_count": 5,
            },
            {
                "id": "peer-mixed-equity-allocation",
                "key": "peer-mixed-equity-allocation",
                "name": "混合型-偏股配置",
                "strategy_family_key": "mixed_equity_allocation",
                "asset_class": "multi_asset",
                "active_passive": "active",
                "benchmark_code": "MIXED-EQUITY-60",
                "benchmark_name": "合同基准权益权重≥60%",
                "inclusion_rules": {"legalType": "混合型", "minimumEquityBenchmarkWeight": 60, "declaredBenchmarkRequired": True},
                "exclusion_rules": {"exclude": ["权重不完整", "无法识别资产类别"]},
                "minimum_peer_count": 5,
            },
            {
                "id": "peer-mixed-balanced-allocation",
                "key": "peer-mixed-balanced-allocation",
                "name": "混合型-平衡配置",
                "strategy_family_key": "mixed_balanced_allocation",
                "asset_class": "multi_asset",
                "active_passive": "active",
                "benchmark_code": "MIXED-BALANCED-30-60",
                "benchmark_name": "合同基准权益权重>30%且<60%",
                "inclusion_rules": {"legalType": "混合型", "equityBenchmarkWeightRange": [30, 60], "declaredBenchmarkRequired": True},
                "exclusion_rules": {"exclude": ["权重不完整", "无法识别资产类别"]},
                "minimum_peer_count": 5,
            },
            {
                "id": "peer-mixed-bond-allocation",
                "key": "peer-mixed-bond-allocation",
                "name": "混合型-偏债配置",
                "strategy_family_key": "mixed_bond_allocation",
                "asset_class": "multi_asset",
                "active_passive": "active",
                "benchmark_code": "MIXED-BOND-30",
                "benchmark_name": "合同基准权益权重≤30%",
                "inclusion_rules": {"legalType": "混合型", "maximumEquityBenchmarkWeight": 30, "declaredBenchmarkRequired": True},
                "exclusion_rules": {"exclude": ["权重不完整", "无法识别资产类别"]},
                "minimum_peer_count": 5,
            },
            {
                "id": "peer-fof-equity-allocation",
                "key": "peer-fof-equity-allocation",
                "name": "FOF-偏股配置",
                "strategy_family_key": "fof_equity_allocation",
                "asset_class": "fof",
                "active_passive": "active",
                "benchmark_code": "FOF-EQUITY-60",
                "benchmark_name": "FOF 合同基准权益权重≥60%",
                "inclusion_rules": {"productType": "FOF", "minimumEquityBenchmarkWeight": 60, "declaredBenchmarkRequired": True},
                "exclusion_rules": {"exclude": ["非FOF", "权重不完整", "无法识别资产类别"]},
                "minimum_peer_count": 5,
            },
            {
                "id": "peer-fof-balanced-allocation",
                "key": "peer-fof-balanced-allocation",
                "name": "FOF-平衡配置",
                "strategy_family_key": "fof_balanced_allocation",
                "asset_class": "fof",
                "active_passive": "active",
                "benchmark_code": "FOF-BALANCED-30-60",
                "benchmark_name": "FOF 合同基准权益权重>30%且<60%",
                "inclusion_rules": {"productType": "FOF", "equityBenchmarkWeightRange": [30, 60], "declaredBenchmarkRequired": True},
                "exclusion_rules": {"exclude": ["非FOF", "权重不完整", "无法识别资产类别"]},
                "minimum_peer_count": 5,
            },
            {
                "id": "peer-fof-bond-allocation",
                "key": "peer-fof-bond-allocation",
                "name": "FOF-偏债配置",
                "strategy_family_key": "fof_bond_allocation",
                "asset_class": "fof",
                "active_passive": "active",
                "benchmark_code": "FOF-BOND-30",
                "benchmark_name": "FOF 合同基准权益权重≤30%",
                "inclusion_rules": {"productType": "FOF", "maximumEquityBenchmarkWeight": 30, "declaredBenchmarkRequired": True},
                "exclusion_rules": {"exclude": ["非FOF", "权重不完整", "无法识别资产类别"]},
                "minimum_peer_count": 5,
            },
        ])
        for rule in cls.TRACKED_INDEX_RULES:
            groups.append({
                "id": rule["peer_group_key"],
                "key": rule["peer_group_key"],
                "name": f"指数-{rule['benchmark_name']}",
                "strategy_family_key": rule["strategy_family_key"],
                "asset_class": rule["asset_class"],
                "active_passive": "passive",
                "benchmark_code": rule["benchmark_code"],
                "benchmark_name": rule["benchmark_name"],
                "inclusion_rules": {
                    "sameIndex": rule["benchmark_code"],
                    "tracking": "passive",
                    "declaredBenchmarkRequired": True,
                },
                "exclusion_rules": {"exclude": ["指数增强", "非同指数"]},
                "minimum_peer_count": 5,
            })
        for rule in cls.ENHANCED_INDEX_RULES:
            groups.append({
                "id": rule["peer_group_key"],
                "key": rule["peer_group_key"],
                "name": f"指数增强-{rule['benchmark_name']}",
                "strategy_family_key": "index_enhanced",
                "asset_class": "index",
                "active_passive": "active",
                "benchmark_code": rule["benchmark_code"],
                "benchmark_name": rule["benchmark_name"],
                "inclusion_rules": {
                    "investmentType": "增强指数型",
                    "contractType": "股票型",
                    "primaryIndex": rule["benchmark_code"],
                    "minimumPrimaryWeight": 90,
                    "declaredBenchmarkRequired": True,
                },
                "exclusion_rules": {
                    "exclude": ["被动指数", "低于90%指数权重", "多指数基准", "主题指数未登记"],
                },
                "minimum_peer_count": 5,
            })
        for rule in cls.ACTIVE_EQUITY_REFERENCE_RULES:
            groups.append({
                "id": rule["peer_group_key"],
                "key": rule["peer_group_key"],
                "name": f"主动权益-{rule['benchmark_name']}参考",
                "strategy_family_key": "active_equity_core",
                "asset_class": "equity",
                "active_passive": "active",
                "benchmark_code": rule["benchmark_code"],
                "benchmark_name": rule["benchmark_name"],
                "inclusion_rules": {
                    "legalType": "股票型",
                    "primaryEquityReference": rule["benchmark_code"],
                    "minimumPrimaryWeight": 80,
                    "declaredBenchmarkRequired": True,
                },
                "exclusion_rules": {
                    "exclude": ["指数基金", "指数增强", "行业主题", "多权益市场基准"],
                },
                "minimum_peer_count": 5,
            })
        for rule in cls.ACTIVE_EQUITY_SECTOR_RULES:
            groups.append({
                "id": rule["peer_group_key"],
                "key": rule["peer_group_key"],
                "name": f"主动权益-行业/{rule['benchmark_name']}",
                "strategy_family_key": "active_equity_sector",
                "asset_class": "equity",
                "active_passive": "active",
                "benchmark_code": rule["benchmark_code"],
                "benchmark_name": rule["benchmark_name"],
                "inclusion_rules": {"legalType": "股票型", "minimumSectorBenchmarkWeight": 70},
                "exclusion_rules": {"exclude": ["行业基准权重不足", "跨行业基准无法归一"]},
                "minimum_peer_count": 5,
            })
        for rule in cls.ACTIVE_FIXED_INCOME_REFERENCE_RULES:
            groups.append({
                "id": rule["peer_group_key"],
                "key": rule["peer_group_key"],
                "name": f"固收-{rule['benchmark_name']}参考",
                "strategy_family_key": "fixed_income_general",
                "asset_class": "fixed_income",
                "active_passive": "active",
                "benchmark_code": rule["benchmark_code"],
                "benchmark_name": rule["benchmark_name"],
                "inclusion_rules": {
                    "legalType": "债券型",
                    "bondReference": rule["benchmark_code"],
                    "minimumPrimaryWeight": rule.get("minimum_primary_weight", 100),
                    "allowedSecondaryReferences": rule.get("allowed_secondary_references", []),
                    "declaredBenchmarkRequired": True,
                    **(
                        {"contractDimensions": rule["contract_dimensions"]}
                        if rule.get("contract_dimensions")
                        else {}
                    ),
                },
                "exclusion_rules": {
                    "exclude": ["可转债", "二级债", "含权益基准", "多个债券指数", "口径或期限不明"],
                },
                "minimum_peer_count": 5,
            })
        return groups


FundClassificationCatalog.CHINABOND_CONTRACT_REFERENCE_RULES = [
    FundClassificationCatalog._chinabond_contract_rule(base_key, price_return_key, tenor_key)
    for base_key, price_return_key, tenor_key in FundClassificationCatalog.CHINABOND_CONTRACT_BUCKETS
]
for _rule in FundClassificationCatalog.CHINABOND_CONTRACT_REFERENCE_RULES:
    _rule["minimum_primary_weight"] = 80
    _rule["allowed_secondary_references"] = ["存款", "现金", "DR007"]
FundClassificationCatalog.ACTIVE_FIXED_INCOME_REFERENCE_RULES = (
    FundClassificationCatalog.CHINABOND_CONTRACT_REFERENCE_RULES
    + FundClassificationCatalog.ACTIVE_FIXED_INCOME_REFERENCE_RULES
)
