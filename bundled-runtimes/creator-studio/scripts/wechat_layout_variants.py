#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup


CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
SECTION_PREFIX_RE = re.compile(r"^\s*([一二三四五六七八九十壹贰叁肆伍陆柒捌玖拾]+|[0-9]+)[、.\s]+")


@dataclass(frozen=True)
class Variant:
    name: str
    label: str
    description: str
    primary: str
    accent: str
    text: str
    muted: str
    paper: str
    heading_style: str
    table_head_bg: str
    table_head_color: str
    table_stripe: str
    table_border: str


VARIANTS: dict[str, Variant] = {
    "editorial_blue_left": Variant(
        name="editorial_blue_left",
        label="01 蓝色左线财经版",
        description="最稳妥，适合公众号长文；大标题左对齐，表格紧凑。",
        primary="#0F4C81",
        accent="#E6EEF7",
        text="#233044",
        muted="#667085",
        paper="#FFFFFF",
        heading_style="border-left:5px solid #0F4C81;padding:7px 0 7px 12px;background:transparent;color:#0F4C81;",
        table_head_bg="#163B5C",
        table_head_color="#FFFFFF",
        table_stripe="#F5F8FC",
        table_border="#D9E2EC",
    ),
    "bloomberg_black_gold": Variant(
        name="bloomberg_black_gold",
        label="02 黑金彭博版",
        description="金融感更强，标题克制，重点数据更醒目。",
        primary="#111827",
        accent="#D7A84F",
        text="#1F2937",
        muted="#6B7280",
        paper="#FFFFFF",
        heading_style="border-left:5px solid #D7A84F;padding:7px 0 7px 12px;background:#111827;color:#FFFFFF;",
        table_head_bg="#111827",
        table_head_color="#F9FAFB",
        table_stripe="#FBF7ED",
        table_border="#E7D8B5",
    ),
    "minimal_gray_report": Variant(
        name="minimal_gray_report",
        label="03 极简研报版",
        description="阅读压力最低，适合表格多、数据多的长文。",
        primary="#334155",
        accent="#E2E8F0",
        text="#263241",
        muted="#64748B",
        paper="#FFFFFF",
        heading_style="border-left:4px solid #94A3B8;padding:6px 0 6px 12px;background:transparent;color:#334155;",
        table_head_bg="#F1F5F9",
        table_head_color="#334155",
        table_stripe="#F8FAFC",
        table_border="#D7DEE8",
    ),
    "red_signal_left": Variant(
        name="red_signal_left",
        label="04 红色信号版",
        description="更有警示感，适合风险提示、政策信号类文章。",
        primary="#A93226",
        accent="#FBEDEA",
        text="#2F2F2F",
        muted="#6B6B6B",
        paper="#FFFFFF",
        heading_style="border-left:5px solid #A93226;padding:7px 0 7px 12px;background:#FBEDEA;color:#A93226;",
        table_head_bg="#7F1D1D",
        table_head_color="#FFFFFF",
        table_stripe="#FFF7F5",
        table_border="#E6C7C1",
    ),
}


def merge_style(existing: str | None, updates: dict[str, str]) -> str:
    pairs: dict[str, str] = {}
    for part in (existing or "").split(";"):
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        pairs[key.strip().lower()] = value.strip()
    pairs.update(updates)
    return "; ".join(f"{key}: {value}" for key, value in pairs.items() if value) + ";"


def set_style(tag: Any, updates: dict[str, str]) -> None:
    tag["style"] = merge_style(tag.get("style"), updates)


def strip_section_prefix(text: str) -> str:
    return SECTION_PREFIX_RE.sub("", text).strip()


def apply_variant(html_text: str, variant: Variant) -> str:
    soup = BeautifulSoup(html_text, "html.parser")
    if soup.html:
        soup.html["lang"] = "zh-CN"
    if soup.body:
        set_style(
            soup.body,
            {
                "padding": "20px 18px",
                "background": variant.paper,
                "max-width": "760px",
                "margin": "0 auto",
                "font-size": "15px",
                "line-height": "1.76",
                "color": variant.text,
                "text-align": "left",
                "word-break": "break-word",
                "-webkit-font-smoothing": "antialiased",
            },
        )

    for section in soup.find_all(["section", "div"]):
        set_style(section, {"line-height": "1.76", "text-align": "left"})

    for tag in soup.find_all("p"):
        set_style(
            tag,
            {
                "margin": "0 4px 1.35em",
                "font-size": "15px",
                "line-height": "1.78",
                "letter-spacing": "0.3px",
                "color": variant.text,
                "font-weight": "400",
                "text-align": "left",
            },
        )

    for tag in soup.find_all(["font", "span"]):
        set_style(tag, {"color": "inherit", "letter-spacing": "inherit", "font-size": "inherit"})

    for tag in soup.find_all(["b", "strong"]):
        set_style(tag, {"color": "inherit", "font-weight": "500", "font-size": "inherit"})

    for idx, tag in enumerate(soup.find_all("h2"), start=1):
        text = strip_section_prefix(tag.get_text(" ", strip=True))
        tag.clear()
        tag.append(f"{idx:02d} {text}")
        tag["id"] = f"dasheng-heading-{idx}"
        tag["class"] = "dasheng-wechat-heading"
        set_style(
            tag,
            {
                "font-family": '-apple-system-font,BlinkMacSystemFont,"Helvetica Neue","PingFang SC","Hiragino Sans GB","Microsoft YaHei UI","Microsoft YaHei",Arial,sans-serif',
                "display": "block",
                "box-sizing": "border-box",
                "margin": "2.6em 0 1.15em",
                "font-size": "18px",
                "line-height": "1.45",
                "font-weight": "700",
                "text-align": "left",
            },
        )
        set_style(tag, dict(part.split(":", 1) for part in variant.heading_style.rstrip(";").split(";") if ":" in part))

    for idx, table in enumerate(soup.find_all("table"), start=1):
        table["id"] = f"dasheng-table-{idx}"
        table["class"] = "dasheng-wechat-table"
        set_style(
            table,
            {
                "width": "100%",
                "max-width": "100%",
                "border-collapse": "collapse",
                "border-spacing": "0",
                "margin": "14px 0 22px",
                "font-size": "12px",
                "line-height": "1.36",
                "color": variant.text,
                "table-layout": "auto",
            },
        )
        for th in table.find_all("th"):
            set_style(
                th,
                {
                    "border": f"1px solid {variant.table_border}",
                    "padding": "5px 6px",
                    "background": variant.table_head_bg,
                    "color": variant.table_head_color,
                    "font-size": "12px",
                    "line-height": "1.35",
                    "font-weight": "700",
                    "text-align": "left",
                    "word-break": "normal",
                    "white-space": "normal",
                },
            )
        for row_i, tr in enumerate(table.find_all("tr")):
            if row_i % 2 == 0:
                set_style(tr, {"background": variant.table_stripe})
            for td in tr.find_all("td"):
                set_style(
                    td,
                    {
                        "border": f"1px solid {variant.table_border}",
                        "padding": "5px 6px",
                        "color": variant.text,
                        "font-size": "12px",
                        "line-height": "1.35",
                        "text-align": "left",
                        "vertical-align": "top",
                        "word-break": "normal",
                        "white-space": "normal",
                    },
                )
                for child in td.find_all(["span", "strong", "b", "font"]):
                    set_style(child, {"color": variant.primary, "font-size": "12px", "font-weight": "600", "line-height": "1.35"})

    for hr in soup.find_all("hr"):
        set_style(hr, {"margin": "2.2em 0", "border": "0", "border-top": f"1px solid {variant.accent}"})

    meta = soup.new_tag("meta")
    meta["name"] = "dasheng-wechat-layout"
    meta["content"] = variant.name
    if soup.head:
        soup.head.append(meta)
    return "<!DOCTYPE html>\n" + str(soup)


def render_screenshot(html_path: Path, screenshot_path: Path, *, width: int, height: int, anchor: str | None = None) -> None:
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    uri = html_path.resolve().as_uri()
    if anchor:
        uri = f"{uri}#{anchor}"
    command = [
        str(CHROME),
        "--headless=new",
        "--disable-gpu",
        f"--screenshot={screenshot_path}",
        f"--window-size={width},{height}",
        uri,
    ]
    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def build_contact_sheet(image_paths: list[Path], output_path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    images = [Image.open(path).convert("RGB") for path in image_paths]
    thumb_w = 360
    label_h = 42
    gap = 18
    thumbs = []
    for img in images:
        scale = thumb_w / img.width
        thumb_h = int(img.height * scale)
        thumbs.append(img.resize((thumb_w, thumb_h)))
    sheet_h = max(t.height for t in thumbs) + label_h + gap * 2
    sheet_w = len(thumbs) * thumb_w + (len(thumbs) + 1) * gap
    sheet = Image.new("RGB", (sheet_w, sheet_h), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for idx, (thumb, path) in enumerate(zip(thumbs, image_paths), start=1):
        x = gap + (idx - 1) * (thumb_w + gap)
        y = gap + label_h
        draw.text((x, gap), path.stem.replace("wechat_layout_", ""), fill=(30, 41, 59), font=font)
        sheet.paste(thumb, (x, y))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate compact WeChat layout variants and screenshots.")
    parser.add_argument("--input-html", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--variant", choices=sorted(VARIANTS), help="Apply only one variant.")
    parser.add_argument("--screenshot", action="store_true")
    parser.add_argument("--section-screenshots", action="store_true", help="Also capture first heading/table regions.")
    parser.add_argument("--width", type=int, default=430)
    parser.add_argument("--height", type=int, default=1600)
    args = parser.parse_args()

    input_path = Path(args.input_html).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    html_text = input_path.read_text(encoding="utf-8", errors="ignore")
    selected = [VARIANTS[args.variant]] if args.variant else list(VARIANTS.values())
    results = []
    screenshot_paths: list[Path] = []
    for variant in selected:
        html_out = output_dir / f"wechat_layout_{variant.name}.html"
        html_out.parent.mkdir(parents=True, exist_ok=True)
        html_out.write_text(apply_variant(html_text, variant), encoding="utf-8")
        row = {
            "variant": variant.name,
            "label": variant.label,
            "description": variant.description,
            "html": str(html_out),
        }
        if args.screenshot:
            shot = output_dir / f"wechat_layout_{variant.name}.png"
            render_screenshot(html_out, shot, width=args.width, height=args.height)
            row["screenshot"] = str(shot)
            screenshot_paths.append(shot)
        if args.section_screenshots:
            heading_shot = output_dir / f"wechat_layout_{variant.name}_heading.png"
            table_shot = output_dir / f"wechat_layout_{variant.name}_table.png"
            render_screenshot(html_out, heading_shot, width=args.width, height=args.height, anchor="dasheng-heading-1")
            render_screenshot(html_out, table_shot, width=args.width, height=args.height, anchor="dasheng-table-1")
            row["heading_screenshot"] = str(heading_shot)
            row["table_screenshot"] = str(table_shot)
        results.append(row)
    if screenshot_paths:
        sheet = output_dir / "wechat_layout_contact_sheet.png"
        build_contact_sheet(screenshot_paths, sheet)
        results.append({"contact_sheet": str(sheet)})
    manifest = {
        "input_html": str(input_path),
        "output_dir": str(output_dir),
        "variants": results,
        "rules": [
            "H2 uses Arabic numeric prefix and left alignment.",
            "Tables use 12px compact text and smaller cell padding.",
            "Paragraphs are not globally blue/bold.",
        ],
    }
    (output_dir / "wechat_layout_variants_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
