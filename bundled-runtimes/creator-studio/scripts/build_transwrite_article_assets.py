#!/usr/bin/env python3
"""为本轮四篇公众号文章生成可核验的数据图与新闻图片素材。"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


RUN_ROOT_DEFAULT = Path(os.environ.get("NEWMA_CREATOR_RUN_ROOT", "output/creator-run"))
FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, size=size, index=1 if bold else 0)
        except OSError:
            continue
    return ImageFont.load_default()


def canvas(title: str, subtitle: str = "") -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (1600, 900), "#FAFAF7")
    draw = ImageDraw.Draw(image)
    draw.text((90, 55), title, fill="#202124", font=font(54, True))
    if subtitle:
        draw.text((92, 125), subtitle, fill="#6B7280", font=font(25))
    draw.line((90, 170, 1510, 170), fill="#D8D5CC", width=2)
    return image, draw


def source_note(draw: ImageDraw.ImageDraw, text: str) -> None:
    draw.text((92, 848), text, fill="#8A8A84", font=font(20))


def save(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, quality=94)


def horizontal_bars(
    path: Path,
    title: str,
    subtitle: str,
    labels: list[str],
    values: list[float],
    source: str,
    *,
    log_scale: bool = False,
    suffix: str = "",
    colors: list[str] | None = None,
) -> None:
    image, draw = canvas(title, subtitle)
    left, right, top, bottom = 380, 1480, 215, 800
    transformed = [math.log10(max(v, 0.01)) + 2 if log_scale else v for v in values]
    min_value = min(transformed)
    max_value = max(transformed)
    if min_value < 0 and not log_scale:
        span = (max_value - min_value) * 1.08
        zero_x = left + (right - left) * (-min_value) / span
    else:
        max_value *= 1.05
        min_value = 0
        zero_x = left
    row_h = (bottom - top) / len(labels)
    palette = colors or ["#2F5597"] * len(labels)
    for idx, (label, value, width_value) in enumerate(zip(labels, values, transformed)):
        y = top + idx * row_h + 10
        h = max(26, row_h - 20)
        draw.text((90, y + h / 2 - 16), label, fill="#303236", font=font(25))
        if min_value < 0 and not log_scale:
            bar_w = (right - left) * abs(width_value) / ((max_value - min_value) * 1.08)
            x0, x1 = (zero_x - bar_w, zero_x) if width_value < 0 else (zero_x, zero_x + bar_w)
            label_x = x0 - 110 if width_value < 0 else x1 + 14
        else:
            bar_w = (right - left) * width_value / max_value
            x0, x1, label_x = left, left + bar_w, left + bar_w + 14
        draw.rounded_rectangle((x0, y, x1, y + h), radius=12, fill=palette[idx % len(palette)])
        draw.text((label_x, y + h / 2 - 16), f"{value:g}{suffix}", fill="#202124", font=font(24, True))
    if log_scale:
        draw.text((1180, 802), "横轴采用对数尺度", fill="#8A8A84", font=font(18))
    source_note(draw, source)
    save(image, path)


def stock_drawdown_bars(path: Path) -> None:
    image, draw = canvas(
        "高点之后，资本市场已经先做了一轮压力测试",
        "MiniMax 与智谱年内最高价 vs 2026 年 8 月 24 日收盘价",
    )
    rows = [
        ("MiniMax-W（0100.HK）", 1330.0, 312.2, "2026-03-18", "-76.5%"),
        ("智谱（2513.HK）", 2980.0, 1007.0, "2026-06-22", "-66.2%"),
    ]
    left, right = 430, 1460
    for idx, (label, peak, close, peak_date, drawdown) in enumerate(rows):
        y = 270 + idx * 255
        max_width = right - left
        peak_width = max_width
        close_width = max_width * close / peak
        draw.text((90, y + 18), label, fill="#202124", font=font(28, True))
        draw.rounded_rectangle((left, y, left + peak_width, y + 72), radius=12, fill="#D9DCE1")
        draw.rounded_rectangle((left, y + 94, left + close_width, y + 166), radius=12, fill="#D62728")
        draw.text((left + 18, y + 17), f"年内高点 {peak:g} 港元（{peak_date}）", fill="#3F4348", font=font(23))
        draw.text((left + close_width + 16, y + 111), f"8/24 收盘 {close:g} 港元", fill="#202124", font=font(23, True))
        draw.text((1250, y + 195), drawdown, fill="#A61C1C", font=font(34, True))
    source_note(
        draw,
        "来源：Yahoo Finance 日行情（0100.HK、2513.HK），截至 2026-08-24；回撤按年内日内高点至当日收盘计算",
    )
    save(image, path)


def grouped_bars(
    path: Path,
    title: str,
    subtitle: str,
    labels: list[str],
    series: list[tuple[str, list[float], str]],
    source: str,
    suffix: str = "",
) -> None:
    image, draw = canvas(title, subtitle)
    left, right, top, bottom = 170, 1510, 230, 770
    all_values = [value for _, values, _ in series for value in values]
    max_value = max(all_values) * 1.18
    for tick in range(0, 6):
        value = max_value * tick / 5
        y = bottom - (bottom - top) * tick / 5
        draw.line((left, y, right, y), fill="#E4E3DE", width=2)
        draw.text((80, y - 14), f"{value:.0f}", fill="#7A7D82", font=font(20))
    group_w = (right - left) / len(labels)
    bar_w = min(95, group_w / (len(series) + 1))
    for i, label in enumerate(labels):
        center = left + group_w * (i + 0.5)
        for j, (name, values, color) in enumerate(series):
            value = values[i]
            x0 = center + (j - (len(series) - 1) / 2) * (bar_w + 12) - bar_w / 2
            y0 = bottom - (bottom - top) * value / max_value
            draw.rounded_rectangle((x0, y0, x0 + bar_w, bottom), radius=10, fill=color)
            draw.text((x0, y0 - 34), f"{value:g}", fill="#303236", font=font(20, True))
        bbox = draw.textbbox((0, 0), label, font=font(24))
        draw.text((center - (bbox[2] - bbox[0]) / 2, bottom + 22), label, fill="#303236", font=font(24))
    legend_x = 1040
    for idx, (name, _, color) in enumerate(series):
        x = legend_x + idx * 220
        draw.rounded_rectangle((x, 187, x + 30, 217), radius=7, fill=color)
        draw.text((x + 42, 184), name, fill="#404348", font=font(22))
    draw.text((95, 195), f"单位：{suffix}" if suffix else "", fill="#7A7D82", font=font(20))
    source_note(draw, source)
    save(image, path)


def line_chart(path: Path, title: str, subtitle: str, dates: list[str], values: list[float], source: str) -> None:
    image, draw = canvas(title, subtitle)
    left, right, top, bottom = 155, 1510, 225, 770
    minimum, maximum = min(values), max(values)
    span = maximum - minimum or 1
    minimum -= span * 0.15
    maximum += span * 0.15
    for tick in range(5):
        value = minimum + (maximum - minimum) * tick / 4
        y = bottom - (bottom - top) * tick / 4
        draw.line((left, y, right, y), fill="#E4E3DE", width=2)
        draw.text((65, y - 14), f"{value:.2f}%", fill="#73777C", font=font(20))
    points = []
    for i, value in enumerate(values):
        x = left + (right - left) * i / max(1, len(values) - 1)
        y = bottom - (bottom - top) * (value - minimum) / (maximum - minimum)
        points.append((x, y))
    draw.line(points, fill="#A61C1C", width=7, joint="curve")
    for x, y in points[-3:]:
        draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill="#A61C1C")
    label_indices = sorted(set([0, len(dates) // 3, 2 * len(dates) // 3, len(dates) - 1]))
    for idx in label_indices:
        x, _ = points[idx]
        label = dates[idx][:7]
        draw.text((x - 42, bottom + 22), label, fill="#50545A", font=font(20))
    last_x, last_y = points[-1]
    draw.text((last_x - 140, last_y - 52), f"{values[-1]:.2f}%", fill="#A61C1C", font=font(27, True))
    source_note(draw, source)
    save(image, path)


def flow_diagram(path: Path, title: str, subtitle: str, steps: list[tuple[str, str]], source: str) -> None:
    image, draw = canvas(title, subtitle)
    left, right = 90, 1510
    width = (right - left - 60 * (len(steps) - 1)) / len(steps)
    colors = ["#E8F0FE", "#FDECC8", "#E5F4EA", "#F8E8EE", "#EDE8F8"]
    for idx, (name, desc) in enumerate(steps):
        x0 = left + idx * (width + 60)
        y0, y1 = 285, 650
        draw.rounded_rectangle((x0, y0, x0 + width, y1), radius=28, fill=colors[idx % len(colors)], outline="#3B4045", width=3)
        draw.text((x0 + 28, y0 + 42), name, fill="#222529", font=font(31, True))
        lines = desc.split("\n")
        for line_idx, line in enumerate(lines):
            draw.text((x0 + 28, y0 + 125 + line_idx * 48), line, fill="#4F545A", font=font(23))
        if idx < len(steps) - 1:
            x = x0 + width + 12
            y = (y0 + y1) / 2
            draw.line((x, y, x + 38, y), fill="#A61C1C", width=6)
            draw.polygon([(x + 38, y), (x + 22, y - 12), (x + 22, y + 12)], fill="#A61C1C")
    source_note(draw, source)
    save(image, path)


def evidence_matrix(path: Path, title: str, rows: list[tuple[str, str, str]], source: str) -> None:
    image, draw = canvas(title, "当前公开证据能证明什么，不能证明什么")
    x_positions = [90, 390, 980, 1510]
    headers = ["维度", "需要看到的证据", "当前可核验状态"]
    for idx, header in enumerate(headers):
        draw.rectangle((x_positions[idx], 210, x_positions[idx + 1], 270), fill="#2F3A4A")
        draw.text((x_positions[idx] + 18, 223), header, fill="white", font=font(24, True))
    row_h = 88
    for row_idx, (dimension, required, status) in enumerate(rows):
        y0 = 270 + row_idx * row_h
        fill = "#FFFFFF" if row_idx % 2 == 0 else "#F3F4F1"
        draw.rectangle((90, y0, 1510, y0 + row_h), fill=fill, outline="#D6D7D2", width=1)
        draw.text((108, y0 + 25), dimension, fill="#202124", font=font(24, True))
        draw.text((408, y0 + 25), required, fill="#44484D", font=font(21))
        color = "#A61C1C" if "不足" in status else "#1F6B43"
        draw.text((998, y0 + 25), status, fill=color, font=font(22, True))
    source_note(draw, source)
    save(image, path)


def download(url: str, path: Path) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        try:
            Image.open(path).verify()
            return True
        except Exception:  # noqa: BLE001
            path.unlink(missing_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=45) as response, path.open("wb") as output:
            shutil.copyfileobj(response, output)
        Image.open(path).verify()
        return True
    except Exception as exc:  # noqa: BLE001
        path.unlink(missing_ok=True)
        print(f"WARN download failed: {url} ({exc})")
        return False


def build(run_root: Path) -> None:
    article_root = run_root / "04_转写" / "articles"

    deepseek = article_root / "deepseek-ecosystem" / "imgs"
    horizontal_bars(
        deepseek / "01_openrouter_blended_cost.png",
        "同一平台口径下，DeepSeek 已不再是最低价",
        "一百万输入 Token + 一百万输出 Token 的合计成本",
        ["GPT-4o-mini", "GPT-5.6 Luna", "Kimi K2.5", "DeepSeek V4 Pro", "GLM 5.3", "GPT-5.6 Sol", "OpenAI o1"],
        [0.75, 1.40, 2.70, 4.488, 5.80, 12.00, 75.00],
        "来源：OpenRouter 模型目录 API，2026-08-24；聚合平台价，不等于厂商直连价",
        log_scale=True,
        suffix=" 美元",
        colors=["#6BAED6", "#74C476", "#FD8D3C", "#D62728", "#9E9AC8", "#636363", "#252525"],
    )
    grouped_bars(
        deepseek / "02_deepseek_peak_offpeak.png",
        "DeepSeek V4 Pro：这次到底涨了多少",
        "缓存命中输入、缓存未命中输入与输出的调价前后对比",
        ["缓存命中输入", "未命中输入", "输出"],
        [
            ("调价前", [0.025, 3, 6], "#8A8F98"),
            ("当前空闲", [0.15, 4.5, 13.5], "#3B6EA8"),
            ("当前高峰", [0.30, 9, 27], "#A61C1C"),
        ],
        "来源：DeepSeek 官方公告、21财经转引公开调价数据；单位：元/百万 Token",
        suffix="元",
    )
    flow_diagram(
        deepseek / "04_framework_deepseek_ecosystem_killline.png",
        "斩杀线是一条会自我强化的链",
        "价格、调用、收入、融资与研发相乘，最后反馈到下一代模型能力",
        [
            ("价格被压低", "单位收入下降\n毛利空间收窄"),
            ("调用量流失", "用户迁往更强\n或更便宜模型"),
            ("估值打折", "ARR 质量受疑\n融资成本上升"),
            ("研发收缩", "算力、人才\n后训练预算减少"),
            ("能力再落后", "下一代发布变慢\n用户继续流失"),
        ],
        "机制推演：收入 = 单价 × 付费调用量 × 留存；图为分析框架，不代表单家公司财务事实",
    )
    horizontal_bars(
        deepseek / "06_cn_official_price_lanes.png",
        "国产旗舰已经重新站回同一价格带",
        "一百万未缓存输入 + 一百万输出的公开直连合计成本",
        ["DeepSeek V4 Pro 空闲", "Kimi K2.6", "DeepSeek V4 Pro 高峰", "GLM-5.3", "Kimi K3"],
        [18, 33.5, 36, 36, 120],
        "来源：DeepSeek、Kimi、智谱官方价格页，2026-08-24；不同模型能力与任务结构不可直接等同",
        suffix=" 元",
        colors=["#6BAED6", "#74C476", "#D62728", "#9E9AC8", "#252525"],
    )
    horizontal_bars(
        deepseek / "07_deepseek_revenue_scenario.png",
        "一万亿月度 Token，对收入意味着什么",
        "假设输入/输出为 80%/20%，输入缓存命中率 50%",
        ["调价前", "当前空闲", "当前高峰"],
        [2.41, 4.56, 9.12],
        "情景测算：公开单价 × 假设调用结构；单位：百万元/月，不代表 DeepSeek 真实调用量或收入",
        suffix=" 百万元",
        colors=["#8A8F98", "#3B6EA8", "#A61C1C"],
    )
    horizontal_bars(
        deepseek / "08_zhipu_rnd_revenue.png",
        "大模型公司的研发账，远比 API 账单更重",
        "智谱 2025 年公开财务数据",
        ["收入", "研发开支", "经调整净亏损"],
        [7.243, 31.804, 31.820],
        "来源：智谱 2025 年年度业绩公告（港交所），单位：亿元人民币",
        suffix=" 亿元",
        colors=["#74C476", "#D62728", "#8C2D04"],
    )
    stock_drawdown_bars(deepseek / "09_zhipu_minimax_drawdown.png")
    download(
        "https://raw.githubusercontent.com/MiniMax-AI/MiniMax-H3/main/assets/overview.png",
        deepseek / "10_minimax_h3_overview.png",
    )
    source_cover = Path("/tmp/deepseek-killline-cover-2.jpg")
    if source_cover.exists():
        with Image.open(source_cover) as image:
            cropped = image.crop((100, 0, image.width, 815)).convert("RGB")
            cropped.save(deepseek / "03_killline_chart_screenshot.jpg", quality=92)

    alibaba = article_root / "alibaba-ai-finance" / "imgs"
    horizontal_bars(
        alibaba / "03_ai_debt_scale.png",
        "AI 基建融资已经进入数千亿美元量级",
        "发行、项目融资与资本平台的公开/预测口径",
        ["Hyperscaler 2025发行", "2026截至报告时", "2026全年直接发行预测", "2027项目融资预测", "2026 AI相关债务", "NVIDIA平台拟撬动资本"],
        [1080, 1940, 2500, 3000, 5000, 5000],
        "来源：Goldman Sachs；NVIDIA Newsroom，2026-08；预测值不等于已完成融资",
        suffix=" 亿美元",
        colors=["#9ECAE1", "#6BAED6", "#3182BD", "#E6550D", "#A61C1C", "#7A3E9D"],
    )
    grouped_bars(
        alibaba / "04_credit_market_share.png",
        "AI 债务正在重写投资级市场的期限结构",
        "AI 相关发行在不同市场切片中的占比",
        ["投资级总供给", "15年以上投资级发行", "CAPEX债务融资比例"],
        [("占比", [18, 40, 33.3], "#2F5597")],
        "来源：Goldman Sachs，2026；均为研究或预测口径",
        suffix="%",
    )
    download(
        "https://blogs.nvidia.com/wp-content/uploads/2026/08/jhh-support-blog-visual-logo-lock-up-3x4-1.png",
        alibaba / "01_nvidia_ai_finance_news.png",
    )
    download(
        "https://wpimg-wscn.awtmt.com/3cb05363-215b-4091-b37a-87e5fc8bb7cb.png",
        alibaba / "02_alibaba_placement_news.png",
    )

    gold = article_root / "gold-three-cycles" / "imgs"
    horizontal_bars(
        gold / "02_gold_q2_demand.png",
        "2026 年二季度黄金买家结构",
        "ETF 当季净流出，但央行、金条金币与珠宝需求仍在",
        ["金条与金币", "央行购金", "珠宝", "科技", "ETF净流量"],
        [307, 289, 278, 80, -45],
        "来源：World Gold Council, Gold Demand Trends Q2 2026；分项不含全部 OTC 与统计调整",
        suffix=" 吨",
        colors=["#C58B18", "#8A6A17", "#D6A84B", "#6B7280", "#A61C1C"],
    )
    fred_csv = Path("/tmp/fred-real-rate.csv")
    if download_text("https://fred.stlouisfed.org/graph/fredgraph.csv?id=REAINTRATREARAT10Y", fred_csv):
        dates, values = [], []
        with fred_csv.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row.get("observation_date", "") >= "2024-01-01" and row.get("REAINTRATREARAT10Y") not in {None, "."}:
                    dates.append(row["observation_date"])
                    values.append(float(row["REAINTRATREARAT10Y"]))
        line_chart(
            gold / "03_us_real_rate_2024_2026.png",
            "实际利率升至 2.20%，黄金仍处高价区",
            "传统机会成本框架受到结构性买盘干扰，但没有失效",
            dates,
            values,
            "来源：FRED，10-Year Real Interest Rate (REAINTRATREARAT10Y)，截至 2026-08",
        )
    flow_diagram(
        gold / "04_gold_three_horizons.png",
        "判断黄金，要把三个时间尺度分开",
        "短期看资金，中期看宏观组合，长期看美元信用",
        [
            ("短期", "央行现实需求\nETF / COT\n比价与拥挤"),
            ("中期", "实际利率\n通胀预期\n增长与避险"),
            ("长期", "储备替代\n制裁与信用\n美元体系尾部风险"),
        ],
        "框架来源：本文整理；数据验证来自 WGC、FRED、CFTC",
    )
    download(
        "https://www.gold.org/sites/default/files/styles/social_image/public/2026-07/GettyImages-2218658693-web_0.jpg?itok=dXBrgMnK",
        gold / "01_wgc_q2_news.jpg",
    )

    minimax = article_root / "minimax-arr-quality" / "imgs"
    flow_diagram(
        minimax / "01_arr_to_cash_flow.png",
        "ARR 不能直接穿越成现金流",
        "每跨过一道门，都需要新的证据",
        [
            ("ARR", "当前运行速度\n按年化折算"),
            ("合同额", "已经签约\n尚未必履约"),
            ("确认收入", "完成履约义务\n进入损益表"),
            ("现金回款", "预收 / 应收\n回款节奏"),
            ("自由现金流", "扣除推理成本\n销售与研发支出"),
        ],
        "来源：IFRS 15；本文按 AI/SaaS 分析口径整理",
    )
    evidence_matrix(
        minimax / "02_minimax_evidence_matrix.png",
        "MiniMax 增长质量的六道证据门",
        [
            ("留存", "续费率、净收入留存、调用扩张", "公开证据不足"),
            ("毛利", "推理成本、折扣后收入、毛利趋势", "公开证据不足"),
            ("回款", "预充值、应收账款、递延收入", "公开证据不足"),
            ("集中度", "前五大客户与单一客户占比", "公开证据不足"),
            ("补贴", "免费额度、返点、获客成本", "公开证据不足"),
            ("海外", "地区收入、合规成本、本地留存", "公开证据不足"),
        ],
        "来源：Bloomberg 报道口径 + IFRS 15；留存、毛利、回款等经营证据仍不足",
    )
    flow_diagram(
        minimax / "03_arr_scenarios.png",
        "同一个“翻倍”，可能通向三种完全不同的估值",
        "后续要靠留存、毛利和现金流把路径分开",
        [
            ("高质量增长", "多客户扩张\n留存改善\n毛利上升"),
            ("补贴增长", "低价换量\n毛利承压\n回款一般"),
            ("大客户脉冲", "单笔合同\n集中度高\n次年基数风险"),
        ],
        "来源：本文情景分析，不代表对 MiniMax 已发生事实的认定",
    )


def download_text(url: str, path: Path) -> bool:
    if path.is_file() and path.read_bytes().startswith(b"observation_date"):
        return True
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = response.read()
        if not data.startswith(b"observation_date"):
            return False
        path.write_bytes(data)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"WARN data download failed: {url} ({exc})")
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", default=str(RUN_ROOT_DEFAULT))
    args = parser.parse_args()
    build(Path(args.run_root).expanduser().resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
