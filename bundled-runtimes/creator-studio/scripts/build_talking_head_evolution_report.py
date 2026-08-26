#!/usr/bin/env python3
"""Build a discussion report for evolving talking-head edit quality."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


RUN_DIR = Path(os.environ.get("DASHENG_TALKING_HEAD_RUN_DIR", str(Path.home() / "Desktop/自媒体创作/talking-head-run"))).expanduser()
OUT_DIR = RUN_DIR / "evolution"
V4_VIDEO = RUN_DIR / "render/final_hk_tech_talking_head_refined_v4_noscan_1200.mp4"
V4_CONTACT = RUN_DIR / "qc/final_v4_contact_sheet.jpg"
CRV_DIR = RUN_DIR / "evolution/crv_v4_baseline"
XIAOLIN_PROFILE = Path(os.environ.get("DASHENG_REFERENCE_STYLE_PROFILE", str(Path.home() / "Desktop/自媒体创作/00_范式学习/视频训练/reference/style_profile.json"))).expanduser()
XIAOLIN_ANALYSIS = Path(os.environ.get("DASHENG_REFERENCE_STYLE_ANALYSIS", str(Path.home() / "Desktop/自媒体创作/00_范式学习/视频训练/reference/style_analysis.md"))).expanduser()
OLD_GATE = RUN_DIR / "qc/director_quality_gate_v4_reaudit.json"
NEW_GATE = RUN_DIR / "director_quality_gate_smoke_v3/scene_plan_quality_gate.json"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def img(path: Path, alt: str) -> str:
    return f'<figure><img src="{path.resolve().as_uri()}" alt="{alt}"><figcaption>{alt}</figcaption></figure>'


def metric_row(name: str, current: Any, target: Any, status: str) -> str:
    return f"<tr><td>{name}</td><td>{current}</td><td>{target}</td><td><b>{status}</b></td></tr>"


def build_report() -> tuple[Path, Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    old_gate = load_json(OLD_GATE)
    new_gate = load_json(NEW_GATE)
    crv = load_json(CRV_DIR / "dasheng_video_reading_manifest.json")
    xiaolin = load_json(XIAOLIN_PROFILE)
    old_m = old_gate["metrics"]
    new_m = new_gate["metrics"]
    crv_out = crv["outputs"]
    x_metrics = xiaolin.get("quantitative_metrics") or []
    x_cuts = [item.get("cuts_per_min_est") for item in x_metrics if item.get("cuts_per_min_est")]
    x_median = [item.get("median_interval_sec_est") for item in x_metrics if item.get("median_interval_sec_est")]
    benchmark = {
        "cuts_per_min_range": f"{min(x_cuts):.2f}-{max(x_cuts):.2f}" if x_cuts else "17-25",
        "median_interval_range": f"{min(x_median):.2f}-{max(x_median):.2f}s" if x_median else "1.4-2.7s",
    }
    evolution = {
        "schema_version": "dasheng.talking_head_evolution_review.v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "baseline_video": str(V4_VIDEO),
        "baseline_crv_manifest": str(CRV_DIR / "dasheng_video_reading_manifest.json"),
        "current_v4": old_gate,
        "candidate_next_plan_gate": new_gate,
        "crv_metrics": {
            "frames_kept": crv_out.get("frame_count"),
            "frames_extracted": 139,
            "dedup_keep_ratio": round((crv_out.get("frame_count") or 0) / 139, 3),
            "grid_count": crv_out.get("grid_count"),
            "report_html": crv_out.get("report_html"),
        },
        "benchmark": benchmark,
        "diagnosis": [
            "当前 v4 最大问题不是技术错误，而是视觉语言重复：CRV 从 139 个候选画面只保留 24 个关键帧。",
            "分镜计划只有 16 个大段，中位镜头 17 秒，导致 PPT 感和停滞感。",
            "证据多数是内部深色卡片，不像真实网页、行情图、公告、产品 UI 或资料画面。",
            "人物长期侧脸同角度，缺少正脸信任锚、表情节奏、手势强调和回真人的镜头目的。",
            "尾段没有记忆点闭环，结论画面仍是同一套卡片/人物角度。",
        ],
        "next_iteration_strategy": [
            "先用 89 个微镜头计划替代 16 个大段计划，目标 17-25 次/分钟视觉变化。",
            "把证据分成 real_data、source_screenshot、user_claim_card、schematic 四级，优先补真实行情/网页/产品 UI。",
            "人物构图改为 speaker_full、speaker_punch、circle_pip、hidden、speaker_return 轮换，不固定右下角。",
            "每 20-30 秒设置一个真实证据峰值，每 45-70 秒做一次结构回收。",
            "终段必须做观点落地视觉闭环：一句话 thesis、三点风险收益、最后回真人。",
        ],
    }
    json_path = OUT_DIR / "talking_head_evolution_review_v0.json"
    json_path.write_text(json.dumps(evolution, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    grid_imgs = "".join(img(path, path.name) for path in sorted((CRV_DIR / "grids").glob("*.jpg")))
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>真人口播剪辑进化复盘 V0</title>
<style>
:root {{
  --bg: #f5f1e8;
  --ink: #171717;
  --muted: #6f675c;
  --line: #d7cdbd;
  --card: #fffaf0;
  --red: #a9382d;
  --green: #246b4f;
  --blue: #234b70;
}}
body {{
  margin: 0;
  background: radial-gradient(circle at 15% 0%, #fff6d7 0, transparent 34%), var(--bg);
  color: var(--ink);
  font-family: "Songti SC", "Noto Serif CJK SC", serif;
  line-height: 1.72;
}}
main {{ max-width: 1180px; margin: 0 auto; padding: 42px 26px 80px; }}
h1 {{ font-size: 42px; line-height: 1.12; margin: 0 0 12px; letter-spacing: -1px; }}
h2 {{ margin-top: 48px; font-size: 28px; border-left: 8px solid var(--red); padding-left: 14px; }}
h3 {{ margin-top: 28px; font-size: 20px; }}
.lead {{ font-size: 18px; color: var(--muted); max-width: 820px; }}
.grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }}
.grid.three {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
figure {{ margin: 0; background: var(--card); border: 1px solid var(--line); padding: 10px; box-shadow: 0 16px 50px rgba(73, 50, 24, .08); }}
img {{ width: 100%; display: block; border-radius: 6px; }}
figcaption {{ color: var(--muted); font-size: 13px; margin-top: 8px; }}
table {{ width: 100%; border-collapse: collapse; background: var(--card); border: 1px solid var(--line); }}
th, td {{ padding: 12px 14px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
th {{ background: #eee2cc; }}
.bad {{ color: var(--red); }}
.good {{ color: var(--green); }}
.note {{ padding: 18px 20px; background: #fff7dc; border: 1px solid #e3c979; border-radius: 12px; }}
li {{ margin: 8px 0; }}
code {{ background: #efe5d4; padding: 2px 5px; border-radius: 4px; }}
</style>
</head>
<body>
<main>
<h1>真人口播剪辑进化复盘 V0</h1>
<p class="lead">这不是再骂一遍旧片，而是把“为什么业余”变成可量化、可复用、可继续迭代的导演系统。当前 v4 是基线，下一版先过分镜和证据门禁，再谈渲染。</p>

<h2>01 指标对照</h2>
<table>
<thead><tr><th>指标</th><th>当前 v4</th><th>目标/标杆</th><th>判断</th></tr></thead>
<tbody>
{metric_row("计划分镜数", old_m["scene_count"], "4-5 分钟 70-100 个微镜头", '<span class="bad">失败</span>')}
{metric_row("视觉变化/分钟", old_m["cuts_per_min"], benchmark["cuts_per_min_range"], '<span class="bad">严重不足</span>')}
{metric_row("中位镜头时长", f'{old_m["median_scene_duration_sec"]}s', benchmark["median_interval_range"], '<span class="bad">太慢</span>')}
{metric_row("CRV 去重后关键帧", f'{crv_out.get("frame_count")} / 139', "关键帧应更丰富且证据形态更多", '<span class="bad">重复度高</span>')}
{metric_row("新版导演表烟测", f'{new_m["scene_count"]} 镜 / {new_m["cuts_per_min"]} 次每分钟', "先过 14 次/分钟硬门槛，目标 17-25", '<span class="good">分镜门槛通过</span>')}
</tbody>
</table>

<h2>02 当前画面证据</h2>
<h3>v4 原始 contact sheet</h3>
{img(V4_CONTACT, "v4 contact sheet")}
<h3>CRV 关键帧网格</h3>
<div class="grid three">{grid_imgs}</div>

<h2>03 诊断</h2>
<ol>
<li><b>节奏颗粒度错。</b>16 个大段平均 16.5 秒，中位 17 秒，观众会感到“画面停着”。</li>
<li><b>证据不够真。</b>卡片和图表像内部讲义，不像真实行情、网页、公告、产品 UI、媒体素材。</li>
<li><b>人物不是信任锚。</b>侧脸同角度重复太多，缺少正脸/手势/表情/回真人的语义目的。</li>
<li><b>视觉系统过单一。</b>深色大屏 + PIP 是主系统，模板名换了但观感没换。</li>
<li><b>尾段没形成记忆闭环。</b>结论没有视觉锤，只是回到同一套人物和卡片。</li>
</ol>

<h2>04 下一版策略</h2>
<div class="note">下一版先不追求“更花”，先追求“更像剪辑”：真实证据、微镜头、人物回归、语义转场、结尾记忆点。</div>
<table>
<thead><tr><th>模块</th><th>改法</th><th>验收标准</th></tr></thead>
<tbody>
<tr><td>分镜</td><td>用 89 个微镜头计划替代 16 个大段计划。</td><td>质量门禁 pass；视觉变化 17-25 次/分钟。</td></tr>
<tr><td>证据</td><td>补真实行情图、网页/新闻/公告截图、产品 UI mock、公司矩阵。</td><td>证据镜头 45%-65%，每个证据标注真实性等级。</td></tr>
<tr><td>人物</td><td>speaker_full / punch / circle PIP / hidden / return 轮换。</td><td>人物不再机械右下角；8-20 秒内回归一次。</td></tr>
<tr><td>动画</td><td>图表轴线增长、文档推近圈注、路径点亮、PIP morph。</td><td>静态图放大不算动画；禁用黄线/扫光。</td></tr>
<tr><td>结尾</td><td>一句话 thesis + 三点选择标准 + 回真人。</td><td>最后 10 秒有清晰记忆点。</td></tr>
</tbody>
</table>

<h2>05 可讨论决策</h2>
<ol>
<li>下一版是否优先做横版生产级，还是先继续 1200x800 审核版？</li>
<li>证据素材优先补真实行情/网页截图，还是先做产品 UI/概念动效？</li>
<li>这类金融口播的人物是否允许短时间完全消失，让证据全屏独立讲 6-10 秒？</li>
</ol>

<h2>06 产物路径</h2>
<p>CRV manifest：<code>{(CRV_DIR / "dasheng_video_reading_manifest.json")}</code></p>
<p>旧门禁报告：<code>{OLD_GATE}</code></p>
<p>新版分镜门禁：<code>{NEW_GATE}</code></p>
</main>
</body>
</html>
"""
    html_path = OUT_DIR / "talking_head_evolution_review_v0.html"
    html_path.write_text(html, encoding="utf-8")
    return json_path, html_path


def main() -> None:
    json_path, html_path = build_report()
    print(json.dumps({"status": "ok", "json": str(json_path), "html": str(html_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
