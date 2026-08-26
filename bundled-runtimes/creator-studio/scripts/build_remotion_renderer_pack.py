#!/usr/bin/env python3
"""Create a production-oriented Remotion renderer pack outside the repo."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

from video_vox_storyboard import vox_micro_shots


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = PROJECT_ROOT / "templates" / "video" / "remotion-director"
ASPECT_DIMENSIONS = {
    "16:9": (1920, 1080),
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "4:5": (1080, 1350),
}

CANONICAL_FAMILIES: dict[str, dict[str, str]] = {
    "speaker-anchor": {
        "component": "SpeakerAnchorFamily",
        "variant": "trust_anchor",
        "motion_signature": "speaker_punch_in_keyword_constellation",
    },
    "data-line-chart": {
        "component": "DataLineChartFamily",
        "variant": "data_native_series",
        "motion_signature": "axis_draw_series_trace_endpoint_annotation",
    },
    "valuation-compare": {
        "component": "ValuationCompareFamily",
        "variant": "peer_multiple_bars",
        "motion_signature": "baseline_lock_peer_bars_ratio_reveal",
    },
    "document-exact-crop": {
        "component": "DocumentExactCropFamily",
        "variant": "source_region",
        "motion_signature": "document_enter_exact_crop_marker_focus",
    },
    "evidence-table": {
        "component": "EvidenceTableFamily",
        "variant": "compact_finance_table",
        "motion_signature": "header_lock_row_stagger_cell_emphasis",
    },
    "logic-flow": {
        "component": "LogicFlowFamily",
        "variant": "causal_nodes",
        "motion_signature": "node_reveal_connector_trace_conclusion_lock",
    },
    "product-ui": {
        "component": "ProductUiFamily",
        "variant": "device_interaction",
        "motion_signature": "device_enter_task_steps_result_confirmation",
    },
    "broll-fullscreen": {
        "component": "BrollFullscreenFamily",
        "variant": "cinematic_context",
        "motion_signature": "video_cut_context_label_subject_return",
    },
    "split-comparison": {
        "component": "SplitComparisonFamily",
        "variant": "paired_argument",
        "motion_signature": "dual_panel_enter_metric_compare_verdict",
    },
    "recap-outro": {
        "component": "RecapOutroFamily",
        "variant": "thesis_recap",
        "motion_signature": "thesis_stack_progressive_lock_clean_exit",
    },
    "vox-editorial-collage": {
        "component": "VoxEditorialCollageFamily",
        "variant": "continuous_paper_evidence_world",
        "motion_signature": "camera_tracks_shared_world_objects_transform_evidence_resolves",
    },
}

SCENE_MEDIA_FIELDS = {
    "document_src": ".png",
    "document_detail_src": ".png",
    "broll_src": ".mp4",
    "background_video_src": ".mp4",
    "pip_video_src": ".mp4",
    "pip_image_src": ".png",
    "secondary_pip_image_src": ".png",
    "linked_entry_src": ".png",
    "motion_plate_src": ".mp4",
    "keyframe_start_src": ".png",
    "keyframe_end_src": ".png",
}

VOX_LAYER_ASSET_TYPES = {"image", "video"}

CHART_COLORS = ["#0d766e", "#d65c45", "#396b88", "#c6933a", "#7257a8"]
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def apply_asset_binding_plan(scene_plan: dict[str, Any], binding_plan: dict[str, Any] | None) -> dict[str, Any]:
    if not binding_plan:
        return copy.deepcopy(scene_plan)
    merged = copy.deepcopy(scene_plan)
    for key, value in (binding_plan.get("plan_overrides") or {}).items():
        merged[key] = copy.deepcopy(value)
    patches = {
        str(item.get("scene_id") or item.get("id")): item
        for item in binding_plan.get("scenes") or binding_plan.get("bindings") or []
        if isinstance(item, dict) and (item.get("scene_id") or item.get("id"))
    }
    known_ids: set[str] = set()
    for scene in merged.get("scenes") or merged.get("segments") or []:
        scene_id = str(scene.get("id") or "")
        known_ids.add(scene_id)
        patch = patches.get(scene_id)
        if not patch:
            continue
        patch_payload = {key: value for key, value in patch.items() if key not in {"scene_id", "id"}}
        scene.clear()
        scene.update(_deep_merge(scene_plan_scene := next(
            item for item in (scene_plan.get("scenes") or scene_plan.get("segments") or [])
            if str(item.get("id") or "") == scene_id
        ), patch_payload))
    unknown = sorted(set(patches) - known_ids)
    if unknown:
        raise ValueError(f"asset binding plan contains unknown scene ids: {', '.join(unknown)}")
    merged["asset_binding_plan"] = str(binding_plan.get("schema_version") or "dasheng.video.asset_binding_plan.v1")
    return merged


def _normalize_captions(scene: dict[str, Any]) -> None:
    if scene.get("captions"):
        return
    cues = scene.get("caption_cues") or scene.get("subtitle_cues") or []
    if not cues:
        return
    scene_start = float(scene.get("start_sec") or 0.0)
    captions: list[dict[str, Any]] = []
    for cue in cues:
        if not isinstance(cue, dict) or not str(cue.get("text") or "").strip():
            continue
        if cue.get("local_start_sec") is not None:
            local_start = float(cue["local_start_sec"])
        else:
            local_start = max(0.0, float(cue.get("start_sec") or 0.0) - scene_start)
        if cue.get("local_end_sec") is not None:
            local_end = float(cue["local_end_sec"])
        else:
            local_end = max(local_start + 0.08, float(cue.get("end_sec") or 0.0) - scene_start)
        captions.append(
            {
                "text": str(cue["text"]).strip(),
                "startMs": round(local_start * 1000),
                "endMs": round(local_end * 1000),
                "timingSource": str(cue.get("timing_source") or scene.get("subtitle_timing_source") or "provider"),
            }
        )
    if captions:
        scene["captions"] = captions


def _contains(scene: dict[str, Any], *tokens: str) -> bool:
    text = " ".join(
        str(scene.get(key) or "")
        for key in ["id", "title", "narration", "core_claim_id", "beat_class", "material_state", "content_part"]
    ).lower()
    return any(token.lower() in text for token in tokens)


def _claim_id(scene: dict[str, Any]) -> str:
    value = scene.get("core_claim_id")
    if value:
        return str(value)
    values = scene.get("core_claim_ids") or []
    return str(values[0]) if values else ""


def _claim_index(claim_ledger: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not claim_ledger:
        return {}
    return {
        str(claim.get("id")): claim
        for claim in claim_ledger.get("claims") or []
        if claim.get("id")
    }


def _merge_evidence_records(scene: dict[str, Any], claim: dict[str, Any] | None) -> list[dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    allowed_asset_ids: set[str] = set()
    claim_items = [
        item
        for item in (claim or {}).get("evidence_items") or []
        if isinstance(item, dict)
    ]
    allowed_asset_ids.update(
        str(item.get("asset_id"))
        for item in claim_items
        if item.get("asset_id") and not item.get("scene_id")
    )
    for requirement in (claim or {}).get("evidence_requirements") or []:
        if not isinstance(requirement, dict):
            continue
        allowed_asset_ids.update(
            str(asset_id)
            for asset_id in requirement.get("satisfied_by_asset_ids") or []
            if asset_id
        )
    has_claim_asset_contract = bool(allowed_asset_ids)
    for item in claim_items:
        if not isinstance(item, dict):
            continue
        asset_id = str(item.get("asset_id") or "")
        if asset_id and (not has_claim_asset_contract or asset_id in allowed_asset_ids):
            records[asset_id] = copy.deepcopy(item)

    binding = scene.get("evidence_binding") or {}
    scene_relation = str(binding.get("relation") or "context")
    scene_confidence = str(binding.get("confidence") or "")
    for item in scene.get("evidence_assets") or []:
        if not isinstance(item, dict):
            continue
        asset_id = str(item.get("id") or item.get("asset_id") or "")
        if not asset_id:
            continue
        if has_claim_asset_contract and asset_id not in allowed_asset_ids:
            continue
        record = records.setdefault(asset_id, {"asset_id": asset_id})
        for key, value in item.items():
            record.setdefault(key, value)
        record.setdefault("relation", scene_relation)
        record.setdefault("confidence", scene_confidence)
        record.setdefault("verdict", "supports" if scene_relation == "direct" else "neutral")
        locator = dict(record.get("source_locator") or {})
        if item.get("path"):
            path = str(item["path"])
            if Path(path).suffix.lower() in IMAGE_SUFFIXES:
                locator.setdefault("local_png", path)
            elif Path(path).suffix.lower() == ".json":
                locator.setdefault("json_path", path)
        if item.get("source_url"):
            locator.setdefault("url", str(item["source_url"]))
        record["source_locator"] = locator

    return sorted(
        records.values(),
        key=lambda item: (
            str(item.get("relation") or "") != "direct",
            str(item.get("verdict") or "") != "supports",
            str(item.get("asset_id") or ""),
        ),
    )


def _candidate_paths(record: dict[str, Any], keys: tuple[str, ...]) -> list[Path]:
    locator = record.get("source_locator") or {}
    candidates: list[Path] = []
    for key in keys:
        value = record.get(key) or locator.get(key)
        if not value:
            continue
        path = Path(str(value)).expanduser()
        if path not in candidates:
            candidates.append(path)
    return candidates


def _load_evidence_json(record: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    candidates = _candidate_paths(
        record,
        ("json_path", "local_json", "local_source", "path"),
    )
    image_candidates = _candidate_paths(
        record,
        ("local_png", "local_screenshot", "local_page_1", "png_path", "image_path", "path"),
    )
    for image_path in image_candidates:
        if image_path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        candidates.append(image_path.with_suffix(".json"))
        if image_path.stem.endswith(".fontfixed"):
            candidates.append(image_path.with_name(image_path.stem.removesuffix(".fontfixed") + ".json"))

    for path in candidates:
        if path.suffix.lower() != ".json" or not path.exists():
            continue
        try:
            return read_json(path.resolve()), str(path.resolve())
        except (OSError, json.JSONDecodeError):
            continue
    return None, ""


def _evidence_image(record: dict[str, Any]) -> str:
    for path in _candidate_paths(
        record,
        ("local_png", "local_screenshot", "local_page_1", "png_path", "image_path", "path"),
    ):
        if path.suffix.lower() in IMAGE_SUFFIXES and path.exists():
            return str(path.resolve())
    return ""


def _evidence_source(record: dict[str, Any], payload: dict[str, Any] | None = None) -> str:
    locator = record.get("source_locator") or {}
    payload = payload or {}
    payload_locator = payload.get("source_locator") or {}
    current_source = payload.get("current_source") or {}
    documents = payload.get("documents") or []
    provider = str(
        record.get("source")
        or locator.get("provider")
        or payload.get("provider")
        or payload.get("source")
        or ""
    )
    url = str(
        record.get("source_url")
        or locator.get("url")
        or payload.get("source_url")
        or payload_locator.get("url")
        or current_source.get("source_url")
        or next((item.get("source_url") for item in documents if isinstance(item, dict) and item.get("source_url")), "")
        or ""
    )
    if provider and url:
        return f"{provider} | {url}"
    return provider or url


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _chart_visual(record: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
    labels = payload.get("labels") or payload.get("dates") or []
    raw_series = payload.get("series") or []
    if not raw_series and payload.get("datasets"):
        raw_series = [
            {
                "name": item.get("label"),
                "color": item.get("borderColor"),
                "values": item.get("data"),
            }
            for item in payload.get("datasets") or []
        ]
    series: list[dict[str, Any]] = []
    for index, item in enumerate(raw_series):
        if not isinstance(item, dict):
            continue
        values = [_number(value) for value in item.get("values") or item.get("data") or []]
        if not values or any(value is None for value in values):
            continue
        series.append(
            {
                "name": str(item.get("name") or item.get("label") or f"Series {index + 1}"),
                "color": str(item.get("color") or item.get("borderColor") or CHART_COLORS[index % len(CHART_COLORS)]),
                "values": [float(value) for value in values if value is not None],
            }
        )
    if not series:
        return None
    if not labels:
        labels = [str(index + 1) for index in range(len(series[0]["values"]))]
    headline = str(payload.get("title") or record.get("title") or "")
    if not headline:
        windows = payload.get("window_returns") or []
        selected = next((item for item in windows if item.get("sessions") == 10), windows[0] if windows else None)
        if selected:
            values = [
                f"{item.get('name') or item.get('ticker')} {float(item.get('return_pct') or 0):+.2f}%"
                for item in selected.get("returns") or []
            ]
            if values:
                headline = f"近{selected.get('sessions')}个交易日：" + " / ".join(values)
    headline = headline or str(record.get("claim_text") or "")
    return {
        "asset_id": str(record.get("asset_id") or record.get("id") or payload.get("asset_id") or payload.get("id") or ""),
        "evidence_relation": str(record.get("relation") or ""),
        "evidence_confidence": str(record.get("confidence") or ""),
        "source": _evidence_source(record, payload),
        "headline": headline,
        "labels": [str(value) for value in labels],
        "series": series,
    }


def _valuation_visual(record: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
    metrics: list[dict[str, Any]] = []
    for row in payload.get("rows") or []:
        if not isinstance(row, dict):
            continue
        value = _number(row.get("company_pe_ttm"))
        peer_value = _number(row.get("peer_pe_ttm"))
        if value is None or peer_value is None:
            continue
        metrics.append(
            {
                "label": str(row.get("company_name") or row.get("company_ticker") or row.get("label") or "Company"),
                "value": value,
                "peer": str(row.get("peer_name") or row.get("peer_ticker") or "Peer"),
                "peer_value": peer_value,
            }
        )
    if not metrics:
        return None
    return {
        "asset_id": str(record.get("asset_id") or record.get("id") or ""),
        "evidence_relation": str(record.get("relation") or ""),
        "evidence_confidence": str(record.get("confidence") or ""),
        "source": _evidence_source(record, payload),
        "unit": str(payload.get("metric") or "PE (TTM)"),
        "metrics": metrics,
    }


def _format_number(value: Any) -> str:
    number = _number(value)
    if number is None:
        return str(value or "-")
    if abs(number) >= 1_000_000_000:
        return f"{number / 1_000_000_000:.2f}bn"
    if abs(number) >= 1_000_000:
        return f"{number / 1_000_000:.2f}m"
    if float(number).is_integer():
        return f"{int(number):,}"
    return f"{number:.2f}"


def _table_visual(record: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
    columns: list[str] = []
    rows: list[list[str]] = []
    if payload.get("dates") and payload.get("net_amount"):
        columns = ["日期", f"净买入（{payload.get('unit') or '原始单位'}）"]
        rows = [
            [str(date), _format_number(value)]
            for date, value in zip(payload.get("dates") or [], payload.get("net_amount") or [])
        ][-6:]
    elif payload.get("documents"):
        columns = ["公司", "指标", "数值", "同比/页码"]
        for document in payload.get("documents") or []:
            if not isinstance(document, dict):
                continue
            for fact in document.get("facts") or []:
                if not isinstance(fact, dict):
                    continue
                yoy = fact.get("yoy_pct")
                suffix = f"{_format_number(yoy)}%" if yoy is not None else f"p.{fact.get('page') or '-'}"
                rows.append(
                    [
                        str(document.get("company") or document.get("period") or "-"),
                        str(fact.get("metric") or fact.get("category") or "-"),
                        str(fact.get("display_value") or "-"),
                        suffix,
                    ]
                )
    elif payload.get("current_models") and payload.get("baseline"):
        columns = ["模型", "输入 $/1M", "输出 $/1M", "相对 GPT-4"]
        baseline = payload.get("baseline") or {}
        rows.append(
            [
                str(baseline.get("model") or "GPT-4"),
                _format_number(baseline.get("input_usd_per_1m")),
                _format_number(baseline.get("output_usd_per_1m")),
                "100%",
            ]
        )
        for model in payload.get("current_models") or []:
            rows.append(
                [
                    str(model.get("model") or "-"),
                    _format_number(model.get("input_cache_miss_usd_per_1m")),
                    _format_number(model.get("output_usd_per_1m")),
                    f"{_format_number(model.get('output_vs_gpt4_pct'))}%",
                ]
            )
    elif payload.get("models"):
        models = payload.get("models") or []
        if any(isinstance(model, dict) and model.get("score") is not None for model in models):
            columns = ["模型", "分数", "状态"]
            rows = [
                [str(model.get("model") or "-"), _format_number(model.get("score")), str(model.get("evaluation_status") or "-")]
                for model in models
                if isinstance(model, dict)
            ]
        elif any(isinstance(model, dict) and model.get("price_per_1m_tokens_usd") for model in models):
            columns = ["模型", "输入未命中", "输出", "上下文"]
            rows = []
            for model in models:
                prices = model.get("price_per_1m_tokens_usd") or {}
                rows.append(
                    [
                        str(model.get("model") or "-"),
                        _format_number(prices.get("input_cache_miss")),
                        _format_number(prices.get("output")),
                        str(model.get("context_length") or "-"),
                    ]
                )
    elif payload.get("latest_repurchase"):
        latest = payload.get("latest_repurchase") or {}
        mandate = payload.get("repurchase_mandate_progress") or {}
        columns = ["指标", "数值", "日期/口径"]
        rows = [
            ["当日回购股数", _format_number(latest.get("shares")), str(latest.get("trading_date") or "-")],
            ["当日回购金额", f"HKD {_format_number(latest.get('aggregate_price_hkd'))}", "官方公告"],
            ["授权下累计回购", _format_number(mandate.get("shares_repurchased_under_mandate")), str(mandate.get("mandate_resolution_date") or "-")],
        ]
    elif payload.get("rows") and isinstance(payload.get("rows")[0], dict):
        raw_rows = payload.get("rows") or []
        scalar_keys = [
            key
            for key, value in raw_rows[0].items()
            if isinstance(value, (str, int, float)) and key not in {"company_secid", "peer_secid"}
        ][:4]
        columns = scalar_keys
        rows = [[_format_number(row.get(key)) for key in scalar_keys] for row in raw_rows[:6]]
    if not columns or not rows:
        return None
    return {
        "asset_id": str(record.get("asset_id") or record.get("id") or payload.get("id") or ""),
        "evidence_relation": str(record.get("relation") or ""),
        "evidence_confidence": str(record.get("confidence") or ""),
        "source": _evidence_source(record, payload),
        "headline": str(payload.get("title") or record.get("title") or ""),
        "columns": columns,
        "rows": rows[:6],
    }


def _filter_visual_for_scene(visual: dict[str, Any], scene: dict[str, Any]) -> dict[str, Any]:
    text = " ".join(str(scene.get(key) or "") for key in ["title", "narration"]).lower()
    tokens = [token for token in ["腾讯", "meta", "阿里", "amazon", "亚马逊", "alphabet", "谷歌", "小米", "apple", "苹果", "deepseek", "hy3"] if token in text]
    filtered = copy.deepcopy(visual)
    if tokens and filtered.get("metrics"):
        metrics = [
            metric
            for metric in filtered["metrics"]
            if any(token in f"{metric.get('label', '')} {metric.get('peer', '')}".lower() for token in tokens)
        ]
        if metrics:
            filtered["metrics"] = metrics
    if tokens and filtered.get("rows"):
        rows = [row for row in filtered["rows"] if any(token in " ".join(row).lower() for token in tokens)]
        if rows:
            filtered["rows"] = rows[:6]
    if any(token in text for token in ["估值", "市盈率", " pe", "pe "]) and filtered.get("rows"):
        rows = [row for row in filtered["rows"] if any(token in " ".join(row).lower() for token in ["估值", "pe", "valuation"])]
        if rows:
            filtered["rows"] = rows[:6]
    return filtered


def _asset_relevance(record: dict[str, Any], scene: dict[str, Any]) -> int:
    scene_text = " ".join(str(scene.get(key) or "") for key in ["title", "narration"]).lower()
    asset_text = " ".join(
        str(record.get(key) or "")
        for key in ["asset_id", "id", "title", "claim_text"]
    ).lower()
    score = 0
    rules = [
        (("token", "成本", "1%"), ("token_cost", "cost_history"), 14),
        (("hy3", "混元", "评分", "榜单", "接近", "60分"), ("hunyuan", "benchmark"), 16),
        (("deepseek", "v4", "定价", "推出", "上线"), ("deepseek", "pricing"), 12),
        (("估值", "pe", "折价", "市盈率"), ("valuation", "peers"), 14),
        (("回购",), ("buyback", "repurchase"), 18),
        (("权重", "成分", "恒生科技", "恒科"), ("hstech_factsheet",), 13),
        (("财报", "业绩", "云", "ai", "研发", "芯片", "ppu"), ("weight_company_results",), 9),
        (("mimo", "小米模型", "开源模型"), ("xiaomi_mimo",), 18),
        (("南向", "净买入", "港股通", "资金承接"), ("southbound", "net_flow"), 16),
        (("韩国", "kospi", "纳斯达克", "美国", "回撤", "崩盘"), ("cross_market", "nasdaq", "kospi"), 15),
        (("阿里云", "云服务", "卖水人", "卖铲子"), ("alibaba_cloud",), 14),
    ]
    for scene_tokens, asset_tokens, weight in rules:
        if any(token in scene_text for token in scene_tokens) and any(token in asset_text for token in asset_tokens):
            score += weight
    return score


def _bind_selected_asset(
    scene: dict[str, Any],
    record: dict[str, Any],
    visual: dict[str, Any],
    renderer_family: str,
) -> None:
    asset_id = str(visual.get("asset_id") or record.get("asset_id") or record.get("id") or "")
    relation = str(record.get("relation") or visual.get("evidence_relation") or "context")
    confidence = str(record.get("confidence") or visual.get("evidence_confidence") or "")
    authenticity = str(record.get("authenticity") or "")
    if relation != "direct" and authenticity in {"real_data", "source_screenshot"}:
        authenticity = f"context_{authenticity}"
    scene["preferred_renderer_family"] = renderer_family
    scene["visual"] = {**(scene.get("visual") or {}), **visual}
    scene["evidence_asset_ids"] = [asset_id] if asset_id else []
    scene["evidence_assets"] = []
    scene["evidence_authenticity"] = authenticity or ("real_data" if renderer_family in {"data-line-chart", "valuation-compare", "evidence-table"} else "source_screenshot")
    scene["evidence_binding"] = {
        "claim_id": _claim_id(scene),
        "claim_text": str(scene.get("title") or scene.get("narration") or ""),
        "relation": relation,
        "source_locator": copy.deepcopy(record.get("source_locator")),
        "confidence": confidence,
        "micro_claim_id": _claim_id(scene),
    }


def _mark_scene_as_schematic(scene: dict[str, Any], relation: str = "assumption") -> None:
    scene["evidence_asset_ids"] = []
    scene["evidence_assets"] = []
    scene["evidence_authenticity"] = "schematic"
    scene["evidence_binding"] = {
        "claim_id": _claim_id(scene),
        "claim_text": str(scene.get("title") or scene.get("narration") or ""),
        "relation": relation,
        "source_locator": None,
        "confidence": "",
        "micro_claim_id": _claim_id(scene),
    }


def _hydrate_scene_from_claim(scene: dict[str, Any], claim: dict[str, Any] | None) -> None:
    if not claim:
        return
    scene["core_claim_type"] = str(claim.get("claim_type") or "")
    disclosure = str(claim.get("disclosure_label") or "")
    if disclosure:
        scene["disclosure_label"] = disclosure

    title = str(scene.get("title") or scene.get("narration") or "")
    text = title.lower()
    claim_type = str(claim.get("claim_type") or "")
    if str(scene.get("beat_class") or "") in {"recap", "outro"}:
        scene["preferred_renderer_family"] = "recap-outro"
        scene["visual"] = {
            **(scene.get("visual") or {}),
            "points": [
                str(claim.get("title") or "核心命题"),
                title,
                disclosure or "保留验证条件",
            ],
        }
        _mark_scene_as_schematic(scene, relation="context")
        return
    records = _merge_evidence_records(scene, claim)
    candidates: list[tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None, str]] = []
    for record in records:
        payload, _ = _load_evidence_json(record)
        chart = _chart_visual(record, payload) if payload else None
        valuation = _valuation_visual(record, payload) if payload else None
        table = _table_visual(record, payload) if payload else None
        image = _evidence_image(record)
        candidates.append((record, chart, valuation, table, image))
    candidates.sort(key=lambda item: _asset_relevance(item[0], scene), reverse=True)

    if claim_type == "rumor" or "市场传闻" in disclosure:
        context = disclosure or "功能示意，尚无官方确认"
        if any(token in text for token in ["分散", "不同app", "不同 app"]):
            scene["preferred_renderer_family"] = "split-comparison"
            scene["visual"] = {
                **(scene.get("visual") or {}),
                "left": {"title": "现在", "value": "多 App 分散"},
                "right": {"title": "传闻情景", "value": "微信集中"},
                "context": context,
            }
        elif any(token in text for token in ["接管", "集中化", "收容"]):
            scene["preferred_renderer_family"] = "logic-flow"
            scene["visual"] = {
                **(scene.get("visual") or {}),
                "nodes": ["用户指令", "Agent 执行", "场景集中"],
                "context": context,
            }
        elif any(token in text for token in ["催化剂", "听到", "听说"]):
            scene["preferred_renderer_family"] = "speaker-anchor"
            scene["visual"] = {
                **(scene.get("visual") or {}),
                "context": context,
                "keywords": ["传闻", "催化", "待确认"],
            }
        else:
            scene["preferred_renderer_family"] = "product-ui"
            scene["visual"] = {
                **(scene.get("visual") or {}),
                "context": context,
                "tasks": ["收到用户指令", title, "返回结果（功能示意）"],
                "keywords": ["传闻", "示意", "待确认"],
            }
        _mark_scene_as_schematic(scene)
        return

    valuation_tokens = ["估值", "市盈率", "pe", "倍", "折价", "对标", "三分之", "1/2", "2/3"]
    if any(token in text for token in valuation_tokens):
        for record, _chart, valuation, _table, _image in candidates:
            if valuation:
                _bind_selected_asset(
                    scene,
                    record,
                    _filter_visual_for_scene(valuation, scene),
                    "valuation-compare",
                )
                return
        if str(scene.get("material_state") or "") == "chart_fullscreen":
            for record, chart, _valuation, _table, _image in candidates:
                if chart:
                    _bind_selected_asset(scene, record, chart, "data-line-chart")
                    return
        for record, _chart, _valuation, table, _image in candidates:
            if table and str(record.get("relation") or "") == "direct":
                _bind_selected_asset(
                    scene,
                    record,
                    _filter_visual_for_scene(table, scene),
                    "evidence-table",
                )
                return

    if str(scene.get("material_state") or "") == "document_fullscreen":
        for record, _chart, _valuation, _table, image in candidates:
            if image and str(record.get("relation") or "") == "direct":
                locator = record.get("source_locator") or {}
                visual = {
                    "asset_id": str(record.get("asset_id") or ""),
                    "evidence_relation": "direct",
                    "evidence_confidence": str(record.get("confidence") or ""),
                    "document_src": image,
                    "document_title": str(record.get("title") or claim.get("title") or title),
                    "source": _evidence_source(record),
                    "callouts": [
                        value
                        for value in [
                            f"p.{locator.get('page')}" if locator.get("page") else "",
                            str(locator.get("region") or ""),
                        ]
                        if value
                    ],
                }
                _bind_selected_asset(scene, record, visual, "document-exact-crop")
                return

    table_tokens = ["回购", "token", "价格", "费用", "评分", "榜单", "财报", "业绩", "权重", "净买入", "流入", "芯片"]
    if any(token in text for token in table_tokens) or str(scene.get("beat_class") or "") in {"evidence_data", "evidence_document"}:
        for record, _chart, _valuation, table, _image in candidates:
            if table and str(record.get("relation") or "") == "direct":
                _bind_selected_asset(
                    scene,
                    record,
                    _filter_visual_for_scene(table, scene),
                    "evidence-table",
                )
                return

    if str(scene.get("material_state") or "") == "chart_fullscreen":
        for record, chart, _valuation, _table, _image in candidates:
            if chart:
                _bind_selected_asset(scene, record, chart, "data-line-chart")
                return
        if str(scene.get("beat_class") or "") == "evidence_data":
            for record, _chart, _valuation, table, _image in candidates:
                if table and str(record.get("relation") or "") == "direct":
                    _bind_selected_asset(
                        scene,
                        record,
                        _filter_visual_for_scene(table, scene),
                        "evidence-table",
                    )
                    return
        if str(scene.get("beat_class") or "") == "logic_chain":
            scene["preferred_renderer_family"] = "logic-flow"
            scene["visual"] = {
                **(scene.get("visual") or {}),
                "nodes": ["上一个案例", title, "下一个证据"],
            }
            _mark_scene_as_schematic(scene, relation="context")
            return

    if claim_type in {"assumption", "forecast", "opinion", "recommendation"}:
        percentages = re.findall(r"\d+(?:\.\d+)?%", title)
        if len(percentages) >= 2:
            scene["preferred_renderer_family"] = "split-comparison"
            scene["visual"] = {
                **(scene.get("visual") or {}),
                "left": {"title": "保守情景", "value": percentages[0]},
                "right": {"title": "乐观情景", "value": percentages[1]},
                "context": disclosure or "作者情景测算",
            }
        elif claim_type == "assumption" and any(token in text for token in ["套餐", "一个月", "块钱", "收费"]):
            scene["preferred_renderer_family"] = "product-ui"
            scene["visual"] = {
                **(scene.get("visual") or {}),
                "context": disclosure or "作者情景测算",
                "tasks": ["设定价格假设", title, "代入渗透率与年化口径"],
                "keywords": ["价格假设", "渗透率", "年化"],
            }
        elif str(scene.get("beat_class") or "") in {"logic_chain", "objection"} or any(
            token in text for token in ["如果", "那么", "因为", "所以", "导致", "意味着", "按理想"]
        ):
            scene["preferred_renderer_family"] = "logic-flow"
            scene["visual"] = {
                **(scene.get("visual") or {}),
                "nodes": [disclosure.split("：", 1)[0] if disclosure else "前提", title, "结果待验证"],
                "context": disclosure,
            }
        else:
            scene["preferred_renderer_family"] = "speaker-anchor"
            scene["visual"] = {
                **(scene.get("visual") or {}),
                "context": disclosure,
                "keywords": [
                    disclosure.split("：", 1)[0][:10] if disclosure else "观点",
                    title[:12],
                    "待验证",
                ],
            }
        _mark_scene_as_schematic(scene)


def hydrate_scene_plan_from_claim_ledger(
    scene_plan: dict[str, Any], claim_ledger: dict[str, Any] | None
) -> dict[str, Any]:
    hydrated = copy.deepcopy(scene_plan)
    claims = _claim_index(claim_ledger)
    if not claims:
        return hydrated
    for scene in hydrated.get("scenes") or hydrated.get("segments") or []:
        _hydrate_scene_from_claim(scene, claims.get(_claim_id(scene)))
    hydrated["renderer_evidence_source"] = str(claim_ledger.get("schema_version") or "claim_evidence_ledger")
    hydrated["claim_evidence_gate_status"] = str(claim_ledger.get("gate_status") or "unknown")
    hydrated["pending_spoken_revision_count"] = sum(
        1
        for claim in claim_ledger.get("claims") or []
        for revision in claim.get("spoken_revision_requirements") or []
        if not revision.get("applied")
    )
    return hydrated


def assign_renderer_family(scene: dict[str, Any]) -> str:
    explicit = str(scene.get("renderer_family") or "")
    if explicit in CANONICAL_FAMILIES:
        return explicit
    template_id = str(scene.get("template_id") or "")
    if template_id in CANONICAL_FAMILIES:
        return template_id

    beat = str(scene.get("beat_class") or "")
    material = str(scene.get("material_state") or "")
    if beat in {"recap", "outro"} or _contains(scene, "总结", "结论", "一句话"):
        return "recap-outro"
    preferred = str(scene.get("preferred_renderer_family") or "")
    if preferred in CANONICAL_FAMILIES:
        return preferred
    visual = scene.get("visual") or {}
    if visual.get("metrics"):
        return "valuation-compare"
    if visual.get("series"):
        return "data-line-chart"
    if visual.get("rows"):
        return "evidence-table"
    if visual.get("document_src"):
        return "document-exact-crop"
    claim_type = str(scene.get("core_claim_type") or "")
    relation = str((scene.get("evidence_binding") or {}).get("relation") or "")
    if claim_type == "rumor":
        return "product-ui"
    if "valuation" in str(scene.get("core_claim_id") or ""):
        return "valuation-compare"
    if material == "document_fullscreen" or beat == "evidence_document":
        if relation in {"context", "assumption"}:
            return "logic-flow" if claim_type in {"assumption", "forecast", "opinion", "recommendation"} else "speaker-anchor"
        return "document-exact-crop"
    if _contains(scene, "估值", "forward pe", "市盈率"):
        return "valuation-compare"
    if material == "chart_fullscreen" or _contains(scene, "折线", "走势", "资金流"):
        return "data-line-chart"
    if material == "split_screen" or _contains(scene, "对比", "一边", "另一边"):
        return "split-comparison"
    if material == "broll_fullscreen" or _contains(scene, "b-roll", "实拍", "场景素材"):
        return "broll-fullscreen"
    if _contains(scene, "微信", "mimo", "agent", "产品", "app", "界面"):
        return "product-ui"
    if _contains(scene, "表格", "财报", "回购", "数据表"):
        return "evidence-table"
    if beat in {"logic_chain", "objection"} or _contains(scene, "因为", "所以", "如果", "导致", "逻辑"):
        return "logic-flow"
    return "speaker-anchor"


def route_scene_plan(
    scene_plan: dict[str, Any], *, claim_ledger: dict[str, Any] | None = None
) -> dict[str, Any]:
    routed = hydrate_scene_plan_from_claim_ledger(scene_plan, claim_ledger)
    lane = str(routed.get("lane") or "")
    is_vox = lane == "vox_explainer_video"
    is_commercial = lane == "commercial_promo_video"
    routed["renderer"] = (
        "dasheng-remotion-vox-collage.v2"
        if is_vox
        else "dasheng-remotion-commercial-promo.v1"
        if is_commercial
        else "dasheng-remotion-director-pack.v1"
    )
    format_spec = routed.get("format") or {}
    routed.setdefault("aspect", str(format_spec.get("aspect_ratio") or "16:9"))
    routed.setdefault("width", int(format_spec.get("width") or 1920))
    routed.setdefault("height", int(format_spec.get("height") or 1080))
    routed.setdefault("fps", int(format_spec.get("fps") or 30))
    if lane in {"talking_head_video", "digital_human_video", "commercial_promo_video"}:
        routed.setdefault("voice_gain", 0.9)
    for scene in routed.get("scenes") or routed.get("segments") or []:
        _normalize_captions(scene)
        source_template = str(scene.get("template_id") or "")
        family = "vox-editorial-collage" if is_vox else assign_renderer_family(scene)
        scene["source_template_id"] = source_template
        scene["template_id"] = family
        scene["renderer_family"] = family
        if is_vox:
            scene["vox_state"] = str(scene.get("narrative_function") or scene.get("type") or "mechanism_explainer")
            scene.setdefault("visual_system", "vox_editorial_paper_collage")
            scene.setdefault("world_id", "shared_paper_evidence_world")
            scene.setdefault("micro_shots", vox_micro_shots(str(scene.get("id") or "scene"), scene["vox_state"]))
            visual = scene.setdefault("visual", {})
            visual.setdefault("collage_style", "paper_diorama")
            visual.setdefault("world_id", str(scene.get("world_id") or "shared_paper_evidence_world"))
            visual.setdefault("micro_shots", scene.get("micro_shots") or [])
            if scene.get("emphasis_cues") and not visual.get("emphasis_cues"):
                visual["emphasis_cues"] = copy.deepcopy(scene["emphasis_cues"])
            if scene.get("entity_labels") and not visual.get("entity_labels"):
                visual["entity_labels"] = copy.deepcopy(scene["entity_labels"])
            if scene.get("subtitle_cues") and not scene.get("captions"):
                scene["captions"] = copy.deepcopy(scene["subtitle_cues"])
            if scene.get("subtitle_timing_source"):
                scene["subtitle_timing_source"] = str(scene["subtitle_timing_source"])
        if is_commercial:
            visual = scene.setdefault("visual", {})
            visual.setdefault("brand_tokens", (routed.get("commercial") or {}).get("brand_tokens") or (scene.get("motion") or {}).get("brand_tokens") or {})
            scene.setdefault("commercial_safe_area_slots", copy.deepcopy(scene.get("safe_area_slots") or {}))
    return routed


def audit_renderer_assets(scene_plan: dict[str, Any]) -> dict[str, Any]:
    render_mode = str(scene_plan.get("render_mode") or "production")
    allow_placeholders = bool(scene_plan.get("allow_placeholders")) or render_mode == "showcase"
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    claim_gate_status = str(scene_plan.get("claim_evidence_gate_status") or "")
    pending_spoken_revisions = int(scene_plan.get("pending_spoken_revision_count") or 0)
    if claim_gate_status == "fail":
        finding = {
            "code": "claim_evidence_gate_failed" if render_mode == "production" else "claim_evidence_gate_pending_review",
            "pending_spoken_revision_count": pending_spoken_revisions,
            "message": "Production rendering requires all contradicted or unsupported spoken claims to be cut, replaced, overdubbed, or re-recorded.",
        }
        if render_mode == "production":
            failures.append(finding)
        else:
            warnings.append(finding)

    if not allow_placeholders:
        for scene in scene_plan.get("scenes") or scene_plan.get("segments") or []:
            scene_id = str(scene.get("id") or "unknown")
            family = str(scene.get("renderer_family") or scene.get("template_id") or "")
            visual = scene.get("visual") or {}

            if family == "document-exact-crop" and not visual.get("document_src"):
                failures.append(
                    {
                        "code": "document_asset_missing",
                        "scene_id": scene_id,
                        "message": "Production document scene requires visual.document_src.",
                    }
                )
            if family == "document-exact-crop" and not visual.get("source"):
                failures.append(
                    {
                        "code": "document_source_missing",
                        "scene_id": scene_id,
                        "message": "Production document scene requires a visible source URL or provider.",
                    }
                )
            if family == "document-exact-crop" and visual.get("evidence_relation") not in {None, "", "direct"}:
                failures.append(
                    {
                        "code": "document_evidence_not_direct",
                        "scene_id": scene_id,
                        "message": "Context-only evidence cannot be presented as an exact source-document proof scene.",
                    }
                )
            if family == "broll-fullscreen" and not visual.get("broll_src"):
                failures.append(
                    {
                        "code": "broll_asset_missing",
                        "scene_id": scene_id,
                        "message": "Production B-roll scene requires moving visual.broll_src footage.",
                    }
                )
            if family == "data-line-chart":
                if not visual.get("series"):
                    failures.append(
                        {
                            "code": "chart_data_missing",
                            "scene_id": scene_id,
                            "message": "Production chart scene requires visual.series.",
                        }
                    )
                if not visual.get("source"):
                    failures.append(
                        {
                            "code": "chart_source_missing",
                            "scene_id": scene_id,
                            "message": "Production chart scene requires a visible data source.",
                        }
                    )
            if family == "valuation-compare" and not visual.get("metrics"):
                failures.append(
                    {
                        "code": "valuation_data_missing",
                        "scene_id": scene_id,
                        "message": "Production valuation scene requires visual.metrics.",
                    }
                )
            if family == "valuation-compare" and not visual.get("source"):
                failures.append(
                    {
                        "code": "valuation_source_missing",
                        "scene_id": scene_id,
                        "message": "Production valuation scene requires a visible same-definition data source.",
                    }
                )
            if family == "evidence-table" and not visual.get("rows"):
                failures.append(
                    {
                        "code": "table_data_missing",
                        "scene_id": scene_id,
                        "message": "Production table scene requires visual.rows.",
                    }
                )
            if family == "evidence-table" and not visual.get("source"):
                failures.append(
                    {
                        "code": "table_source_missing",
                        "scene_id": scene_id,
                        "message": "Production evidence table requires a visible source URL or provider.",
                    }
                )

            for field in SCENE_MEDIA_FIELDS:
                source_value = visual.get(field)
                if source_value and not Path(str(source_value)).expanduser().exists():
                    failures.append(
                        {
                            "code": "scene_media_file_missing",
                            "scene_id": scene_id,
                            "field": field,
                            "path": str(source_value),
                            "message": "Scene media path does not exist.",
                        }
                    )

            for item_index, item in enumerate(visual.get("pip_items") or [], start=1):
                if not isinstance(item, dict):
                    continue
                source_value = item.get("src")
                if source_value and not Path(str(source_value)).expanduser().exists():
                    failures.append(
                        {
                            "code": "scene_pip_media_file_missing",
                            "scene_id": scene_id,
                            "item_index": item_index,
                            "path": str(source_value),
                            "message": "PIP media path does not exist.",
                        }
                    )

            sfx_src = (scene.get("audio") or {}).get("sfx_src")
            if sfx_src and not Path(str(sfx_src)).expanduser().exists():
                failures.append(
                    {
                        "code": "scene_sfx_file_missing",
                        "scene_id": scene_id,
                        "path": str(sfx_src),
                        "message": "Scene sound effect path does not exist.",
                    }
                )

            if family == "vox-editorial-collage":
                layers = [item for item in visual.get("scene_layers") or [] if isinstance(item, dict)]
                if len(layers) < 8:
                    failures.append(
                        {
                            "code": "vox_independent_layer_count_low",
                            "scene_id": scene_id,
                            "actual": len(layers),
                            "minimum": 8,
                            "message": "Production VOX scenes require at least eight independently animated layers.",
                        }
                    )
                motion_fields: set[str] = set()
                depths: set[float] = set()
                for layer in layers:
                    layer_id = str(layer.get("id") or "unknown")
                    asset_type = str(layer.get("asset_type") or "")
                    source_value = layer.get("src")
                    if asset_type in VOX_LAYER_ASSET_TYPES and not source_value:
                        failures.append(
                            {
                                "code": "vox_layer_asset_missing",
                                "scene_id": scene_id,
                                "layer_id": layer_id,
                                "message": "Image and video VOX layers require src.",
                            }
                        )
                    elif source_value and not Path(str(source_value)).expanduser().exists():
                        failures.append(
                            {
                                "code": "vox_layer_asset_file_missing",
                                "scene_id": scene_id,
                                "layer_id": layer_id,
                                "path": str(source_value),
                                "message": "VOX layer asset path does not exist.",
                            }
                        )
                    depths.add(float(layer.get("depth") or 0))
                    keyframes = [
                        item
                        for field in ("entry_path", "motion_path", "exit_path")
                        for item in layer.get(field) or []
                        if isinstance(item, dict)
                    ]
                    for field in ("x", "y", "z", "rotation", "rotate_x", "rotate_y", "scale", "opacity"):
                        values = [item.get(field) for item in keyframes if isinstance(item.get(field), (int, float))]
                        if len(set(values)) > 1 or any(value not in {0, 1} for value in values):
                            motion_fields.add(field)
                    if len({item.get("value") for item in layer.get("rotation_keyframes") or []}) > 1:
                        motion_fields.add("rotation")
                    if len({item.get("value") for item in layer.get("scale_keyframes") or []}) > 1:
                        motion_fields.add("scale")
                if len(motion_fields) < 3:
                    failures.append(
                        {
                            "code": "vox_motion_vocabulary_low",
                            "scene_id": scene_id,
                            "actual": sorted(motion_fields),
                            "minimum": 3,
                            "message": "Production VOX scenes require at least three independent motion dimensions.",
                        }
                    )
                camera_keys = [item for item in visual.get("camera_keyframes") or [] if isinstance(item, dict)]
                camera_z = {item.get("z") for item in camera_keys if isinstance(item.get("z"), (int, float))}
                if len(camera_keys) < 2 or (len(camera_z) < 2 and len(depths) < 2):
                    failures.append(
                        {
                            "code": "vox_depth_camera_missing",
                            "scene_id": scene_id,
                            "message": "Production VOX scenes require camera keyframes and real depth separation.",
                        }
                    )

    return {
        "schema_version": "dasheng.video.renderer_asset_gate.v1",
        "status": "pass" if not failures else "fail",
        "render_mode": render_mode,
        "allow_placeholders": allow_placeholders,
        "failure_count": len(failures),
        "warning_count": len(warnings),
        "failures": failures,
        "warnings": warnings,
    }


def build_renderer_contract() -> dict[str, Any]:
    return {
        "schema_version": "dasheng.video.renderer_contract.v1",
        "renderer": "NewmaRemotionDirectorPack",
        "source": "src/DirectorVideo.tsx",
        "audio_architecture": {
            "voice": "single_continuous_root_track",
            "scene_video": "muted_visual_only",
            "bgm": "separate_continuous_root_track",
        },
        "asset_policy": {
            "production_placeholders": "blocked",
            "showcase_placeholders": "explicitly_allowed",
            "scene_media": "linked_into_public_assets",
        },
        "consumed_scene_fields": [
            "template_id",
            "speaker_state",
            "material_state",
            "pip_shape",
            "transition_in",
            "transition_out",
            "html_animation_behavior",
            "audio",
        ],
        "templates": {
            template_id: {"status": "implemented", **definition}
            for template_id, definition in CANONICAL_FAMILIES.items()
        },
    }


def build_showcase_plan() -> dict[str, Any]:
    scenes: list[dict[str, Any]] = []
    cursor = 0.0
    showcase_compositions = {
        "speaker-anchor": ("full", "transparent_overlay", "none"),
        "data-line-chart": ("hidden", "chart_fullscreen", "none"),
        "valuation-compare": ("rounded_rect_pip", "evidence_fullscreen", "rounded_rect"),
        "document-exact-crop": ("hidden", "document_fullscreen", "none"),
        "evidence-table": ("circle_pip", "evidence_fullscreen", "circle"),
        "logic-flow": ("vertical_strip", "evidence_fullscreen", "none"),
        "product-ui": ("rounded_rect_pip", "evidence_fullscreen", "phone_mockup"),
        "broll-fullscreen": ("hidden", "broll_fullscreen", "none"),
        "split-comparison": ("half_right", "split_screen", "none"),
        "recap-outro": ("hidden", "evidence_fullscreen", "none"),
        "vox-editorial-collage": ("hidden", "evidence_fullscreen", "none"),
    }
    demo_visuals = {
        "data-line-chart": {
            "series": [
                {"name": "恒生科技", "color": "#0d766e", "values": [100, 104, 101, 109, 116, 121]},
                {"name": "纳斯达克", "color": "#d65c45", "values": [100, 102, 106, 103, 101, 99]},
            ],
            "labels": ["W1", "W2", "W3", "W4", "W5", "W6"],
            "source": "Renderer demo data, not production evidence",
        },
        "valuation-compare": {
            "metrics": [
                {"label": "腾讯", "value": 14, "peer": "Meta", "peer_value": 23},
                {"label": "小米", "value": 18, "peer": "Apple", "peer_value": 31},
            ],
            "unit": "Forward PE demo",
        },
        "document-exact-crop": {
            "document_title": "官方文件精确区域",
            "callouts": ["页码 + 表格行", "只高亮当前命题"],
            "source": "Demo document",
        },
        "evidence-table": {
            "columns": ["命题", "数据", "来源"],
            "rows": [["回购", "金额/股数", "公司公告"], ["估值", "同口径 PE", "数据终端"]],
        },
        "logic-flow": {"nodes": ["成本下降", "调用增加", "应用扩张", "收入验证"]},
        "product-ui": {"tasks": ["读取工作群", "提取待办", "生成报告"]},
        "broll-fullscreen": {"context": "真实 B-roll 位置，不使用静态图片缩放冒充动画"},
        "split-comparison": {
            "left": {"title": "事实", "value": "官方数据"},
            "right": {"title": "判断", "value": "作者推演"},
        },
        "recap-outro": {"points": ["先核验证据", "再生成素材", "最后进入渲染"]},
        "speaker-anchor": {"keywords": ["问题", "证据", "结论"]},
        "vox-editorial-collage": {
            "eyebrow": "VOX EVIDENCE WORLD",
            "nodes": ["风格板", "微分镜", "起止关键帧", "连续纸张世界"],
            "source": "Renderer showcase",
        },
    }
    for index, template_id in enumerate(CANONICAL_FAMILIES, start=1):
        duration = 3.6
        speaker_state, material_state, pip_shape = showcase_compositions[template_id]
        scenes.append(
            {
                "id": f"showcase_{index:02d}",
                "title": CANONICAL_FAMILIES[template_id]["variant"].replace("_", " ").title(),
                "narration": f"Renderer showcase: {template_id}",
                "start_sec": round(cursor, 3),
                "end_sec": round(cursor + duration, 3),
                "duration_sec": duration,
                "beat_class": "recap" if template_id == "recap-outro" else "evidence_data",
                "template_id": template_id,
                "renderer_family": template_id,
                "speaker_state": speaker_state,
                "material_state": material_state,
                "pip_shape": pip_shape,
                "transition_in": "hard_cut" if index == 1 else "cross_dissolve",
                "transition_out": "hard_cut",
                "html_animation_behavior": CANONICAL_FAMILIES[template_id]["motion_signature"],
                "audio": {"duck_bgm": True, "sfx": None},
                "visual": demo_visuals[template_id],
            }
        )
        cursor += duration
    return {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "talking_head_video",
        "aspect": "16:9",
        "title": "Newma Renderer Family Showcase",
        "fps": 30,
        "width": 1920,
        "height": 1080,
        "source_video": "",
        "bgm_src": "",
        "render_mode": "showcase",
        "allow_placeholders": True,
        "scenes": scenes,
    }


def write_renderer_project(
    output_dir: Path,
    scene_plan: dict[str, Any],
    *,
    source_video: str = "",
    bgm_src: str = "",
) -> dict[str, Path]:
    output_dir = output_dir.expanduser().resolve()
    if not TEMPLATE_ROOT.exists():
        raise FileNotFoundError(f"Remotion renderer template not found: {TEMPLATE_ROOT}")
    output_dir.mkdir(parents=True, exist_ok=True)
    for source in TEMPLATE_ROOT.rglob("*"):
        relative = source.relative_to(TEMPLATE_ROOT)
        if relative.parts and relative.parts[0] == "node_modules":
            continue
        target = output_dir / relative
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    payload = copy.deepcopy(scene_plan)
    payload.setdefault("fps", 30)
    default_width, default_height = ASPECT_DIMENSIONS.get(str(payload.get("aspect") or "16:9"), (1920, 1080))
    payload.setdefault("width", default_width)
    payload.setdefault("height", default_height)

    asset_gate_path = output_dir / "renderer_asset_gate.json"
    asset_report = audit_renderer_assets(payload)
    write_json(asset_gate_path, asset_report)
    if asset_report["status"] != "pass":
        raise ValueError("production renderer assets are incomplete; inspect renderer_asset_gate.json")

    def link_public_asset(source_value: str, stem: str, fallback_suffix: str) -> str:
        source = Path(source_value).expanduser().resolve()
        if not source.exists():
            raise FileNotFoundError(f"Media asset not found: {source}")
        relative = Path("assets") / f"{stem}{source.suffix or fallback_suffix}"
        target = output_dir / "public" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            target.unlink()
        try:
            os.link(source, target)
        except OSError:
            shutil.copy2(source, target)
        return relative.as_posix()

    if source_video:
        payload["source_video"] = link_public_asset(source_video, "source_video", ".mp4")
    if bgm_src:
        payload["bgm_src"] = link_public_asset(bgm_src, "bgm", ".wav")

    for index, scene in enumerate(payload.get("scenes") or payload.get("segments") or [], start=1):
        visual = scene.get("visual") or {}
        scene_slug = re.sub(r"[^0-9A-Za-z_-]+", "_", str(scene.get("id") or index)).strip("_") or str(index)
        for field, fallback_suffix in SCENE_MEDIA_FIELDS.items():
            source_value = visual.get(field)
            if not source_value:
                continue
            visual[field] = link_public_asset(
                str(source_value),
                f"scenes/{index:03d}_{scene_slug}/{field}",
                fallback_suffix,
            )
        for pip_index, item in enumerate(visual.get("pip_items") or [], start=1):
            if not isinstance(item, dict) or not item.get("src"):
                continue
            source_value = str(item["src"])
            fallback_suffix = ".mp4" if item.get("type") == "video" else ".png"
            item["src"] = link_public_asset(
                source_value,
                f"scenes/{index:03d}_{scene_slug}/pip/{pip_index:02d}",
                fallback_suffix,
            )
        for layer_index, layer in enumerate(visual.get("scene_layers") or [], start=1):
            if not isinstance(layer, dict) or not layer.get("src"):
                continue
            source_value = str(layer["src"])
            fallback_suffix = ".mp4" if layer.get("asset_type") == "video" else ".png"
            layer_slug = re.sub(r"[^0-9A-Za-z_-]+", "_", str(layer.get("id") or layer_index)).strip("_") or str(layer_index)
            layer["src"] = link_public_asset(
                source_value,
                f"scenes/{index:03d}_{scene_slug}/layers/{layer_index:02d}_{layer_slug}",
                fallback_suffix,
            )
        if visual:
            scene["visual"] = visual
        audio = scene.get("audio") or {}
        if audio.get("sfx_src"):
            audio["sfx_src"] = link_public_asset(
                str(audio["sfx_src"]),
                f"scenes/{index:03d}_{scene_slug}/sfx",
                ".wav",
            )
            scene["audio"] = audio

    scene_plan_path = output_dir / "data" / "scene_plan.json"
    contract_path = output_dir / "renderer_contract.json"
    write_json(scene_plan_path, payload)
    write_json(contract_path, build_renderer_contract())
    return {
        "project_dir": output_dir,
        "scene_plan": scene_plan_path,
        "renderer_contract": contract_path,
        "asset_gate": asset_gate_path,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the Newma Remotion director renderer project.")
    parser.add_argument("--scene-plan")
    parser.add_argument("--claim-ledger", default="")
    parser.add_argument("--asset-binding-plan", default="")
    parser.add_argument("--showcase", action="store_true")
    parser.add_argument("--review", action="store_true")
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--source-video", default="")
    parser.add_argument("--bgm", default="")
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.showcase:
        plan = build_showcase_plan()
    elif args.scene_plan:
        claim_ledger = read_json(Path(args.claim_ledger).expanduser().resolve()) if args.claim_ledger else None
        binding_plan = read_json(Path(args.asset_binding_plan).expanduser().resolve()) if args.asset_binding_plan else None
        source_plan = apply_asset_binding_plan(
            read_json(Path(args.scene_plan).expanduser().resolve()),
            binding_plan,
        )
        plan = route_scene_plan(
            source_plan,
            claim_ledger=claim_ledger,
        )
        # The ledger may add evidence defaults, but explicit reviewed asset bindings
        # remain authoritative for the renderer payload.
        plan = apply_asset_binding_plan(plan, binding_plan)
    else:
        raise SystemExit("Provide --scene-plan or --showcase")
    if args.review:
        plan["render_mode"] = "review"
    if args.audit_only:
        output_dir = Path(args.output_dir).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        scene_plan_path = output_dir / "scene_plan.renderer_ready.json"
        asset_gate_path = output_dir / "renderer_asset_gate.json"
        report = audit_renderer_assets(plan)
        write_json(scene_plan_path, plan)
        write_json(asset_gate_path, report)
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "scene_plan": str(scene_plan_path),
                    "asset_gate": str(asset_gate_path),
                    "failure_count": report["failure_count"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if report["status"] == "pass" else 1
    result = write_renderer_project(
        Path(args.output_dir),
        plan,
        source_video=args.source_video,
        bgm_src=args.bgm,
    )
    print(json.dumps({key: str(value) for key, value in result.items()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
