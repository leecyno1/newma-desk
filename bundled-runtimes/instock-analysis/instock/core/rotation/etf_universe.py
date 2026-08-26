#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""SW 2021 level-1 industry ETF universe used by the rotation module."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from instock.core.industry_taxonomy import (
    SW_2021_L1_INDEX_CODES,
    SW_2021_L1_INDUSTRIES,
)


@dataclass(frozen=True)
class SectorETF:
    code: str
    name: str
    industry: str
    industry_aliases: Tuple[str, ...]
    proxy_type: str = "direct"
    proxy_note: str = ""
    signal_code: str = ""
    signal_name: str = ""

    @property
    def resolved_signal_code(self) -> str:
        return self.signal_code or SW_2021_L1_INDEX_CODES.get(self.industry, self.code)

    @property
    def resolved_signal_name(self) -> str:
        if self.signal_name:
            return self.signal_name
        if self.industry in SW_2021_L1_INDEX_CODES:
            return f"申万{self.industry}指数"
        return self.name

    @property
    def has_industry_index_signal(self) -> bool:
        return self.resolved_signal_code != self.code


DEFAULT_SECTOR_ETFS: Tuple[SectorETF, ...] = (
    SectorETF("159825", "农业ETF", "农林牧渔", ("农林牧渔", "农业", "养殖", "种植")),
    SectorETF("159870", "化工ETF", "基础化工", ("基础化工", "化工", "化学原料", "化学制品")),
    SectorETF("515210", "钢铁ETF", "钢铁", ("钢铁", "普钢", "特钢")),
    SectorETF("512400", "有色金属ETF", "有色金属", ("有色金属", "贵金属", "工业金属", "小金属")),
    SectorETF("515260", "电子ETF", "电子", ("电子", "半导体", "消费电子", "元件")),
    SectorETF("516110", "汽车ETF", "汽车", ("汽车", "汽车零部件", "乘用车", "商用车")),
    SectorETF("159996", "家电ETF", "家用电器", ("家用电器", "家电")),
    SectorETF("515170", "食品饮料ETF", "食品饮料", ("食品饮料", "食品", "饮料", "白酒")),
    SectorETF(
        "517880", "品牌消费ETF", "纺织服饰", ("纺织服饰", "纺织制造", "服装家纺", "饰品"),
        "thematic_proxy", "暂无纯纺织服饰一级行业 ETF，使用品牌消费 ETF 代理。",
    ),
    SectorETF(
        "159936", "可选消费ETF", "轻工制造", ("轻工制造", "家居用品", "造纸", "包装印刷"),
        "thematic_proxy", "暂无纯轻工制造一级行业 ETF，使用可选消费 ETF 代理家居与耐用消费暴露。",
    ),
    SectorETF("512010", "医药ETF", "医药生物", ("医药生物", "医药", "生物制品", "化学制药", "中药")),
    SectorETF("159301", "公用事业ETF", "公用事业", ("公用事业", "电力", "燃气", "水务")),
    SectorETF("159666", "交通运输ETF", "交通运输", ("交通运输", "物流", "航运港口", "铁路公路", "航空机场")),
    SectorETF("512200", "房地产ETF", "房地产", ("房地产", "住宅开发", "房屋建设", "物业管理")),
    SectorETF(
        "159725", "线上消费ETF", "商贸零售", ("商贸零售", "互联网电商", "商业物业经营", "专业连锁"),
        "thematic_proxy", "暂无纯商贸零售一级行业 ETF，使用线上消费 ETF 代理零售与电商暴露。",
    ),
    SectorETF("159766", "旅游ETF", "社会服务", ("社会服务", "旅游", "酒店餐饮", "景点")),
    SectorETF(
        "510210", "上证指数ETF", "综合", ("综合", "综合Ⅱ"),
        "broad_market_proxy", "综合行业缺少可交易的纯行业 ETF，使用上证指数 ETF 作为广泛市场代理。",
    ),
    SectorETF("159745", "建材ETF", "建筑材料", ("建筑材料", "建材", "水泥", "玻璃玻纤")),
    SectorETF("516970", "基建ETF", "建筑装饰", ("建筑装饰", "基础建设", "基建", "工程咨询")),
    SectorETF(
        "516160", "新能源ETF", "电力设备", ("电力设备", "光伏设备", "风电设备", "电池"),
        "thematic_proxy", "暂无成熟的纯电力设备一级行业 ETF，使用新能源 ETF 代理主要电力设备暴露。",
    ),
    SectorETF("512660", "军工ETF", "国防军工", ("国防军工", "军工", "兵装", "航空", "航天", "船舶")),
    SectorETF("512720", "计算机ETF", "计算机", ("计算机", "软件", "IT服务")),
    SectorETF("512980", "传媒ETF", "传媒", ("传媒", "游戏", "影视", "出版")),
    SectorETF("515880", "通信ETF", "通信", ("通信", "电信运营", "通信设备")),
    SectorETF("512800", "银行ETF", "银行", ("银行",)),
    SectorETF("512070", "证券保险ETF", "非银金融", ("非银金融", "证券", "保险", "多元金融")),
    SectorETF("516960", "机械ETF", "机械设备", ("机械设备", "工程机械", "专用设备", "通用设备")),
    SectorETF("515220", "煤炭ETF", "煤炭", ("煤炭", "焦炭")),
    SectorETF("561360", "石油ETF", "石油石化", ("石油石化", "油气开采", "炼化及贸易", "油服工程")),
    SectorETF("512580", "环保ETF", "环保", ("环保", "环境治理", "环保设备")),
    SectorETF(
        "561130", "国货ETF", "美容护理", ("美容护理", "化妆品", "个护用品", "医疗美容"),
        "thematic_proxy", "暂无纯美容护理一级行业 ETF，使用国货 ETF 代理化妆品与个人护理暴露。",
    ),
)
