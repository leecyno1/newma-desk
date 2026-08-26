#!/usr/bin/env python3
"""Bind real evidence assets to a talking-head scene plan and build a review page."""

from __future__ import annotations

import argparse
import html
import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from video_scene_plan_quality_gate import audit_scene_plan


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def as_uri(path: str | Path | None) -> str:
    if not path:
        return ""
    return Path(path).expanduser().resolve().as_uri()


def load_assets(asset_dir: Path) -> dict[str, dict[str, Any]]:
    assets: dict[str, dict[str, Any]] = {}
    chart = asset_dir / "tencent_alibaba_xiaomi_6m.fontfixed.png"
    if chart.exists():
        assets["chart_tencent_alibaba_xiaomi_6m"] = {
            "id": "chart_tencent_alibaba_xiaomi_6m",
            "kind": "real_data",
            "title": "腾讯 / 阿里 / 小米 6个月走势分化",
            "path": str(chart),
            "source_url": "https://finance.yahoo.com/quote/0700.HK/chart/",
            "note": "本地已成功生成。Yahoo 后续被限流，因此该图保留为已验证序列，不再扩展伪指数。",
        }

    screenshot_manifest = asset_dir / "source_screenshots_manifest.json"
    if screenshot_manifest.exists():
        for item in read_json(screenshot_manifest).get("assets") or []:
            if item.get("status") != "ok":
                continue
            if int(item.get("bytes") or 0) < 80_000:
                continue
            asset_id = f"shot_{item['id']}"
            assets[asset_id] = {
                "id": asset_id,
                "kind": "source_screenshot",
                "title": item.get("title") or item["id"],
                "path": item.get("path"),
                "source_url": item.get("url"),
                "note": "网页截图证据，渲染时应做文档推近、圈注、局部高亮，不做静态缩放。",
            }

    factsheet = asset_dir / "screenshots/hstech_factsheet_page1.png"
    if factsheet.exists():
        assets["hstech_factsheet_page1"] = {
            "id": "hstech_factsheet_page1",
            "kind": "source_screenshot",
            "title": "恒生科技指数 factsheet：成分、相对表现、PE、波动率",
            "path": str(factsheet),
            "source_url": "https://www.hsi.com.hk/static/uploads/contents/en/dl_centre/factsheets/hsteche.pdf",
            "note": "强证据。适合全屏文档镜头，人物可短暂消失。",
        }
    return assets


def keyword_binding(scene: dict[str, Any], assets: dict[str, dict[str, Any]]) -> dict[str, Any]:
    text = " ".join(
        str(scene.get(key) or "")
        for key in ["id", "title", "narration", "beat_class", "material_state"]
    )
    refs = [str(item) for item in scene.get("evidence_refs") or []]
    text = text + " " + " ".join(refs)
    scene_id = str(scene.get("id") or "")

    def has(*tokens: str) -> bool:
        return any(token in text for token in tokens)

    def evidence_contract(
        relation: str,
        *,
        source_locator: dict[str, Any] | None = None,
        confidence: str = "medium",
    ) -> dict[str, Any]:
        return {
            "claim_id": scene_id or str(scene.get("title") or "unnamed_claim"),
            "claim_text": str(scene.get("title") or scene.get("narration") or ""),
            "relation": relation,
            "source_locator": source_locator,
            "confidence": confidence,
        }

    binding: dict[str, Any] = {
        "asset_ids": [],
        "evidence_authenticity": scene.get("evidence_authenticity") or "",
        "evidence_note": "",
        "motion_behavior": scene.get("html_animation_behavior") or "",
        "risk_note": "",
        "suggested_speaker_state": scene.get("speaker_state"),
        "suggested_material_state": scene.get("material_state"),
        "evidence_binding": evidence_contract("assumption", confidence="low"),
    }

    if has("微信", "个人的 AI", "朋友圈", "工作群", "小微AI"):
        if "shot_tencent_investors" in assets:
            binding.update(
                {
                    "asset_ids": ["shot_tencent_investors"],
                    "evidence_authenticity": "user_claim_card",
                    "evidence_note": "腾讯投资者首页只能确认公司来源，不能直接证明微信 AI 功能、定价或渗透率。",
                    "motion_behavior": "webpage_context_enter_then_assumption_nodes_reveal",
                    "suggested_speaker_state": "circle_pip",
                    "suggested_material_state": "document_fullscreen",
                    "risk_note": "微信 AI 的具体功能和商业化参数必须明确标记为市场传闻或作者推演。",
                    "evidence_binding": evidence_contract(
                        "context",
                        source_locator={
                            "kind": "webpage_context",
                            "asset_id": "shot_tencent_investors",
                            "region": "company_investor_homepage",
                        },
                        confidence="low",
                    ),
                }
            )
    elif has("云服务", "云厂商", "卖水人", "卖铲子", "战略芯片", "量产"):
        candidates = [asset for asset in ["shot_alibaba_cloud", "shot_alibaba_results"] if asset in assets]
        if candidates:
            direct_cloud_claim = has("云服务", "云厂商", "卖水人", "卖铲子") and not has("战略芯片", "量产")
            primary_asset = candidates[0]
            binding.update(
                {
                    "asset_ids": candidates[:2],
                    "evidence_authenticity": "source_screenshot" if direct_cloud_claim else "user_claim_card",
                    "evidence_note": "阿里云官网可直接支持云服务业务存在；芯片量产和估值外推仍属于待验证判断。",
                    "motion_behavior": "browser_screenshot_slide_stack_with_exact_cloud_region_highlight",
                    "suggested_speaker_state": "rounded_rect_pip",
                    "suggested_material_state": "document_fullscreen",
                    "evidence_binding": evidence_contract(
                        "direct" if direct_cloud_claim else "context",
                        source_locator={
                            "kind": "webpage_region",
                            "asset_id": primary_asset,
                            "region": "cloud_product_or_results_section",
                        },
                        confidence="high" if direct_cloud_claim else "low",
                    ),
                }
            )
    elif has("MiMo"):
        candidates = [asset for asset in ["shot_xiaomi_ir", "shot_xiaomi_global"] if asset in assets]
        if candidates:
            binding.update(
                {
                    "asset_ids": candidates[:1],
                    "evidence_authenticity": "user_claim_card",
                    "evidence_note": "小米官网背景不能直接证明 MiMo 排名或模型能力。",
                    "motion_behavior": "webpage_context_enter_then_model_claim_badge",
                    "suggested_speaker_state": "circle_pip",
                    "suggested_material_state": "document_fullscreen",
                    "risk_note": "MiMo 排名和能力必须补模型榜单或官方技术报告。",
                    "evidence_binding": evidence_contract(
                        "context",
                        source_locator={"kind": "webpage_context", "asset_id": candidates[0], "region": "company_homepage"},
                        confidence="low",
                    ),
                }
            )
    elif has("恒科", "恒生科技", "权重股", "IPO"):
        if "hstech_factsheet_page1" in assets:
            direct_index_claim = has("权重股", "成分", "指数结构", "恒生科技指数") and not has(
                "IPO", "业绩", "AI", "最便宜", "全球", "产品", "50%"
            )
            binding.update(
                {
                    "asset_ids": ["hstech_factsheet_page1"],
                    "evidence_authenticity": "source_screenshot" if direct_index_claim else "user_claim_card",
                    "evidence_note": "恒生科技 factsheet 可直接支持指数结构、成分和表内指标；不能证明公司业绩、AI进展或IPO风险已经过去。",
                    "motion_behavior": "document_fullscreen_push_in_then_circle_mark_index_performance_and_pe_table",
                    "suggested_speaker_state": "hidden" if direct_index_claim else "circle_pip",
                    "suggested_material_state": "document_fullscreen",
                    "evidence_binding": evidence_contract(
                        "direct" if direct_index_claim else "context",
                        source_locator={
                            "kind": "document_region",
                            "asset_id": "hstech_factsheet_page1",
                            "page": 1,
                            "region": "index_constituents_performance_and_fundamentals",
                        },
                        confidence="high" if direct_index_claim else "low",
                    ),
                }
            )
    elif has("腾讯", "阿里", "小米", "Meta", "亚马逊", "苹果", "PE", "估值", "走势", "股价"):
        if "chart_tencent_alibaba_xiaomi_6m" in assets:
            direct_market_claim = has("走势", "股价", "涨", "跌", "回调", "反弹", "表现", "分化") and not has(
                "PE", "估值", "倍", "增速", "造了一个腾讯", "AI"
            )
            binding.update(
                {
                    "asset_ids": ["chart_tencent_alibaba_xiaomi_6m"],
                    "evidence_authenticity": "real_data" if direct_market_claim else "user_claim_card",
                    "evidence_note": "该行情序列只直接支持价格走势和相对表现，不能证明PE、收入增速或商业化测算。",
                    "motion_behavior": "line_chart_fullscreen_axis_draw_then_three_series_reveal_with_endpoint_callouts",
                    "suggested_speaker_state": "hidden" if direct_market_claim else "rounded_rect_pip",
                    "suggested_material_state": "chart_fullscreen",
                    "evidence_binding": evidence_contract(
                        "direct" if direct_market_claim else "context",
                        source_locator={
                            "kind": "data_series",
                            "asset_id": "chart_tencent_alibaba_xiaomi_6m",
                            "series": ["0700.HK", "9988.HK", "1810.HK"],
                            "window": "6m",
                        },
                        confidence="high" if direct_market_claim else "low",
                    ),
                }
            )
    elif scene.get("evidence_authenticity") == "real_data":
        binding.update(
            {
                "evidence_authenticity": "user_claim_card",
                "evidence_note": "原计划标 real_data，但当前缺少机器可验证来源，先降级为作者观点/测算卡。",
                "motion_behavior": "assumption_card_step_reveal_with_source_pending_badge",
                "risk_note": "渲染前若不能补外部数据，画面必须明确写“作者测算/情景假设”。",
            }
        )
    elif scene.get("evidence_authenticity") == "schematic" or "evidence" in str(scene.get("material_state") or ""):
        binding.update(
            {
                "evidence_authenticity": "schematic",
                "evidence_note": "概念/节奏镜头。可用 HTML 动画解释，但不能伪装成网页或行情。",
                "motion_behavior": scene.get("html_animation_behavior") or "semantic_html_motion_required",
            }
        )

    return binding


def bind_scene_plan(plan: dict[str, Any], assets: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    new_plan = dict(plan)
    new_plan["schema_version"] = "dasheng.video.scene_plan.real_evidence_review.v1"
    new_plan["created_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    new_plan["evidence_policy"] = {
        "review_resolution": "1200x800",
        "priorities": ["真实行情图", "官网/网页截图", "官方PDF factsheet", "作者观点卡必须降级标注"],
        "speaker_hidden_allowed": True,
        "render_blocker": "真实证据审核页未通过前不进入成片渲染。",
    }
    bound_scenes: list[dict[str, Any]] = []
    bindings: list[dict[str, Any]] = []
    for scene in plan.get("scenes") or []:
        bound = dict(scene)
        binding = keyword_binding(bound, assets)
        asset_ids = binding["asset_ids"]
        if asset_ids:
            bound["evidence_asset_ids"] = asset_ids
            bound["evidence_assets"] = [
                {
                    "id": asset_id,
                    "kind": assets[asset_id].get("kind"),
                    "title": assets[asset_id].get("title"),
                    "path": assets[asset_id].get("path"),
                    "source_url": assets[asset_id].get("source_url"),
                }
                for asset_id in asset_ids
                if asset_id in assets
            ]
        if binding["evidence_authenticity"]:
            bound["evidence_authenticity"] = binding["evidence_authenticity"]
        bound["evidence_binding"] = binding["evidence_binding"]
        if binding["motion_behavior"]:
            bound["html_animation_behavior"] = binding["motion_behavior"]
        if binding["suggested_speaker_state"]:
            bound["speaker_state"] = binding["suggested_speaker_state"]
        if binding["suggested_material_state"]:
            bound["material_state"] = binding["suggested_material_state"]
        risk_notes = list(bound.get("risk_notes") or [])
        if binding["risk_note"]:
            risk_notes.append(binding["risk_note"])
        if binding["evidence_note"]:
            risk_notes.append(binding["evidence_note"])
        if risk_notes:
            bound["risk_notes"] = risk_notes
        bindings.append(
            {
                "scene_id": bound.get("id"),
                "time": f"{bound.get('start_sec')}-{bound.get('end_sec')}s",
                "title": bound.get("title"),
                "asset_ids": asset_ids,
                "evidence_authenticity": bound.get("evidence_authenticity"),
                "evidence_binding": bound.get("evidence_binding"),
                "speaker_state": bound.get("speaker_state"),
                "material_state": bound.get("material_state"),
                "motion_behavior": bound.get("html_animation_behavior"),
                "note": binding["evidence_note"],
                "risk": binding["risk_note"],
            }
        )
        bound_scenes.append(bound)
    break_repeated_compositions(bound_scenes)
    for item, scene in zip(bindings, bound_scenes):
        item["speaker_state"] = scene.get("speaker_state")
        item["material_state"] = scene.get("material_state")
        item["pip_shape"] = scene.get("pip_shape")
    new_plan["scenes"] = bound_scenes
    return new_plan, bindings


def composition_key(scene: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(scene.get("speaker_state") or "unknown"),
        str(scene.get("material_state") or "unknown"),
        str(scene.get("pip_shape") or "unknown"),
    )


def break_repeated_compositions(scenes: list[dict[str, Any]]) -> None:
    """Avoid the fixed-layout failure mode before the quality gate runs."""
    run_key: tuple[str, str, str] | None = None
    run_count = 0
    for index, scene in enumerate(scenes):
        key = composition_key(scene)
        if key == run_key:
            run_count += 1
        else:
            run_key = key
            run_count = 1
        if run_count <= 2:
            continue

        material = str(scene.get("material_state") or "")
        if material in {"document_fullscreen", "chart_fullscreen", "evidence_fullscreen"}:
            alternatives = [
                ("hidden", "none"),
                ("rounded_rect_pip", "rounded_rect"),
                ("circle_pip", "circle"),
                ("vertical_strip", "none"),
            ]
            prev_key = composition_key(scenes[index - 1]) if index > 0 else None
            for speaker_state, pip_shape in alternatives:
                candidate = (speaker_state, material, pip_shape)
                if candidate != prev_key:
                    scene["speaker_state"] = speaker_state
                    scene["pip_shape"] = pip_shape
                    break
            notes = list(scene.get("risk_notes") or [])
            notes.append("自动打断连续构图：避免固定右下角/同类PIP超过两个镜头。")
            scene["risk_notes"] = notes
        else:
            scene["speaker_state"] = "full" if scene.get("speaker_state") != "full" else "speaker_punch_in"
            scene["pip_shape"] = "none"
        run_key = composition_key(scene)
        run_count = 1


def asset_figure(asset: dict[str, Any]) -> str:
    path = asset.get("path")
    if not path or not Path(path).exists():
        return '<div class="missing">素材缺失</div>'
    return (
        f'<figure><img src="{as_uri(path)}" alt="{esc(asset.get("title"))}">'
        f'<figcaption>{esc(asset.get("title"))}</figcaption></figure>'
    )


def build_review_html(plan: dict[str, Any], assets: dict[str, dict[str, Any]], bindings: list[dict[str, Any]], output: Path) -> None:
    scenes = plan.get("scenes") or []
    strong = sum(1 for scene in scenes if scene.get("evidence_authenticity") in {"real_data", "source_screenshot"})
    user_claim = sum(1 for scene in scenes if scene.get("evidence_authenticity") == "user_claim_card")
    schematic = sum(1 for scene in scenes if scene.get("evidence_authenticity") == "schematic")
    hidden = sum(1 for scene in scenes if scene.get("speaker_state") == "hidden")
    rows = []
    for index, scene in enumerate(scenes, 1):
        evidence_assets = scene.get("evidence_assets") or []
        preview = "".join(asset_figure(asset) for asset in evidence_assets) or '<div class="missing">无真实证据素材</div>'
        risks = "；".join(str(item) for item in scene.get("risk_notes") or [])
        source_urls = "<br>".join(
            f'<a href="{esc(asset.get("source_url"))}">{esc(asset.get("source_url"))}</a>'
            for asset in evidence_assets
            if asset.get("source_url")
        )
        rows.append(
            f"""
            <tr class="{esc(scene.get('evidence_authenticity') or 'none')}">
              <td><b>{index:02d}</b><br><code>{esc(scene.get('id'))}</code><br>{float(scene.get('start_sec', 0)):.1f}-{float(scene.get('end_sec', 0)):.1f}s</td>
              <td><b>{esc(scene.get('title'))}</b><p>{esc(scene.get('narration'))}</p></td>
              <td><span class="pill">{esc(scene.get('evidence_authenticity') or 'none')}</span><br>{source_urls}</td>
              <td>{preview}</td>
              <td>{esc(scene.get('speaker_state'))}<br>{esc(scene.get('material_state'))}<br>{esc(scene.get('pip_shape'))}</td>
              <td>{esc(scene.get('template_id'))}<br><small>{esc(scene.get('html_animation_behavior'))}</small></td>
              <td>{esc(risks)}</td>
            </tr>
            """
        )

    asset_cards = "\n".join(
        f"""
        <article>
          {asset_figure(asset)}
          <p><b>{esc(asset.get('kind'))}</b></p>
          <p>{esc(asset.get('note'))}</p>
          <p><a href="{esc(asset.get('source_url'))}">{esc(asset.get('source_url'))}</a></p>
        </article>
        """
        for asset in assets.values()
    )
    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(plan.get("title"))}｜真实证据分镜审核 V1</title>
<style>
:root {{ --bg:#f4efe5; --ink:#151515; --muted:#70695e; --line:#d9cdbb; --card:#fffaf0; --red:#9d2f24; --green:#245c45; --blue:#254c78; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font-family:"Songti SC","PingFang SC",serif; line-height:1.6; }}
main {{ max-width:1460px; margin:0 auto; padding:36px 22px 80px; }}
h1 {{ margin:0 0 10px; font-size:34px; line-height:1.15; }}
h2 {{ margin-top:38px; border-left:8px solid var(--red); padding-left:12px; }}
.lead {{ max-width:880px; color:var(--muted); font-size:17px; }}
.metrics {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:24px 0; }}
.metric {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:14px 16px; }}
.metric b {{ display:block; font-size:26px; }}
.asset-grid {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:14px; }}
article, figure {{ margin:0; }}
article {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:12px; }}
img {{ width:100%; display:block; border-radius:8px; border:1px solid rgba(0,0,0,.08); }}
figcaption {{ font-size:12px; color:var(--muted); margin-top:6px; }}
table {{ width:100%; border-collapse:collapse; background:var(--card); border:1px solid var(--line); font-size:13px; }}
th,td {{ border-bottom:1px solid var(--line); padding:10px; text-align:left; vertical-align:top; }}
th {{ position:sticky; top:0; background:#eadcc7; z-index:2; }}
td:nth-child(1) {{ width:86px; }}
td:nth-child(2) {{ width:250px; }}
td:nth-child(4) {{ width:260px; }}
td:nth-child(6) {{ width:210px; }}
.pill {{ display:inline-block; padding:2px 8px; border-radius:999px; background:#ece0cc; font-weight:700; }}
tr.real_data .pill {{ background:#d8eadf; color:var(--green); }}
tr.source_screenshot .pill {{ background:#dfe8f5; color:var(--blue); }}
tr.user_claim_card .pill {{ background:#f3dfcf; color:#8b4a18; }}
tr.schematic .pill {{ background:#eee7d8; color:#63513b; }}
.missing {{ min-height:80px; display:grid; place-items:center; background:#eee2d1; border:1px dashed #c7b89f; color:var(--muted); border-radius:10px; text-align:center; padding:8px; }}
small {{ color:var(--muted); }}
a {{ color:var(--blue); word-break:break-all; }}
</style>
</head>
<body>
<main>
<h1>真实证据分镜审核 V1｜1200x800 审核版</h1>
<p class="lead">这一版不渲染成片，只审核“证据是否真实、人物是否该出现、动效是否有意义”。强证据来自真实行情图、官网截图和恒生科技官方 factsheet；没有外部验证的数据一律降级成作者观点卡。</p>
<section class="metrics">
  <div class="metric"><span>分镜数</span><b>{len(scenes)}</b></div>
  <div class="metric"><span>真实/来源证据</span><b>{strong}</b></div>
  <div class="metric"><span>作者观点卡</span><b>{user_claim}</b></div>
  <div class="metric"><span>人物隐藏镜头</span><b>{hidden}</b></div>
</section>
<h2>证据素材包</h2>
<div class="asset-grid">{asset_cards}</div>
<h2>逐分镜审核表</h2>
<table>
<thead><tr><th>时间</th><th>口播/语义</th><th>证据等级/来源</th><th>证据预览</th><th>人物/版式</th><th>模板/动效</th><th>风险备注</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
</main>
</body>
</html>
"""
    output.write_text(html_text, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build real-evidence review artifacts for talking-head scene plans.")
    parser.add_argument("--scene-plan", required=True)
    parser.add_argument("--asset-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scene_plan = Path(args.scene_plan).expanduser().resolve()
    asset_dir = Path(args.asset_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    assets = load_assets(asset_dir)
    plan, bindings = bind_scene_plan(read_json(scene_plan), assets)
    out_plan = output_dir / "scene_plan.v1_real_evidence.json"
    out_bindings = output_dir / "evidence_binding_manifest.json"
    out_gate = output_dir / "scene_plan_quality_gate.json"
    out_html = output_dir / "storyboard_real_evidence_review.html"
    out_assets = output_dir / "evidence_assets_manifest.json"
    write_json(out_plan, plan)
    write_json(out_bindings, {"schema_version": "dasheng.evidence_binding_manifest.v1", "created_at": datetime.now().astimezone().isoformat(timespec="seconds"), "bindings": bindings})
    write_json(out_assets, {"schema_version": "dasheng.evidence_assets_manifest.v1", "created_at": datetime.now().astimezone().isoformat(timespec="seconds"), "assets": list(assets.values())})
    gate = audit_scene_plan(plan)
    gate["scene_plan"] = str(out_plan)
    write_json(out_gate, gate)
    build_review_html(plan, assets, bindings, out_html)
    shutil.copy2(out_html, output_dir / "index.html")
    print(json.dumps({"status": "ok", "output_dir": str(output_dir), "scene_plan": str(out_plan), "review_html": str(out_html), "gate": str(out_gate), "gate_status": gate["status"]}, ensure_ascii=False, indent=2))
    return 0 if gate["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
