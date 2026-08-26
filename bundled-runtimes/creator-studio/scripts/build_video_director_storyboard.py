#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from video_driver_rules import (
    audio_for_beat,
    explainer_state_for_beat,
    load_driver_rules,
    score_driver,
    transition_for_beat,
    weighted_driver_score,
)

from build_storyboard_template_review_table import review_controls_cell, review_page_script


TEXT_RE = re.compile(r"\s+")
DEFAULT_ROUTER_PATH = Path("configs/video/html_anything_template_router.json")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TEMPLATE_PREVIEW_ROOTS = [
    Path(os.environ.get("HTML_VIDEO_ROOT", str(PROJECT_ROOT / "vendor/reserved/render/html-video"))).expanduser() / "templates",
]


@dataclass
class Asset:
    id: str
    type: str
    heading: str
    summary: str
    rows: list[list[str]] = field(default_factory=list)
    headers: list[str] = field(default_factory=list)
    original_src: str = ""
    local_copy: str = ""
    alt: str = ""


@dataclass
class Section:
    id: str
    heading: str
    level: int
    paragraphs: list[str] = field(default_factory=list)
    asset_refs: list[str] = field(default_factory=list)


def clean_text(text: str) -> str:
    return TEXT_RE.sub(" ", html.unescape(text or "")).strip()


def safe_name(text: str, max_len: int = 40) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", text).strip("_")
    return cleaned[:max_len] or "asset"


def table_rows(el: Any) -> list[list[str]]:
    rows: list[list[str]] = []
    for tr in el.find_all("tr"):
        row = [clean_text(cell.get_text(" ", strip=True)) for cell in tr.find_all(["th", "td"])]
        if any(row):
            rows.append(row)
    return rows


def parse_article(source_html: Path, image_output_dir: Path) -> tuple[dict[str, Any], list[Section], list[Asset]]:
    soup = BeautifulSoup(source_html.read_text(encoding="utf-8", errors="ignore"), "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()

    title = clean_text(soup.title.get_text(" ", strip=True)) if soup.title else source_html.stem
    h1 = soup.find("h1")
    main_heading = clean_text(h1.get_text(" ", strip=True)) if h1 else title

    sections: list[Section] = []
    assets: list[Asset] = []
    current: Section | None = None
    table_index = 0
    image_index = 0

    def ensure_section() -> Section:
        nonlocal current
        if current is None:
            current = Section(id="section_001", heading=main_heading or title, level=1)
            sections.append(current)
        return current

    for el in soup.find_all(["h1", "h2", "h3", "p", "table", "img"]):
        if el.name in {"h1", "h2", "h3"}:
            heading = clean_text(el.get_text(" ", strip=True))
            if not heading:
                continue
            current = Section(id=f"section_{len(sections) + 1:03d}", heading=heading, level=int(el.name[1]))
            sections.append(current)
            continue

        if el.name == "p":
            text = clean_text(el.get_text(" ", strip=True))
            if len(text) >= 8:
                ensure_section().paragraphs.append(text)
            continue

        if el.name == "table":
            rows = table_rows(el)
            if not rows:
                continue
            table_index += 1
            section = ensure_section()
            headers = rows[0]
            preview = "；".join(" / ".join(row[:3]) for row in rows[1:4])
            summary = f"{section.heading}：{clean_text(preview)[:120]}"
            asset = Asset(
                id=f"table_{table_index:03d}",
                type="table",
                heading=section.heading,
                summary=summary,
                rows=rows,
                headers=headers,
            )
            assets.append(asset)
            section.asset_refs.append(asset.id)
            continue

        if el.name == "img":
            src = clean_text(el.get("src") or "")
            if not src:
                continue
            image_index += 1
            section = ensure_section()
            alt = clean_text(el.get("alt") or f"文章资料图 {image_index}")
            local_copy = ""
            src_path = Path(src).expanduser()
            if src_path.exists():
                image_output_dir.mkdir(parents=True, exist_ok=True)
                target = image_output_dir / f"image_{image_index:03d}_{safe_name(src_path.name, 60)}"
                if src_path.resolve() != target.resolve():
                    shutil.copy2(src_path, target)
                local_copy = str(target)
            asset = Asset(
                id=f"image_{image_index:03d}",
                type="image",
                heading=section.heading,
                summary=f"{section.heading}：{alt}",
                original_src=src,
                local_copy=local_copy,
                alt=alt,
            )
            assets.append(asset)
            section.asset_refs.append(asset.id)

    paragraph_count = sum(len(section.paragraphs) for section in sections)
    text_chars = sum(len("".join(section.paragraphs)) for section in sections)
    article = {
        "source_html": str(source_html),
        "title": title,
        "main_heading": main_heading,
        "section_count": len(sections),
        "paragraph_count": paragraph_count,
        "text_chars": text_chars,
        "table_count": table_index,
        "image_count": image_index,
    }
    return article, sections, assets


def load_router(path: Path) -> dict[str, Any]:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"part_router": {}}


def router_match(router: dict[str, Any], content_part: str, fallback: str) -> dict[str, Any]:
    entry = (router.get("part_router") or {}).get(content_part) or {}
    candidates = entry.get("candidates") or []
    return {
        "content_part": content_part,
        "template_id": entry.get("primary") or fallback,
        "fallback": fallback,
        "alternates": entry.get("alternates") or [],
        "reason": (candidates[0] if candidates else {}).get("reason", "director fallback"),
    }


def asset_map(assets: list[Asset]) -> dict[str, Asset]:
    return {asset.id: asset for asset in assets}


def asset_preview(asset: Asset, rows: int = 4) -> dict[str, Any]:
    if asset.type == "table":
        return {"headers": asset.headers, "rows": asset.rows[:rows]}
    return {"alt": asset.alt, "original_src": asset.original_src, "local_copy": asset.local_copy}


def template_preview_path(template_id: str, preview_roots: list[Path] | None = None) -> Path | None:
    candidates: list[Path] = []
    for root in (preview_roots or []) + DEFAULT_TEMPLATE_PREVIEW_ROOTS:
        candidates.extend(
            [
                root / f"{template_id}.png",
                root / f"{template_id}.jpg",
                root / f"{template_id}.webp",
                root / template_id / "preview.png",
                root / template_id / "preview.jpg",
                root / template_id / "preview.webp",
                root / template_id / "assets" / "screenshot-1.png",
            ]
        )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def template_preview_cell(template_id: str, preview_roots: list[Path] | None = None) -> str:
    preview = template_preview_path(template_id, preview_roots)
    if preview:
        return f'<img class="template-shot" src="{preview.resolve().as_uri()}" alt="{html.escape(template_id)}">'
    return (
        '<div class="missing-shot">'
        "<b>暂无模板截图</b>"
        f"<code>{html.escape(template_id)}</code>"
        "<small>后续补 templates/&lt;id&gt;/preview.png</small>"
        "</div>"
    )


def scene_blueprints() -> list[dict[str, Any]]:
    return [
        {
            "title": "楼市真的和股市无关吗？",
            "voiceover": "过去二十年，A股五轮牛市，中国楼市四轮暴涨。最关键的规律是：股市涨幅超过50%后，楼市往往在6到18个月后跟涨。",
            "content_part": "opening_hook",
            "shot_type": "kinetic_hook",
            "duration_sec": 8,
            "evidence_refs": ["table_001", "table_002", "image_001"],
            "visual_intent": "用暗色金融纪录片开场，先抛出50%阈值和6-18个月传导，制造反常识冲突。",
            "core_meaning_lock": "股市牛市与楼市不是简单相关，而是存在财富效应传导。",
        },
        {
            "title": "五轮牛市，四轮传导",
            "voiceover": "2005年、2008年、2014年、2019年，股市上涨之后，楼市都出现过明显跟随。当前第五轮行情还没到最终答案，但它已经接近关键阈值。",
            "content_part": "financial_chart",
            "shot_type": "chart_reveal",
            "duration_sec": 10,
            "evidence_refs": ["table_001", "table_002", "table_003"],
            "visual_intent": "把五轮A股牛市与四轮楼市爆发做成上下双轴时间线，突出时滞。",
            "core_meaning_lock": "历史样本的重点是滞后传导，不是说楼市一定同步上涨。",
        },
        {
            "title": "为什么偏偏是50%？",
            "voiceover": "50%不是玄学，而是居民资产负债表的行为阈值。100元跌到70元，需要涨回50%，才会重新觉得自己没有亏。",
            "content_part": "logic_chain",
            "shot_type": "formula_animation",
            "duration_sec": 9,
            "evidence_refs": ["table_002", "table_003"],
            "visual_intent": "用70到105的数字动画解释财富深坑效应，再接回购房决策。",
            "core_meaning_lock": "50%代表财富修复和心理预期重构的门槛。",
        },
        {
            "title": "居民资产负债表的坑有多深",
            "voiceover": "如果按2021年峰值和2025年估算，人均房产资产从约42万降到约27万，人均净资产从约21万降到约6万。",
            "content_part": "data_table",
            "shot_type": "table_scan",
            "duration_sec": 11,
            "evidence_refs": ["table_004", "table_005", "image_002"],
            "visual_intent": "先扫表，再把42万、27万、21万、6万四个数字做成下坠式数据卡。",
            "core_meaning_lock": "居民不消费、不买房的核心不是利率，而是资产负债表尚未修复。",
        },
        {
            "title": "工资填坑太慢",
            "voiceover": "纯靠工资和储蓄修复这道坑，原文估算需要12年以上。收入增速放慢时，政策再松，也很难让居民马上重新加杠杆。",
            "content_part": "financial_chart",
            "shot_type": "stat_card",
            "duration_sec": 9,
            "evidence_refs": ["table_004", "table_005"],
            "visual_intent": "用12.5年的倒计时尺强调工资修复的慢，以及房产缩水的快。",
            "core_meaning_lock": "收入修复速度不足以单独支撑楼市快速反转。",
        },
        {
            "title": "股市可能是最快的填坑工具",
            "voiceover": "如果权益资产上涨50%，居民金融资产会多出约16.5万亿。连续三年牛市，则有机会弥补相当一部分财富深坑。",
            "content_part": "data_table",
            "shot_type": "data_rollup",
            "duration_sec": 10,
            "evidence_refs": ["table_006"],
            "visual_intent": "把33万亿、16.5万亿、三年复利、24%深坑修复做成滚动数字墙。",
            "core_meaning_lock": "股市财富效应可能比单纯政策刺激更快修复居民购买力。",
        },
        {
            "title": "楼市三因素：信贷、财富、政策",
            "voiceover": "分析楼市最简洁的框架，是三件事：信贷决定有没有能力买，财富决定想不想买，政策决定让不让买。",
            "content_part": "overall_outline",
            "shot_type": "framework_map",
            "duration_sec": 9,
            "evidence_refs": ["table_007"],
            "visual_intent": "三角结构图：信贷、财富、政策。财富节点作为主光源，信贷和政策作为放大器与闸门。",
            "core_meaning_lock": "三因素框架是全文后续判断的骨架。",
        },
        {
            "title": "种子、放大器、闸门",
            "voiceover": "财富因素是种子，信贷是放大器，政策是闸门。政策可以放开入口，但如果钱包空了，路再宽也没人上车。",
            "content_part": "logic_chain",
            "shot_type": "causal_path",
            "duration_sec": 9,
            "evidence_refs": ["table_007"],
            "visual_intent": "做成三段路径高亮：净资产修复，到贷款意愿，再到成交释放。",
            "core_meaning_lock": "政策不能凭空创造需求，只能释放被压制的需求。",
        },
        {
            "title": "历史上共振，房价才会爆发",
            "voiceover": "2008到2010、2014到2017，是信贷、财富、政策三因素共振。2022到2025，则是政策托底，但财富和信贷同时拖后腿。",
            "content_part": "data_table",
            "shot_type": "cycle_matrix",
            "duration_sec": 11,
            "evidence_refs": ["table_008", "table_009"],
            "visual_intent": "用红绿矩阵展示每个周期的三因素方向，再把2026标成结构性底部。",
            "core_meaning_lock": "历史复盘说明，单靠政策宽松并不足以让楼市重新上涨。",
        },
        {
            "title": "为什么2022到2025政策失灵",
            "voiceover": "限购放开、利率降到低位、税费减免都已经发生，但房价仍然下跌。原因是居民在还贷、降杠杆、收缩资产负债表。",
            "content_part": "warning_or_risk",
            "shot_type": "risk_card",
            "duration_sec": 10,
            "evidence_refs": ["table_008", "table_009", "table_013"],
            "visual_intent": "用政策按钮全部点亮，但居民钱包持续变暗的反差动画。",
            "core_meaning_lock": "政策油门已经踩下，但居民端没有形成真实购买力。",
        },
        {
            "title": "从增量开发，转向存量运营",
            "voiceover": "房地产的主线正在从拿地、盖房、卖出去，转向收购、改造、运营。城市更新，是存量时代的核心信号。",
            "content_part": "chapter_divider",
            "shot_type": "chapter_shift",
            "duration_sec": 8,
            "evidence_refs": ["table_010"],
            "visual_intent": "章节转场：施工塔吊退场，旧城网格被扫描，进入城市更新地图。",
            "core_meaning_lock": "城市更新是政策和产业主线变化，不是简单旧改概念。",
        },
        {
            "title": "棚改到城市更新的十年演进",
            "voiceover": "2015到2018是棚改货币化，2019到2021是老旧小区改造，2024到2026则是城市更新全面铺开。",
            "content_part": "data_table",
            "shot_type": "timeline_table",
            "duration_sec": 10,
            "evidence_refs": ["table_010"],
            "visual_intent": "把四个阶段做成横向时间轴，投资强度用柱状背景表现。",
            "core_meaning_lock": "新周期的刺激方式不再复制棚改大水漫灌。",
        },
        {
            "title": "城市更新的四个信号",
            "voiceover": "供给转向存量，以旧换新铺开，好房子标准重塑供给，土地供给缩量提质。它们共同指向一件事：不是没需求，而是旧供给不匹配。",
            "content_part": "logic_chain",
            "shot_type": "four_signal_grid",
            "duration_sec": 11,
            "evidence_refs": [],
            "visual_intent": "四宫格信号卡，逐个点亮，每个信号配小图标和短关键词。",
            "core_meaning_lock": "城市更新解决的是存量质量、置换链条和供给结构问题。",
        },
        {
            "title": "钱从哪来：特别国债和专项债",
            "voiceover": "这轮财政扩张规模不小，专项债、特别国债、收储和城市更新都在提供弹药。但弹药能否点燃楼市，取决于传导效率。",
            "content_part": "financial_chart",
            "shot_type": "funding_map",
            "duration_sec": 11,
            "evidence_refs": ["table_011", "table_012"],
            "visual_intent": "资金从央行、财政、地方、收储、改造流向居民和开发商，做成管道流动画。",
            "core_meaning_lock": "财政工具提供弹药，但不等于立刻形成楼市需求。",
        },
        {
            "title": "M2很多，为什么房价没涨",
            "voiceover": "2023到2025，M2总量很大，但房地产失去了印钞机功能。钱困在银行体系和生产端，没有顺利传到居民买房。",
            "content_part": "data_table",
            "shot_type": "liquidity_trap",
            "duration_sec": 11,
            "evidence_refs": ["table_011"],
            "visual_intent": "对比2009、2015、2023-2025三条货币传导路径，最后一条出现断点。",
            "core_meaning_lock": "宽货币不等于宽信用，更不等于居民买房意愿恢复。",
        },
        {
            "title": "特别国债的两个条件",
            "voiceover": "特别国债能不能激活楼市，关键看两点：收储价格能不能成交，收购后的存量房能不能转成真实租赁或保障需求。",
            "content_part": "logic_chain",
            "shot_type": "condition_gate",
            "duration_sec": 9,
            "evidence_refs": ["table_012"],
            "visual_intent": "两道闸门动画：价格成交、真实需求。两道都打开，流动性才进入楼市。",
            "core_meaning_lock": "收储不是万能，必须形成真实交易和真实需求。",
        },
        {
            "title": "低利率不等于愿意借钱",
            "voiceover": "房贷利率已经降到约3.1%，但居民仍在主动还贷。信贷因素当前最大的约束，不是价格，而是意愿。",
            "content_part": "financial_chart",
            "shot_type": "credit_chart",
            "duration_sec": 10,
            "evidence_refs": ["table_013"],
            "visual_intent": "折线或阶梯图表现利率下行、住户中长期贷款仍偏弱的背离。",
            "core_meaning_lock": "信贷修复的核心不是利率水平，而是居民是否愿意重新扩表。",
        },
        {
            "title": "四个原因压住居民杠杆",
            "voiceover": "收入预期恶化、财富深坑未填、房价预期没扭转、居民杠杆率接近饱和。这四件事，让低利率也撬不动需求。",
            "content_part": "warning_or_risk",
            "shot_type": "risk_stack",
            "duration_sec": 10,
            "evidence_refs": ["table_013"],
            "visual_intent": "四层压力堆叠在居民资产负债表上，每层出现对应关键词。",
            "core_meaning_lock": "居民不是不懂低利率，而是不愿在不确定性中继续透支未来。",
        },
        {
            "title": "未来释放空间在哪里",
            "voiceover": "增量空间不是没有，而是在收储盘活置换、以旧换新、好房子需求、房价预期扭转、租金回报率回升这些路径里。",
            "content_part": "data_table",
            "shot_type": "path_table",
            "duration_sec": 10,
            "evidence_refs": ["table_014"],
            "visual_intent": "把六条路径做成路线图，从政策端一路连接到成交端。",
            "core_meaning_lock": "未来机会更可能来自结构性修复，而不是全面普涨。",
        },
        {
            "title": "确认信号：连续三个月转正",
            "voiceover": "最值得盯的确认信号，是住户中长期贷款连续三个月转正。它代表居民重新愿意把未来收入折现到今天。",
            "content_part": "pull_quote",
            "shot_type": "signal_card",
            "duration_sec": 8,
            "evidence_refs": ["table_014", "table_013"],
            "visual_intent": "做成监控仪表盘：住户中长期贷款连续3月转正，作为红灯转绿灯。",
            "core_meaning_lock": "信贷转正是楼市真正恢复的确认信号之一。",
        },
        {
            "title": "地产周期是最长的经济周期",
            "voiceover": "房地产周期通常15到25年，牵动钢铁、水泥、家电、装修和金融。楼市不是单一行业，它是经济的压舱石。",
            "content_part": "chapter_divider",
            "shot_type": "macro_bridge",
            "duration_sec": 8,
            "evidence_refs": ["table_015"],
            "visual_intent": "电影化转场到全球地产周期，城市天际线和产业链节点缓慢展开。",
            "core_meaning_lock": "房地产周期影响的是整个经济周期，而非单一地产行业。",
        },
        {
            "title": "中国更像英国，不像日本",
            "voiceover": "全球样本里，日本是长期阴跌，美国是出清后V型恢复，英国是核心城市领先。中国当前更接近核心城市先复苏、区域极端分化。",
            "content_part": "data_table",
            "shot_type": "global_compare",
            "duration_sec": 11,
            "evidence_refs": ["table_015", "table_016", "table_017"],
            "visual_intent": "四国房价恢复路径叠加线，突出日本、美国、英国、中国的分叉。",
            "core_meaning_lock": "中国底部路径更可能是结构性分化，而不是日本式全国长期阴跌。",
        },
        {
            "title": "中国和日本的关键差异",
            "voiceover": "中国城镇化率仍有空间，政府工具箱更主动，居民杠杆相对可控。但人口和通缩压力仍然需要警惕。",
            "content_part": "data_table",
            "shot_type": "comparison_cards",
            "duration_sec": 9,
            "evidence_refs": ["table_017"],
            "visual_intent": "中国、日本两列对照卡，优势用冷绿，风险用琥珀色标注。",
            "core_meaning_lock": "不能简单把中国地产等同于日本1991。",
        },
        {
            "title": "当前底部：五个绿灯，两个红灯",
            "voiceover": "价格和供给层面已经出现多个触底信号，但居民信贷和开发投资仍是红灯。结论是结构性底部，而不是V型反转。",
            "content_part": "data_table",
            "shot_type": "traffic_light_dashboard",
            "duration_sec": 11,
            "evidence_refs": ["table_018"],
            "visual_intent": "把七个指标做成交通灯仪表盘，五绿二红，最后打出结构性底部。",
            "core_meaning_lock": "底部已接近，但全面回暖还缺居民信贷和投资端确认。",
        },
        {
            "title": "结构性底部意味着什么",
            "voiceover": "上层是一线核心区和强二线核心区，价格先企稳；下层是弱二线和三四线，可能还要更长时间出清。",
            "content_part": "logic_chain",
            "shot_type": "two_layer_market",
            "duration_sec": 9,
            "evidence_refs": ["table_018", "table_020"],
            "visual_intent": "将城市分成上下两层市场，上层缓慢回升，下层继续磨底。",
            "core_meaning_lock": "房地产未来不是整体同涨同跌，而是城市与产品的结构分化。",
        },
        {
            "title": "地产股：赔率优先",
            "voiceover": "在三因素框架下，地产股赌的是赔率，不是确定性。PB低到极端水平，说明市场已经把很多悲观情景计入价格。",
            "content_part": "financial_chart",
            "shot_type": "valuation_card",
            "duration_sec": 9,
            "evidence_refs": ["table_019"],
            "visual_intent": "用PB估值区间做低位赔率卡，标注央企龙头、优质民企、出险房企。",
            "core_meaning_lock": "地产股逻辑是困境反转赔率，风险仍需分层。",
            "qc_flags": ["此段位于原文知识星球提示后，发布前请确认公开边界。"],
        },
        {
            "title": "怎么筛地产股",
            "voiceover": "优先看融资成本低、土储稳、产品力强的央国企和优质民企；高杠杆出险房企赔率高，但债务风险也最大。",
            "content_part": "data_table",
            "shot_type": "selection_matrix",
            "duration_sec": 9,
            "evidence_refs": ["table_019"],
            "visual_intent": "四类公司风险收益矩阵：央企、优质民企、出险房企、物管公司。",
            "core_meaning_lock": "投资标的需要按融资能力、产品力和债务风险分层。",
            "qc_flags": ["此段涉及投资判断，成片需保留风险提示。"],
        },
        {
            "title": "买房：底部确认，但分化是主线",
            "voiceover": "一线核心区和强二线核心区，可以开始择优；弱二线和三四线仍以观望、置换和减仓为主。",
            "content_part": "data_table",
            "shot_type": "city_tier_table",
            "duration_sec": 10,
            "evidence_refs": ["table_020"],
            "visual_intent": "城市层级表动态扫描，重点突出一线核心、强二线、弱二线、三四线的不同策略。",
            "core_meaning_lock": "买房策略的核心是城市层级分化，而不是无脑抄底。",
            "qc_flags": ["此段位于原文知识星球提示后，发布前请确认公开边界。"],
        },
        {
            "title": "五个操作原则",
            "voiceover": "选城市大于选楼盘，买新规不买旧规，从赌升值转向看租金，抓以旧换新窗口，并保留15%到20%的流动性。",
            "content_part": "overall_outline",
            "shot_type": "checklist",
            "duration_sec": 11,
            "evidence_refs": ["table_020"],
            "visual_intent": "五条原则做成竖屏清单，每条用短动效确认，不做大段文字堆叠。",
            "core_meaning_lock": "底部不等于反转，操作上仍要保留安全垫。",
            "qc_flags": ["此段涉及操作建议，成片需保留免责声明。"],
        },
        {
            "title": "最终判断：等三因素重新共振",
            "voiceover": "楼市反弹的核心，不是单点政策，而是财富修复、信贷转正、政策释放重新共振。现在更像结构性底部的左侧。",
            "content_part": "logic_chain",
            "shot_type": "final_decision_tree",
            "duration_sec": 10,
            "evidence_refs": ["table_007", "table_009", "table_018"],
            "visual_intent": "回收三因素框架，把财富、信贷、政策三条线汇入结构性底部结论。",
            "core_meaning_lock": "文章最终结论是结构性底部与等待共振，而不是无条件看多。",
        },
        {
            "title": "结尾与风险提示",
            "voiceover": "以上只是基于公开数据和原文框架的市场分析，不构成投资建议。真正的确认，还是要回到数据：成交、价格、贷款和居民收入。",
            "content_part": "closing_outro",
            "shot_type": "outro",
            "duration_sec": 7,
            "evidence_refs": [],
            "visual_intent": "品牌收束，最后保留数据来源与风险提示，音乐淡出。",
            "core_meaning_lock": "保留风险提示，不把策略判断包装成确定承诺。",
        },
    ]


def build_storyboard(
    article: dict[str, Any],
    sections: list[Section],
    assets: list[Asset],
    router: dict[str, Any],
    *,
    duration_target_sec: int,
) -> dict[str, Any]:
    assets_by_id = asset_map(assets)
    rules = load_driver_rules()
    scenes = []
    cursor = 0.0
    last_evidence_at = 0.0
    used_asset_ids: set[str] = set()

    fallback_by_part = {
        "article_title": "frame-liquid-bg-hero",
        "opening_hook": "frame-glitch-title",
        "overall_outline": "frame-flowchart-sticky",
        "chapter_divider": "frame-light-leak-cinema",
        "logic_chain": "frame-flowchart-sticky",
        "data_chart": "frame-data-chart-nyt",
        "financial_chart": "frame-data-chart-nyt",
        "data_table": "data-report",
        "article_image": "doc-kami-parchment",
        "news_or_document": "doc-kami-parchment",
        "warning_or_risk": "deck-safety-alert",
        "pull_quote": "blog-post",
        "closing_outro": "frame-logo-outro",
    }

    blueprints = scene_blueprints()
    raw_total = sum(float(item["duration_sec"]) for item in blueprints)
    scale = duration_target_sec / raw_total if raw_total else 1.0

    for idx, bp in enumerate(blueprints, 1):
        evidence_refs = [ref for ref in bp.get("evidence_refs", []) if ref in assets_by_id]
        used_asset_ids.update(evidence_refs)
        content_part = bp["content_part"]
        planned_duration = max(5.0, round(float(bp["duration_sec"]) * scale, 3))
        beat_class = {
            "opening_hook": "hook",
            "chapter_divider": "chapter",
            "overall_outline": "logic_chain",
            "logic_chain": "logic_chain",
            "data_table": "evidence_data",
            "data_chart": "evidence_data",
            "financial_chart": "evidence_data",
            "article_image": "evidence_document",
            "news_or_document": "evidence_document",
            "warning_or_risk": "objection",
            "pull_quote": "claim",
            "closing_outro": "recap",
        }.get(content_part, "claim")
        if evidence_refs:
            last_evidence_at = cursor
        scores = score_driver(
            f"{bp['title']}。{bp['voiceover']}",
            beat_class=beat_class,
            duration=planned_duration,
            seconds_since_evidence=cursor - last_evidence_at,
            index=idx,
            lane="explainer",
        )
        match = router_match(router, content_part, fallback_by_part.get(content_part, "frame-flowchart-sticky"))
        evidence_assets = [asset_preview(assets_by_id[ref]) for ref in evidence_refs]
        scenes.append(
            {
                "scene_id": f"director_scene_{idx:03d}",
                "start_sec": round(cursor, 3),
                "duration_sec": planned_duration,
                "end_sec": round(cursor + planned_duration, 3),
                "beat_class": beat_class,
                "director_state": explainer_state_for_beat(
                    beat_class,
                    index=idx,
                    seconds_since_evidence=cursor - last_evidence_at,
                ),
                "driver_scores": scores,
                "driver_score": weighted_driver_score(scores, rules),
                "content_part": content_part,
                "template_id": match["template_id"],
                "template_source": "html-anything-router/html-video-custom-scene",
                "template_match": match,
                "title": bp["title"],
                "voiceover_text": bp["voiceover"],
                "core_meaning_lock": bp["core_meaning_lock"],
                "visual_intent": bp["visual_intent"],
                "shot_type": bp["shot_type"],
                "evidence_refs": evidence_refs,
                "evidence_assets_preview": evidence_assets,
                "variables": {
                    "safe_area": "9:16 vertical; no face safe zone needed for no-human mode; keep bottom 14% available for subtitles",
                    "style": "dark navy/black finance documentary, warm amber accent, restrained Bloomberg-like information density",
                    "asset_refs": evidence_refs,
                },
                "motion": {
                    "entrance": motion_entrance(content_part),
                    "focus_change": motion_focus(content_part),
                    "exit": motion_exit(content_part),
                    "gsap_required": True,
                    "lottie_role": lottie_role(content_part),
                    "lottie_rule": "decorative only; real tables/charts/images remain the evidence layer",
                },
                "audio": {
                    **audio_for_beat(beat_class),
                    "bgm": "restrained cinematic financial documentary, no vocals",
                    "voice_provider_next_step": "MiniMax CLI after storyboard approval",
                },
                "transition_to_next": transition_for_beat(beat_class, lane="explainer", duration=planned_duration),
                "qc_notes": bp.get("qc_flags", []) + qc_notes(content_part, evidence_refs),
                "original_refs": section_refs_for_assets(sections, evidence_refs),
            }
        )
        cursor += planned_duration

    missing_assets = [asset.id for asset in assets if asset.id not in used_asset_ids]
    return {
        "schema_version": "dasheng.video_director_storyboard.v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "lane": "nohuman_explainer",
        "status": "awaiting_user_review_before_material_generation",
        "source_article": article,
        "title": "地产周期论：信贷、财富、政策的三重共振",
        "aspect": "9:16",
        "duration_target_sec": duration_target_sec,
        "duration_estimate_sec": round(cursor, 3),
        "scene_count": len(scenes),
        "style": {
            "name": "地产周期调查片 / 金融纪录片 / Bloomberg-inspired vertical",
            "palette": ["#07111f", "#0e2238", "#d7a84f", "#edf2f7", "#a63d2d"],
            "typography": "serious condensed sans for titles; readable Chinese sans for body; small tables with strong row highlights",
            "rhythm": "voiceover-driven; evidence every 20-35s; chapter reset every 45-90s",
            "avoid": ["PPT翻页", "泛化模型图", "假图表", "开发标签", "过大字幕遮挡证据"],
        },
        "talking_head_rule": {
            "enabled_this_run": False,
            "future_flow": "先生成真人口播稿 -> 用户录像上传 -> 以真人音频/字幕为主时间轴 -> 再合成证据画面和剪辑",
        },
        "asset_coverage": {
            "total_assets": len(assets),
            "used_assets": sorted(used_asset_ids),
            "missing_assets": missing_assets,
            "coverage_ok": not missing_assets,
        },
        "review_required": [
            "确认 30 个分镜是否保留全部核心观点。",
            "确认知识星球提示后的地产股/买房策略是否进入公开视频。",
            "确认口播调性：偏博士犀利版，还是进一步压缩成平台短视频版。",
        ],
        "scenes": scenes,
    }


def motion_entrance(content_part: str) -> str:
    return {
        "opening_hook": "glitch_title_snap_in",
        "chapter_divider": "light_leak_fade_in",
        "logic_chain": "nodes_stagger_in",
        "data_table": "table_mask_reveal",
        "financial_chart": "axis_draw_then_series_reveal",
        "warning_or_risk": "amber_alert_stack_in",
        "closing_outro": "logo_blocks_assemble",
    }.get(content_part, "fade_push_in")


def motion_focus(content_part: str) -> str:
    return {
        "opening_hook": "50_percent_threshold_pulse",
        "chapter_divider": "chapter_keyword_glow",
        "logic_chain": "path_highlight_by_voiceover",
        "data_table": "row_scan_and_key_cell_zoom",
        "financial_chart": "number_countup_and_annotation_pin",
        "warning_or_risk": "risk_layers_press_down",
        "closing_outro": "source_and_disclaimer_hold",
    }.get(content_part, "subtle_camera_push")


def motion_exit(content_part: str) -> str:
    return {
        "opening_hook": "impact_cut_to_evidence",
        "chapter_divider": "film_burn_to_next",
        "logic_chain": "path_completes_then_cut",
        "data_table": "highlight_row_freeze_then_push",
        "financial_chart": "annotation_hold_then_fade",
        "warning_or_risk": "hard_cut_after_warning",
        "closing_outro": "music_tail_fade",
    }.get(content_part, "short_fade_out")


def lottie_role(content_part: str) -> str:
    return {
        "opening_hook": "market_signal_alert",
        "chapter_divider": "light_leak_transition",
        "logic_chain": "flow_accent",
        "data_table": "scanner_accent",
        "financial_chart": "ticker_accent",
        "warning_or_risk": "risk_alarm_accent",
        "closing_outro": "brand_glow",
    }.get(content_part, "ambient_particle")


def qc_notes(content_part: str, evidence_refs: list[str]) -> list[str]:
    notes = []
    if content_part in {"data_table", "financial_chart"} and not evidence_refs:
        notes.append("数据场景缺少证据引用，渲染前必须补足或改为观点场景。")
    if content_part in {"logic_chain", "overall_outline"}:
        notes.append("逻辑图只做结构解释，不得伪造成真实数据图。")
    if content_part in {"data_table", "financial_chart"}:
        notes.append("图表/表格必须复用文章数据；Lottie 只做装饰。")
    return notes


def section_refs_for_assets(sections: list[Section], evidence_refs: list[str]) -> list[dict[str, str]]:
    refs = []
    for section in sections:
        matched = sorted(set(section.asset_refs).intersection(evidence_refs))
        if matched:
            refs.append({"section_id": section.id, "heading": section.heading, "asset_refs": ",".join(matched)})
    return refs


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_voiceover(path: Path, storyboard: dict[str, Any]) -> None:
    lines = [
        f"# {storyboard['title']} 无头口播稿",
        "",
        f"- 状态：{storyboard['status']}",
        f"- 预计时长：{storyboard['duration_estimate_sec']} 秒",
        "- 注意：审核通过后再调用 MiniMax CLI 生成正式配音。",
        "",
    ]
    for scene in storyboard["scenes"]:
        lines.append(f"## {scene['scene_id']} {scene['title']}")
        lines.append(scene["voiceover_text"])
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_voiceover_txt(path: Path, storyboard: dict[str, Any]) -> None:
    text = "\n".join(scene["voiceover_text"] for scene in storyboard["scenes"])
    path.write_text(text + "\n", encoding="utf-8")


def write_review_html(
    path: Path,
    storyboard: dict[str, Any],
    assets: list[Asset],
    voiceover_md: Path,
    *,
    template_preview_roots: list[Path] | None = None,
    source_storyboard: Path | None = None,
) -> None:
    used_by: dict[str, list[str]] = {asset.id: [] for asset in assets}
    for scene in storyboard["scenes"]:
        for ref in scene.get("evidence_refs", []):
            used_by.setdefault(ref, []).append(scene["scene_id"])

    asset_rows = []
    for asset in assets:
        preview = ""
        if asset.type == "table":
            preview = " / ".join(asset.headers[:5])
        elif asset.local_copy:
            preview = f'<img class="thumb" src="{Path(asset.local_copy).as_uri()}" alt="{html.escape(asset.alt)}">'
        else:
            preview = html.escape(asset.alt)
        coverage = "、".join(used_by.get(asset.id) or ["未使用"])
        asset_rows.append(
            "<tr>"
            f"<td><code>{asset.id}</code></td>"
            f"<td>{html.escape(asset.type)}</td>"
            f"<td>{html.escape(asset.heading)}</td>"
            f"<td>{preview}</td>"
            f"<td>{html.escape(coverage)}</td>"
            "</tr>"
        )

    contact_rows = []
    scene_payload = []
    for scene in storyboard["scenes"]:
        chips = ", ".join(scene.get("evidence_refs", [])) or "结构/转场场景"
        qc_text = "；".join(scene.get("qc_notes", [])) or "无"
        motion = scene.get("motion") or {}
        motion_text = " → ".join(
            item
            for item in [
                str(motion.get("entrance") or ""),
                str(motion.get("focus_change") or ""),
                str(motion.get("exit") or ""),
            ]
            if item
        )
        scene_payload.append(
            {
                "scene_id": scene["scene_id"],
                "index": scene["scene_id"].split("_")[-1],
                "title": scene["title"],
                "template_id": scene["template_id"],
            }
        )
        contact_rows.append(
            f'<tr data-scene-id="{html.escape(scene["scene_id"])}">'
            f"<td class=\"num\">{scene['scene_id'].split('_')[-1]}</td>"
            f"<td class=\"time\">{scene['start_sec']:.1f}-{scene['end_sec']:.1f}s<br><small>{scene['duration_sec']:.1f}s</small></td>"
            f"<td>{template_preview_cell(str(scene['template_id']), template_preview_roots)}</td>"
            f"<td><code>{html.escape(scene['template_id'])}</code><br><small>{html.escape(scene['content_part'])} · {html.escape(scene['beat_class'])}</small></td>"
            f"<td><b>{html.escape(scene['title'])}</b><p>{html.escape(scene['voiceover_text'])}</p></td>"
            f"<td>{html.escape(scene['core_meaning_lock'])}<br><small>{html.escape(scene['visual_intent'])}</small><br><small>{html.escape(motion_text)}</small></td>"
            f"<td>{html.escape(chips)}</td>"
            f"<td>{html.escape(qc_text)}</td>"
            f'<td class="decision">{review_controls_cell(scene["scene_id"], str(scene["template_id"]))}</td>'
            "</tr>"
        )

    scene_cards = []
    for scene in storyboard["scenes"]:
        chips = "".join(f"<span>{html.escape(ref)}</span>" for ref in scene.get("evidence_refs", [])) or "<em>无直接证据，结构/转场场景</em>"
        qc = "".join(f"<li>{html.escape(item)}</li>" for item in scene.get("qc_notes", []))
        if not qc:
            qc = "<li>无特殊问题。</li>"
        scene_cards.append(
            f"""
            <article class="scene" id="{html.escape(scene['scene_id'])}">
              <div class="scene-top">
                <code>{html.escape(scene['scene_id'])}</code>
                <strong>{scene['start_sec']:.1f}s - {scene['end_sec']:.1f}s · {scene['duration_sec']:.1f}s</strong>
                <span class="beat">{html.escape(scene['beat_class'])}</span>
              </div>
              <h3>{html.escape(scene['title'])}</h3>
              <p class="voice">{html.escape(scene['voiceover_text'])}</p>
              <dl>
                <dt>核心意思锁定</dt><dd>{html.escape(scene['core_meaning_lock'])}</dd>
                <dt>画面设计</dt><dd>{html.escape(scene['visual_intent'])}</dd>
                <dt>模板</dt><dd><code>{html.escape(scene['template_id'])}</code> · {html.escape(scene['content_part'])}</dd>
                <dt>运镜/动效</dt><dd>{html.escape(scene['motion']['entrance'])} → {html.escape(scene['motion']['focus_change'])} → {html.escape(scene['motion']['exit'])}</dd>
                <dt>证据资产</dt><dd class="chips">{chips}</dd>
              </dl>
              <details>
                <summary>质检备注</summary>
                <ul>{qc}</ul>
              </details>
            </article>
            """
        )

    review_items = "".join(f"<li>{html.escape(item)}</li>" for item in storyboard["review_required"])
    html_doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(storyboard['title'])} · 导演分镜审核</title>
  <style>
    :root {{
      --bg: #07111f;
      --panel: #0e1d31;
      --panel2: #122842;
      --text: #edf2f7;
      --muted: #9fb2ca;
      --gold: #d7a84f;
      --red: #a63d2d;
      --line: rgba(215,168,79,.24);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background:
        radial-gradient(circle at 20% 0%, rgba(215,168,79,.16), transparent 28rem),
        linear-gradient(135deg, #050b14, var(--bg) 45%, #0d1728);
      color: var(--text);
      font-family: "PingFang SC", "Noto Sans CJK SC", "Source Han Sans SC", sans-serif;
      line-height: 1.65;
    }}
    header {{
      padding: 36px 28px 22px;
      border-bottom: 1px solid var(--line);
      position: sticky;
      top: 0;
      z-index: 2;
      backdrop-filter: blur(18px);
      background: rgba(7,17,31,.82);
    }}
    h1 {{ margin: 0 0 10px; font-size: clamp(26px, 4vw, 48px); letter-spacing: .03em; }}
    h2 {{ margin: 34px 0 14px; color: var(--gold); }}
    h3 {{ margin: 8px 0 10px; font-size: 22px; }}
    a {{ color: var(--gold); }}
    .meta, .notice, .grid, table, .scene {{
      width: min(1180px, calc(100vw - 36px));
      margin-left: auto;
      margin-right: auto;
    }}
    .meta {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      padding: 22px 0;
    }}
    .stat, .notice, .scene, table {{
      background: linear-gradient(180deg, rgba(18,40,66,.92), rgba(14,29,49,.92));
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: 0 18px 60px rgba(0,0,0,.22);
    }}
    .stat {{ padding: 16px; }}
    .stat b {{ display: block; font-size: 28px; color: var(--gold); }}
    .stat span {{ color: var(--muted); font-size: 13px; }}
    .notice {{ padding: 18px 22px; margin-top: 8px; }}
    .notice strong {{ color: var(--gold); }}
    .toolbar {{
      width: min(1680px, calc(100vw - 36px));
      margin: 18px auto 0;
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: rgba(16,29,48,.88);
      display: flex;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }}
    .toolbar b {{ color: var(--gold); }}
    button, .file-label {{ border: 1px solid var(--line); background: #142842; color: var(--text); border-radius: 999px; padding: 8px 13px; cursor: pointer; font: inherit; }}
    button:hover, .file-label:hover {{ background: #1d3656; }}
    .file-label input {{ display: none; }}
    .ok {{ color: #7ee2a8; font-weight: 800; }}
    .warn {{ color: #f1b66d; font-weight: 800; }}
    .grid {{ display: grid; grid-template-columns: 220px 1fr; gap: 18px; align-items: start; }}
    nav {{
      position: sticky;
      top: 132px;
      max-height: calc(100vh - 150px);
      overflow: auto;
      padding: 14px;
      background: rgba(14,29,49,.72);
      border: 1px solid var(--line);
      border-radius: 16px;
    }}
    nav a {{ display: block; text-decoration: none; padding: 7px 8px; border-radius: 10px; color: var(--muted); font-size: 13px; }}
    nav a:hover {{ background: rgba(215,168,79,.12); color: var(--text); }}
    .scene {{ padding: 20px; margin: 0 0 16px; }}
    .scene-top {{ display: flex; gap: 12px; align-items: center; color: var(--muted); flex-wrap: wrap; }}
    code {{ color: #ffe6a3; }}
    .beat {{ margin-left: auto; color: var(--gold); border: 1px solid var(--line); padding: 2px 8px; border-radius: 999px; }}
    .voice {{ font-size: 18px; color: #fff7e6; border-left: 4px solid var(--gold); padding-left: 14px; }}
    dl {{ display: grid; grid-template-columns: 110px 1fr; gap: 7px 14px; }}
    dt {{ color: var(--muted); }}
    dd {{ margin: 0; }}
    .chips span {{
      display: inline-block;
      border: 1px solid var(--line);
      color: var(--gold);
      padding: 2px 8px;
      border-radius: 999px;
      margin: 0 6px 6px 0;
      font-size: 12px;
    }}
    table {{ border-collapse: collapse; overflow: hidden; margin-top: 14px; margin-bottom: 34px; }}
    th, td {{ border-bottom: 1px solid rgba(255,255,255,.08); padding: 10px 12px; text-align: left; vertical-align: top; font-size: 13px; }}
    th {{ color: var(--gold); background: rgba(215,168,79,.08); }}
    .contact-table {{ width: min(1680px, calc(100vw - 36px)); }}
    .contact-table th {{ position: sticky; top: 104px; z-index: 1; background: #10243a; }}
    .contact-table p {{ margin: 6px 0 0; color: #fff7e6; line-height: 1.55; }}
    .num {{ color: var(--gold); font-weight: 800; font-size: 18px; }}
    .time {{ color: var(--muted); white-space: nowrap; }}
    .decision {{ color: #fff4d6; line-height: 1.8; min-width: 180px; }}
    .decision-box label {{ display: block; white-space: nowrap; }}
    .template-override, .review-note {{ width: 100%; margin-top: 6px; border: 1px solid rgba(215,168,79,.28); border-radius: 10px; background: #091423; color: var(--text); padding: 7px; font: inherit; }}
    .review-note {{ min-height: 54px; resize: vertical; }}
    .template-shot {{ width: 170px; height: 96px; object-fit: cover; border-radius: 12px; border: 1px solid var(--line); background: #000; display: block; }}
    .missing-shot {{ width: 170px; min-height: 96px; border: 1px dashed rgba(215,168,79,.45); border-radius: 12px; padding: 10px; color: var(--muted); background: rgba(0,0,0,.18); }}
    .missing-shot b {{ display: block; color: #e08c7b; margin-bottom: 4px; }}
    .missing-shot small {{ display: block; margin-top: 5px; }}
    .thumb {{ max-width: 160px; max-height: 90px; border-radius: 10px; border: 1px solid var(--line); }}
    details {{ margin-top: 10px; color: var(--muted); }}
    footer {{ padding: 40px 28px; text-align: center; color: var(--muted); }}
    @media (max-width: 860px) {{
      .meta {{ grid-template-columns: repeat(2, 1fr); }}
      .grid {{ display: block; }}
      nav {{ position: static; margin-bottom: 16px; }}
      dl {{ grid-template-columns: 1fr; }}
      .beat {{ margin-left: 0; }}
      .template-shot, .missing-shot {{ width: 120px; height: 72px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>{html.escape(storyboard['title'])}</h1>
    <div>无头口播导演分镜审核页 · <strong style="color:var(--gold)">未生成最终视频</strong> · 通过后再进入配音、素材、渲染</div>
  </header>

  <section class="meta">
    <div class="stat"><b>{storyboard['scene_count']}</b><span>分镜数量</span></div>
    <div class="stat"><b>{storyboard['duration_estimate_sec']:.0f}s</b><span>预计时长</span></div>
    <div class="stat"><b>{len(assets)}</b><span>证据资产</span></div>
    <div class="stat"><b>{'OK' if storyboard['asset_coverage']['coverage_ok'] else '检查'}</b><span>资产覆盖</span></div>
  </section>

  <section class="notice">
    <strong>审核重点：</strong>
    <ul>{review_items}</ul>
    <p>口播稿：<a href="{voiceover_md.as_uri()}">{html.escape(voiceover_md.name)}</a></p>
  </section>

  <section class="toolbar">
    <b>审核门禁：</b><span id="gateStatus" class="warn">仍需修改</span>
    <span>通过 <b id="approvedCount">0</b></span>
    <span>待审 <b id="pendingCount">0</b></span>
    <span>阻塞 <b id="blockerCount">0</b></span>
    <button id="markAllApproved" type="button">全部标记通过</button>
    <button id="exportDecision" type="button">导出 storyboard_review_decision.json</button>
    <button id="copyDecision" type="button">复制 JSON</button>
    <label class="file-label">导入 JSON<input id="importDecision" type="file" accept="application/json"></label>
  </section>

  <h2 class="meta">分镜-模板联系表（生成前必审）</h2>
  <table class="contact-table">
    <thead><tr><th>#</th><th>时间</th><th>模板截图</th><th>模板/类型</th><th>分镜与口播</th><th>核心/画面/动效</th><th>证据资产</th><th>风险点</th><th>审核</th></tr></thead>
    <tbody>{''.join(contact_rows)}</tbody>
  </table>

  <h2 class="meta">证据资产覆盖</h2>
  <table>
    <thead><tr><th>ID</th><th>类型</th><th>所属章节</th><th>预览</th><th>用于分镜</th></tr></thead>
    <tbody>{''.join(asset_rows)}</tbody>
  </table>

  <section class="grid">
    <nav>
      {''.join(f'<a href="#{html.escape(scene["scene_id"])}">{html.escape(scene["scene_id"])} · {html.escape(scene["title"])}</a>' for scene in storyboard["scenes"])}
    </nav>
    <main>{''.join(scene_cards)}</main>
  </section>

  <footer>Newma Video Director · storyboard first, render after review.</footer>
  {review_page_script(scene_payload, source_storyboard)}
</body>
</html>
"""
    path.write_text(html_doc, encoding="utf-8")


def write_inventory(path: Path, article: dict[str, Any], sections: list[Section], assets: list[Asset]) -> dict[str, Any]:
    payload = {
        "schema_version": "dasheng.article_asset_inventory.v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "article": article,
        "sections": [
            {
                "id": section.id,
                "heading": section.heading,
                "level": section.level,
                "paragraph_count": len(section.paragraphs),
                "text_chars": len("".join(section.paragraphs)),
                "paragraphs_preview": section.paragraphs[:3],
                "asset_refs": section.asset_refs,
            }
            for section in sections
        ],
        "assets": [
            {
                "id": asset.id,
                "type": asset.type,
                "heading": asset.heading,
                "summary": asset.summary,
                "headers": asset.headers,
                "rows": asset.rows,
                "original_src": asset.original_src,
                "local_copy": asset.local_copy,
                "alt": asset.alt,
            }
            for asset in assets
        ],
    }
    write_json(path, payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an auditable Newma video director storyboard from an article HTML.")
    parser.add_argument("--html", required=True, help="Source article HTML.")
    parser.add_argument("--output-dir", required=True, help="Desktop creation output directory.")
    parser.add_argument("--template-router", default=str(DEFAULT_ROUTER_PATH))
    parser.add_argument("--template-preview-root", action="append", default=[])
    parser.add_argument("--duration-target-sec", type=int, default=300)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_html = Path(args.html).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = output_dir / "assets"
    article, sections, assets = parse_article(source_html, assets_dir / "source_images")
    router = load_router(Path(args.template_router).expanduser().resolve())

    inventory_path = output_dir / "article_asset_inventory.json"
    write_inventory(inventory_path, article, sections, assets)

    storyboard = build_storyboard(
        article,
        sections,
        assets,
        router,
        duration_target_sec=args.duration_target_sec,
    )
    storyboard_path = output_dir / "director_storyboard.nohuman.json"
    write_json(storyboard_path, storyboard)

    voiceover_md = output_dir / "nohuman_voiceover_script.md"
    voiceover_txt = output_dir / "full_voiceover_script.txt"
    write_voiceover(voiceover_md, storyboard)
    write_voiceover_txt(voiceover_txt, storyboard)

    review_html = output_dir / "director_storyboard.nohuman.review.html"
    template_preview_roots = [Path(item).expanduser().resolve() for item in args.template_preview_root]
    write_review_html(
        review_html,
        storyboard,
        assets,
        voiceover_md,
        template_preview_roots=template_preview_roots,
        source_storyboard=storyboard_path,
    )

    manifest = {
        "schema_version": "dasheng.video_director_run_manifest.v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": "awaiting_user_review",
        "source_html": str(source_html),
        "output_dir": str(output_dir),
        "paths": {
            "asset_inventory": str(inventory_path),
            "storyboard": str(storyboard_path),
            "voiceover_markdown": str(voiceover_md),
            "voiceover_text": str(voiceover_txt),
            "review_html": str(review_html),
            "storyboard_template_review_table": str(review_html),
        },
        "external_dependencies": {
            "html_video_root": "${HTML_VIDEO_ROOT:-vendor/reserved/render/html-video}",
            "html_anything_root": "${HTML_ANYTHING_ROOT:-vendor/reserved/render/html-anything}",
            "minimax_cli": "not_called_before_storyboard_approval",
        },
        "next_steps_after_approval": [
            "调用 MiniMax CLI 生成单条完整旁白音频。",
            "按分镜生成 HTML/HyperFrames/GSAP scene pack。",
            "动态化文章表格、图片和数据图。",
            "混入低音量纪录片配乐并渲染竖屏 MP4。",
            "生成质检报告和抽帧图。",
        ],
    }
    manifest_path = output_dir / "director_run_manifest.json"
    write_json(manifest_path, manifest)

    print(
        json.dumps(
            {
                "status": "ok",
                "output_dir": str(output_dir),
                "review_html": str(review_html),
                "storyboard": str(storyboard_path),
                "voiceover": str(voiceover_md),
                "scenes": storyboard["scene_count"],
                "duration": storyboard["duration_estimate_sec"],
                "asset_coverage_ok": storyboard["asset_coverage"]["coverage_ok"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
