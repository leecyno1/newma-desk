#!/usr/bin/env python3
"""生成墨丘利实验室黄金文章的 Meta Pilot Lab 黑金图表。"""

from __future__ import annotations

import csv
import io
import os
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


OUT = Path(os.environ.get("NEWMA_CREATOR_ASSET_OUTPUT", "output/mercury-gold/imgs"))
W, H = 1600, 900
BG = "#08090B"
PANEL = "#111216"
GRID = "#29261E"
GOLD = "#D4AF37"
GOLD_2 = "#F2D98B"
IVORY = "#F6F0E2"
MUTED = "#9C978A"
RED = "#9E2A2B"
BLUE = "#7D9DB8"
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


def text_right(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, *, fill: str, face) -> None:
    box = draw.textbbox((0, 0), text, font=face)
    draw.text((xy[0] - box[2], xy[1]), text, fill=fill, font=face)


def base(title: str, deck: str, source: str, chart_id: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(image)
    for x in range(90, 1511, 110):
        draw.line((x, 205, x, 810), fill=GRID, width=1)
    for y in range(235, 811, 95):
        draw.line((90, y, 1510, y), fill=GRID, width=1)
    draw.text((90, 45), "META PILOT LAB  /  MERCURY MARKET NOTE", fill=GOLD, font=font(20, True))
    text_right(draw, (1510, 45), chart_id, fill=MUTED, face=font(18))
    draw.text((90, 83), title, fill=IVORY, font=font(55, True))
    draw.text((92, 151), deck, fill=GOLD_2, font=font(24))
    draw.line((90, 195, 1510, 195), fill=GOLD, width=2)
    draw.rectangle((0, 828, W, H), fill="#0C0D10")
    draw.text((90, 848), source, fill=MUTED, font=font(17))
    text_right(draw, (1510, 844), "墨丘利实验室", fill=GOLD, face=font(22, True))
    return image, draw


def save(image: Image.Image, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    image.save(OUT / name, quality=96)


def demand_chart() -> None:
    image, draw = base(
        "Q2 谁在买黄金？",
        "ETF 在卖，央行与实物买盘仍在接力",
        "来源：World Gold Council, Gold Demand Trends Q2 2026；单位：吨；分项不含全部 OTC 与统计调整",
        "GOLD / 01",
    )
    data = [("金条与金币", 307.1), ("央行购金", 288.9), ("珠宝消费", 278.2), ("科技用金", 80.4), ("ETF 净流量", -44.8)]
    left, zero, right = 330, 500, 1430
    top, row_h = 245, 102
    scale = (right - zero) / 330
    draw.line((zero, 225, zero, 760), fill="#5C5544", width=2)
    for idx, (label, value) in enumerate(data):
        y = top + idx * row_h
        draw.text((100, y + 16), label, fill=IVORY, font=font(25, True))
        if value >= 0:
            x0, x1, color = zero, zero + value * scale, GOLD if idx < 2 else GOLD_2
            value_x = x1 + 18
        else:
            x0, x1, color = zero + value * scale, zero, RED
            value_x = x0 - 120
        draw.rounded_rectangle((x0, y, x1, y + 58), radius=12, fill=color)
        draw.text((value_x, y + 12), f"{value:+.1f}" if value < 0 else f"{value:.1f}", fill=IVORY, font=font(24, True))
    draw.rounded_rectangle((1125, 704, 1500, 795), radius=18, fill=PANEL, outline=GOLD, width=2)
    draw.text((1150, 722), "总需求（含 OTC）", fill=MUTED, font=font(20))
    draw.text((1150, 752), "1,268.9 吨", fill=GOLD_2, font=font(30, True))
    save(image, "12_meta_pilot_gold_demand.png")


def etf_chart() -> None:
    image, draw = base(
        "资金回来了，但还没全面共振",
        "二季度流出，七月重新流入；资金结构仍有明显地域差异",
        "来源：World Gold Council, Gold ETF Flows July 2026；Q2 流量与 7 月持仓变化均为吨",
        "GOLD / 02",
    )
    draw.rounded_rectangle((90, 235, 760, 785), radius=22, fill=PANEL, outline="#2D2A22", width=2)
    draw.text((125, 270), "持仓变化（吨）", fill=IVORY, font=font(29, True))
    zero_y = 540
    draw.line((145, zero_y, 705, zero_y), fill="#625C4C", width=2)
    bars = [("2026 Q2", -44.8, RED), ("2026 年 7 月", 23.0, GOLD)]
    for idx, (label, value, color) in enumerate(bars):
        x0 = 235 + idx * 265
        h = abs(value) * 5.0
        y0, y1 = (zero_y, zero_y + h) if value < 0 else (zero_y - h, zero_y)
        draw.rounded_rectangle((x0, y0, x0 + 130, y1), radius=13, fill=color)
        draw.text((x0 + 18, y0 - 44 if value > 0 else y1 + 10), f"{value:+.1f}", fill=IVORY, font=font(25, True))
        draw.text((x0 - 5, 685), label, fill=MUTED, font=font(21))
    cards = [
        ("7 月净流入", "30 亿美元"),
        ("全球 AUM", "5,300 亿美元"),
        ("全球持仓", "4,068 吨"),
        ("年初至今流入", "110 亿美元"),
    ]
    for idx, (label, value) in enumerate(cards):
        col, row = idx % 2, idx // 2
        x, y = 820 + col * 350, 255 + row * 250
        draw.rounded_rectangle((x, y, x + 315, y + 205), radius=22, fill=PANEL, outline=GOLD if idx == 0 else "#39342A", width=2)
        draw.text((x + 28, y + 32), label, fill=MUTED, font=font(22))
        draw.text((x + 28, y + 88), value, fill=GOLD_2 if idx != 0 else GOLD, font=font(34, True))
        if idx == 0:
            draw.text((x + 28, y + 145), "连续两个月流出后反转", fill=IVORY, font=font(18))
    save(image, "13_meta_pilot_etf_reversal.png")


def fred_rows() -> list[tuple[str, float]]:
    cached = Path("/tmp/fred-real-rate.csv")
    if cached.is_file():
        rows = list(csv.DictReader(cached.read_text(encoding="utf-8").splitlines()))
    else:
        request = urllib.request.Request(
            "https://fred.stlouisfed.org/graph/fredgraph.csv?id=REAINTRATREARAT10Y",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            rows = list(csv.DictReader(io.StringIO(response.read().decode("utf-8"))))
    return [
        (row["observation_date"], float(row["REAINTRATREARAT10Y"]))
        for row in rows
        if row["observation_date"] >= "2024-01-01" and row["REAINTRATREARAT10Y"] != "."
    ]


def real_rate_chart() -> None:
    rows = fred_rows()
    image, draw = base(
        "实际利率升到 2.20%，黄金仍在高位",
        "传统机会成本框架受到结构性买盘干扰，但没有消失",
        "来源：FRED, 10-Year Real Interest Rate (REAINTRATREARAT10Y)；截至 2026-08",
        "GOLD / 03",
    )
    left, right, top, bottom = 140, 1490, 255, 735
    values = [value for _, value in rows]
    low, high = min(values) - 0.08, max(values) + 0.08
    for tick in range(5):
        value = low + (high - low) * tick / 4
        y = bottom - (bottom - top) * tick / 4
        draw.line((left, y, right, y), fill="#302C23", width=2)
        draw.text((65, y - 13), f"{value:.2f}%", fill=MUTED, font=font(18))
    points = []
    for idx, (_, value) in enumerate(rows):
        x = left + (right - left) * idx / max(1, len(rows) - 1)
        y = bottom - (bottom - top) * (value - low) / (high - low)
        points.append((x, y))
    draw.line(points, fill=GOLD, width=7, joint="curve")
    for x, y in points[-3:]:
        draw.ellipse((x - 8, y - 8, x + 8, y + 8), fill=GOLD_2)
    for idx in sorted({0, len(rows) // 3, 2 * len(rows) // 3, len(rows) - 1}):
        x, _ = points[idx]
        draw.text((x - 42, 758), rows[idx][0][:7], fill=MUTED, font=font(18))
    last_x, last_y = points[-1]
    draw.rounded_rectangle((last_x - 205, last_y - 84, last_x - 15, last_y - 25), radius=14, fill=PANEL, outline=GOLD, width=2)
    draw.text((last_x - 180, last_y - 73), f"{values[-1]:.2f}%", fill=GOLD_2, font=font(27, True))
    save(image, "14_meta_pilot_real_rate.png")


def cot_chart() -> None:
    image, draw = base(
        "COMEX 多头占优，但它只是一扇窗口",
        "Managed Money 净多 141,648 张；不能代表伦敦场外、上海和全球实物市场",
        "来源：CFTC Commitments of Traders，COMEX Gold，2026-08-18",
        "GOLD / 04",
    )
    draw.rounded_rectangle((100, 245, 1500, 760), radius=24, fill=PANEL, outline="#312D24", width=2)
    rows = [("多头", 154595, GOLD), ("空头", 12947, RED)]
    max_value = 165000
    for idx, (label, value, color) in enumerate(rows):
        y = 345 + idx * 150
        draw.text((145, y + 12), label, fill=IVORY, font=font(28, True))
        draw.rounded_rectangle((285, y, 1350, y + 68), radius=15, fill="#24221C")
        draw.rounded_rectangle((285, y, 285 + 1065 * value / max_value, y + 68), radius=15, fill=color)
        text_right(draw, (1440, y + 13), f"{value:,} 张", fill=IVORY, face=font(25, True))
    draw.text((145, 675), "总未平仓", fill=MUTED, font=font(22))
    draw.text((330, 662), "406,260 张", fill=IVORY, font=font(31, True))
    draw.rounded_rectangle((1010, 650, 1445, 730), radius=18, fill="#201C12", outline=GOLD, width=2)
    draw.text((1040, 670), "净多头  141,648 张", fill=GOLD_2, font=font(28, True))
    save(image, "15_meta_pilot_cot_position.png")


def imf_chart() -> None:
    image, draw = base(
        "美元储备份额没有崩，长期逻辑要更精确",
        "2026Q1 美元份额温和回升；黄金超过美债主要来自金价估值效应",
        "来源：IMF Data Brief, COFER, 2026Q1；COFER 不包含货币黄金",
        "GOLD / 05",
    )
    series = [("2025 Q4", 56.42), ("2026 Q1", 57.13)]
    for idx, (label, value) in enumerate(series):
        y = 300 + idx * 170
        draw.text((120, y + 17), label, fill=IVORY, font=font(27, True))
        draw.rounded_rectangle((320, y, 1420, y + 82), radius=18, fill="#25231D")
        draw.rounded_rectangle((320, y, 320 + 1100 * value / 100, y + 82), radius=18, fill=GOLD if idx else GOLD_2)
        text_right(draw, (1490, y + 18), f"{value:.2f}%", fill=IVORY, face=font(28, True))
    draw.rounded_rectangle((115, 660, 1490, 770), radius=20, fill=PANEL, outline=GOLD, width=2)
    draw.text((150, 685), "IMF 的表述：2025 年黄金在官方储备中的占比超过美债，几乎完全由黄金价格上涨推动。", fill=GOLD_2, font=font(24, True))
    draw.text((150, 725), "所以，储备分散是慢变量；单季汇率估值和金价波动会放大表面份额变化。", fill=IVORY, font=font(21))
    save(image, "16_meta_pilot_imf_reserves.png")


def scenario_chart() -> None:
    image, draw = base(
        "未来黄金，重点看四条路",
        "资金与宏观同向时趋势最强；二者背离时波动最大",
        "框架：墨丘利实验室；验证指标来自 WGC、FRED、CFTC 与 IMF",
        "GOLD / 06",
    )
    cells = [
        ("基准路径", "ETF 温和流入\n实际利率缓慢回落\n央行需求保持", GOLD_2),
        ("流动性牛市", "美元走弱\n高低切加速\nETF 与期货共振", GOLD),
        ("宏观逆风", "实际利率再上行\n美元走强\n多头去杠杆", RED),
        ("信用冲击", "财政或制裁风险抬升\n官方与私人买盘同步", BLUE),
    ]
    for idx, (title, desc, color) in enumerate(cells):
        col, row = idx % 2, idx // 2
        x, y = 110 + col * 720, 250 + row * 270
        draw.rounded_rectangle((x, y, x + 660, y + 225), radius=24, fill=PANEL, outline=color, width=3)
        draw.text((x + 35, y + 28), title, fill=color, font=font(31, True))
        for line_idx, line in enumerate(desc.split("\n")):
            draw.text((x + 38, y + 92 + line_idx * 40), f"• {line}", fill=IVORY, font=font(22))
    save(image, "17_meta_pilot_gold_scenarios.png")


def market_snapshot_chart() -> None:
    image, draw = base(
        "海外周日晚盘继续抬价，国内黄金同步走强",
        "8 月 23 日海外参考行情 + 8 月 24 日国内完整收盘",
        "来源：Polygon / Alpha Vantage / Tushare fut_daily / 上海黄金交易所 / 新浪财经 / 腾讯财经",
        "GOLD / 07",
    )
    cards = [
        (90, "海外｜8 月 23 日", GOLD, [
            ("4,623.84", 42, IVORY),
            ("美元/盎司", 21, MUTED),
            ("周日晚间延迟行情", 22, GOLD_2),
            ("较 8 月 21 日  +0.51%", 24, IVORY),
            ("区间 4,602.79—4,624.43", 19, MUTED),
            ("周日数据，不作正式收盘", 18, RED),
        ]),
        (580, "国内黄金｜8 月 24 日", GOLD_2, [
            ("AU2610  1,006.82", 34, IVORY),
            ("较昨结算  +2.86%", 24, GOLD),
            ("Au99.99  1,004.21", 30, IVORY),
            ("收盘涨幅  +2.10%", 22, GOLD_2),
            ("黄金 ETF 样本", 19, MUTED),
            ("+1.87%—+1.97%", 25, IVORY),
        ]),
        (1070, "A 股黄金｜8 月 24 日", BLUE, [
            ("黄金概念  +0.78%", 34, IVORY),
            ("27 只成分", 20, MUTED),
            ("11 涨 / 8 跌 / 8 平", 25, GOLD_2),
            ("西部黄金  +6.27%", 22, IVORY),
            ("山东黄金  -1.48%", 22, IVORY),
            ("板块上涨，但内部分化", 20, BLUE),
        ]),
    ]
    for x, heading, accent, rows in cards:
        draw.rounded_rectangle((x, 245, x + 440, 785), radius=24, fill=PANEL, outline=accent, width=3)
        draw.text((x + 30, 275), heading, fill=accent, font=font(27, True))
        draw.line((x + 30, 325, x + 410, 325), fill="#39342A", width=2)
        y = 355
        for label, size, color in rows:
            draw.text((x + 30, y), label, fill=color, font=font(size, color in (IVORY, GOLD, GOLD_2)))
            y += 66 if size >= 30 else 58
    save(image, "18_meta_pilot_market_snapshot_0824.png")


def watermark_xiaohei() -> None:
    for name in ["09_xiaohei_three_clocks.png", "10_xiaohei_reserve_insurance.png", "11_xiaohei_portfolio_rebalance.png"]:
        path = OUT / name
        image = Image.open(path).convert("RGBA")
        layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        label = "墨丘利实验室  ·  XIAOHEI LAB"
        face = font(max(18, image.width // 68), True)
        box = draw.textbbox((0, 0), label, font=face)
        x, y = image.width - (box[2] - box[0]) - 42, image.height - 58
        draw.rounded_rectangle((x - 18, y - 9, image.width - 22, image.height - 20), radius=12, fill=(5, 5, 5, 165), outline=(212, 175, 55, 150), width=2)
        draw.text((x, y), label, fill=(242, 217, 139, 220), font=face)
        Image.alpha_composite(image, layer).convert("RGB").save(path, quality=96)


def main() -> None:
    market_snapshot_chart()
    demand_chart()
    etf_chart()
    real_rate_chart()
    cot_chart()
    imf_chart()
    scenario_chart()
    watermark_xiaohei()


if __name__ == "__main__":
    main()
