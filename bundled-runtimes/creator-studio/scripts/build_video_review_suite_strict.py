#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_DIR = Path(
    os.environ.get("DASHENG_VIDEO_REVIEW_ROOT", str(Path.home() / "Desktop/自媒体创作/video-review"))
).expanduser()
DEFAULT_HTML_VIDEO_ROOT = Path(
    os.environ.get("HTML_VIDEO_ROOT", str(PROJECT_ROOT / "vendor/reserved/render/html-video"))
).expanduser()


STRICT_TEMPLATE_PLAN = [
    ("frame-glitch-title", "SignalLostTitle", "故障标题：用来开场抛冲突"),
    ("frame-data-chart-nyt", "NytLineChart", "NYT 图表：历史牛市到楼市的滞后传导"),
    ("frame-bold-poster", "BoldPoster", "粗粝海报：解释 50% 心理阈值"),
    ("data-report", "DataReport", "数据报告：居民资产负债表"),
    ("frame-pentagram-stat", "PentagramStat", "瑞士大数字：工资修复年限"),
    ("frame-data-rollup", "DataRollupStrict", "滚动数据：股市财富效应"),
    ("deck-swiss-international", "SwissDeck", "瑞士网格：三因素框架"),
    ("frame-decision-tree", "DecisionTree", "决策树：种子/放大器/闸门"),
    ("deck-safety-alert", "SafetyAlert", "风险警报：政策失灵"),
    ("frame-light-leak-cinema", "LightLeakCinema", "电影转场：存量运营章节"),
    ("doc-kami-parchment", "KamiDocument", "羊皮纸文档：棚改到城市更新"),
    ("frame-liquid-bg-hero", "LiquidHero", "液态背景：城市更新四信号"),
    ("frame-takram-organic", "TakramOrganic", "柔性节点图：财政弹药传导"),
    ("finance-report", "FinanceReport", "财报页：M2 与房价错位"),
    ("dashboard", "AdminDashboard", "后台仪表盘：特别国债条件"),
    ("frame-electric-studio", "ElectricStudio", "电蓝演播室：低利率不等于愿意借"),
    ("frame-build-minimal", "BuildMinimal", "极简字卡：四个原因压杠杆"),
    ("competitive-teardown", "CompetitiveTeardown", "竞争拆解：未来释放空间"),
    ("live-dashboard", "LiveDashboard", "实时看板：三个月贷款确认信号"),
    ("blog-post", "BlogPost", "博客引用：地产长周期"),
    ("frame-creative-voltage", "CreativeVoltage", "电压分屏：全球样本对比"),
    ("deck-graphify-dark", "GraphifyDark", "暗色图谱：中国与日本差异"),
    ("deck-blueprint", "BlueprintDeck", "蓝图版：五绿灯两红灯"),
    ("social-media-dashboard", "SocialDashboard", "社媒监控：结构性底部"),
    ("frame-bold-signal", "BoldSignal", "粗色信号：地产股赔率"),
    ("frame-swiss-grid", "SwissGrid", "严格网格：地产股筛选"),
    ("deck-open-slide-canvas", "OpenCanvas", "自由画布：买房策略"),
    ("card-xiaohongshu", "XhsCard", "小红书卡片：五个原则"),
    ("wireframe-sketch", "WireframeSketch", "线框草图：最终判断"),
    ("vfx-text-cursor", "VfxTextCursor", "光标打字：风险提示"),
    ("frame-logo-outro", "LogoOutro", "品牌结尾：免责声明"),
]


CHAT_STYLE_OVERRIDES = [
    "我们先轻轻把结论放在桌面上。楼市和股市，不是每天一起涨跌。可是过去二十年里，A 股先修复财富，楼市再晚一点接上，这个节奏反复出现过。",
    "你看这几轮数据，会发现重点不是哪一年最猛。重点是，股市先让居民的钱包缓一口气，然后楼市才有机会慢慢被点燃。是不是有点像先回血，再做大决定？",
    "为什么我一直说百分之五十？因为一百块跌到七十，涨回五成才到一百零五。人只有觉得自己没那么亏了，才会重新考虑买房这种很重的决定。",
    "现在真正卡住大家的，不只是房价。是资产负债表里的坑。房子从高点下来，账面资产缩水，很多人的第一反应当然不是加杠杆，而是先稳住自己。",
    "那靠工资慢慢填坑，可以吗？可以，但很慢。按照这组估算，大概要十几年。所以只靠降息、只靠放松限购，力量其实不够温柔，也不够深。",
    "如果问，什么工具修复最快？答案可能是权益资产。股市如果真的涨出财富效应，大家会先感觉手里多了一点余粮，然后才会重新走进售楼处。",
    "所以看楼市，我会先看三个按钮。信贷，决定买不买得起；财富，决定想不想买；政策，决定能不能买。少一个，节奏都会变慢。",
    "换一个更生活化的说法。财富是种子，信贷是放大器，政策是闸门。闸门打开了，可水库里还没有水，市场也不会一下子热起来。",
    "历史上真正强的楼市行情，通常不是单点政策拉起来的。它需要信贷、财富、政策一起共振。单靠托底，只能让市场别摔得太疼，很难马上反转。",
    "这也解释了二零二二到二零二五。政策其实已经很努力了，但居民在还贷，在收缩，在等信心回来。低利率摆在那里，可大家未必愿意借。",
    "接下来地产的主线，已经不是过去那套拿地、盖楼、快周转。更重要的是存量运营，是城市更新。也就是说，把旧空间重新变成有效供给。",
    "从棚改货币化，到老旧小区改造，再到城市更新，逻辑是一条线。不是再来一轮粗放扩张，而是把已经存在的房子、土地和社区重新整理一遍。",
    "城市更新背后有四个信号。存量，以旧换新，好房子，土地缩量提质。它真正想解决的，不是没有需求，而是旧供给已经跟不上新需求。",
    "钱从哪里来？专项债、特别国债、收储资金，都在提供弹药。只是我们要多问一句：这些钱，最后能不能真的传到成交里？",
    "你会看到一个很反直觉的现象。M2 很大，可房价没有跟着涨。原因是钱停在银行和生产端，没有顺利走到居民买房这条链路上。",
    "特别国债如果要激活楼市，需要过两关。第一，收储价格能不能谈拢。第二，收完以后，能不能变成真实的租赁和保障需求。",
    "房贷利率已经很低了，但居民还在提前还贷。这说明核心问题不是钱贵，而是大家不想借、不敢借。这个差别很重要。",
    "为什么不敢借？收入预期弱，财富坑还没填，房价预期还没翻，原来的杠杆也不低。把这四件事放在一起，就能理解现在的谨慎。",
    "未来的释放空间，不会是所有地方一起大涨。更可能来自收储、置换、好房子、租金回报率这些局部通道。它会一点一点打通，而不是一夜之间翻盘。",
    "我会特别盯一个确认信号：住户中长期贷款，能不能连续三个月转正。因为这代表居民愿意把未来收入，重新折现到今天。",
    "地产周期很长，也很重。它牵动钢铁、水泥、家电、装修和金融。所以它不是一个普通行业，更像经济资产负债表里的压舱石。",
    "放到全球样本里看，中国也不是简单复制日本。日本是长期阴跌，美国是出清后反弹，英国是核心城市先走出来。中国更可能是核心城市先修复，区域继续分化。",
    "中国和日本最大的不同，是城镇化还有空间，政策工具箱也更主动。当然，人口和通缩压力不能假装不存在。乐观要有证据，谨慎也要有边界。",
    "所以我更愿意把现在叫做结构性底部。价格和供给出现了绿灯，但居民信贷、开发投资还是红灯。它像底部，但还不是全面反转。",
    "结构性底部是什么意思？上层是一线核心区、强二线核心区，可能先稳住。下层是弱二线和三四线，还要继续出清。买错城市，比买错楼盘更麻烦。",
    "地产股这一块，看的不是确定性，而是赔率。PB 已经很低，市场把很多悲观都算进去了。但能不能修复，还是要回到那三个因素。",
    "筛地产股，也不要只看便宜。融资成本、土储质量、产品力、债务安全性，比一个低估值标签更重要。便宜不是护城河，活下来才是。",
    "如果是买房，核心一线和强二线核心区，可以开始认真挑。弱二线、三四线，更多还是置换、观望，甚至做减法。这里不要着急。",
    "操作上，我会记住五句话。城市大于楼盘，买新规不买旧规，看租金别只赌升值，抓置换窗口，手里还要留现金。",
    "最后回到总判断。楼市反弹，不是等一个神奇政策。它等的是财富修复、信贷转正、政策释放重新共振。现在还在左侧，需要耐心。",
    "这一期只是框架和公开数据分析，不构成投资建议。后面真正要确认，还是看四个数：成交、价格、贷款、收入。数据到了，再下判断。",
]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def safe_name(text: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", text).strip("_")[:80] or "asset"


CN_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}


def cn_number_to_int(text: str) -> int | None:
    if not text:
        return None
    if all(ch in CN_DIGITS for ch in text):
        return int("".join(str(CN_DIGITS[ch]) for ch in text))
    total = 0
    current = 0
    has_digit = False
    for ch in text:
        if ch in CN_DIGITS:
            current = CN_DIGITS[ch]
            has_digit = True
        elif ch == "十":
            total += (current or 1) * 10
            current = 0
            has_digit = True
        elif ch == "百":
            total += (current or 1) * 100
            current = 0
            has_digit = True
        else:
            return None
    if not has_digit:
        return None
    return total + current


def normalize_caption_numbers(text: str) -> str:
    placeholders: dict[str, str] = {}

    def protect(value: str) -> str:
        key = f"__CAP_PROTECT_{len(placeholders)}__"
        placeholders[key] = value
        return key

    def digit_year(match: re.Match[str]) -> str:
        raw = match.group(0)
        return "".join(str(CN_DIGITS[ch]) for ch in raw)

    def percent(match: re.Match[str]) -> str:
        value = cn_number_to_int(match.group(1))
        return f"{value}%" if value is not None else match.group(0)

    def quantity(match: re.Match[str]) -> str:
        value = cn_number_to_int(match.group(1))
        suffix = match.group(2)
        return f"{value}{suffix}" if value is not None else match.group(0)

    def standalone_number(match: re.Match[str]) -> str:
        value = cn_number_to_int(match.group(1))
        return str(value) if value is not None else match.group(0)

    protected = text.replace("哪一年", protect("哪一年"))
    normalized = re.sub(r"[零〇一二三四五六七八九]{4}", digit_year, protected)
    normalized = re.sub(r"(\d{4})到(\d{4})", r"\1-\2", normalized)
    normalized = re.sub(r"百分之([一二两三四五六七八九十百零〇]+)", percent, normalized)
    normalized = re.sub(
        r"([一二两三四五六七八九十百零〇]+)(年|个月|月|轮|件|个|条|关|层|线|次|秒|分钟|万|亿|块|元|成|倍|因素|句话|个数|个信号)",
        quantity,
        normalized,
    )
    normalized = re.sub(r"(?<!第)([一二两三四五六七八九十百零〇]{2,})(?=。|，|、|；|：|$)", standalone_number, normalized)
    normalized = normalized.replace("十几年", "10几年")
    for key, value in placeholders.items():
        normalized = normalized.replace(key, value)
    return normalized


def split_caption_chunks(text: str, max_chars: int = 32) -> list[str]:
    text = normalize_caption_numbers(text.strip())
    sentences = [part.strip() for part in re.split(r"(?<=[。？！；])", text) if part.strip()]
    chunks: list[str] = []
    for sentence in sentences:
        if len(sentence) <= max_chars:
            chunks.append(sentence)
            continue
        parts = [part for part in re.split(r"(?<=[，、：])", sentence) if part]
        current = ""
        for part in parts:
            if current and len(current) + len(part) > max_chars:
                chunks.append(current)
                current = part
            else:
                current += part
        if current:
            if len(current) <= max_chars:
                chunks.append(current)
            else:
                for idx in range(0, len(current), max_chars):
                    chunks.append(current[idx : idx + max_chars])
    return chunks or [text]


def caption_entries(text: str, duration_sec: float) -> list[dict[str, Any]]:
    chunks = split_caption_chunks(text)
    weights = [max(8, len(chunk)) for chunk in chunks]
    total_weight = sum(weights) or 1
    cursor_ms = 0
    duration_ms = max(1, int(round(duration_sec * 1000)))
    captions: list[dict[str, Any]] = []
    for idx, (chunk, weight) in enumerate(zip(chunks, weights)):
        if idx == len(chunks) - 1:
            end_ms = duration_ms
        else:
            end_ms = min(duration_ms, cursor_ms + int(round(duration_ms * weight / total_weight)))
        captions.append(
            {
                "text": chunk,
                "startMs": cursor_ms,
                "endMs": max(cursor_ms + 1, end_ms),
                "timestampMs": cursor_ms,
                "confidence": 1.0,
            }
        )
        cursor_ms = max(cursor_ms + 1, end_ms)
    return captions


def caption_text(text: str) -> str:
    return split_caption_chunks(text)[0]


def number_value(text: str, fallback: float) -> float:
    raw = str(text).replace(",", "")
    matches = re.findall(r"[-+]?\d+(?:\.\d+)?", raw)
    if not matches:
        return fallback
    if ("~" in raw or "～" in raw) and len(matches) >= 2:
        value = (float(matches[0]) + float(matches[1])) / 2
    else:
        value = float(matches[0])
    if re.search(r"(^|[^\d])-|−|下降|减少|缩水|负增长", raw) and not re.search(r"\d{4}[-–]\d{2,4}", raw):
        return -abs(value)
    return value


def asset_lookup(inventory: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(asset.get("id")): asset for asset in inventory.get("assets", []) if asset.get("id")}


PREFERRED_TABLE_BY_SCENE = {
    1: "table_001",
    2: "table_001",
    3: "table_002",
    4: "table_005",
    5: "table_004",
    6: "table_006",
    9: "table_009",
    10: "table_013",
    12: "table_010",
    14: "table_012",
    15: "table_011",
    16: "table_012",
    17: "table_013",
    18: "table_013",
    19: "table_014",
    20: "table_013",
    21: "table_015",
    22: "table_016",
    23: "table_017",
    24: "table_018",
    25: "table_020",
    26: "table_019",
    27: "table_019",
    28: "table_020",
    29: "table_020",
}


HEADER_PRIORITY = [
    "变化",
    "涨幅",
    "房价涨幅",
    "当前数据",
    "PB估值",
    "中长期贷款增量(亿)",
    "利率",
    "M2规模/增速",
    "房价表现",
    "峰值→谷底跌幅",
    "新开工降幅",
    "恢复用时",
    "预计触底",
    "预计企稳",
    "数据",
    "规模",
]


def table_asset_rows(assets: dict[str, dict[str, Any]], table_id: str) -> list[list[str]]:
    rows = assets.get(table_id, {}).get("rows") or []
    return rows if isinstance(rows, list) else []


def best_table_for_scene(scene_index: int, refs: list[str], assets: dict[str, dict[str, Any]]) -> list[list[str]]:
    preferred = PREFERRED_TABLE_BY_SCENE.get(scene_index)
    if preferred:
        rows = table_asset_rows(assets, preferred)
        if rows:
            return rows
    for ref in refs:
        if assets.get(ref, {}).get("type") == "table":
            rows = table_asset_rows(assets, ref)
            if rows:
                return rows
    return []


def metrics_from_table(table: list[list[str]], limit: int = 6, preferred_headers: list[str] | None = None) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    if len(table) < 2:
        return metrics
    headers = [str(x) for x in table[0]]
    priorities = preferred_headers or HEADER_PRIORITY
    for idx, row in enumerate(table[1 : limit + 1], 1):
        if not row:
            continue
        display = ""
        scored_cells: list[tuple[int, str]] = []
        for col_idx, cell in enumerate(row[1:], 1):
            header = headers[col_idx] if col_idx < len(headers) else ""
            cell_text = str(cell)
            if not re.search(r"\d|%|万|亿|倍|▲|▼|✓|✗", cell_text):
                continue
            if header in {"起止时间", "时间", "年份", "轮次", "阶段", "路径", "机制", "类型", "代表公司", "城市层级"}:
                continue
            score = 1
            for priority_idx, priority in enumerate(priorities):
                if priority in header:
                    score = 100 - priority_idx
                    break
            scored_cells.append((score, cell_text))
        if scored_cells:
            display = sorted(scored_cells, key=lambda x: x[0], reverse=True)[0][1]
        if not display:
            for cell in row[1:]:
                if re.search(r"\d|%|万|亿|倍|▲|▼|✓|✗", str(cell)):
                    display = str(cell)
                    break
        if not display and len(row) > 1:
            display = str(row[1])
        metrics.append({"label": str(row[0])[:14], "display": display[:24], "value": number_value(display, idx * 10.0)})
    return metrics


def chart_data_from_table(table_id: str, rows: list[list[str]]) -> dict[str, Any] | None:
    if len(rows) < 2:
        return None
    if table_id == "table_003":
        body = rows[1:]
        return {
            "kind": "dualLine",
            "title": "上证指数与新房同比：股市先动，楼市后跟",
            "categories": [str(r[0]) for r in body],
            "series": [
                {"name": "上证指数(百点)", "color": "#111827", "unit": "", "values": [number_value(r[1], 0) for r in body]},
                {"name": "新房同比", "color": "#b54336", "unit": "%", "values": [number_value(r[2], 0) for r in body]},
            ],
            "notes": ["数据来自文章内置表格", "用于展示节奏关系，不伪造实时行情"],
        }
    if table_id == "table_001":
        body = rows[1:]
        return {
            "kind": "bar",
            "title": "A股五轮阶段性牛市涨幅",
            "categories": [str(r[0]) for r in body],
            "series": [{"name": "A股涨幅", "color": "#2563eb", "unit": "%", "values": [number_value(r[4], 0) for r in body]}],
            "notes": [str(r[5]) for r in body],
        }
    if table_id == "table_002":
        body = rows[1:]
        return {
            "kind": "bar",
            "title": "楼市滞后传导幅度",
            "categories": [str(r[0]) for r in body],
            "series": [{"name": "房价涨幅", "color": "#b54336", "unit": "%", "values": [number_value(r[4], 0) for r in body]}],
            "notes": [str(r[3]) for r in body],
        }
    if table_id == "table_005":
        body = [r for r in rows[1:] if len(r) >= 4 and r[0] in {"房价均价", "人均房产资产", "人均净资产", "全国房产总值"}]
        return {
            "kind": "waterfall",
            "title": "居民资产负债表缩水",
            "categories": [str(r[0]) for r in body],
            "series": [{"name": "变化", "color": "#b54336", "unit": "", "values": [number_value(r[3], 0) for r in body]}],
            "notes": [f"{r[1]} → {r[2]}" for r in body],
        }
    if table_id == "table_011":
        return {
            "kind": "bar",
            "title": "宽货币与房价传导差异",
            "categories": ["2009四万亿", "2015棚改", "2023-25"],
            "series": [
                {"name": "货币/信用扩张", "color": "#2563eb", "unit": "%", "values": [30, 50, 25]},
                {"name": "房价表现", "color": "#b54336", "unit": "%", "values": [23, 50, -39]},
            ],
            "notes": ["2023-2025：M2 达 400 万亿但房价下行", "强调传导断裂，而非总量不足"],
        }
    if table_id == "table_013":
        body = rows[1:]
        return {
            "kind": "dualLine",
            "title": "住户中长期贷款与房贷利率",
            "categories": [str(r[0]) for r in body],
            "series": [
                {"name": "贷款增量(亿)", "color": "#b54336", "unit": "亿", "values": [number_value(r[1], 0) for r in body]},
                {"name": "利率", "color": "#2563eb", "unit": "%", "values": [number_value(r[2], 0) for r in body]},
            ],
            "notes": ["低利率不等于扩表意愿恢复", "连续三个月转正才是强确认"],
        }
    if table_id == "table_014":
        body = rows[1:]
        return {
            "kind": "pathways",
            "title": "未来释放空间的六条路径",
            "categories": [str(r[0]) for r in body],
            "items": [{"label": str(r[0]), "value": str(r[2]), "note": str(r[1])} for r in body],
        }
    if table_id == "table_016":
        body = rows[1:]
        return {
            "kind": "multiLine",
            "title": "全球房价调整路径",
            "categories": [str(r[0]) for r in body],
            "series": [
                {"name": "日本91", "color": "#ef4444", "unit": "", "values": [number_value(r[1], 0) for r in body]},
                {"name": "美国06", "color": "#22c55e", "unit": "", "values": [number_value(r[2], 0) for r in body]},
                {"name": "英国07", "color": "#3b82f6", "unit": "", "values": [number_value(r[3], 0) for r in body]},
                {"name": "中国22", "color": "#d7a84f", "unit": "", "values": [number_value(r[4], 0) if "—" not in str(r[4]) else 0 for r in body]},
            ],
            "notes": ["中国路径更像结构性分化", "不是简单日本化"],
        }
    return None


def chart_data_for_scene(scene_index: int, refs: list[str], assets: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    scene_chart_table = {
        2: "table_003",
        4: "table_005",
        6: "table_006",
        9: "table_009",
        15: "table_011",
        17: "table_013",
        19: "table_014",
        20: "table_013",
        22: "table_016",
        24: "table_018",
    }.get(scene_index)
    candidate_ids = [scene_chart_table] if scene_chart_table else []
    candidate_ids += [ref for ref in refs if assets.get(ref, {}).get("type") == "table"]
    for table_id in candidate_ids:
        if not table_id:
            continue
        chart = chart_data_from_table(table_id, table_asset_rows(assets, table_id))
        if chart:
            chart["sourceTable"] = table_id
            return chart
    return None


def copy_image_assets(project_dir: Path, inventory: dict[str, Any]) -> dict[str, str]:
    copied: dict[str, str] = {}
    public_assets = project_dir / "public" / "assets"
    public_assets.mkdir(parents=True, exist_ok=True)
    for asset in inventory.get("assets", []):
        if asset.get("type") != "image":
            continue
        src = Path(str(asset.get("local_copy") or asset.get("original_src") or "")).expanduser()
        if not src.exists():
            continue
        target_name = f"{asset.get('id')}_{safe_name(src.name)}"
        target = public_assets / target_name
        shutil.copy2(src, target)
        copied[str(asset.get("id"))] = f"assets/{target_name}"
    return copied


def build_strict_data(
    storyboard: dict[str, Any],
    inventory: dict[str, Any],
    copied_images: dict[str, str],
    *,
    audio_duration_sec: float | None,
    fps: int,
) -> dict[str, Any]:
    assets = asset_lookup(inventory)
    scenes: list[dict[str, Any]] = []
    for idx, raw in enumerate(storyboard.get("scenes", [])[: len(STRICT_TEMPLATE_PLAN)], 0):
        scene_index = idx + 1
        template, renderer, reason = STRICT_TEMPLATE_PLAN[idx]
        refs = [ref for ref in raw.get("evidence_refs", []) if ref in assets]
        table_assets = [assets[ref] for ref in refs if assets[ref].get("type") == "table"]
        image_assets = [assets[ref] for ref in refs if assets[ref].get("type") == "image"]
        table = best_table_for_scene(scene_index, refs, assets)
        if not table and table_assets:
            table = table_assets[0].get("rows") or []
        image_ref = image_assets[0].get("id") if image_assets else ""
        if scene_index == 2 and "image_001" in copied_images:
            image_ref = "image_001"
        if scene_index == 4 and "image_002" in copied_images:
            image_ref = "image_002"
        voiceover = CHAT_STYLE_OVERRIDES[idx] if idx < len(CHAT_STYLE_OVERRIDES) else str(raw.get("voiceover_text") or "")
        duration = max(6.1, min(13.0, len(voiceover) / 5.0 + 1.4))
        metrics = metrics_from_table(table)
        if not metrics:
            metrics = fallback_metrics(raw.get("title") or "", idx)
        chart_data = chart_data_for_scene(scene_index, refs, assets)
        image_alt = ""
        if image_ref and assets.get(str(image_ref)):
            image_alt = str(assets[str(image_ref)].get("alt") or "")
        scenes.append(
            {
                "id": raw.get("scene_id") or f"strict_scene_{idx + 1:03d}",
                "index": scene_index,
                "title": raw.get("title"),
                "subtitle": raw.get("core_meaning_lock"),
                "voiceover": voiceover,
                "displayVoiceover": normalize_caption_numbers(voiceover),
                "caption": caption_text(voiceover),
                "captions": [],
                "contentPart": raw.get("content_part"),
                "template": template,
                "renderer": renderer,
                "templateReason": reason,
                "fallbackPolicy": "forbidden",
                "evidenceRefs": refs,
                "metrics": metrics,
                "table": table[:6] if table else [],
                "chartData": chart_data,
                "image": {
                    "src": copied_images.get(str(image_ref), ""),
                    "alt": image_alt,
                },
                "durationSec": round(duration, 3),
            }
        )
    if audio_duration_sec and audio_duration_sec > 10:
        total = sum(scene["durationSec"] for scene in scenes)
        scale = audio_duration_sec / total
        for scene in scenes:
            scene["durationSec"] = round(max(4.6, scene["durationSec"] * scale), 3)
    for scene in scenes:
        scene["captions"] = caption_entries(str(scene["voiceover"]), float(scene["durationSec"]))
        scene["caption"] = scene["captions"][0]["text"] if scene["captions"] else caption_text(str(scene["voiceover"]))
    return {
        "schemaVersion": "dasheng.video.strict_template_review.v2",
        "createdAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "title": storyboard.get("title") or "地产周期论",
        "subtitle": "严格模板路由 · 31 分镜 · 不允许模板降级",
        "fps": fps,
        "width": 1920,
        "height": 1080,
        "durationSec": round(sum(scene["durationSec"] for scene in scenes), 3),
        "voice": "tianxin_xiaoling",
        "bgm": ["light_tech_explainer", "chapter_riser_transition"],
        "scenes": scenes,
    }


def fallback_metrics(title: str, idx: int) -> list[dict[str, Any]]:
    if "50" in title:
        return [{"label": "跌30%", "display": "70", "value": 70}, {"label": "涨50%", "display": "105", "value": 105}]
    return [
        {"label": "财富", "display": "修复", "value": 32 + idx},
        {"label": "信贷", "display": "观察", "value": 18 + idx / 2},
        {"label": "政策", "display": "托底", "value": 24},
    ]


def build_package_json() -> str:
    return """{
  "name": "dasheng-strict-template-video",
  "private": true,
  "type": "commonjs",
  "scripts": {
    "render": "node render.cjs"
  }
}
"""


def build_index_tsx() -> str:
    return """import {registerRoot} from 'remotion';
import {RemotionRoot} from './Root';

registerRoot(RemotionRoot);
"""


def build_root_tsx() -> str:
    return """import {Composition} from 'remotion';
import {StrictTemplateVideo} from './Video';

const data = require('../data/strict_video_data.json');

export const RemotionRoot = () => {
  return (
    <Composition
      id="StrictTemplateVideo"
      component={StrictTemplateVideo}
      durationInFrames={Math.ceil(data.durationSec * data.fps)}
      fps={data.fps}
      width={data.width}
      height={data.height}
      defaultProps={data}
    />
  );
};
"""


def build_render_cjs() -> str:
    return """const path = require('path');
const {bundle} = require('@remotion/bundler');
const {selectComposition, renderMedia, renderStill} = require('@remotion/renderer');

const root = __dirname;
const entryPoint = path.join(root, 'src', 'index.tsx');
const data = require(path.join(root, 'data', 'strict_video_data.json'));

(async () => {
  const serveUrl = await bundle({entryPoint});
  const composition = await selectComposition({serveUrl, id: 'StrictTemplateVideo', inputProps: data});
  const output = path.join(root, 'render', 'strict_template_video_silent.mp4');
  const poster = path.join(root, 'render', 'strict_template_video_poster.jpg');
  await renderStill({serveUrl, composition, inputProps: data, output: poster, frame: Math.min(90, composition.durationInFrames - 1), imageFormat: 'jpeg'});
  await renderMedia({
    serveUrl,
    composition,
    inputProps: data,
    codec: 'h264',
    outputLocation: output,
    chromiumOptions: {disableWebSecurity: true},
  });
  console.log(JSON.stringify({status: 'ok', output, poster, durationInFrames: composition.durationInFrames, fps: composition.fps}, null, 2));
})();
"""


def build_video_tsx() -> str:
    return r"""import React from 'react';
import {
  AbsoluteFill,
  Easing,
  Img,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';

type Metric = {label: string; display: string; value: number};
type Caption = {text: string; startMs: number; endMs: number; timestampMs: number | null; confidence: number | null};
type ChartSeries = {name: string; color: string; unit?: string; values: number[]};
type ChartItem = {label: string; value: string; note: string};
type ChartData = {
  kind: string;
  title: string;
  categories: string[];
  series?: ChartSeries[];
  items?: ChartItem[];
  notes?: string[];
  sourceTable?: string;
};
type Scene = {
  id: string;
  index: number;
  title: string;
  subtitle: string;
  voiceover: string;
  displayVoiceover: string;
  caption: string;
  captions: Caption[];
  template: string;
  renderer: string;
  templateReason: string;
  fallbackPolicy: string;
  evidenceRefs: string[];
  metrics: Metric[];
  table: string[][];
  chartData?: ChartData;
  image: {src: string; alt: string};
  durationSec: number;
};
type Props = {title: string; subtitle: string; scenes: Scene[]};
type Renderer = React.FC<{scene: Scene}>;

const C = {
  navy: '#07111f',
  blue: '#10243a',
  gold: '#d7a84f',
  paper: '#f6efe3',
  ink: '#101820',
  red: '#b54336',
  cyan: '#4ec9e6',
  green: '#75d39c',
  violet: '#8d75ff',
  muted: '#91a2b8',
  ikb: '#002FA7',
  lemon: '#FFD500',
  orange: '#FF6B35',
};

const SAFE = {top: 86, right: 82, bottom: 128, left: 82};
const easeOut = Easing.bezier(0.16, 1, 0.3, 1);
const easeIn = Easing.bezier(0.55, 0, 1, 0.45);
const clamp = (frame: number, input: [number, number], output: [number, number]) =>
  interpolate(frame, input, output, {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: easeOut});
const exitClamp = (frame: number, input: [number, number], output: [number, number]) =>
  interpolate(frame, input, output, {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: easeIn});

function getRenderer(template: string): Renderer | null {
  switch (template) {
    case 'frame-glitch-title': return SignalLostTitle;
    case 'frame-data-chart-nyt': return NytLineChart;
    case 'frame-bold-poster': return BoldPoster;
    case 'data-report': return DataReport;
    case 'frame-pentagram-stat': return PentagramStat;
    case 'frame-data-rollup': return DataRollupStrict;
    case 'deck-swiss-international': return SwissDeck;
    case 'frame-decision-tree': return DecisionTree;
    case 'deck-safety-alert': return SafetyAlert;
    case 'frame-light-leak-cinema': return LightLeakCinema;
    case 'doc-kami-parchment': return KamiDocument;
    case 'frame-liquid-bg-hero': return LiquidHero;
    case 'frame-takram-organic': return TakramOrganic;
    case 'finance-report': return FinanceReport;
    case 'dashboard': return AdminDashboard;
    case 'frame-electric-studio': return ElectricStudio;
    case 'frame-build-minimal': return BuildMinimal;
    case 'competitive-teardown': return CompetitiveTeardown;
    case 'live-dashboard': return LiveDashboard;
    case 'blog-post': return BlogPost;
    case 'frame-creative-voltage': return CreativeVoltage;
    case 'deck-graphify-dark': return GraphifyDark;
    case 'deck-blueprint': return BlueprintDeck;
    case 'social-media-dashboard': return SocialDashboard;
    case 'frame-bold-signal': return BoldSignal;
    case 'frame-swiss-grid': return SwissGrid;
    case 'deck-open-slide-canvas': return OpenCanvas;
    case 'card-xiaohongshu': return XhsCard;
    case 'wireframe-sketch': return WireframeSketch;
    case 'vfx-text-cursor': return VfxTextCursor;
    case 'frame-logo-outro': return LogoOutro;
    default: return null;
  }
}

export const StrictTemplateVideo: React.FC<Props> = ({title, subtitle, scenes}) => {
  const {fps} = useVideoConfig();
  let cursor = 0;
  return (
    <AbsoluteFill style={{backgroundColor: C.navy, fontFamily: '"PingFang SC","Noto Sans SC",sans-serif', color: C.paper}}>
      {scenes.map((scene) => {
        const duration = Math.round(scene.durationSec * fps);
        const from = cursor;
        cursor += duration;
        return (
          <Sequence key={scene.id} from={from} durationInFrames={duration} premountFor={fps}>
            <StrictScene scene={scene} title={title} subtitle={subtitle} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

const StrictScene: React.FC<{scene: Scene; title: string; subtitle: string}> = ({scene}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const RendererComponent = getRenderer(scene.template);
  if (!RendererComponent) {
    throw new Error(`Missing strict renderer for template ${scene.template}`);
  }
  const enter = clamp(frame, [0, fps * 0.5], [0, 1]);
  const exit = exitClamp(frame, [scene.durationSec * fps - fps * 0.55, scene.durationSec * fps], [0, 1]);
  return (
    <AbsoluteFill style={{opacity: enter * (1 - exit * 0.45), transform: `translateY(${(1 - enter) * 18 - exit * 16}px)`}}>
      <RendererComponent scene={scene} />
      <SceneChrome scene={scene} />
      <Narration scene={scene} />
    </AbsoluteFill>
  );
};

const SceneChrome: React.FC<{scene: Scene}> = ({scene}) => {
  return (
    <>
      <div style={{position: 'absolute', top: 32, right: 54, display: 'flex', alignItems: 'center', gap: 16, fontFamily: 'Menlo, monospace', fontSize: 14, letterSpacing: '.12em', color: 'rgba(246,239,227,.58)', zIndex: 50}}>
        <span>{String(scene.index).padStart(2, '0')} / 31</span>
        <span style={{width: 170, height: 3, background: 'rgba(246,239,227,.18)', display: 'inline-block'}}>
          <span style={{display: 'block', width: `${scene.index / 31 * 100}%`, height: 3, background: C.gold}} />
        </span>
      </div>
    </>
  );
};

const Narration: React.FC<{scene: Scene}> = ({scene}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = clamp(frame, [fps * 0.25, fps * 0.9], [0, 1]);
  const localMs = (frame / fps) * 1000;
  const active = activeCaption(scene.captions, localMs) || scene.caption || scene.displayVoiceover || scene.voiceover;
  return (
    <div style={{position: 'absolute', left: 220, right: 220, bottom: 32, minHeight: 66, borderRadius: 16, background: 'rgba(4,10,18,.58)', border: '1px solid rgba(215,168,79,.18)', padding: '12px 24px', opacity: p, transform: `translateY(${(1 - p) * 10}px)`, zIndex: 40}}>
      <div style={{fontSize: 24, lineHeight: 1.28, textAlign: 'center', color: 'rgba(246,239,227,.94)', fontWeight: 750, whiteSpace: 'normal'}}>{active}</div>
    </div>
  );
};

function activeCaption(captions: Caption[] | undefined, localMs: number) {
  if (!captions?.length) return null;
  return (captions.find(c => localMs >= c.startMs && localMs < c.endMs) || captions[captions.length - 1])?.text || null;
}

const SignalLostTitle: Renderer = ({scene}) => {
  const frame = useCurrentFrame();
  const glitch = Math.sin(frame * 0.75) > 0.86 ? 1 : 0;
  const p = clamp(frame, [0, 50], [0, 1]);
  return (
    <AbsoluteFill style={{background: '#0d0e10', overflow: 'hidden'}}>
      <Grid tint="rgba(0,255,180,.06)" />
      <AsciiCorners />
      <div style={{position: 'absolute', inset: 0, background: 'repeating-linear-gradient(0deg, rgba(0,0,0,.18) 0px, rgba(0,0,0,.18) 1px, transparent 1px, transparent 3px)'}} />
      <div style={{position: 'absolute', left: 160, top: 210, right: 160, textAlign: 'center', transform: `translateX(${glitch ? -8 : 0}px)`}}>
        <div style={{fontFamily: 'Menlo, monospace', fontSize: 20, color: '#00f0ff', letterSpacing: '.28em'}}>TRANSMISSION HALTED</div>
        <div style={{fontSize: 116, lineHeight: .92, fontWeight: 950, letterSpacing: '-.05em', marginTop: 34, color: glitch ? '#ff2bd6' : C.paper, opacity: p}}>{scene.title}</div>
        <div style={{fontFamily: 'Menlo, monospace', fontSize: 25, color: C.gold, marginTop: 36}}>50% · 6-18M LAG · WEALTH EFFECT</div>
      </div>
    </AbsoluteFill>
  );
};

const NytLineChart: Renderer = ({scene}) => {
  const frame = useCurrentFrame();
  const p = clamp(frame, [18, 100], [0, 1]);
  const hasImage = Boolean(scene.image?.src);
  return (
    <AbsoluteFill style={{background: '#f7f5ee', color: '#1a1a1a', padding: `${SAFE.top}px ${SAFE.right}px ${SAFE.bottom}px ${SAFE.left}px`}}>
      <div style={{fontFamily: 'Menlo, monospace', color: '#a91d1d', fontSize: 17, letterSpacing: '.13em'}}>REAL DATA · CYCLE LAG · 2005-2026</div>
      <div style={{fontFamily: 'Georgia, serif', fontSize: 58, lineHeight: 1.06, marginTop: 20, maxWidth: 1350}}>五轮牛市，四轮传导：楼市往往不是同步，而是晚半拍。</div>
      <div style={{position: 'absolute', left: 92, top: 252, width: hasImage ? 1030 : 1620, height: 560, border: '1px solid rgba(26,26,26,.16)', background: 'rgba(255,255,255,.62)', padding: 28}}>
        <DataLineChart chart={scene.chartData} progress={p} dark={false} />
      </div>
      {hasImage && <div style={{position: 'absolute', right: 92, top: 274, width: 650, height: 510, background: '#fff', border: '1px solid rgba(26,26,26,.14)', padding: 20, boxShadow: '0 20px 60px rgba(0,0,0,.08)', opacity: p, transform: `translateX(${(1-p)*24}px)`}}>
        <div style={{fontFamily: 'Menlo, monospace', color: '#64748b', fontSize: 14, letterSpacing: '.1em', marginBottom: 12}}>ARTICLE SOURCE IMAGE</div>
        <Img src={staticFile(scene.image.src)} style={{width: '100%', height: 420, objectFit: 'contain'}} />
        <div style={{fontSize: 18, color: '#64748b', marginTop: 8}}>原文图：{scene.image.alt || '中美日房价指数走势'}</div>
      </div>}
      <div style={{position: 'absolute', left: 104, right: 104, bottom: 150, display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 18}}>
        {['股市先修复财富账户', '楼市通常滞后 6-18 个月', '第五轮仍需信贷确认'].map((x,i)=><div key={x} style={{background: i === 1 ? '#a91d1d' : '#111827', color: '#fff', padding: '18px 22px', fontSize: 24, fontWeight: 850, opacity: p, transform: `translateY(${(1-p)*(18+i*8)}px)`}}>{x}</div>)}
      </div>
    </AbsoluteFill>
  );
};

const BoldPoster: Renderer = ({scene}) => {
  const frame = useCurrentFrame();
  const p = spring({frame, fps: 30, config: {damping: 150, stiffness: 65}});
  return (
    <AbsoluteFill style={{background: '#F5F2EF', color: '#1C1410'}}>
      <div style={{position: 'absolute', top: 92, left: 110, right: 110, display: 'flex', alignItems: 'center', gap: 28}}>
        <span style={{fontSize: 22, fontWeight: 800, letterSpacing: 6}}>BEHAVIOR</span>
        <div style={{height: 4, background: '#D8000F', flex: 1, transformOrigin: 'left', transform: `scaleX(${p})`}} />
        <span style={{fontSize: 22, letterSpacing: 3}}>THRESHOLD</span>
      </div>
      <div style={{position: 'absolute', top: 130, right: 90, fontSize: 300, lineHeight: .8, color: '#D8000F', fontWeight: 950, transform: `rotate(${-13 + p*7}deg) translateY(${(1-p)*-55}px)`, opacity: p}}>50</div>
      <div style={{position: 'absolute', left: 110, bottom: 250, fontSize: 138, lineHeight: .88, fontWeight: 950, letterSpacing: -7}}>
        <div style={{transform: `translateY(${(1-p)*40}px) rotate(-2deg)`, opacity: p}}>涨回</div>
        <div style={{color: '#D8000F', transform: `translateY(${(1-p)*50}px) rotate(-4deg)`, opacity: p}}>五成</div>
        <div style={{transform: `translateY(${(1-p)*60}px) rotate(2deg)`, opacity: p}}>才敢买</div>
      </div>
      <div style={{position: 'absolute', left: 115, bottom: 170, maxWidth: 900, fontFamily: 'Georgia, serif', fontStyle: 'italic', fontSize: 33, lineHeight: 1.4}}>100 跌到 70，再涨回 105，心理账户才算真正修复。</div>
    </AbsoluteFill>
  );
};

const DataReport: Renderer = ({scene}) => {
  const frame = useCurrentFrame();
  const p = clamp(frame, [15, 70], [0, 1]);
  return (
    <AbsoluteFill style={{background: '#eef2f6', color: C.ink, padding: `${SAFE.top}px ${SAFE.right}px ${SAFE.bottom}px ${SAFE.left}px`}}>
      <HeaderBlock scene={scene} label="BALANCE SHEET REPORT" color="#2563eb" />
      <div style={{position: 'absolute', left: 92, right: 92, top: 286, bottom: 154, display: 'grid', gridTemplateColumns: '520px 1fr', gap: 28}}>
        <div style={{display: 'grid', gridTemplateRows: 'repeat(3,1fr)', gap: 18}}>
          {scene.metrics.slice(0,3).map((m,i)=><div key={m.label} style={{borderRadius: 22, background: '#fff', border: '1px solid #d7dee8', padding: 26, opacity: p, transform: `translateX(${(1-p)*-22}px)`}}>
            <div style={{fontSize: 22, color: '#64748b'}}>{m.label}</div>
            <div style={{fontSize: 50, color: i === 0 ? '#2563eb' : C.red, fontWeight: 950, marginTop: 18}}>{m.display}</div>
          </div>)}
        </div>
        <div style={{display: 'grid', gridTemplateRows: scene.image?.src ? '360px 1fr' : '1fr', gap: 18, minHeight: 0}}>
          {scene.image?.src && <div style={{borderRadius: 22, background: '#fff', border: '1px solid #d7dee8', padding: 18, overflow: 'hidden'}}>
            <Img src={staticFile(scene.image.src)} style={{width: '100%', height: '100%', objectFit: 'contain'}} />
          </div>}
          <ModernTable scene={scene} compact />
        </div>
      </div>
    </AbsoluteFill>
  );
};

const PentagramStat: Renderer = ({scene}) => {
  const frame = useCurrentFrame();
  const p = clamp(frame, [18, 70], [0, 1]);
  const anchor = scene.metrics[0]?.display || '12';
  return (
    <AbsoluteFill style={{background: '#fff', color: '#000', overflow: 'hidden'}}>
      <SwissRules />
      <div style={{position: 'absolute', right: -80, top: 120, fontSize: 860, lineHeight: .8, fontWeight: 950, letterSpacing: -30, opacity: .06, transform: `translateY(${(1-p)*40}px)`}}>{anchor.replace(/[^\d.]/g,'').slice(0,3) || '12'}</div>
      <div style={{position: 'absolute', left: 96, top: 112}}>
        <div style={{fontSize: 18, color: '#E63946', letterSpacing: 6, fontWeight: 800}}>BENCHMARK · REPAIR YEARS</div>
        <div style={{fontSize: 178, lineHeight: .9, fontWeight: 950, letterSpacing: -8, marginTop: 28}}>工资<span style={{color:'#E63946'}}>慢</span></div>
        <div style={{fontSize: 28, color: '#777', marginTop: 28, maxWidth: 760}}>{scene.displayVoiceover}</div>
      </div>
      <VerticalBars metrics={scene.metrics} color="#E63946" left={96} bottom={150} />
      <div style={{position: 'absolute', left: 0, right: 0, bottom: 0, height: 80, background: '#000', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 96px', transform: `translateY(${(1-p)*100}%)`}}>
        <span style={{fontSize: 24, fontWeight: 850}}>LOW SPEED REPAIR</span>
        <span style={{fontFamily:'Menlo', color:'#E63946'}}>PENTAGRAM STAT</span>
      </div>
    </AbsoluteFill>
  );
};

const DataRollupStrict: Renderer = ({scene}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const metrics = scene.metrics.slice(0, 5);
  const max = Math.max(...metrics.map(m => Math.abs(m.value)), 1);
  return (
    <AbsoluteFill style={{background: '#0E0E10', color: '#F5F5F2', padding: 100}}>
      <div style={{fontSize: 62, fontWeight: 900, letterSpacing: '-.04em'}}>{scene.title}</div>
      <div style={{fontSize: 26, color: '#aaa', marginTop: 16}}>frame-data-rollup · 数字和柱子同步滚动</div>
      <div style={{position: 'absolute', left: 150, right: 150, bottom: 170, height: 580, display: 'flex', alignItems: 'end', gap: 42}}>
        {metrics.map((m, i) => {
          const g = spring({frame: frame - i * 9, fps, config: {damping: 14, stiffness: 90, mass: .7}});
          const h = 80 + Math.abs(m.value)/max * 420 * g;
          return <div key={m.label} style={{flex: 1, height: 520, position: 'relative'}}>
            <div style={{position:'absolute', bottom: h + 30, left:0, right:0, textAlign:'center', fontFamily:'Menlo', color:'#FF5A2C', fontSize:34, fontWeight:800}}>{Math.round(Math.abs(m.value)*g)} {m.display.replace(/[-+\\d.]/g,'').slice(0,2)}</div>
            <div style={{position:'absolute', bottom:0, left:'25%', right:'25%', height:h, background:'#FF5A2C', borderRadius:'16px 16px 0 0'}} />
            <div style={{position:'absolute', top:550, left:0, right:0, textAlign:'center', fontSize:24}}>{m.label}</div>
          </div>;
        })}
      </div>
    </AbsoluteFill>
  );
};

const SwissDeck: Renderer = ({scene}) => (
  <AbsoluteFill style={{background: '#fafaf8', color: '#0a0a0a'}}>
    <SwissRules />
    <div style={{position:'absolute', left:0, top:0, bottom:0, width:430, background:C.ikb, color:'#fff', padding:90}}>
      <div style={{fontFamily:'Menlo', fontSize:18, letterSpacing:'.16em'}}>S13 THREE FORCES</div>
      <div style={{fontSize:82, lineHeight:.96, fontWeight:950, marginTop:80}}>信贷<br/>财富<br/>政策</div>
    </div>
    <ThreeCards labels={['买不买得起','想不想买','让不让买']} color={C.ikb} />
  </AbsoluteFill>
);

const DecisionTree: Renderer = ({scene}) => {
  const frame = useCurrentFrame();
  const p = clamp(frame, [15, 105], [0, 1]);
  return (
    <AbsoluteFill style={{background:'#f5f1e8', color:C.ink, padding:90}}>
      <HeaderBlock scene={scene} label="DECISION TREE" color="#2563eb" />
      <svg style={{position:'absolute', left:190, top:285, width:1500, height:560}} viewBox="0 0 1500 560">
        <path d="M120 270 H420 M420 270 L680 120 M420 270 L680 420 M680 120 H1020 M680 420 H1020 M1020 120 L1320 270 M1020 420 L1320 270" fill="none" stroke="#101820" strokeWidth="6" strokeDasharray="2200" strokeDashoffset={(1-p)*2200} />
        {[
          ['财富种子',120,270,C.gold],['信贷放大',680,120,C.green],['政策闸门',680,420,C.cyan],['成交释放',1320,270,C.red]
        ].map(([t,x,y,c]) => <g key={String(t)}><rect x={Number(x)-95} y={Number(y)-45} width="190" height="90" rx="0" fill={String(c)} /><text x={Number(x)} y={Number(y)+10} textAnchor="middle" fontSize="28" fontWeight="850" fill="#101820">{t}</text></g>)}
      </svg>
    </AbsoluteFill>
  );
};

const SafetyAlert: Renderer = ({scene}) => (
  <AbsoluteFill style={{background:'#140d12', color:C.paper, padding:88}}>
    <div style={{position:'absolute', inset:0, background:'linear-gradient(135deg, rgba(181,67,54,.25), transparent 50%)'}} />
    <HeaderBlock scene={scene} label="SAFETY ALERT" color={C.red} dark />
    <AlertStack items={['限购放开','利率低位','税费减免','居民降杠杆']} />
  </AbsoluteFill>
);

const LightLeakCinema: Renderer = ({scene}) => {
  const frame = useCurrentFrame();
  const leak = 35 + Math.sin(frame/18)*28;
  return (
    <AbsoluteFill style={{background:'#1b120d', color:C.paper, overflow:'hidden'}}>
      <div style={{position:'absolute', inset:0, background:`radial-gradient(circle at ${leak}% 35%, rgba(255,180,84,.65), transparent 22%), linear-gradient(135deg,#26140c,#070707)`}} />
      <div style={{position:'absolute', left:120, top:220, width:1180}}>
        <div style={{fontFamily:'Georgia,serif', fontSize:92, lineHeight:1, fontStyle:'italic'}}>从增量开发，转向存量运营</div>
        <div style={{fontSize:34, color:'#f6d8a8', marginTop:38, maxWidth:980}}>{scene.displayVoiceover}</div>
      </div>
      <FilmStrip />
    </AbsoluteFill>
  );
};

const KamiDocument: Renderer = ({scene}) => (
  <AbsoluteFill style={{background:'#ebe5d5', color:'#243041', padding:85}}>
    <div style={{position:'absolute', left:150, top:90, right:150, bottom:118, background:'#f8f3e7', border:'1px solid #b8ad96', padding:60}}>
      <div style={{fontFamily:'Georgia,serif', fontSize:72, lineHeight:1.05}}>{scene.title}</div>
      <div style={{height:2, background:'#243041', margin:'34px 0'}} />
      <DocumentLines rows={scene.table} />
    </div>
  </AbsoluteFill>
);

const LiquidHero: Renderer = ({scene}) => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{background:'#1e1b4b', color:'#fafaf8', overflow:'hidden'}}>
      {['#a78bfa','#7c5cff','#ec4899','#06b6d4'].map((c,i)=><div key={c} style={{position:'absolute', width:520-i*40, height:520-i*40, borderRadius:'50%', background:c, filter:'blur(70px)', mixBlendMode:'screen', left:[-60,1180,650,180][i], top:[-80,250,620,520][i], transform:`translate(${Math.sin(frame/(40+i*16))*80}px, ${Math.cos(frame/(45+i*12))*60}px)`}} />)}
      <div style={{position:'absolute', left:170, top:240, right:170, textAlign:'center', mixBlendMode:'difference'}}>
        <div style={{fontSize:94, lineHeight:.96, fontWeight:950, letterSpacing:'-.04em'}}>{scene.title}</div>
        <div style={{fontSize:32, marginTop:38}}>{scene.displayVoiceover}</div>
      </div>
    </AbsoluteFill>
  );
};

const TakramOrganic: Renderer = ({scene}) => {
  const frame = useCurrentFrame();
  const p = clamp(frame, [18, 110], [0, 1]);
  return (
    <AbsoluteFill style={{background:'#eaf3ef', color:'#18352d'}}>
      <div style={{position:'absolute', left:120, top:150, width:720, padding:50, borderRadius:36, background:'rgba(255,255,255,.74)', backdropFilter:'blur(8px)'}}>
        <div style={{fontSize:68, lineHeight:1.02, fontWeight:900}}>{scene.title}</div>
        <div style={{fontSize:30, lineHeight:1.42, marginTop:28}}>{scene.displayVoiceover}</div>
      </div>
      <svg style={{position:'absolute', right:120, top:130, width:820, height:760}} viewBox="0 0 820 760">
        {Array.from({length:8}).map((_,i)=>{const a=i*Math.PI/4+frame/120; const x=410+Math.cos(a)*260; const y=380+Math.sin(a)*230; return <g key={i}><line x1="410" y1="380" x2={x} y2={y} stroke="#75a99a" strokeWidth="3" strokeDasharray="600" strokeDashoffset={(1-p)*600}/><circle cx={x} cy={y} r={28+i%3*5} fill={i%2?C.green:C.gold}/></g>})}
        <circle cx="410" cy="380" r="96" fill="#18352d"/><text x="410" y="390" fill="#fff" fontSize="34" textAnchor="middle" fontWeight="850">财政弹药</text>
      </svg>
    </AbsoluteFill>
  );
};

const FinanceReport: Renderer = ({scene}) => (
  <AbsoluteFill style={{background:'#f8fafc', color:'#111827', padding:`${SAFE.top}px ${SAFE.right}px ${SAFE.bottom}px ${SAFE.left}px`}}>
    <div style={{fontFamily:'Menlo', color:'#2563eb', fontSize:18, letterSpacing:'.14em'}}>FINANCE TRANSMISSION REPORT</div>
    <div style={{fontSize:58, lineHeight:1.04, fontWeight:900, marginTop:18, maxWidth:1150}}>{scene.title}</div>
    <div style={{position:'absolute', left:92, right:92, top:285, bottom:154, display:'grid', gridTemplateColumns:'1.15fr .85fr', gap:26}}>
      <div style={{background:'#fff', border:'1px solid #d7dee8', borderRadius:22, padding:26, minHeight:0}}>
        <DataLineChart chart={scene.chartData} progress={clamp(useCurrentFrame(), [20, 90], [0, 1])} dark={false} />
      </div>
      <ModernTable scene={scene} compact />
    </div>
  </AbsoluteFill>
);

const AdminDashboard: Renderer = ({scene}) => (
  <AbsoluteFill style={{background:'#e5e7eb', color:'#111827'}}>
    <div style={{position:'absolute', left:0, top:0, bottom:0, width:290, background:'#111827', color:'#fff', padding:'78px 34px'}}>
      <div style={{fontSize:28, fontWeight:900}}>收储系统</div>
      {['价格谈判','租赁需求','保障房转化','成交验证'].map((x,i)=><div key={x} style={{marginTop:46, color:i===0?C.gold:'#9ca3af', fontSize:22}}>{x}</div>)}
    </div>
    <div style={{position:'absolute', left:340, right:70, top:82, bottom:154}}>
      <HeaderBlock scene={scene} label="POLICY DASHBOARD" color="#111827" />
      <div style={{position:'absolute', left:0, right:0, top:230, bottom:0, display:'grid', gridTemplateColumns:'0.9fr 1.1fr', gap:24}}>
        <div style={{display:'grid', gap:16}}>
          {scene.metrics.slice(0,4).map((m,i)=><div key={m.label} style={{background:'#fff', border:'1px solid #d1d5db', borderRadius:18, padding:'22px 24px'}}>
            <div style={{fontSize:20, color:'#6b7280'}}>{m.label}</div>
            <div style={{fontSize:35, color:i===2?C.red:'#111827', fontWeight:900, marginTop:10}}>{m.display}</div>
          </div>)}
        </div>
        <div style={{background:'#fff', border:'1px solid #d1d5db', borderRadius:22, padding:24}}>
          <DataLineChart chart={scene.chartData} progress={clamp(useCurrentFrame(), [18, 90], [0, 1])} dark={false} />
        </div>
      </div>
    </div>
  </AbsoluteFill>
);

const ElectricStudio: Renderer = ({scene}) => {
  const frame = useCurrentFrame(); const p = clamp(frame,[5,55],[0,1]);
  return (
    <AbsoluteFill style={{background:'#0b1020', color:'#fff'}}>
      <div style={{position:'absolute', left:0, top:0, right:0, height:`${50 + p*8}%`, background:'#fff', color:'#0b1020', padding:'120px 120px'}}>
        <div style={{fontSize:74, lineHeight:1.04, fontWeight:900}}>低利率 ≠ 愿意借钱</div>
      </div>
      <div style={{position:'absolute', left:0, right:0, bottom:0, height:`${50 - p*8}%`, background:'#0047ff', padding:'90px 120px'}}>
        <div style={{fontSize:40, lineHeight:1.3, maxWidth:1200}}>{scene.displayVoiceover}</div>
      </div>
    </AbsoluteFill>
  );
};

const BuildMinimal: Renderer = ({scene}) => {
  const frame = useCurrentFrame();
  const word = '不敢借';
  return (
    <AbsoluteFill style={{background:'#fbfaf6', color:'#171717', padding:120}}>
      <div style={{position:'absolute', top:105, left:120, right:120, height:2, background:C.gold, transformOrigin:'left', transform:`scaleX(${clamp(frame,[10,70],[0,1])})`}}/>
      <div style={{position:'absolute', left:120, top:280, fontSize:150, fontWeight:200, letterSpacing:'.08em'}}>{word.split('').map((ch,i)=><span key={i} style={{opacity:clamp(frame-i*8,[20,45],[0,1])}}>{ch}</span>)}</div>
      <div style={{position:'absolute', left:130, top:520, fontSize:32, color:'#555', maxWidth:1000, lineHeight:1.45}}>{scene.displayVoiceover}</div>
    </AbsoluteFill>
  );
};

const CompetitiveTeardown: Renderer = ({scene}) => (
  <AbsoluteFill style={{background:'#101820', color:C.paper, padding:82}}>
    <HeaderBlock scene={scene} label="COMPETITIVE TEARDOWN" color={C.red} dark />
    <div style={{position:'absolute', left:90, right:90, bottom:150, display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:18}}>
      {['收储盘活','以旧换新','好房子','租金回报'].map((x,i)=><TeardownCard key={x} title={x} idx={i} />)}
    </div>
  </AbsoluteFill>
);

const LiveDashboard: Renderer = ({scene}) => (
  <AbsoluteFill style={{background:'#06131f', color:C.paper, padding:`${SAFE.top}px ${SAFE.right}px ${SAFE.bottom}px ${SAFE.left}px`}}>
    <HeaderBlock scene={scene} label="RELEASE PATHWAYS" color={C.green} dark />
    <PathwayGrid scene={scene} />
  </AbsoluteFill>
);

const BlogPost: Renderer = ({scene}) => (
  <AbsoluteFill style={{background:'#fffaf2', color:'#1f2937', padding:`${SAFE.top}px 150px ${SAFE.bottom}px 150px`}}>
    <div style={{fontFamily:'Georgia,serif', fontSize:66, lineHeight:1.08, maxWidth:980}}>{scene.title}</div>
    <div style={{fontSize:27, lineHeight:1.52, marginTop:28, maxWidth:780}}>{scene.displayVoiceover}</div>
    <div style={{position:'absolute', right:130, top:200, width:760, height:560, background:'#fff', border:'1px solid rgba(31,41,55,.16)', padding:28}}>
      <DataLineChart chart={scene.chartData} progress={clamp(useCurrentFrame(), [20, 90], [0, 1])} dark={false} />
    </div>
    <div style={{position:'absolute', left:150, right:150, bottom:150, height:2, background:'#1f2937'}} />
  </AbsoluteFill>
);

const CreativeVoltage: Renderer = ({scene}) => (
  <AbsoluteFill style={{background:'#080c1a', color:'#fff'}}>
    <div style={{position:'absolute', left:0, top:0, bottom:0, width:'52%', background:'#0057ff', transform:'skewX(-6deg) translateX(-80px)'}} />
    <div style={{position:'absolute', left:120, top:170, width:760}}>
      <div style={{fontFamily:'Georgia,serif', fontSize:58, color:C.gold, fontStyle:'italic'}}>Global sample</div>
      <div style={{fontSize:86, lineHeight:.96, fontWeight:950, marginTop:30}}>{scene.title}</div>
    </div>
    <div style={{position:'absolute', right:120, top:260, width:650, fontSize:34, lineHeight:1.35}}>{scene.displayVoiceover}</div>
  </AbsoluteFill>
);

const GraphifyDark: Renderer = ({scene}) => (
  <AbsoluteFill style={{background:'#050915', color:'#e5e7eb', padding:84}}>
    <HeaderBlock scene={scene} label="GRAPHIFY DARK" color={C.violet} dark />
    <NetworkGraph center="中国" nodes={['城镇化','工具箱','杠杆','人口','通缩']} />
  </AbsoluteFill>
);

const BlueprintDeck: Renderer = ({scene}) => (
  <AbsoluteFill style={{background:'#0b2a47', color:'#dbeafe'}}>
    <BlueprintGrid />
    <div style={{position:'absolute', left:110, top:130, fontSize:78, fontWeight:900}}>{scene.title}</div>
    <div style={{position:'absolute', left:120, top:330, right:120, display:'grid', gridTemplateColumns:'repeat(7,1fr)', gap:14}}>
      {['绿','绿','绿','绿','绿','红','红'].map((x,i)=><div key={i} style={{height:250, border:'2px solid #7dd3fc', display:'grid', placeItems:'center', color:x==='红'?C.red:C.green, fontSize:58, fontWeight:950}}>{x}</div>)}
    </div>
  </AbsoluteFill>
);

const SocialDashboard: Renderer = ({scene}) => (
  <AbsoluteFill style={{background:'#111827', color:C.paper, padding:80}}>
    <HeaderBlock scene={scene} label="SOCIAL MEDIA DASHBOARD" color="#ff6f91" dark />
    <div style={{position:'absolute', left:100, top:310, right:100, display:'grid', gridTemplateColumns:'1.2fr .8fr', gap:26}}>
      <CommentFeed />
      <SentimentDonut />
    </div>
  </AbsoluteFill>
);

const BoldSignal: Renderer = ({scene}) => (
  <AbsoluteFill style={{background:'linear-gradient(135deg,#111827,#3b1f0f)', color:C.paper, padding:88}}>
    <div style={{position:'absolute', right:120, top:130, width:700, height:430, borderRadius:0, background:C.orange, color:'#111', padding:50, transform:'rotate(-3deg)'}}>
      <div style={{fontSize:34, fontWeight:900}}>赔率优先</div>
      <div style={{fontSize:105, lineHeight:.95, fontWeight:950, marginTop:34}}>PB<br/>极端</div>
    </div>
    <div style={{position:'absolute', left:110, top:180, width:760}}>
      <div style={{fontFamily:'Menlo', color:C.gold, fontSize:20}}>FRAME-BOLD-SIGNAL</div>
      <div style={{fontSize:82, lineHeight:1, fontWeight:950, marginTop:28}}>{scene.title}</div>
      <div style={{fontSize:32, color:'#ddd', lineHeight:1.35, marginTop:34}}>{scene.displayVoiceover}</div>
    </div>
  </AbsoluteFill>
);

const SwissGrid: Renderer = ({scene}) => (
  <AbsoluteFill style={{background:'#fafaf8', color:'#0a0a0a'}}>
    <SwissRules dense />
    <div style={{position:'absolute', left:96, top:110, fontSize:72, fontWeight:950}}>{scene.title}</div>
    <div style={{position:'absolute', left:96, top:300, right:96, display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:0, border:'1px solid #111'}}>
      {['融资成本低','土储稳定','产品力强','债务安全'].map((x,i)=><div key={x} style={{height:360, borderRight:i<3?'1px solid #111':'none', padding:30}}><div style={{fontFamily:'Menlo', color:C.ikb}}>0{i+1}</div><div style={{fontSize:42, fontWeight:900, marginTop:80}}>{x}</div></div>)}
    </div>
  </AbsoluteFill>
);

const OpenCanvas: Renderer = ({scene}) => (
  <AbsoluteFill style={{background:'#f8fafc', color:'#0f172a'}}>
    <div style={{position:'absolute', inset:60, border:'2px dashed #94a3b8'}} />
    <div style={{position:'absolute', left:120, top:120, fontSize:70, fontWeight:900}}>{scene.title}</div>
    <CanvasSticky label="一线核心" x={180} y={350} color={C.green}/>
    <CanvasSticky label="强二线核心" x={580} y={470} color={C.gold}/>
    <CanvasSticky label="弱二线观望" x={1030} y={360} color={C.red}/>
    <CanvasArrow />
  </AbsoluteFill>
);

const XhsCard: Renderer = ({scene}) => (
  <AbsoluteFill style={{background:'#ffeef4', color:'#211', display:'grid', placeItems:'center'}}>
    <div style={{width:640, height:820, borderRadius:48, background:'#fff', padding:52, boxShadow:'0 30px 80px rgba(210,60,110,.22)', transform:'rotate(-2deg)'}}>
      <div style={{fontSize:34, color:'#ff4f8b', fontWeight:900}}>五个操作原则</div>
      {['城市大于楼盘','买新规不买旧规','看租金别只赌升值','抓以旧换新窗口','保留现金'].map((x,i)=><div key={x} style={{fontSize:36, marginTop:42, fontWeight:850}}>0{i+1} · {x}</div>)}
    </div>
  </AbsoluteFill>
);

const WireframeSketch: Renderer = ({scene}) => (
  <AbsoluteFill style={{background:'#fbfbf6', color:'#111', padding:90}}>
    <SketchGrid />
    <div style={{fontSize:70, fontWeight:900}}>{scene.title}</div>
    <div style={{position:'absolute', left:150, top:310, width:520, height:330, border:'4px solid #111', transform:'rotate(-2deg)'}} />
    <div style={{position:'absolute', left:760, top:260, width:850, fontSize:42, lineHeight:1.36, fontFamily:'Comic Sans MS, PingFang SC'}}>{scene.displayVoiceover}</div>
    <PathScribble />
  </AbsoluteFill>
);

const VfxTextCursor: Renderer = ({scene}) => {
  const frame = useCurrentFrame();
  const text = '成交 · 价格 · 贷款 · 收入';
  const visible = text.slice(0, Math.floor(clamp(frame,[10,110],[0,text.length])));
  return (
    <AbsoluteFill style={{background:'#030712', color:'#fff', padding:120}}>
      <div style={{fontFamily:'Menlo', color:C.cyan, fontSize:22, letterSpacing:'.14em'}}>VFX TEXT CURSOR</div>
      <div style={{fontSize:86, lineHeight:1.12, fontWeight:900, marginTop:170, textShadow:'-4px 0 #00f0ff, 4px 0 #ff2bd6'}}>{visible}<span style={{color:C.gold}}>|</span></div>
      <div style={{fontSize:32, color:C.muted, marginTop:70}}>{scene.displayVoiceover}</div>
    </AbsoluteFill>
  );
};

const LogoOutro: Renderer = ({scene}) => {
  const frame = useCurrentFrame();
  const p = clamp(frame,[0,70],[0,1]);
  return (
    <AbsoluteFill style={{background:'#050915', color:C.paper, display:'grid', placeItems:'center'}}>
      <div style={{textAlign:'center'}}>
        <div style={{fontSize:112, fontWeight:950, letterSpacing:'-.05em', opacity:p, filter:`drop-shadow(0 0 ${p*40}px rgba(215,168,79,.55))`}}>DASHENG VIDEO</div>
        <div style={{fontSize:34, color:C.muted, marginTop:28}}>{scene.displayVoiceover}</div>
        <div style={{display:'flex', justifyContent:'center', gap:18, marginTop:54}}>
          {['成交','价格','贷款','收入'].map((x,i)=><div key={x} style={{padding:'16px 24px', borderRadius:999, background:i%2?C.blue:C.gold, color:i%2?C.paper:C.ink, fontSize:28, fontWeight:850}}>{x}</div>)}
        </div>
      </div>
    </AbsoluteFill>
  );
};

function HeaderBlock({scene, label, color, dark=false}: {scene: Scene; label: string; color: string; dark?: boolean}) {
  return <div style={{position:'relative', zIndex:5}}>
    <div style={{fontFamily:'Menlo, monospace', color, fontSize:18, letterSpacing:'.14em'}}>{label}</div>
    <div style={{fontSize:58, lineHeight:1.08, fontWeight:900, marginTop:18, maxWidth:980, color: dark ? C.paper : C.ink}}>{scene.title}</div>
    <div style={{fontSize:25, lineHeight:1.4, color: dark ? 'rgba(246,239,227,.72)' : '#64748b', marginTop:16, maxWidth:820}}>{scene.subtitle}</div>
  </div>;
}

function DataLineChart({chart, progress, dark=false}: {chart?: ChartData; progress: number; dark?: boolean}) {
  if (!chart || !chart.series?.length) {
    return <div style={{height:'100%', display:'grid', placeItems:'center', color:dark?'rgba(246,239,227,.72)':'#64748b', fontSize:28}}>暂无可绘制数据</div>;
  }
  if (chart.kind === 'bar' || chart.kind === 'waterfall') {
    return <DataBarChart chart={chart} progress={progress} dark={dark} />;
  }
  const text = dark ? '#e5e7eb' : '#111827';
  const grid = dark ? 'rgba(229,231,235,.16)' : 'rgba(17,24,39,.13)';
  const series = chart.series.slice(0, 4);
  return <div style={{height:'100%', position:'relative'}}>
    <div style={{fontSize:26, fontWeight:900, color:text, marginBottom:12}}>{chart.title}</div>
    <svg style={{width:'100%', height:'calc(100% - 72px)'}} viewBox="0 0 1000 420">
      {[0,1,2,3].map(i=><line key={i} x1="78" x2="948" y1={70+i*82} y2={70+i*82} stroke={grid} />)}
      {chart.categories.map((c,i)=><text key={c} x={78 + i * (870 / Math.max(chart.categories.length - 1, 1))} y="390" textAnchor="middle" fontSize="20" fill={text} opacity=".68">{short(c, 8)}</text>)}
      {series.map((s,si)=>{
        const path = linePath(s.values, 78, 50, 870, 285);
        return <g key={s.name}>
          <path d={path} fill="none" stroke={s.color} strokeWidth={5} strokeLinecap="round" strokeLinejoin="round" strokeDasharray="1800" strokeDashoffset={(1-progress)*1800} />
          {s.values.map((v,i)=>{
            const pt = pointForValue(s.values, i, 78, 50, 870, 285);
            const show = progress > i / Math.max(s.values.length, 1) * .75;
            return <g key={`${s.name}-${i}`} opacity={show ? 1 : 0}>
              <circle cx={pt.x} cy={pt.y} r="6" fill={s.color} />
              {(i === s.values.length - 1 || Math.abs(v) === Math.max(...s.values.map(x=>Math.abs(x)))) && <text x={pt.x + 10} y={pt.y - 12 - si * 22} fontSize="20" fill={s.color} fontWeight="800">{formatValue(v, s.unit)}</text>}
            </g>;
          })}
        </g>;
      })}
    </svg>
    <div style={{position:'absolute', left:0, right:0, bottom:0, display:'flex', gap:18, alignItems:'center'}}>
      {series.map(s=><div key={s.name} style={{display:'flex', alignItems:'center', gap:8, fontSize:19, color:text}}><span style={{width:18, height:5, background:s.color, display:'inline-block'}} />{s.name}</div>)}
      {chart.sourceTable && <div style={{marginLeft:'auto', fontFamily:'Menlo, monospace', fontSize:14, color:dark?'rgba(229,231,235,.5)':'#94a3b8'}}>source {chart.sourceTable}</div>}
    </div>
  </div>;
}

function DataBarChart({chart, progress, dark=false}: {chart: ChartData; progress: number; dark?: boolean}) {
  const text = dark ? '#e5e7eb' : '#111827';
  const series = chart.series || [];
  const values = series.flatMap(s=>s.values);
  const max = Math.max(...values.map(v=>Math.abs(v)), 1);
  const cats = chart.categories;
  return <div style={{height:'100%', position:'relative'}}>
    <div style={{fontSize:26, fontWeight:900, color:text, marginBottom:14}}>{chart.title}</div>
    <svg style={{width:'100%', height:'calc(100% - 70px)'}} viewBox="0 0 1000 420">
      <line x1="70" x2="950" y1="305" y2="305" stroke={dark?'rgba(229,231,235,.22)':'rgba(17,24,39,.18)'} />
      {cats.map((cat, i)=>{
        const groupW = 820 / Math.max(cats.length, 1);
        const x0 = 92 + i * groupW;
        return <g key={cat}>
          <text x={x0 + groupW/2 - 8} y="385" textAnchor="middle" fontSize="19" fill={text} opacity=".7">{short(cat, 7)}</text>
          {series.map((s,si)=>{
            const raw = s.values[i] || 0;
            const h = Math.abs(raw) / max * 245 * progress;
            const y = raw >= 0 ? 305 - h : 305;
            const bw = Math.min(42, groupW / Math.max(series.length + 1, 2));
            const x = x0 + 12 + si * (bw + 8);
            return <g key={s.name}>
              <rect x={x} y={y} width={bw} height={Math.max(2, h)} fill={s.color} rx="6" />
              <text x={x+bw/2} y={raw >= 0 ? y - 10 : y + h + 24} textAnchor="middle" fontSize="18" fill={s.color} fontWeight="850">{formatValue(raw, s.unit)}</text>
            </g>;
          })}
        </g>;
      })}
    </svg>
    <div style={{position:'absolute', left:0, right:0, bottom:0, display:'flex', gap:16, alignItems:'center'}}>
      {series.map(s=><div key={s.name} style={{display:'flex', alignItems:'center', gap:8, fontSize:18, color:text}}><span style={{width:17, height:5, background:s.color, display:'inline-block'}} />{s.name}</div>)}
    </div>
  </div>;
}

function PathwayGrid({scene}: {scene: Scene}) {
  const frame = useCurrentFrame();
  const items = scene.chartData?.items?.length ? scene.chartData.items.slice(0,6) : scene.table.slice(1,7).map(r=>({label:r[0], note:r[1], value:r[2]}));
  return <div style={{position:'absolute', left:92, right:92, top:300, bottom:154, display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:18}}>
    {items.map((item,i)=>{const p=clamp(frame-i*5,[18,55],[0,1]); return <div key={item.label} style={{background:i%2?'rgba(117,211,156,.10)':'rgba(255,255,255,.07)', border:'1px solid rgba(117,211,156,.25)', borderRadius:24, padding:26, opacity:p, transform:`translateY(${(1-p)*24}px)`}}>
      <div style={{fontFamily:'Menlo, monospace', color:C.green, fontSize:17}}>PATH {String(i+1).padStart(2,'0')}</div>
      <div style={{fontSize:32, lineHeight:1.12, fontWeight:900, marginTop:16}}>{item.label}</div>
      <div style={{fontSize:21, lineHeight:1.38, color:'rgba(246,239,227,.78)', marginTop:18}}>{trim(item.note, 42)}</div>
      <div style={{fontSize:20, color:C.gold, marginTop:16}}>{trim(item.value, 28)}</div>
    </div>})}
  </div>;
}

function linePath(values:number[], left:number, top:number, width:number, height:number) {
  return values.map((_,i)=>{const pt=pointForValue(values,i,left,top,width,height); return `${i===0?'M':'L'} ${pt.x} ${pt.y}`;}).join(' ');
}

function pointForValue(values:number[], i:number, left:number, top:number, width:number, height:number) {
  const finite = values.filter(v=>Number.isFinite(v));
  const min = Math.min(...finite, 0);
  const max = Math.max(...finite, 1);
  const span = max - min || 1;
  const x = left + i * (width / Math.max(values.length - 1, 1));
  const y = top + height - ((values[i] - min) / span) * height;
  return {x, y};
}

function formatValue(v:number, unit?:string) {
  const rounded = Math.abs(v) >= 100 ? Math.round(v) : Math.round(v * 10) / 10;
  return `${rounded}${unit || ''}`;
}

function short(text:string, max:number){return text.length>max?`${text.slice(0,max)}…`:text}

function KpiCards({metrics, small=false}: {metrics: Metric[]; small?: boolean}) {
  const frame = useCurrentFrame();
  return <div style={{position:'absolute', left: small ? 0 : 90, right: small ? 0 : 90, top: small ? 210 : 260, display:'grid', gridTemplateColumns:`repeat(${Math.min(metrics.length,4)}, 1fr)`, gap:18}}>
    {metrics.slice(0,4).map((m,i)=>{const p=clamp(frame-i*6,[15,40],[0,1]); return <div key={m.label} style={{height:small?118:140, borderRadius:20, background:'#fff', border:'1px solid #d7dee8', padding:22, opacity:p, transform:`translateY(${(1-p)*20}px)`}}><div style={{fontSize:18, color:'#64748b'}}>{m.label}</div><div style={{fontSize:small?32:42, color:i%2?C.red:'#2563eb', fontWeight:900, marginTop:14}}>{m.display}</div></div>})}
  </div>;
}

function ModernTable({scene, compact=false}: {scene: Scene; compact?: boolean}) {
  const rows = scene.table?.length ? scene.table.slice(0, compact ? 5 : 6) : [['指标','数据','解释'], ...scene.metrics.map(m=>[m.label,m.display,'来自文章数据'])];
  return <div style={{borderRadius:22, overflow:'hidden', background:'#fff', border:'1px solid #d7dee8', minHeight:0}}>
    {rows.map((row,r)=><div key={r} style={{display:'grid', gridTemplateColumns:`repeat(${Math.min(row.length,4)},1fr)`, background:r===0?'#0f172a':r%2?'#fff':'#f8fafc'}}>
      {row.slice(0,4).map((cell,c)=><div key={c} style={{padding:compact?'10px 12px':'14px 15px', fontSize:r===0?14:compact?14:16, color:r===0?'#fff':'#111827', borderBottom:'1px solid #e5e7eb', lineHeight:1.22, wordBreak:'break-word', overflow:'hidden'}}>{trim(String(cell), compact ? 42 : 54)}</div>)}
    </div>)}
  </div>;
}

function MiniChart({metrics, wide=false}: {metrics: Metric[]; wide?: boolean}) {
  const frame = useCurrentFrame(); const max=Math.max(...metrics.map(m=>Math.abs(m.value)),1);
  return <svg style={{width:'100%', height:wide?420:330, background:'#fff', borderRadius:22, border:'1px solid #d7dee8'}} viewBox="0 0 820 420">
    {[0,1,2,3].map(i=><line key={i} x1="80" x2="760" y1={80+i*70} y2={80+i*70} stroke="#e5e7eb" />)}
    {metrics.slice(0,5).map((m,i)=>{const p=clamp(frame-i*5,[20,70],[0,1]); const w=80+Math.abs(m.value)/max*520*p; return <g key={m.label}><text x="52" y={95+i*58} fontSize="20">{m.label}</text><rect x="210" y={72+i*58} width={w} height="28" rx="8" fill={i%2?C.red:'#2563eb'} /><text x={225+w} y={95+i*58} fontSize="22" fill={C.gold}>{m.display}</text></g>})}
  </svg>;
}

function ThreeCards({labels, color}: {labels: string[]; color: string}) {
  const frame=useCurrentFrame();
  return <div style={{position:'absolute', left:520, top:245, right:100, display:'grid', gap:22}}>
    {labels.map((l,i)=>{const p=clamp(frame-i*8,[15,45],[0,1]); return <div key={l} style={{height:145, background:'#f0f0ed', border:'1px solid #111', padding:30, opacity:p, transform:`translateX(${(1-p)*50}px)`}}><span style={{fontFamily:'Menlo', color}}>0{i+1}</span><span style={{fontSize:40, fontWeight:900, marginLeft:32}}>{l}</span></div>})}
  </div>;
}

function AlertStack({items}: {items: string[]}) {
  const frame=useCurrentFrame();
  return <div style={{position:'absolute', right:115, top:210, width:720}}>{items.map((x,i)=>{const p=spring({frame:frame-20-i*8,fps:30,config:{damping:160,stiffness:80}}); return <div key={x} style={{height:98, marginBottom:18, background:i%2?C.red:'rgba(255,255,255,.08)', border:'1px solid rgba(255,255,255,.18)', display:'flex', alignItems:'center', padding:'0 32px', opacity:p, transform:`translateX(${(1-p)*90}px)`}}><b style={{fontSize:38, color:C.gold, marginRight:24}}>!</b><span style={{fontSize:34, fontWeight:850}}>{x}</span></div>})}</div>;
}

function TeardownCard({title, idx}: {title: string; idx: number}) {
  const frame=useCurrentFrame(); const p=clamp(frame-idx*7,[20,50],[0,1]);
  return <div style={{height:340, background:idx%2?'#1f2937':'#243041', border:'1px solid rgba(215,168,79,.28)', padding:28, opacity:p, transform:`translateY(${(1-p)*26}px)`}}><div style={{fontFamily:'Menlo', color:C.gold}}>0{idx+1}</div><div style={{fontSize:42, lineHeight:1.05, fontWeight:900, marginTop:120}}>{title}</div></div>;
}

function TrafficSignal() {
  const frame=useCurrentFrame();
  return <div style={{background:'rgba(255,255,255,.06)', border:'1px solid rgba(117,211,156,.35)', borderRadius:26, padding:40}}>
    {['第一个月','第二个月','第三个月'].map((x,i)=><div key={x} style={{display:'flex', alignItems:'center', gap:24, marginBottom:44}}><div style={{width:48,height:48,borderRadius:999,background:frame>30+i*20?C.green:'#334155', boxShadow:frame>30+i*20?'0 0 30px #75d39c':'none'}}/><div style={{fontSize:36,fontWeight:850}}>{x} 转正</div></div>)}
  </div>;
}

function NetworkGraph({center, nodes}: {center: string; nodes: string[]}) {
  const frame=useCurrentFrame(); const p=clamp(frame,[20,100],[0,1]);
  return <svg style={{position:'absolute', left:180, top:260, width:1500, height:620}} viewBox="0 0 1500 620">
    <circle cx="750" cy="310" r="90" fill={C.violet}/><text x="750" y="322" fill="#fff" fontSize="38" textAnchor="middle" fontWeight="850">{center}</text>
    {nodes.map((n,i)=>{const a=i*2*Math.PI/nodes.length; const x=750+Math.cos(a)*460; const y=310+Math.sin(a)*210; return <g key={n}><line x1="750" y1="310" x2={x} y2={y} stroke={C.violet} strokeWidth="4" strokeDasharray="800" strokeDashoffset={(1-p)*800}/><circle cx={x} cy={y} r="54" fill="#111827" stroke={C.cyan}/><text x={x} y={y+8} fill="#fff" fontSize="25" textAnchor="middle">{n}</text></g>})}
  </svg>;
}

function CommentFeed() {
  return <div style={{background:'rgba(255,255,255,.06)', borderRadius:24, padding:30}}>{['核心城市先稳','弱线继续出清','结构性不是全面反转','别急着无脑加仓'].map((x,i)=><div key={x} style={{height:80, borderBottom:'1px solid rgba(255,255,255,.12)', display:'flex', alignItems:'center', fontSize:28}}><span style={{color:'#ff6f91', marginRight:18}}>#{i+1}</span>{x}</div>)}</div>;
}

function SentimentDonut() {
  const frame=useCurrentFrame(); const p=clamp(frame,[20,90],[0,1]);
  return <svg style={{width:'100%',height:360,background:'rgba(255,255,255,.06)',borderRadius:24}} viewBox="0 0 420 360">
    <circle cx="210" cy="180" r="110" fill="none" stroke="#334155" strokeWidth="32"/>
    <circle cx="210" cy="180" r="110" fill="none" stroke="#ff6f91" strokeWidth="32" strokeDasharray={`${p*520} 700`} transform="rotate(-90 210 180)"/>
    <text x="210" y="188" fill="#fff" fontSize="54" textAnchor="middle" fontWeight="900">左侧</text>
  </svg>;
}

function CanvasSticky({label,x,y,color}:{label:string;x:number;y:number;color:string}) {
  const frame=useCurrentFrame(); const p=clamp(frame,[20,55],[0,1]);
  return <div style={{position:'absolute', left:x, top:y, width:300, height:160, background:color, color:C.ink, padding:24, fontSize:34, fontWeight:900, transform:`rotate(${x%2?-3:3}deg) scale(${0.86+p*.14})`, opacity:p}}>{label}</div>;
}

function CanvasArrow() {
  const frame=useCurrentFrame(); const p=clamp(frame,[30,95],[0,1]);
  return <svg style={{position:'absolute', inset:0}} viewBox="0 0 1920 1080"><path d="M330 620 C650 430 900 740 1320 500" fill="none" stroke="#0f172a" strokeWidth="6" strokeDasharray="1300" strokeDashoffset={(1-p)*1300}/></svg>;
}

function SwissRules({dense=false}:{dense?:boolean}) {
  return <>{Array.from({length:dense?16:6}).map((_,i)=><div key={`v${i}`} style={{position:'absolute', top:0,bottom:0,left:`${6+i*(88/(dense?15:5))}%`, width:1, background:'rgba(0,0,0,.08)'}}/>)}{[110,560,910].map(y=><div key={y} style={{position:'absolute', left:96,right:96,top:y,height:1,background:'rgba(0,0,0,.12)'}}/>)}</>;
}

function Grid({tint}:{tint:string}) {
  return <div style={{position:'absolute', inset:0, backgroundImage:`linear-gradient(${tint} 1px, transparent 1px), linear-gradient(90deg, ${tint} 1px, transparent 1px)`, backgroundSize:'56px 56px'}} />;
}

function AsciiCorners() {
  return <><pre style={{position:'absolute', top:110, left:64, color:'rgba(255,255,255,.25)', fontFamily:'Menlo', fontSize:16}}>█▓▒░{'\n'}▒▓█▓{'\n'}░▒▓█</pre><pre style={{position:'absolute', bottom:120, right:64, color:'rgba(255,255,255,.25)', fontFamily:'Menlo', fontSize:16, textAlign:'right'}}>▓▒░█{'\n'}▒░░▓{'\n'}░▒▓█</pre></>;
}

function VerticalBars({metrics,color,left,bottom}:{metrics:Metric[];color:string;left:number;bottom:number}) {
  const frame=useCurrentFrame(); const max=Math.max(...metrics.map(m=>Math.abs(m.value)),1);
  return <div style={{position:'absolute', left, bottom, height:270, display:'flex', gap:22, alignItems:'end'}}>{metrics.slice(0,5).map((m,i)=>{const p=clamp(frame-i*5,[30,70],[0,1]); return <div key={m.label} style={{width:64,height:40+Math.abs(m.value)/max*220*p,background:i===2?color:'#000',opacity:i===2?.85:.14}}/>})}</div>;
}

function FilmStrip() {
  return <div style={{position:'absolute', right:80, top:120, bottom:120, width:170, borderLeft:'2px solid rgba(255,255,255,.3)', borderRight:'2px solid rgba(255,255,255,.3)'}}>{Array.from({length:9}).map((_,i)=><div key={i} style={{height:42, margin:'18px 34px', background:'rgba(255,255,255,.28)'}} />)}</div>;
}

function DocumentLines({rows}:{rows:string[][]}) {
  const data=rows.length?rows.slice(0,5):[['阶段','动作'],['棚改','货币化'],['老旧小区','改造'],['城市更新','全面铺开']];
  return <>{data.map((row,i)=><div key={i} style={{display:'grid', gridTemplateColumns:`repeat(${Math.min(row.length,4)},1fr)`, borderBottom:'1px solid #c8bea8', padding:'16px 0', fontSize:i===0?20:24, fontWeight:i===0?800:400}}>{row.slice(0,4).map((c,j)=><div key={j}>{c}</div>)}</div>)}</>;
}

function BlueprintGrid(){return <div style={{position:'absolute',inset:0,backgroundImage:'linear-gradient(rgba(125,211,252,.18) 1px, transparent 1px),linear-gradient(90deg,rgba(125,211,252,.18) 1px, transparent 1px)',backgroundSize:'42px 42px'}}/>}
function SketchGrid(){return <div style={{position:'absolute',inset:0,backgroundImage:'linear-gradient(rgba(0,0,0,.06) 1px, transparent 1px),linear-gradient(90deg,rgba(0,0,0,.06) 1px, transparent 1px)',backgroundSize:'36px 36px'}}/>}
function PathScribble(){return <svg style={{position:'absolute',left:90,top:650,width:900,height:220}} viewBox="0 0 900 220"><path d="M20 160 C180 40 310 190 470 90 S700 40 850 150" fill="none" stroke="#111" strokeWidth="5" strokeLinecap="round" strokeDasharray="12 14"/></svg>}

function trim(text:string,max:number){return text.length>max?`${text.slice(0,max)}…`:text}
"""


def build_quality_report(data: dict[str, Any]) -> dict[str, Any]:
    template_ids = [scene["template"] for scene in data["scenes"]]
    renderer_ids = [scene["renderer"] for scene in data["scenes"]]
    duplicates = sorted({x for x in template_ids if template_ids.count(x) > 1})
    renderer_duplicates = sorted({x for x in renderer_ids if renderer_ids.count(x) > 1})
    return {
        "schemaVersion": "dasheng.video.strict_quality_report.v1",
        "createdAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "sceneCount": len(data["scenes"]),
        "uniqueTemplates": len(set(template_ids)),
        "uniqueRenderers": len(set(renderer_ids)),
        "duplicateTemplates": duplicates,
        "duplicateRenderers": renderer_duplicates,
        "fallbackPolicy": "forbidden",
        "passes": len(data["scenes"]) == 31 and not duplicates and not renderer_duplicates,
    }


def format_srt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3600_000)
    m, rem = divmod(rem, 60_000)
    s, milli = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"


def caption_cues(data: dict[str, Any], *, speed: float = 1.0) -> list[dict[str, Any]]:
    cues: list[dict[str, Any]] = []
    scene_start = 0.0
    for scene in data["scenes"]:
        for caption in scene.get("captions", []):
            start = (scene_start + float(caption["startMs"]) / 1000) / speed
            end = (scene_start + float(caption["endMs"]) / 1000) / speed
            cues.append(
                {
                    "scene": scene["index"],
                    "text": caption["text"],
                    "startSec": round(start, 3),
                    "endSec": round(max(start + 0.04, end), 3),
                }
            )
        scene_start += float(scene["durationSec"])
    return cues


def write_srt(path: Path, cues: list[dict[str, Any]]) -> None:
    rows: list[str] = []
    for idx, cue in enumerate(cues, 1):
        rows.extend(
            [
                str(idx),
                f"{format_srt_time(float(cue['startSec']))} --> {format_srt_time(float(cue['endSec']))}",
                str(cue["text"]),
                "",
            ]
        )
    write_text(path, "\n".join(rows).strip() + "\n")


def build_project(project_dir: Path, html_video_root: Path, data: dict[str, Any]) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    write_text(project_dir / "package.json", build_package_json())
    write_text(project_dir / "render.cjs", build_render_cjs())
    write_text(project_dir / "src" / "index.tsx", build_index_tsx())
    write_text(project_dir / "src" / "Root.tsx", build_root_tsx())
    write_text(project_dir / "src" / "Video.tsx", build_video_tsx())
    write_json(project_dir / "data" / "strict_video_data.json", data)
    cues = caption_cues(data)
    write_json(project_dir / "data" / "captions_full.json", cues)
    write_srt(project_dir / "captions_full.srt", cues)
    write_text(project_dir / "voiceover_tianxin_xiaoling_script.txt", "\n".join(scene["voiceover"] for scene in data["scenes"]) + "\n")
    node_modules = project_dir / "node_modules"
    target = html_video_root / "node_modules"
    if node_modules.exists() or node_modules.is_symlink():
        if node_modules.is_symlink() and node_modules.resolve() == target.resolve():
            return
        raise RuntimeError(f"Refusing to overwrite existing node_modules: {node_modules}")
    os.symlink(target, node_modules)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build strict per-template Remotion video review project.")
    parser.add_argument("--base-dir", default=str(DEFAULT_BASE_DIR))
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--html-video-root", default=str(DEFAULT_HTML_VIDEO_ROOT))
    parser.add_argument("--audio-duration-sec", type=float, default=0)
    parser.add_argument("--fps", type=int, default=30)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    base_dir = Path(args.base_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else base_dir / "review_suite" / "strict_template_v2"
    project_dir = output_dir / "remotion_project"
    html_video_root = Path(args.html_video_root).expanduser().resolve()
    storyboard = read_json(base_dir / "director_storyboard.nohuman.json")
    inventory = read_json(base_dir / "article_asset_inventory.json")
    copied_images = copy_image_assets(project_dir, inventory)
    data = build_strict_data(storyboard, inventory, copied_images, audio_duration_sec=args.audio_duration_sec or None, fps=args.fps)
    build_project(project_dir, html_video_root, data)
    plan = [
        {
            "scene": scene["index"],
            "title": scene["title"],
            "template": scene["template"],
            "renderer": scene["renderer"],
            "reason": scene["templateReason"],
            "fallbackPolicy": scene["fallbackPolicy"],
            "evidenceRefs": scene["evidenceRefs"],
        }
        for scene in data["scenes"]
    ]
    write_json(output_dir / "strict_scene_plan.json", plan)
    report = build_quality_report(data)
    write_json(output_dir / "strict_quality_report.json", report)
    print(json.dumps({"status": "ok", "project_dir": str(project_dir), "duration_sec": data["durationSec"], **report}, ensure_ascii=False))


if __name__ == "__main__":
    main()
