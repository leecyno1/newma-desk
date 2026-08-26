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
DEFAULT_HTML_EVERYTHING_ROOT = Path(
    os.environ.get("HTML_ANYTHING_ROOT", str(PROJECT_ROOT / "vendor/reserved/render/html-anything"))
).expanduser()


FULL_TEMPLATE_SEQUENCE = [
    "frame-glitch-title",
    "frame-data-chart-nyt",
    "frame-flowchart-sticky",
    "data-report",
    "frame-data-rollup",
    "frame-pentagram-stat",
    "deck-swiss-international",
    "frame-decision-tree",
    "deck-safety-alert",
    "frame-light-leak-cinema",
    "doc-kami-parchment",
    "frame-liquid-bg-hero",
    "frame-build-minimal",
    "finance-report",
    "dashboard",
    "frame-nyt-graph",
    "frame-electric-studio",
    "competitive-teardown",
    "live-dashboard",
    "blog-post",
    "frame-warm-grain",
    "deck-graphify-dark",
    "deck-blueprint",
    "social-media-dashboard",
    "frame-takram-organic",
    "frame-bold-signal",
    "deck-open-slide-canvas",
    "card-xiaohongshu",
    "wireframe-sketch",
    "vfx-text-cursor",
    "frame-logo-outro",
]


SHOWCASE_TEMPLATE_PRIORITY = [
    "frame-glitch-title",
    "vfx-text-cursor",
    "frame-liquid-bg-hero",
    "frame-data-rollup",
    "frame-data-chart-nyt",
    "frame-nyt-graph",
    "frame-decision-tree",
    "frame-swiss-grid",
    "frame-warm-grain",
    "frame-bold-poster",
    "frame-bold-signal",
    "frame-electric-studio",
    "frame-light-leak-cinema",
    "frame-pentagram-stat",
    "frame-takram-organic",
    "frame-vignelli",
    "frame-build-minimal",
    "frame-product-promo",
    "frame-logo-outro",
    "video-hyperframes",
    "motion-frames",
    "finance-report",
    "data-report",
    "dashboard",
    "live-dashboard",
    "deck-swiss-international",
    "deck-guizang-editorial",
    "deck-graphify-dark",
    "deck-blueprint",
    "deck-open-slide-canvas",
    "deck-safety-alert",
    "competitive-teardown",
    "exec-briefing-memo",
    "experiment-readout",
    "doc-kami-parchment",
    "magazine-poster",
    "poster-hero",
    "article-magazine",
    "blog-post",
    "mockup-device-3d",
    "frame-macos-notification",
    "card-xiaohongshu",
    "social-media-dashboard",
    "social-carousel",
    "social-x-post-card",
    "wireframe-sketch",
    "web-proto-editorial",
    "web-proto-brutalist",
]


CHAT_STYLE_OVERRIDES = [
    "我先把结论摊开：楼市不是跟股市每天同涨同跌，但过去二十年有个很硬的规律，A股涨过一轮以后，房子往往晚半拍动。",
    "你看五轮牛市这张表，最有意思的不是哪一年涨了多少，而是股市先修复居民钱包，楼市再慢慢接上。",
    "为什么总盯着百分之五十？因为一百块跌到七十，得涨回五成，人才会觉得自己终于没那么亏了，才敢重新做大决策。",
    "现在居民资产负债表这个坑非常深。房产从高点下来以后，账面资产缩水，大家第一反应不是买房，是先保命、先还债。",
    "光靠工资能不能把坑填回来？很慢。原文算下来要十几年，所以只靠降息、放开限购，肯定不够。",
    "那什么补坑最快？权益资产。股市如果真涨出一轮财富效应，居民突然觉得手里有余粮了，看房的人才会回来。",
    "所以我看楼市就盯三个按钮：信贷、财富、政策。信贷管你买不买得起，财富管你想不想买，政策管让不让你买。",
    "更白话一点，财富是种子，信贷是放大器，政策是闸门。闸门打开但水库没水，成交也起不来。",
    "历史上真正厉害的楼市行情，基本都是三件事一起共振。单靠一个政策托底，只能让市场别摔太狠，很难马上反转。",
    "这也是为什么二二年到二五年，政策明明很松，市场还是弱。居民在降杠杆，信心没回来，低利率也撬不动。",
    "接下来地产不是回到老路子，拿地、盖楼、快周转。主线会变成存量运营，城市更新，就是这个时代的关键词。",
    "从棚改货币化，到老旧小区改造，再到城市更新，这条线其实很清楚：不是继续无脑扩张，而是把旧供给重新盘活。",
    "城市更新背后有四个信号：存量、以旧换新、好房子、土地缩量提质。意思就是，需求还在，但旧产品不匹配了。",
    "钱从哪来？专项债、特别国债、收储资金都在给弹药。问题不是有没有钱，而是钱能不能传到真实成交。",
    "你会发现，M2 很大，房价却没动。因为钱卡在银行和生产端，没有顺利进入居民买房这条链路。",
    "特别国债要真正激活楼市，得过两关：收储价格谈得拢，收完以后能不能变成租赁和保障需求。",
    "房贷利率已经很低了，但居民还在提前还贷。这说明当下的核心矛盾不是贷款贵，而是不想借、不敢借。",
    "压住居民杠杆的原因也不复杂：收入预期弱、财富坑没填、房价预期没翻、杠杆本来就不低。",
    "未来释放空间在哪里？不是一刀切大涨，而是收储、置换、好房子、租金回报率这些局部通道慢慢打通。",
    "最关键的确认信号，我会盯住户中长期贷款。连续三个月转正，才说明居民又愿意把未来收入折现到今天。",
    "地产周期很长，它不是一个单独行业。它会牵动钢铁、水泥、家电、装修、金融，所以它更像经济的压舱石。",
    "拿全球样本看，中国不像日本那种一路阴跌，也不完全像美国出清后 V 型。更像核心城市先走出来，区域极端分化。",
    "中国和日本最大的差别，是城镇化还有空间，政策工具箱也更主动。但人口和通缩压力，不能假装不存在。",
    "所以现在我更愿意叫它结构性底部。价格和供给有些绿灯，但居民信贷、开发投资还是红灯，别急着喊全面反转。",
    "结构性底部的意思是，上层核心城市先稳，下层弱二线、三四线继续出清。买错城市，比买错楼盘更麻烦。",
    "地产股这里，逻辑不是确定性，是赔率。PB 打到很低，市场已经塞进很多悲观假设，但它仍然要看三因素能不能共振。",
    "筛地产股也别只看便宜。融资成本、土储质量、产品力、债务安全性，这些比一个低估值标签重要多了。",
    "如果是买房，一线核心和强二线核心可以开始择优；弱二线、三四线，更多还是置换、观望和减仓。",
    "操作上记住五句话：城市大于楼盘，买新规不买旧规，看租金别只赌升值，抓置换窗口，手里留现金。",
    "最后的总判断是，楼市反弹不是等一个政策，而是等财富修复、信贷转正、政策释放重新共振。现在还在左侧。",
    "这期只做框架和数据分析，不构成投资建议。后面真要确认，还是回到四个数：成交、价格、贷款、收入。",
]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def safe_name(text: str) -> str:
    text = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", text).strip("_")
    return text[:80] or "asset"


def parse_frontmatter(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8", errors="ignore")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    meta: dict[str, str] = {}
    for line in parts[1].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip().strip('"').strip("'")
        if value.startswith("[") or value.startswith("{"):
            continue
        meta[key.strip()] = value
    return meta


def scan_html_video_templates(root: Path) -> list[dict[str, Any]]:
    templates: list[dict[str, Any]] = []
    templates_dir = root / "templates"
    if not templates_dir.exists():
        return templates
    for folder in sorted(p for p in templates_dir.iterdir() if p.is_dir()):
        yaml_path = folder / "template.html-video.yaml"
        skill_path = folder / "SKILL.md"
        meta = parse_frontmatter(skill_path)
        yaml_text = yaml_path.read_text(encoding="utf-8", errors="ignore") if yaml_path.exists() else ""
        def pick(key: str, fallback: str = "") -> str:
            m = re.search(rf"^{key}:\s*(.+)$", yaml_text, re.M)
            return (m.group(1).strip().strip('"').strip("'") if m else fallback)
        templates.append(
            {
                "id": pick("id", folder.name),
                "name": pick("name", meta.get("name") or folder.name),
                "zhName": meta.get("zh_name") or pick("name", folder.name),
                "description": pick("description", meta.get("description") or "html-video template").replace(">", "").strip(),
                "source": "html-video",
                "category": pick("category", "video-frame"),
                "path": str(folder),
            }
        )
    return templates


def scan_html_everything_templates(root: Path) -> list[dict[str, Any]]:
    templates: list[dict[str, Any]] = []
    skills_dir = root / "next" / "src" / "lib" / "templates" / "skills"
    if not skills_dir.exists():
        return templates
    for folder in sorted(p for p in skills_dir.iterdir() if p.is_dir()):
        meta = parse_frontmatter(folder / "SKILL.md")
        templates.append(
            {
                "id": meta.get("name") or folder.name,
                "name": meta.get("en_name") or meta.get("name") or folder.name,
                "zhName": meta.get("zh_name") or meta.get("name") or folder.name,
                "description": meta.get("description") or "HTML Anything skill template",
                "source": "html-everything",
                "category": meta.get("category") or meta.get("scenario") or "html-template",
                "path": str(folder),
            }
        )
    return templates


def template_catalog(html_video_root: Path, html_everything_root: Path) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for template in scan_html_video_templates(html_video_root) + scan_html_everything_templates(html_everything_root):
        key = (template["source"], template["id"])
        if key in seen:
            continue
        seen.add(key)
        template["visualFamily"] = family_for_template(template["id"], template.get("category", ""))
        template["reviewUse"] = review_use_for_template(template["id"])
        out.append(template)
    return out


def family_for_template(template_id: str, category: str = "") -> str:
    tid = template_id.lower()
    cat = category.lower()
    if "glitch" in tid or "cursor" in tid or "hero" in tid:
        return "kinetic-title"
    if "chart" in tid or "graph" in tid or "finance" in tid or "data" in tid or "dashboard" in tid:
        return "data-viz"
    if "flow" in tid or "decision" in tid or "blueprint" in tid or "wireframe" in tid:
        return "logic-map"
    if "safety" in tid or "alert" in tid or "teardown" in tid:
        return "risk-alert"
    if "light" in tid or "cinema" in tid or "warm" in tid or "takram" in tid:
        return "cinematic-bridge"
    if "social" in tid or "card" in tid or "xiaohongshu" in tid or "twitter" in tid or "reddit" in tid:
        return "social-card"
    if "mobile" in tid or "device" in tid or "macos" in tid or "prototype" in tid:
        return "device-mockup"
    if "doc" in tid or "article" in tid or "blog" in tid or "magazine" in tid:
        return "editorial-doc"
    if "deck" in tid or cat == "deck":
        return "deck-frame"
    if "logo" in tid or "outro" in tid:
        return "outro"
    return "mixed-frame"


def review_use_for_template(template_id: str) -> str:
    tid = template_id.lower()
    if "glitch" in tid or "cursor" in tid or "hero" in tid:
        return "开头、章节强转场、金句爆点"
    if "chart" in tid or "data" in tid or "finance" in tid or "dashboard" in tid:
        return "真实数据、表格、KPI、市场证据"
    if "flow" in tid or "decision" in tid or "blueprint" in tid:
        return "逻辑链路、因果结构、操作步骤"
    if "alert" in tid or "teardown" in tid:
        return "风险提示、反方观点、冲突段落"
    if "doc" in tid or "article" in tid or "blog" in tid or "magazine" in tid:
        return "引用、文档证据、原文片段、长段解释"
    if "social" in tid or "card" in tid or "xiaohongshu" in tid:
        return "评论、观点卡、平台化摘要"
    if "logo" in tid or "outro" in tid:
        return "结尾、免责声明、CTA"
    return "补充视觉变化与节奏切换"


def asset_lookup(inventory: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(asset.get("id")): asset for asset in inventory.get("assets", []) if asset.get("id")}


def number_value(text: str, fallback: float) -> float:
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(text).replace(",", ""))
    if not match:
        return fallback
    value = float(match.group(0))
    if "-" in str(text):
        return -abs(value)
    return value


def metrics_from_table(table: list[list[str]], limit: int = 6) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    for idx, row in enumerate(table[1 : limit + 1], 1):
        if not row:
            continue
        display = ""
        for cell in row[1:]:
            if re.search(r"\d|%|万|亿|年|倍", str(cell)):
                display = str(cell)
                break
        if not display and len(row) > 1:
            display = str(row[1])
        metrics.append(
            {
                "label": str(row[0])[:14],
                "display": display[:22],
                "value": number_value(display, idx * 12.0),
            }
        )
    return metrics


def copy_image_assets(base_dir: Path, project_dir: Path, inventory: dict[str, Any]) -> dict[str, str]:
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


def scene_family(content_part: str, template_id: str) -> str:
    part = content_part or ""
    if part == "opening_hook":
        return "hook"
    if part == "chapter_divider":
        return "chapter"
    if part == "closing_outro":
        return "outro"
    if part in {"warning_or_risk"}:
        return "risk"
    if part in {"logic_chain", "overall_outline"}:
        return "logic"
    if "dashboard" in template_id:
        return "dashboard"
    if part in {"data_table", "financial_chart", "data_chart"}:
        return "data"
    if part == "pull_quote":
        return "quote"
    return "data"


def build_full_data(
    storyboard: dict[str, Any],
    inventory: dict[str, Any],
    copied_images: dict[str, str],
    *,
    audio_duration_sec: float | None,
    fps: int,
) -> dict[str, Any]:
    assets = asset_lookup(inventory)
    scenes: list[dict[str, Any]] = []
    for idx, scene in enumerate(storyboard.get("scenes", []), 0):
        refs = [ref for ref in scene.get("evidence_refs", []) if ref in assets]
        table_assets = [assets[ref] for ref in refs if assets[ref].get("type") == "table"]
        image_assets = [assets[ref] for ref in refs if assets[ref].get("type") == "image"]
        table = table_assets[0].get("rows") if table_assets else []
        template = FULL_TEMPLATE_SEQUENCE[idx % len(FULL_TEMPLATE_SEQUENCE)]
        voiceover = CHAT_STYLE_OVERRIDES[idx] if idx < len(CHAT_STYLE_OVERRIDES) else str(scene.get("voiceover_text") or "")
        duration = max(5.4, min(12.5, len(voiceover) / 5.6 + 1.0))
        image_ref = image_assets[0].get("id") if image_assets else ""
        scenes.append(
            {
                "id": scene.get("scene_id") or f"scene_{idx + 1:03d}",
                "index": idx + 1,
                "title": scene.get("title"),
                "subtitle": scene.get("core_meaning_lock"),
                "voiceover": voiceover,
                "contentPart": scene.get("content_part"),
                "template": template,
                "templateSource": "html-video" if template.startswith("frame-") or template == "vfx-text-cursor" else "html-everything",
                "visualFamily": scene_family(scene.get("content_part"), template),
                "evidenceRefs": refs,
                "metrics": metrics_from_table(table),
                "table": table[:6] if table else [],
                "image": {
                    "src": copied_images.get(str(image_ref), ""),
                    "alt": image_assets[0].get("alt") if image_assets else "",
                },
                "durationSec": round(duration, 3),
            }
        )
    if audio_duration_sec and audio_duration_sec > 10:
        total = sum(scene["durationSec"] for scene in scenes)
        scale = audio_duration_sec / total
        for scene in scenes:
            scene["durationSec"] = round(max(4.5, scene["durationSec"] * scale), 3)
    return {
        "schemaVersion": "dasheng.video.review.full31.v1",
        "createdAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "title": storyboard.get("title") or "地产周期论",
        "subtitle": "横版无头口播 · 31 分镜 · 模板轮换评审版",
        "fps": fps,
        "width": 1920,
        "height": 1080,
        "durationSec": round(sum(scene["durationSec"] for scene in scenes), 3),
        "scenes": scenes,
    }


def build_template_showcase_data(catalog: list[dict[str, Any]], *, fps: int) -> dict[str, Any]:
    by_id = {item["id"]: item for item in catalog}
    selected: list[dict[str, Any]] = []
    for tid in SHOWCASE_TEMPLATE_PRIORITY:
        matches = [item for item in catalog if item["id"] == tid]
        selected.extend(matches[:1])
    for item in catalog:
        if len(selected) >= 56:
            break
        if item["id"] not in {x["id"] for x in selected}:
            selected.append(item)
    slides = []
    for idx, item in enumerate(selected, 1):
        slides.append(
            {
                "index": idx,
                "id": item["id"],
                "name": item.get("zhName") or item.get("name") or item["id"],
                "description": item.get("description") or "",
                "source": item.get("source"),
                "category": item.get("category"),
                "visualFamily": item.get("visualFamily") or family_for_template(item["id"]),
                "reviewUse": item.get("reviewUse") or review_use_for_template(item["id"]),
                "durationSec": 3.8,
            }
        )
    return {
        "schemaVersion": "dasheng.video.review.templates.v1",
        "createdAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "title": "HTML Video × HTML Anything 模板视觉评审",
        "subtitle": f"展示 {len(slides)} 个代表模板；完整目录 {len(catalog)} 个",
        "fps": fps,
        "width": 1920,
        "height": 1080,
        "durationSec": round(sum(item["durationSec"] for item in slides), 3),
        "templates": slides,
    }


def build_voice_showcase_data(voice_results: list[dict[str, Any]], *, fps: int) -> dict[str, Any]:
    entries = []
    for idx, item in enumerate(voice_results, 1):
        if item.get("status") != "ok" or not item.get("file"):
            continue
        entries.append(
            {
                "index": idx,
                "id": item.get("id"),
                "name": item.get("name") or item.get("id"),
                "durationSec": round(float(item.get("duration") or 0), 3),
                "file": item.get("file"),
            }
        )
    return {
        "schemaVersion": "dasheng.video.review.voices.v1",
        "createdAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "title": "MiniMax 女声试听",
        "subtitle": f"{len(entries)} 个女声音色逐段切换",
        "fps": fps,
        "width": 1920,
        "height": 1080,
        "durationSec": round(sum(item["durationSec"] for item in entries), 3),
        "voices": entries,
    }


def build_bgm_showcase_data(bgm_results_path: Path, *, fps: int) -> dict[str, Any]:
    entries = []
    if bgm_results_path.exists():
        bgm_results = read_json(bgm_results_path)
        for idx, item in enumerate(bgm_results, 1):
            if item.get("status") != "ok" or not item.get("file"):
                continue
            entries.append(
                {
                    "index": idx,
                    "id": item.get("id"),
                    "name": bgm_name(str(item.get("id") or "")),
                    "durationSec": 24,
                    "sourceDurationSec": round(float(item.get("duration") or 0), 3),
                    "file": item.get("file"),
                    "use": bgm_use(str(item.get("id") or "")),
                }
            )
    return {
        "schemaVersion": "dasheng.video.review.bgm.v1",
        "createdAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "title": "MiniMax BGM 试听",
        "subtitle": f"{len(entries)} 个无歌词候选，每段 24 秒",
        "fps": fps,
        "width": 1920,
        "height": 1080,
        "durationSec": round(sum(item["durationSec"] for item in entries), 3),
        "tracks": entries,
    }


def bgm_name(track_id: str) -> str:
    names = {
        "bloomberg_dark_pulse": "彭博暗脉冲",
        "warm_investor_chat": "投资人聊天底",
        "cinematic_documentary_tension": "纪录片紧张垫",
        "light_tech_explainer": "轻科技解释",
        "chapter_riser_transition": "章节转场/数据揭示",
    }
    return names.get(track_id, track_id.replace("_", " "))


def bgm_use(track_id: str) -> str:
    uses = {
        "bloomberg_dark_pulse": "默认市场分析底乐，适合严肃金融判断。",
        "warm_investor_chat": "更接地气，适合投资人聊天式口播。",
        "cinematic_documentary_tension": "适合风险、冲突、政策压力段落。",
        "light_tech_explainer": "适合 AI、科技、方法论解释段落。",
        "chapter_riser_transition": "适合章节切换、数据揭示和短转场。",
    }
    return uses.get(track_id, "备用 BGM 候选。")


def build_package_json() -> str:
    return """{
  "name": "dasheng-video-review-suite",
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
import {BgmShowcase, FullDirectorVideo, TemplateShowcase, VoiceShowcase} from './Video';

const fullData = require('../data/full_video_data.json');
const templateData = require('../data/template_showcase_data.json');
const voiceData = require('../data/voice_showcase_data.json');
const bgmData = require('../data/bgm_showcase_data.json');

export const RemotionRoot = () => {
  return (
    <>
      <Composition
        id="FullDirectorVideo"
        component={FullDirectorVideo}
        durationInFrames={Math.ceil(fullData.durationSec * fullData.fps)}
        fps={fullData.fps}
        width={fullData.width}
        height={fullData.height}
        defaultProps={fullData}
      />
      <Composition
        id="TemplateShowcase"
        component={TemplateShowcase}
        durationInFrames={Math.ceil(templateData.durationSec * templateData.fps)}
        fps={templateData.fps}
        width={templateData.width}
        height={templateData.height}
        defaultProps={templateData}
      />
      <Composition
        id="VoiceShowcase"
        component={VoiceShowcase}
        durationInFrames={Math.ceil(voiceData.durationSec * voiceData.fps)}
        fps={voiceData.fps}
        width={voiceData.width}
        height={voiceData.height}
        defaultProps={voiceData}
      />
      <Composition
        id="BgmShowcase"
        component={BgmShowcase}
        durationInFrames={Math.ceil(bgmData.durationSec * bgmData.fps)}
        fps={bgmData.fps}
        width={bgmData.width}
        height={bgmData.height}
        defaultProps={bgmData}
      />
    </>
  );
};
"""


def build_render_cjs() -> str:
    return """const path = require('path');
const {bundle} = require('@remotion/bundler');
const {selectComposition, renderMedia, renderStill} = require('@remotion/renderer');

const root = __dirname;
const entryPoint = path.join(root, 'src', 'index.tsx');
const id = process.argv[2] || 'FullDirectorVideo';
const dataMap = {
  FullDirectorVideo: require(path.join(root, 'data', 'full_video_data.json')),
  TemplateShowcase: require(path.join(root, 'data', 'template_showcase_data.json')),
  VoiceShowcase: require(path.join(root, 'data', 'voice_showcase_data.json')),
  BgmShowcase: require(path.join(root, 'data', 'bgm_showcase_data.json')),
};
const outputMap = {
  FullDirectorVideo: 'full_31_silent.mp4',
  TemplateShowcase: 'template_showcase_silent.mp4',
  VoiceShowcase: 'voice_showcase_silent.mp4',
  BgmShowcase: 'bgm_showcase_silent.mp4',
};

(async () => {
  if (!dataMap[id]) {
    throw new Error(`Unknown composition: ${id}`);
  }
  const serveUrl = await bundle({entryPoint});
  const composition = await selectComposition({
    serveUrl,
    id,
    inputProps: dataMap[id],
  });
  const renderDir = path.join(root, 'render');
  const output = path.join(renderDir, outputMap[id]);
  const poster = path.join(renderDir, `${id}_poster.jpg`);
  await renderStill({
    serveUrl,
    composition,
    inputProps: dataMap[id],
    output: poster,
    frame: Math.min(90, composition.durationInFrames - 1),
    imageFormat: 'jpeg',
  });
  await renderMedia({
    serveUrl,
    composition,
    inputProps: dataMap[id],
    codec: 'h264',
    outputLocation: output,
    chromiumOptions: {disableWebSecurity: true},
  });
  console.log(JSON.stringify({status: 'ok', id, output, poster, durationInFrames: composition.durationInFrames, fps: composition.fps}, null, 2));
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
type Scene = {
  id: string;
  index: number;
  title: string;
  subtitle: string;
  voiceover: string;
  contentPart: string;
  template: string;
  templateSource: string;
  visualFamily: string;
  metrics: Metric[];
  table: string[][];
  image: {src: string; alt: string};
  durationSec: number;
};
type FullProps = {title: string; subtitle: string; scenes: Scene[]};
type TemplateItem = {index: number; id: string; name: string; description: string; source: string; category: string; visualFamily: string; reviewUse: string; durationSec: number};
type TemplateProps = {title: string; subtitle: string; templates: TemplateItem[]};
type VoiceItem = {index: number; id: string; name: string; durationSec: number};
type VoiceProps = {title: string; subtitle: string; voices: VoiceItem[]};
type BgmItem = {index: number; id: string; name: string; durationSec: number; sourceDurationSec: number; use: string};
type BgmProps = {title: string; subtitle: string; tracks: BgmItem[]};

const C = {
  bg: '#07111f',
  blue: '#12263d',
  blue2: '#1e3d5a',
  paper: '#f6efe3',
  gold: '#d7a84f',
  red: '#b54336',
  green: '#75d39c',
  cyan: '#4ec9e6',
  violet: '#8d75ff',
  muted: '#91a2b8',
  ink: '#101820',
};

const easeOut = Easing.bezier(0.16, 1, 0.3, 1);
const easeIn = Easing.bezier(0.55, 0, 1, 0.45);

const clamp = (value: number, input: [number, number], output: [number, number]) =>
  interpolate(value, input, output, {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: easeOut,
  });

const exitClamp = (value: number, input: [number, number], output: [number, number]) =>
  interpolate(value, input, output, {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: easeIn,
  });

export const FullDirectorVideo: React.FC<FullProps> = ({title, subtitle, scenes}) => {
  const {fps} = useVideoConfig();
  let cursor = 0;
  return (
    <AbsoluteFill style={baseStyle}>
      <Atmosphere />
      {scenes.map((scene) => {
        const duration = Math.round(scene.durationSec * fps);
        const from = cursor;
        cursor += duration;
        return (
          <Sequence key={scene.id} from={from} durationInFrames={duration} premountFor={fps}>
            <DirectorScene scene={scene} title={title} subtitle={subtitle} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

export const TemplateShowcase: React.FC<TemplateProps> = ({title, subtitle, templates}) => {
  const {fps} = useVideoConfig();
  let cursor = 0;
  return (
    <AbsoluteFill style={baseStyle}>
      <Atmosphere />
      {templates.map((item) => {
        const duration = Math.round(item.durationSec * fps);
        const from = cursor;
        cursor += duration;
        return (
          <Sequence key={`${item.source}-${item.id}-${item.index}`} from={from} durationInFrames={duration} premountFor={fps}>
            <TemplateCard item={item} title={title} subtitle={subtitle} total={templates.length} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

export const VoiceShowcase: React.FC<VoiceProps> = ({title, subtitle, voices}) => {
  const {fps} = useVideoConfig();
  let cursor = 0;
  return (
    <AbsoluteFill style={baseStyle}>
      <Atmosphere />
      {voices.map((voice) => {
        const duration = Math.round(voice.durationSec * fps);
        const from = cursor;
        cursor += duration;
        return (
          <Sequence key={voice.id} from={from} durationInFrames={duration} premountFor={fps}>
            <VoiceCard voice={voice} title={title} subtitle={subtitle} total={voices.length} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

export const BgmShowcase: React.FC<BgmProps> = ({title, subtitle, tracks}) => {
  const {fps} = useVideoConfig();
  let cursor = 0;
  return (
    <AbsoluteFill style={baseStyle}>
      <Atmosphere />
      {tracks.map((track) => {
        const duration = Math.round(track.durationSec * fps);
        const from = cursor;
        cursor += duration;
        return (
          <Sequence key={track.id} from={from} durationInFrames={duration} premountFor={fps}>
            <BgmCard track={track} title={title} subtitle={subtitle} total={tracks.length} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

const baseStyle: React.CSSProperties = {
  backgroundColor: C.bg,
  color: C.paper,
  fontFamily: '"PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif',
  overflow: 'hidden',
};

const Atmosphere: React.FC = () => {
  const frame = useCurrentFrame();
  const drift = Math.sin(frame / 80) * 30;
  return (
    <AbsoluteFill>
      <div style={{position: 'absolute', inset: 0, background: `radial-gradient(circle at ${24 + drift / 10}% 18%, rgba(215,168,79,.18), transparent 26%), radial-gradient(circle at 78% 68%, rgba(78,201,230,.12), transparent 28%), linear-gradient(135deg, #030814, #07111f 58%, #111827)`}} />
      <div style={{position: 'absolute', inset: 0, opacity: 0.11, backgroundImage: 'linear-gradient(rgba(255,255,255,.09) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.09) 1px, transparent 1px)', backgroundSize: '52px 52px', transform: `translate(${drift}px, 0)`}} />
      <div style={{position: 'absolute', inset: 0, background: 'linear-gradient(180deg, rgba(0,0,0,.04), rgba(0,0,0,.35))'}} />
    </AbsoluteFill>
  );
};

const DirectorScene: React.FC<{scene: Scene; title: string; subtitle: string}> = ({scene, title, subtitle}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const enter = clamp(frame, [0, fps * 0.65], [0, 1]);
  const exit = exitClamp(frame, [scene.durationSec * fps - fps * 0.6, scene.durationSec * fps], [0, 1]);
  return (
    <AbsoluteFill style={{padding: 58, opacity: enter * (1 - exit * 0.55), transform: `translateY(${(1 - enter) * 24 - exit * 20}px)`}}>
      <Chrome scene={scene} total={31} />
      {scene.visualFamily === 'hook' ? <Hook scene={scene} title={title} subtitle={subtitle} /> : null}
      {scene.visualFamily === 'chapter' ? <Chapter scene={scene} /> : null}
      {scene.visualFamily === 'risk' ? <RiskScene scene={scene} /> : null}
      {scene.visualFamily === 'logic' ? <LogicScene scene={scene} /> : null}
      {scene.visualFamily === 'quote' ? <QuoteScene scene={scene} /> : null}
      {scene.visualFamily === 'outro' ? <OutroScene scene={scene} /> : null}
      {['data', 'dashboard'].includes(scene.visualFamily) ? <DataScene scene={scene} /> : null}
      <Narration scene={scene} />
    </AbsoluteFill>
  );
};

const Chrome: React.FC<{scene: Scene; total: number}> = ({scene, total}) => {
  const frame = useCurrentFrame();
  const x = -((frame * 2) % 780);
  return (
    <>
      <div style={{position: 'absolute', top: 36, left: 58, right: 58, height: 1, background: 'linear-gradient(90deg, transparent, rgba(215,168,79,.82), transparent)'}} />
      <div style={{position: 'absolute', top: 48, left: 64, right: 64, display: 'flex', justifyContent: 'space-between', color: C.gold, fontFamily: 'Menlo, monospace', fontSize: 16, letterSpacing: '.13em'}}>
        <span>DASHENG DIRECTOR · NO-HUMAN · TEMPLATE REVIEW</span>
        <span>{String(scene.index).padStart(2, '0')} / {String(total).padStart(2, '0')} · {scene.template}</span>
      </div>
      <div style={{position: 'absolute', left: 0, right: 0, bottom: 0, height: 28, overflow: 'hidden', color: 'rgba(246,239,227,.28)', fontFamily: 'Menlo, monospace', fontSize: 14}}>
        <div style={{whiteSpace: 'nowrap', transform: `translateX(${x}px)`}}>
          REAL DATA · HOUSING CYCLE · WEALTH EFFECT · CREDIT · POLICY · CITY RENEWAL · REAL DATA · HOUSING CYCLE ·
        </div>
      </div>
    </>
  );
};

const Hook: React.FC<{scene: Scene; title: string; subtitle: string}> = ({scene, title, subtitle}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const titleP = clamp(frame, [0, fps * 0.85], [0, 1]);
  const numberP = clamp(frame, [fps * 1.1, fps * 3.2], [0, 1]);
  const flicker = Math.sin(frame * 0.7) > 0.84 ? 1 : 0;
  return (
    <>
      <div style={{position: 'absolute', left: 94, top: 172, width: 1040}}>
        <div style={{color: C.gold, fontSize: 24, letterSpacing: '.2em', marginBottom: 22}}>地产周期论 · 横版动态评审</div>
        <div style={{fontSize: 86, lineHeight: 1.02, fontWeight: 920, letterSpacing: '-.05em', opacity: titleP, transform: `translateX(${(1 - titleP) * -70}px)`}}>{title}</div>
        <div style={{fontSize: 31, color: C.muted, marginTop: 22, maxWidth: 860}}>{subtitle}</div>
        <div style={{fontSize: 42, lineHeight: 1.1, color: flicker ? C.cyan : C.paper, marginTop: 58, fontWeight: 850}}>{scene.title}</div>
      </div>
      <div style={{position: 'absolute', right: 110, top: 190, width: 520, height: 520, borderRadius: 36, background: 'rgba(18,38,61,.86)', border: '1px solid rgba(215,168,79,.35)', padding: 42, boxShadow: '0 28px 90px rgba(0,0,0,.35)'}}>
        <div style={{fontFamily: 'Menlo, monospace', color: C.gold, fontSize: 20}}>BEHAVIOR THRESHOLD</div>
        <div style={{fontSize: 144, fontWeight: 920, marginTop: 62, transform: `scale(${0.82 + numberP * 0.18})`}}>50%</div>
        <div style={{height: 14, borderRadius: 999, overflow: 'hidden', background: 'rgba(255,255,255,.12)', marginTop: 40}}>
          <div style={{height: '100%', width: `${numberP * 100}%`, background: `linear-gradient(90deg, ${C.red}, ${C.gold})`}} />
        </div>
        <div style={{fontSize: 26, color: C.muted, marginTop: 34}}>股市财富效应跨过阈值，楼市才有机会接力。</div>
      </div>
    </>
  );
};

const DataScene: React.FC<{scene: Scene}> = ({scene}) => {
  const metrics = scene.metrics.length ? scene.metrics : fallbackMetrics(scene);
  return (
    <>
      <SceneTitle scene={scene} label={scene.visualFamily === 'dashboard' ? 'LIVE DASHBOARD' : 'EVIDENCE'} />
      <BarChart metrics={metrics} />
      <LinePulse metrics={metrics} />
      <TableOrImage scene={scene} />
      {scene.visualFamily === 'dashboard' ? <DashboardOverlay metrics={metrics} /> : null}
    </>
  );
};

const SceneTitle: React.FC<{scene: Scene; label: string}> = ({scene, label}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = clamp(frame, [0, fps * 0.55], [0, 1]);
  return (
    <div style={{position: 'absolute', left: 88, top: 120, width: 760}}>
      <div style={{color: C.gold, fontFamily: 'Menlo, monospace', fontSize: 17, letterSpacing: '.16em'}}>{label} · {scene.template}</div>
      <div style={{fontSize: 54, fontWeight: 880, lineHeight: 1.08, marginTop: 16, opacity: p, transform: `translateY(${(1 - p) * 22}px)`}}>{scene.title}</div>
      <div style={{fontSize: 24, color: C.muted, lineHeight: 1.42, marginTop: 18, maxWidth: 690}}>{scene.subtitle}</div>
    </div>
  );
};

const BarChart: React.FC<{metrics: Metric[]}> = ({metrics}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const max = Math.max(...metrics.map((m) => Math.abs(m.value)), 1);
  return (
    <svg style={{position: 'absolute', left: 86, top: 366, width: 930, height: 435}} viewBox="0 0 930 435">
      {[0, 1, 2, 3].map((i) => <line key={i} x1={220 + i * 170} x2={220 + i * 170} y1={20} y2={380} stroke="rgba(246,239,227,.12)" />)}
      {metrics.slice(0, 5).map((m, i) => {
        const p = spring({frame: frame - 15 - i * 7, fps, config: {damping: 180, stiffness: 75}});
        const w = 80 + (Math.abs(m.value) / max) * 560 * p;
        const y = 42 + i * 72;
        const negative = m.value < 0 || String(m.display).includes('-');
        return (
          <g key={`${m.label}-${i}`}>
            <text x={0} y={y + 30} fill={C.paper} fontSize={23} fontFamily="Menlo, monospace">{m.label}</text>
            <rect x={220} y={y} width={w} height={38} rx={9} fill={negative ? C.red : i % 2 ? C.cyan : '#2f6f9f'} />
            <text x={238 + w} y={y + 29} fill={C.gold} fontSize={26} fontWeight={850}>{m.display}</text>
          </g>
        );
      })}
    </svg>
  );
};

const LinePulse: React.FC<{metrics: Metric[]}> = ({metrics}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = clamp(frame, [fps * 1.0, fps * 4.5], [0, 1]);
  const path = 'M 110 265 C 230 230 300 285 420 205 S 650 140 820 80';
  return (
    <svg style={{position: 'absolute', left: 960, top: 378, width: 820, height: 300}} viewBox="0 0 900 320">
      <rect x="0" y="0" width="900" height="320" rx="28" fill="rgba(18,38,61,.72)" stroke="rgba(215,168,79,.25)" />
      <text x="44" y="58" fill={C.gold} fontSize="20" fontFamily="Menlo, monospace">CYCLE SIGNAL</text>
      {[0, 1, 2, 3].map((i) => <line key={i} x1="50" x2="850" y1={100 + i * 45} y2={100 + i * 45} stroke="rgba(246,239,227,.10)" />)}
      <path d={path} fill="none" stroke="rgba(246,239,227,.16)" strokeWidth="7" strokeLinecap="round" />
      <path d={path} fill="none" stroke={C.gold} strokeWidth="7" strokeLinecap="round" strokeDasharray="1000" strokeDashoffset={(1 - p) * 1000} />
      <circle cx={110 + p * 710} cy={265 - p * 185 + Math.sin(frame / 10) * 12} r="12" fill={C.cyan} />
      <text x="44" y="285" fill={C.muted} fontSize="22">{metrics[0]?.label || '财富'} → {metrics[1]?.label || '信贷'} → {metrics[2]?.label || '楼市'}</text>
    </svg>
  );
};

const TableOrImage: React.FC<{scene: Scene}> = ({scene}) => {
  const frame = useCurrentFrame();
  const hasImage = scene.image?.src;
  if (hasImage && scene.index % 4 === 1) {
    const p = clamp(frame, [20, 65], [0, 1]);
    return (
      <div style={{position: 'absolute', right: 86, top: 148, width: 700, height: 430, borderRadius: 28, overflow: 'hidden', border: '1px solid rgba(215,168,79,.32)', background: '#0d1b2d', opacity: p, transform: `scale(${0.94 + p * 0.06})`}}>
        <Img src={staticFile(scene.image.src)} style={{width: '100%', height: '100%', objectFit: 'cover', opacity: 0.88}} />
        <div style={{position: 'absolute', left: 22, right: 22, bottom: 20, padding: '14px 18px', borderRadius: 16, background: 'rgba(7,17,31,.78)', color: C.paper, fontSize: 20}}>{scene.image.alt || '文章原图'}</div>
      </div>
    );
  }
  const rows = scene.table || [];
  if (!rows.length) return null;
  return (
    <div style={{position: 'absolute', right: 82, top: 138, width: 720, borderRadius: 24, overflow: 'hidden', border: '1px solid rgba(215,168,79,.28)', background: 'rgba(246,239,227,.96)', color: C.ink}}>
      {rows.slice(0, 5).map((row, r) => {
        const p = clamp(frame - r * 7, [18, 42], [0, 1]);
        return (
          <div key={r} style={{display: 'grid', gridTemplateColumns: `repeat(${Math.min(row.length, 4)}, 1fr)`, opacity: p, transform: `translateX(${(1 - p) * 30}px)`, background: r === 0 ? C.blue : r % 2 ? '#fffaf0' : '#ece5d5'}}>
            {row.slice(0, 4).map((cell, c) => (
              <div key={`${r}-${c}`} style={{padding: '15px 13px', fontSize: r === 0 ? 16 : 17, lineHeight: 1.24, color: r === 0 ? C.paper : C.ink, borderBottom: '1px solid rgba(16,24,32,.12)'}}>{cell}</div>
            ))}
          </div>
        );
      })}
    </div>
  );
};

const DashboardOverlay: React.FC<{metrics: Metric[]}> = ({metrics}) => {
  const frame = useCurrentFrame();
  return (
    <div style={{position: 'absolute', right: 100, bottom: 170, display: 'grid', gridTemplateColumns: 'repeat(3, 190px)', gap: 14}}>
      {metrics.slice(0, 3).map((m, i) => {
        const p = clamp(frame - 26 - i * 8, [0, 24], [0, 1]);
        return (
          <div key={m.label} style={{height: 112, borderRadius: 20, background: 'rgba(7,17,31,.72)', border: '1px solid rgba(78,201,230,.35)', padding: 18, opacity: p, transform: `translateY(${(1 - p) * 20}px)`}}>
            <div style={{fontSize: 17, color: C.muted}}>{m.label}</div>
            <div style={{fontSize: 32, color: i === 1 ? C.green : C.gold, fontWeight: 850, marginTop: 12}}>{m.display}</div>
          </div>
        );
      })}
    </div>
  );
};

const LogicScene: React.FC<{scene: Scene}> = ({scene}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = clamp(frame, [fps * 0.9, fps * 4.2], [0, 1]);
  const nodes = logicNodes(scene);
  return (
    <>
      <SceneTitle scene={scene} label="LOGIC MAP" />
      <svg style={{position: 'absolute', inset: 0}} viewBox="0 0 1920 1080">
        <path d="M340 585 C560 420 720 705 930 545 S1240 430 1540 620" fill="none" stroke="rgba(246,239,227,.14)" strokeWidth={10} strokeLinecap="round" />
        <path d="M340 585 C560 420 720 705 930 545 S1240 430 1540 620" fill="none" stroke={C.gold} strokeWidth={7} strokeLinecap="round" strokeDasharray="1350" strokeDashoffset={(1 - p) * 1350} />
      </svg>
      {nodes.map((node, i) => <LogicNode key={node} text={node} index={i} />)}
    </>
  );
};

const LogicNode: React.FC<{text: string; index: number}> = ({text, index}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const positions = [[250, 500], [640, 650], [1010, 455], [1390, 630], [1490, 400]];
  const [left, top] = positions[index] || [260 + index * 300, 550];
  const p = spring({frame: frame - fps * 0.55 - index * 10, fps, config: {damping: 170, stiffness: 86}});
  return (
    <div style={{position: 'absolute', left, top, width: 245, minHeight: 118, borderRadius: 24, padding: 22, background: index % 2 ? 'rgba(117,211,156,.94)' : 'rgba(215,168,79,.94)', color: C.ink, opacity: p, transform: `scale(${0.82 + p * 0.18})`, boxShadow: '0 20px 70px rgba(0,0,0,.32)'}}>
      <div style={{fontFamily: 'Menlo, monospace', fontSize: 16, opacity: 0.68}}>0{index + 1}</div>
      <div style={{fontSize: 28, lineHeight: 1.13, fontWeight: 850, marginTop: 9}}>{text}</div>
    </div>
  );
};

const RiskScene: React.FC<{scene: Scene}> = ({scene}) => {
  const items = riskItems(scene);
  return (
    <>
      <SceneTitle scene={scene} label="RISK CHECK" />
      <div style={{position: 'absolute', right: 110, top: 190, width: 700}}>
        {items.map((item, i) => <RiskItem key={item} item={item} index={i} />)}
      </div>
    </>
  );
};

const RiskItem: React.FC<{item: string; index: number}> = ({item, index}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = spring({frame: frame - fps * 0.5 - index * 11, fps, config: {damping: 180, stiffness: 82}});
  return (
    <div style={{height: 92, marginBottom: 18, borderRadius: 22, background: index % 2 ? 'rgba(181,67,54,.92)' : 'rgba(18,38,61,.92)', border: '1px solid rgba(215,168,79,.26)', padding: '21px 28px', display: 'flex', alignItems: 'center', gap: 20, opacity: p, transform: `translateX(${(1 - p) * 80}px)`}}>
      <div style={{width: 42, height: 42, borderRadius: 999, background: C.gold, color: C.ink, display: 'grid', placeItems: 'center', fontWeight: 900}}>!</div>
      <div style={{fontSize: 29, fontWeight: 820}}>{item}</div>
    </div>
  );
};

const Chapter: React.FC<{scene: Scene}> = ({scene}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = clamp(frame, [0, fps * 1.2], [0, 1]);
  return (
    <>
      <div style={{position: 'absolute', left: 100, top: 230, width: 1180}}>
        <div style={{fontFamily: 'Menlo, monospace', color: C.gold, fontSize: 22, letterSpacing: '.2em'}}>CHAPTER RESET</div>
        <div style={{fontSize: 86, fontWeight: 920, marginTop: 28, lineHeight: 1.02, transform: `translateX(${(1 - p) * -70}px)`, opacity: p}}>{scene.title}</div>
        <div style={{fontSize: 34, color: C.muted, marginTop: 24, maxWidth: 950}}>{scene.voiceover}</div>
      </div>
      <div style={{position: 'absolute', right: 140, top: 180, width: 340, height: 700, borderRadius: 999, background: `linear-gradient(180deg, rgba(215,168,79,${0.18 + p * 0.25}), rgba(78,201,230,.06))`, transform: `rotate(${10 - p * 20}deg) scale(${0.9 + p * 0.1})`, filter: 'blur(1px)'}} />
    </>
  );
};

const QuoteScene: React.FC<{scene: Scene}> = ({scene}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = spring({frame: frame - 12, fps, config: {damping: 150, stiffness: 72}});
  return (
    <>
      <div style={{position: 'absolute', left: 160, top: 160, right: 160, bottom: 210, borderRadius: 38, background: 'rgba(246,239,227,.96)', color: C.ink, padding: 70, transform: `scale(${0.9 + p * 0.1})`, opacity: p, boxShadow: '0 30px 100px rgba(0,0,0,.34)'}}>
        <div style={{fontFamily: 'Georgia, serif', fontSize: 160, color: C.gold, lineHeight: 0.7}}>“</div>
        <div style={{fontSize: 70, lineHeight: 1.13, fontWeight: 880, letterSpacing: '-.03em'}}>{scene.title}</div>
        <div style={{fontSize: 34, lineHeight: 1.45, color: '#314156', marginTop: 34}}>{scene.voiceover}</div>
        <div style={{position: 'absolute', right: 70, bottom: 48, fontFamily: 'Menlo, monospace', fontSize: 18, color: C.red}}>CONFIRMATION SIGNAL</div>
      </div>
    </>
  );
};

const OutroScene: React.FC<{scene: Scene}> = ({scene}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = clamp(frame, [0, fps * 1.0], [0, 1]);
  const glow = 0.45 + Math.sin(frame / 12) * 0.12;
  return (
    <>
      <div style={{position: 'absolute', inset: 0, background: `radial-gradient(circle at 50% 42%, rgba(215,168,79,${glow}), transparent 28%)`}} />
      <div style={{position: 'absolute', left: 230, right: 230, top: 245, textAlign: 'center'}}>
        <div style={{fontSize: 88, fontWeight: 920, lineHeight: 1.05, opacity: p}}>等三因素重新共振</div>
        <div style={{fontSize: 34, color: C.muted, lineHeight: 1.45, marginTop: 34}}>{scene.voiceover}</div>
        <div style={{display: 'flex', justifyContent: 'center', gap: 18, marginTop: 54}}>
          {['成交', '价格', '贷款', '收入'].map((x, i) => <div key={x} style={{padding: '18px 26px', borderRadius: 999, background: i % 2 ? C.blue2 : C.gold, color: i % 2 ? C.paper : C.ink, fontSize: 30, fontWeight: 850}}>{x}</div>)}
        </div>
      </div>
    </>
  );
};

const Narration: React.FC<{scene: Scene}> = ({scene}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = clamp(frame, [fps * 0.3, fps * 1.0], [0, 1]);
  return (
    <div style={{position: 'absolute', left: 88, right: 88, bottom: 54, minHeight: 98, borderRadius: 24, background: 'rgba(4,10,18,.74)', border: '1px solid rgba(215,168,79,.28)', padding: '19px 28px', opacity: p, transform: `translateY(${(1 - p) * 18}px)`, backdropFilter: 'blur(18px)'}}>
      <div style={{fontFamily: 'Menlo, monospace', color: C.gold, fontSize: 14, letterSpacing: '.14em', marginBottom: 8}}>VOICEOVER · 投资人聊天口吻</div>
      <div style={{fontSize: 28, lineHeight: 1.34}}>{trimText(scene.voiceover, 70)}</div>
    </div>
  );
};

const TemplateCard: React.FC<{item: TemplateItem; title: string; subtitle: string; total: number}> = ({item, title, subtitle, total}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = clamp(frame, [0, fps * 0.55], [0, 1]);
  const accent = accentForFamily(item.visualFamily);
  return (
    <AbsoluteFill style={{padding: 70, opacity: p, transform: `translateY(${(1 - p) * 24}px)`}}>
      <div style={{position: 'absolute', top: 48, left: 70, right: 70, display: 'flex', justifyContent: 'space-between', color: C.gold, fontFamily: 'Menlo, monospace', fontSize: 17, letterSpacing: '.12em'}}>
        <span>{title}</span>
        <span>{String(item.index).padStart(2, '0')} / {String(total).padStart(2, '0')} · {item.source}</span>
      </div>
      <div style={{position: 'absolute', left: 90, top: 150, width: 730}}>
        <div style={{fontFamily: 'Menlo, monospace', color: accent, fontSize: 22, letterSpacing: '.16em'}}>{item.visualFamily.toUpperCase()}</div>
        <div style={{fontSize: 68, lineHeight: 1.02, fontWeight: 920, letterSpacing: '-.04em', marginTop: 22}}>{item.name}</div>
        <div style={{fontSize: 26, color: C.muted, lineHeight: 1.38, marginTop: 24}}>{trimText(item.description, 88)}</div>
        <div style={{fontSize: 24, color: C.paper, lineHeight: 1.38, marginTop: 40, padding: '22px 26px', borderRadius: 22, background: 'rgba(18,38,61,.82)', border: '1px solid rgba(215,168,79,.25)'}}>适合：{item.reviewUse}</div>
      </div>
      <div style={{position: 'absolute', right: 100, top: 150, width: 720, height: 720, borderRadius: 34, background: 'rgba(18,38,61,.72)', border: `1px solid ${accent}66`, overflow: 'hidden'}}>
        <TemplateVisual family={item.visualFamily} accent={accent} />
      </div>
      <div style={{position: 'absolute', left: 90, bottom: 74, fontFamily: 'Menlo, monospace', color: 'rgba(246,239,227,.54)', fontSize: 17}}>{subtitle} · template-id: {item.id} · category: {item.category}</div>
    </AbsoluteFill>
  );
};

const TemplateVisual: React.FC<{family: string; accent: string}> = ({family, accent}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = clamp(frame, [10, fps * 2.6], [0, 1]);
  if (family === 'data-viz') {
    return <BarChart metrics={[{label: '成交', display: '+18%', value: 18}, {label: '信贷', display: '-7%', value: -7}, {label: '价格', display: '+4%', value: 4}, {label: '库存', display: '12月', value: 12}]} />;
  }
  if (family === 'logic-map') {
    return <div style={{position: 'absolute', inset: 0, transform: 'scale(.76) translate(-270px, -210px)'}}><LogicScene scene={mockScene('信贷 · 财富 · 政策', '三因素共振才是反转条件')} /></div>;
  }
  if (family === 'risk-alert') {
    return <div style={{position: 'absolute', inset: 0, transform: 'scale(.72) translate(-340px, -180px)'}}><RiskScene scene={mockScene('风险不是没了', '收入、杠杆、预期仍在约束')} /></div>;
  }
  if (family === 'social-card' || family === 'device-mockup') {
    return (
      <div style={{position: 'absolute', left: 170, top: 70, width: 370, height: 590, borderRadius: 44, background: '#f7f0e5', color: C.ink, padding: 32, transform: `rotate(${-5 + p * 5}deg) scale(${0.9 + p * 0.1})`, boxShadow: '0 28px 80px rgba(0,0,0,.35)'}}>
        <div style={{fontSize: 20, color: C.red, fontWeight: 850}}>小红书/手机框</div>
        <div style={{fontSize: 42, lineHeight: 1.1, fontWeight: 920, marginTop: 40}}>一句话观点卡</div>
        <div style={{fontSize: 24, lineHeight: 1.35, marginTop: 34}}>适合评论、截图、社媒二创和章节总结。</div>
        <div style={{position: 'absolute', left: 32, right: 32, bottom: 32, height: 70, borderRadius: 22, background: accent}} />
      </div>
    );
  }
  if (family === 'editorial-doc' || family === 'deck-frame') {
    return (
      <div style={{position: 'absolute', left: 70, top: 64, right: 70, bottom: 64, borderRadius: 8, background: '#f5f1e7', color: C.ink, padding: 48, transform: `translateY(${(1 - p) * 20}px)`}}>
        <div style={{fontFamily: 'Georgia, serif', fontSize: 58, lineHeight: 1.02}}>Editorial Evidence</div>
        <div style={{height: 2, background: accent, margin: '30px 0'}} />
        {[0, 1, 2, 3, 4].map((i) => <div key={i} style={{height: 24, width: `${82 - i * 9}%`, background: i === 0 ? accent : '#c7c0b2', marginBottom: 22, opacity: p}} />)}
      </div>
    );
  }
  if (family === 'outro') {
    return <OutroScene scene={mockScene('关注四个确认信号', '成交、价格、贷款、收入')} />;
  }
  return (
    <>
      <div style={{position: 'absolute', inset: 0, background: `radial-gradient(circle at ${35 + p * 35}% ${35 + Math.sin(frame / 8) * 12}%, ${accent}88, transparent 34%)`}} />
      <div style={{position: 'absolute', left: 80, top: 120, fontSize: 86, fontWeight: 920, lineHeight: 1.0, color: C.paper, transform: `translateX(${(1 - p) * -50}px)`}}>Kinetic<br />Frame</div>
      <div style={{position: 'absolute', left: 84, top: 365, width: 410, height: 14, background: 'rgba(255,255,255,.18)', borderRadius: 999, overflow: 'hidden'}}>
        <div style={{width: `${p * 100}%`, height: '100%', background: accent}} />
      </div>
      <div style={{position: 'absolute', right: 86, bottom: 82, width: 180, height: 180, borderRadius: 999, border: `10px solid ${accent}`, transform: `scale(${0.7 + p * 0.3}) rotate(${frame * 2}deg)`}} />
    </>
  );
};

const VoiceCard: React.FC<{voice: VoiceItem; title: string; subtitle: string; total: number}> = ({voice, title, subtitle, total}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = clamp(frame, [0, fps * 0.7], [0, 1]);
  return (
    <AbsoluteFill style={{padding: 86, opacity: p}}>
      <div style={{position: 'absolute', top: 52, left: 86, right: 86, display: 'flex', justifyContent: 'space-between', color: C.gold, fontFamily: 'Menlo, monospace', fontSize: 18, letterSpacing: '.13em'}}>
        <span>{title}</span>
        <span>{String(voice.index).padStart(2, '0')} / {String(total).padStart(2, '0')}</span>
      </div>
      <div style={{position: 'absolute', left: 120, top: 210, right: 120}}>
        <div style={{fontSize: 34, color: C.muted}}>当前试听声音</div>
        <div style={{fontSize: 92, lineHeight: 1.03, fontWeight: 920, letterSpacing: '-.05em', marginTop: 20}}>{voice.name}</div>
        <div style={{fontFamily: 'Menlo, monospace', color: C.gold, fontSize: 28, marginTop: 24}}>{voice.id} · {voice.durationSec.toFixed(1)}s</div>
      </div>
      <Equalizer />
      <div style={{position: 'absolute', left: 120, right: 120, bottom: 108, padding: '28px 34px', borderRadius: 28, background: 'rgba(18,38,61,.82)', border: '1px solid rgba(215,168,79,.28)'}}>
        <div style={{fontSize: 31, lineHeight: 1.42}}>试听标准：投资人聊天口吻，不要太播音腔；适合长期固定为无头口播默认女声。</div>
        <div style={{fontSize: 20, color: C.muted, marginTop: 14}}>{subtitle}</div>
      </div>
    </AbsoluteFill>
  );
};

const Equalizer: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <div style={{position: 'absolute', left: 120, right: 120, top: 520, height: 180, display: 'flex', alignItems: 'center', gap: 10}}>
      {Array.from({length: 58}).map((_, i) => {
        const h = 28 + Math.abs(Math.sin(frame / 8 + i * 0.55)) * 130;
        return <div key={i} style={{width: 18, height: h, borderRadius: 999, background: i % 3 === 0 ? C.gold : i % 3 === 1 ? C.cyan : C.green, opacity: 0.72}} />;
      })}
    </div>
  );
};

const BgmCard: React.FC<{track: BgmItem; title: string; subtitle: string; total: number}> = ({track, title, subtitle, total}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = clamp(frame, [0, fps * 0.7], [0, 1]);
  const color = [C.gold, C.cyan, C.red, C.green, C.violet][(track.index - 1) % 5];
  return (
    <AbsoluteFill style={{padding: 86, opacity: p}}>
      <div style={{position: 'absolute', top: 52, left: 86, right: 86, display: 'flex', justifyContent: 'space-between', color: C.gold, fontFamily: 'Menlo, monospace', fontSize: 18, letterSpacing: '.13em'}}>
        <span>{title}</span>
        <span>{String(track.index).padStart(2, '0')} / {String(total).padStart(2, '0')}</span>
      </div>
      <div style={{position: 'absolute', left: 120, top: 190, right: 120}}>
        <div style={{fontSize: 34, color: C.muted}}>当前试听 BGM</div>
        <div style={{fontSize: 88, lineHeight: 1.04, fontWeight: 920, letterSpacing: '-.05em', marginTop: 20}}>{track.name}</div>
        <div style={{fontFamily: 'Menlo, monospace', color, fontSize: 27, marginTop: 24}}>{track.id} · excerpt 24s · source {track.sourceDurationSec.toFixed(0)}s</div>
      </div>
      <MusicBars color={color} />
      <div style={{position: 'absolute', left: 120, right: 120, bottom: 112, padding: '30px 36px', borderRadius: 30, background: 'rgba(18,38,61,.82)', border: `1px solid ${color}66`}}>
        <div style={{fontSize: 34, lineHeight: 1.36}}>{track.use}</div>
        <div style={{fontSize: 20, color: C.muted, marginTop: 14}}>{subtitle}</div>
      </div>
    </AbsoluteFill>
  );
};

const MusicBars: React.FC<{color: string}> = ({color}) => {
  const frame = useCurrentFrame();
  return (
    <div style={{position: 'absolute', left: 120, right: 120, top: 515, height: 190, display: 'flex', alignItems: 'end', gap: 8}}>
      {Array.from({length: 72}).map((_, i) => {
        const h = 24 + Math.abs(Math.sin(frame / 7 + i * 0.38) + Math.sin(frame / 19 + i * 0.7)) * 62;
        return <div key={i} style={{width: 15, height: h, borderRadius: 999, background: i % 4 === 0 ? C.gold : color, opacity: 0.55 + (i % 5) * 0.07}} />;
      })}
    </div>
  );
};

const trimText = (text: string, max: number) => {
  if (!text) return '';
  return text.length > max ? `${text.slice(0, max)}…` : text;
};

const fallbackMetrics = (scene: Scene): Metric[] => {
  if (scene.title.includes('50')) return [{label: '跌30%', display: '70', value: 70}, {label: '涨50%', display: '105', value: 105}, {label: '阈值', display: '50%', value: 50}];
  if (scene.title.includes('三个月')) return [{label: '贷款', display: '3个月', value: 3}, {label: '成交', display: '确认', value: 18}, {label: '收入', display: '观察', value: 12}];
  return [{label: '财富', display: '修复中', value: 34}, {label: '信贷', display: '偏弱', value: -12}, {label: '政策', display: '托底', value: 25}, {label: '成交', display: '分化', value: 18}];
};

const logicNodes = (scene: Scene) => {
  if (scene.title.includes('三因素')) return ['信贷', '财富', '政策', '楼市'];
  if (scene.title.includes('种子')) return ['财富是种子', '信贷放大', '政策开闸', '成交释放'];
  if (scene.title.includes('城市更新')) return ['存量供给', '以旧换新', '好房子', '缩量提质'];
  if (scene.title.includes('国债')) return ['收储价格', '租赁需求', '保障需求', '真实成交'];
  if (scene.title.includes('结构性')) return ['核心城市', '强二线', '弱二线', '三四线'];
  if (scene.title.includes('最终')) return ['财富修复', '信贷转正', '政策释放', '三因素共振'];
  return ['判断', '证据', '传导', '结论'];
};

const riskItems = (scene: Scene) => {
  if (scene.title.includes('政策失灵')) return ['居民还贷', '降杠杆', '预期没翻', '资产表收缩'];
  if (scene.title.includes('四个原因')) return ['收入预期弱', '财富坑未填', '房价预期弱', '杠杆接近饱和'];
  return ['确认不足', '区域分化', '债务风险', '流动性压力'];
};

const mockScene = (title: string, subtitle: string): Scene => ({
  id: 'mock',
  index: 0,
  title,
  subtitle,
  voiceover: subtitle,
  contentPart: '',
  template: '',
  templateSource: '',
  visualFamily: 'logic',
  metrics: [],
  table: [],
  image: {src: '', alt: ''},
  durationSec: 4,
});

const accentForFamily = (family: string) => {
  if (family === 'data-viz') return C.cyan;
  if (family === 'logic-map') return C.green;
  if (family === 'risk-alert') return C.red;
  if (family === 'cinematic-bridge') return C.gold;
  if (family === 'social-card') return '#ff6f91';
  if (family === 'device-mockup') return '#67e8f9';
  if (family === 'editorial-doc') return '#f5d38a';
  if (family === 'deck-frame') return '#86a7ff';
  if (family === 'outro') return C.gold;
  return C.violet;
};
"""


def build_review_html(output: Path, catalog: list[dict[str, Any]], full_data: dict[str, Any]) -> None:
    rows = "\n".join(
        f"<tr><td>{i + 1}</td><td><code>{item['id']}</code></td><td>{item.get('zhName') or item.get('name')}</td><td>{item.get('source')}</td><td>{item.get('visualFamily')}</td><td>{item.get('reviewUse')}</td></tr>"
        for i, item in enumerate(catalog)
    )
    scene_rows = "\n".join(
        f"<tr><td>{scene['index']}</td><td>{scene['title']}</td><td><code>{scene['template']}</code></td><td>{scene['visualFamily']}</td><td>{', '.join(scene.get('evidenceRefs') or [])}</td></tr>"
        for scene in full_data["scenes"]
    )
    html = f"""<!doctype html>
<meta charset="utf-8">
<title>Newma Video Review Suite</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;background:#f4efe4;color:#101820;margin:0;padding:32px;}}
h1{{font-size:34px;margin:0 0 8px;}}
h2{{margin-top:36px;}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:14px;overflow:hidden;box-shadow:0 10px 30px rgba(0,0,0,.06);}}
th,td{{font-size:13px;text-align:left;padding:10px 12px;border-bottom:1px solid #e7dfd1;vertical-align:top;}}
th{{background:#10243a;color:#f6efe3;position:sticky;top:0;}}
code{{font-family:Menlo,monospace;color:#9f3129;}}
.note{{color:#566579;line-height:1.6;max-width:980px;}}
</style>
<h1>Newma Video Review Suite</h1>
<p class="note">生成时间：{datetime.now().astimezone().isoformat(timespec='seconds')}。完整模板目录 {len(catalog)} 个；31 分镜完整版已为每个分镜分配不同视觉角色和模板。</p>
<h2>31 分镜模板分配</h2>
<table><thead><tr><th>#</th><th>分镜</th><th>模板</th><th>视觉角色</th><th>证据资产</th></tr></thead><tbody>{scene_rows}</tbody></table>
<h2>完整模板目录</h2>
<table><thead><tr><th>#</th><th>ID</th><th>名称</th><th>来源</th><th>视觉角色</th><th>建议场景</th></tr></thead><tbody>{rows}</tbody></table>
"""
    write_text(output, html)


def build_remotion_project(
    project_dir: Path,
    html_video_root: Path,
    full_data: dict[str, Any],
    template_data: dict[str, Any],
    voice_data: dict[str, Any],
    bgm_data: dict[str, Any],
) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    write_text(project_dir / "package.json", build_package_json())
    write_text(project_dir / "render.cjs", build_render_cjs())
    write_text(project_dir / "src" / "index.tsx", build_index_tsx())
    write_text(project_dir / "src" / "Root.tsx", build_root_tsx())
    write_text(project_dir / "src" / "Video.tsx", build_video_tsx())
    write_json(project_dir / "data" / "full_video_data.json", full_data)
    write_json(project_dir / "data" / "template_showcase_data.json", template_data)
    write_json(project_dir / "data" / "voice_showcase_data.json", voice_data)
    write_json(project_dir / "data" / "bgm_showcase_data.json", bgm_data)
    write_text(project_dir / "full_voiceover_chat_script.txt", "\n".join(scene["voiceover"] for scene in full_data["scenes"]) + "\n")
    node_modules = project_dir / "node_modules"
    target = html_video_root / "node_modules"
    if node_modules.exists() or node_modules.is_symlink():
        if node_modules.is_symlink() and node_modules.resolve() == target.resolve():
            return
        raise RuntimeError(f"Refusing to overwrite existing node_modules: {node_modules}")
    os.symlink(target, node_modules)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Newma video template / voice / full-scene review suite.")
    parser.add_argument("--base-dir", default=str(DEFAULT_BASE_DIR))
    parser.add_argument("--output-dir", default="")
    parser.add_argument("--html-video-root", default=str(DEFAULT_HTML_VIDEO_ROOT))
    parser.add_argument("--html-everything-root", default=str(DEFAULT_HTML_EVERYTHING_ROOT))
    parser.add_argument("--audio-duration-sec", type=float, default=0)
    parser.add_argument("--fps", type=int, default=30)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    base_dir = Path(args.base_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else base_dir / "review_suite"
    project_dir = output_dir / "remotion_review_suite"
    html_video_root = Path(args.html_video_root).expanduser().resolve()
    html_everything_root = Path(args.html_everything_root).expanduser().resolve()

    storyboard = read_json(base_dir / "director_storyboard.nohuman.json")
    inventory = read_json(base_dir / "article_asset_inventory.json")
    voice_results = read_json(output_dir / "voice_showcase" / "voice_results.json")
    catalog = template_catalog(html_video_root, html_everything_root)
    copied_images = copy_image_assets(base_dir, project_dir, inventory)
    full_data = build_full_data(
        storyboard,
        inventory,
        copied_images,
        audio_duration_sec=args.audio_duration_sec or None,
        fps=args.fps,
    )
    template_data = build_template_showcase_data(catalog, fps=args.fps)
    voice_data = build_voice_showcase_data(voice_results, fps=args.fps)
    bgm_data = build_bgm_showcase_data(output_dir / "bgm_showcase" / "bgm_results.json", fps=args.fps)

    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "template_catalog.json", catalog)
    build_remotion_project(project_dir, html_video_root, full_data, template_data, voice_data, bgm_data)
    build_review_html(output_dir / "video_review_index.html", catalog, full_data)
    write_json(
        output_dir / "review_suite_manifest.json",
        {
            "schemaVersion": "dasheng.video.review_suite_manifest.v1",
            "createdAt": datetime.now().astimezone().isoformat(timespec="seconds"),
            "baseDir": str(base_dir),
            "projectDir": str(project_dir),
            "templateCatalog": str((output_dir / "template_catalog.json").resolve()),
            "reviewIndex": str((output_dir / "video_review_index.html").resolve()),
            "counts": {
                "catalogTemplates": len(catalog),
                "templateShowcaseSlides": len(template_data["templates"]),
                "voices": len(voice_data["voices"]),
                "bgmTracks": len(bgm_data["tracks"]),
                "fullScenes": len(full_data["scenes"]),
            },
            "renderCommands": [
                "node render.cjs VoiceShowcase",
                "node render.cjs BgmShowcase",
                "node render.cjs TemplateShowcase",
                "node render.cjs FullDirectorVideo",
            ],
        },
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "project_dir": str(project_dir),
                "templates": len(catalog),
                "template_showcase_slides": len(template_data["templates"]),
                "voices": len(voice_data["voices"]),
                "bgm_tracks": len(bgm_data["tracks"]),
                "full_scenes": len(full_data["scenes"]),
                "full_duration_sec": full_data["durationSec"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
