#!/usr/bin/env python3
"""Apply a human-readable editorial brief to an auto-generated scene plan."""

from __future__ import annotations

import argparse
import copy
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def merge_dict(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_dict(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def midpoint(scene: dict[str, Any]) -> float:
    return (float(scene.get("start_sec", 0)) + float(scene.get("end_sec", 0))) / 2


def interval_match(items: list[dict[str, Any]], time_sec: float) -> dict[str, Any] | None:
    for item in items:
        if float(item.get("start_sec", 0)) <= time_sec < float(item.get("end_sec", 10**9)):
            return item
    return None


def cleanup_routing_text(text: str, replacements: dict[str, str]) -> str:
    cleaned = text
    generic = {
        "space CX": "SpaceX",
        "space x": "SpaceX",
        "SBCX": "SpaceX",
        "space sex": "SpaceX",
        "四VCX": "SpaceX",
        "starlink": "Starlink",
        "starling": "Starlink",
        "a股": "A股",
        "nasa": "NASA",
        "ps": "PS",
        "PS,": "PS，",
        "估值的毛": "估值的锚",
    }
    for source, target in {**generic, **replacements}.items():
        cleaned = cleaned.replace(source, target)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"([，。！？])\1+", r"\1", cleaned)
    cleaned = re.sub(r"^(?:嗯|呃|啊)[，,\s]*", "", cleaned)
    return cleaned.strip()


def phrase_for_scene(chapter: dict[str, Any], scene: dict[str, Any]) -> str:
    phrases = [str(item) for item in chapter.get("phrases") or [] if str(item).strip()]
    if not phrases:
        return str(chapter.get("title") or scene.get("title") or "")
    start = float(chapter.get("start_sec", 0))
    end = max(start + 0.001, float(chapter.get("end_sec", start + 1)))
    progress = min(0.999999, max(0.0, (midpoint(scene) - start) / (end - start)))
    return phrases[min(len(phrases) - 1, int(progress * len(phrases)))]


def cycle_value(chapter: dict[str, Any], key: str, index: int, fallback: Any) -> Any:
    values = chapter.get(key) or []
    if not values:
        return fallback
    return copy.deepcopy(values[index % len(values)])


def chart_visual(asset: dict[str, Any]) -> dict[str, Any]:
    payload = read_json(Path(asset["data_json"]).expanduser().resolve())
    dates = payload.get("dates") or payload.get("labels") or []
    labels = [str(value)[5:] if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value)) else str(value) for value in dates]
    series = []
    colors = ["#0d766e", "#d65c45", "#396b88", "#c6933a", "#7257a8"]
    for index, item in enumerate(payload.get("series") or []):
        series.append(
            {
                "name": str(item.get("name") or item.get("ticker") or f"序列{index + 1}"),
                "color": item.get("color") or colors[index % len(colors)],
                "values": item.get("values") or [],
            }
        )
    return {
        "labels": labels,
        "series": series,
        "source": asset.get("source"),
    }


def table_visual(asset: dict[str, Any]) -> dict[str, Any]:
    payload = read_json(Path(asset["data_json"]).expanduser().resolve())
    rows = payload.get("rows") or []
    if rows and isinstance(rows[0], dict):
        columns = asset.get("columns") or list(rows[0].keys())
        normalized_rows = [[str(row.get(column, "-")) for column in columns] for row in rows]
    else:
        columns = asset.get("columns") or payload.get("columns") or []
        normalized_rows = [[str(value) for value in row] for row in rows]
    return {
        "columns": columns,
        "rows": normalized_rows,
        "source": asset.get("source") or payload.get("provider"),
    }


def asset_visual(asset: dict[str, Any], scene: dict[str, Any], cue: dict[str, Any]) -> dict[str, Any]:
    kind = str(asset.get("kind") or "")
    visual: dict[str, Any] = {}
    if kind == "chart":
        visual = chart_visual(asset)
    elif kind == "table":
        visual = table_visual(asset)
    elif kind == "document":
        visual = {
            "document_src": str(Path(asset["path"]).expanduser().resolve()),
            "document_title": asset.get("title"),
            "callouts": asset.get("callouts") or [],
            "source": asset.get("source"),
        }
    elif kind == "broll":
        visual = {
            "broll_src": str(Path(asset["path"]).expanduser().resolve()),
            "broll_start_sec": round(
                float(asset.get("asset_start_sec", 0))
                + max(0.0, float(scene.get("start_sec", 0)) - float(cue.get("start_sec", 0))),
                3,
            ),
            "context": asset.get("context"),
            "source": asset.get("source"),
        }
    return visual


def default_visual(
    scene: dict[str, Any],
    chapter: dict[str, Any],
    pattern: dict[str, Any],
    scene_index: int,
) -> dict[str, Any]:
    family = str(pattern.get("template_id") or "speaker-anchor")
    title = str(scene.get("title") or chapter.get("title") or "")
    keywords = cycle_value(chapter, "keyword_sets", scene_index, chapter.get("keywords") or [])
    visual: dict[str, Any] = {
        "eyebrow": pattern.get("eyebrow") or chapter.get("eyebrow") or "核心判断",
        "keywords": keywords,
        "display_mode": pattern.get("display_mode") or "card",
    }
    if family == "logic-flow":
        visual["nodes"] = cycle_value(
            chapter,
            "logic_sequences",
            scene_index,
            [chapter.get("title") or "条件", title, "定价结果"],
        )
        visual["source"] = chapter.get("logic_source") or "逻辑示意，不构成外部证据"
    elif family == "split-comparison":
        comparison = cycle_value(
            chapter,
            "comparisons",
            scene_index,
            {
                "left": {"title": "SpaceX", "value": "自主供应链"},
                "right": {"title": "国内体系", "value": "体系内协同"},
            },
        )
        visual.update(comparison)
    elif family == "recap-outro":
        visual["points"] = cycle_value(chapter, "recap_sets", scene_index, chapter.get("keywords") or [])
    return visual


def normalize_pattern(pattern: dict[str, Any]) -> dict[str, Any]:
    family = str(pattern.get("template_id") or "speaker-anchor")
    defaults = {
        "speaker-anchor": ("full", "none", "none"),
        "logic-flow": ("vertical_strip", "evidence_fullscreen", "none"),
        "split-comparison": ("hidden", "evidence_fullscreen", "none"),
        "recap-outro": ("hidden", "evidence_fullscreen", "none"),
    }
    speaker_state, material_state, pip_shape = defaults.get(family, ("full", "transparent_overlay", "none"))
    return {
        "template_id": family,
        "speaker_state": pattern.get("speaker_state") or speaker_state,
        "material_state": pattern.get("material_state") or material_state,
        "pip_shape": pattern.get("pip_shape") or pip_shape,
        "transition_in": pattern.get("transition_in") or "hard_cut",
        "transition_out": pattern.get("transition_out") or "hard_cut",
        "html_animation_behavior": pattern.get("html_animation_behavior") or "semantic_motion_required",
        "camera": pattern.get("camera") or {"scale": 1.0, "x": 0.0, "y": 0.0},
    }


def composition_key(scene: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(scene.get("speaker_state") or "unknown"),
        str(scene.get("material_state") or "unknown"),
        str(scene.get("pip_shape") or "unknown"),
    )


def break_repeated_compositions(scenes: list[dict[str, Any]]) -> None:
    previous: tuple[str, str, str] | None = None
    run_count = 0
    for index, scene in enumerate(scenes):
        key = composition_key(scene)
        if key == previous:
            run_count += 1
        else:
            previous = key
            run_count = 1
        if run_count <= 2:
            continue

        family = str(scene.get("template_id") or "")
        material = str(scene.get("material_state") or "")
        if family in {"split-comparison", "recap-outro"}:
            scene.update(
                {
                    "template_id": "speaker-anchor",
                    "speaker_state": "speaker_punch_in",
                    "material_state": "transparent_overlay",
                    "pip_shape": "nested_card",
                    "camera": {"scale": 1.07, "x": -0.01, "y": 0.0},
                    "html_animation_behavior": "speaker_punch_in_keyword_constellation",
                }
            )
            scene.setdefault("visual", {})["display_mode"] = "keyword_only"
        elif material == "broll_fullscreen":
            alternatives = [
                ("hidden", "none"),
                ("circle_pip", "circle"),
                ("rounded_rect_pip", "rounded_rect"),
            ]
            speaker_state, pip_shape = alternatives[index % len(alternatives)]
            scene["speaker_state"] = speaker_state
            scene["pip_shape"] = pip_shape
        elif material in {"document_fullscreen", "chart_fullscreen", "evidence_fullscreen"}:
            alternatives = [
                ("hidden", "none"),
                ("circle_pip", "circle"),
                ("rounded_rect_pip", "rounded_rect"),
                ("vertical_strip", "none"),
            ]
            speaker_state, pip_shape = alternatives[index % len(alternatives)]
            scene["speaker_state"] = speaker_state
            scene["pip_shape"] = pip_shape
        else:
            scene["speaker_state"] = "speaker_punch_in" if scene.get("speaker_state") == "full" else "full"
            scene["pip_shape"] = "nested_card" if scene["speaker_state"] == "speaker_punch_in" else "none"

        notes = list(scene.get("risk_notes") or [])
        notes.append("导演门禁自动打断连续同构镜头。")
        scene["risk_notes"] = notes
        previous = composition_key(scene)
        run_count = 1


def fill_visual_timeline(scenes: list[dict[str, Any]], total_duration: float) -> None:
    if not scenes:
        return
    scenes.sort(key=lambda scene: float(scene.get("start_sec", 0)))
    scenes[0]["start_sec"] = 0.0
    for current, following in zip(scenes, scenes[1:]):
        current["end_sec"] = float(following.get("start_sec", current.get("end_sec", 0)))
        current["duration_sec"] = round(
            max(1 / 30, float(current["end_sec"]) - float(current.get("start_sec", 0))),
            3,
        )
    scenes[-1]["end_sec"] = max(float(scenes[-1].get("end_sec", 0)), total_duration)
    scenes[-1]["duration_sec"] = round(
        max(1 / 30, float(scenes[-1]["end_sec"]) - float(scenes[-1].get("start_sec", 0))),
        3,
    )


def apply_brief(plan: dict[str, Any], brief: dict[str, Any]) -> dict[str, Any]:
    output = copy.deepcopy(plan)
    output.update(
        {
            "schema_version": "dasheng.video.scene_plan.editorial_brief.v1",
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "title": brief.get("title") or output.get("title"),
            "aspect": brief.get("aspect") or "16:9",
            "fps": int(brief.get("fps") or 30),
            "width": int(brief.get("width") or 1920),
            "height": int(brief.get("height") or 1080),
            "speaker_object_position": brief.get("speaker_object_position") or "50% 50%",
            "voice_gain": float(brief.get("voice_gain") or 0.9),
            "render_mode": "production",
            "allow_placeholders": False,
            "subtitle_policy": {"render": False, "stage": "downstream_manual"},
            "editorial_brief": brief.get("id") or "inline",
            "evidence_policy": {
                "strong_evidence_requires_direct_binding": True,
                "schematic_motion_must_not_impersonate_external_evidence": True,
            },
        }
    )
    chapters = brief.get("chapters") or []
    cues = brief.get("cues") or []
    assets = {str(item["id"]): item for item in brief.get("assets") or []}
    replacements = {str(k): str(v) for k, v in (brief.get("routing_text_replacements") or {}).items()}
    default_cycle = brief.get("composition_cycle") or [{"template_id": "speaker-anchor", "display_mode": "clean"}]

    for index, scene in enumerate(output.get("scenes") or []):
        for stale_field in [
            "evidence_authenticity",
            "evidence_asset_ids",
            "evidence_assets",
            "evidence_binding",
            "evidence_refs",
        ]:
            scene.pop(stale_field, None)
        time_sec = midpoint(scene)
        chapter = interval_match(chapters, time_sec) or {
            "id": "uncategorized",
            "title": output.get("title"),
            "start_sec": 0,
            "end_sec": output.get("duration_estimate_sec") or 10**9,
        }
        scene["chapter_id"] = chapter.get("id")
        scene["narration"] = cleanup_routing_text(str(scene.get("narration") or scene.get("title") or ""), replacements)
        scene["title"] = phrase_for_scene(chapter, scene)
        cue = interval_match(cues, time_sec)
        pattern = normalize_pattern(cue or default_cycle[index % len(default_cycle)])
        scene.update(pattern)
        scene["audio"] = merge_dict(scene.get("audio") or {}, {"duck_bgm": pattern["template_id"] != "speaker-anchor"})
        scene["visual"] = default_visual(scene, chapter, cue or default_cycle[index % len(default_cycle)], index)
        scene["risk_notes"] = [
            "口播音轨必须保持单一连续根轨；分镜切换不得重启或截断人声。",
            "禁止黄线扫描、静态图片缩放冒充动画、开发占位文案。",
        ]
        if cue:
            scene["title"] = str(cue.get("title") or scene["title"])
            scene["visual"] = merge_dict(scene["visual"], cue.get("visual") or {})
            for field in ["core_claim_id", "core_claim_type", "evidence_authenticity", "evidence_binding"]:
                if field in cue:
                    scene[field] = copy.deepcopy(cue[field])
            asset_id = str(cue.get("asset_id") or "")
            if asset_id:
                asset = assets[asset_id]
                scene["visual"] = merge_dict(scene["visual"], asset_visual(asset, scene, cue))
                scene["evidence_asset_ids"] = [asset_id]
                scene["evidence_assets"] = [
                    {
                        "id": asset_id,
                        "kind": asset.get("kind"),
                        "title": asset.get("title"),
                        "path": asset.get("path") or asset.get("data_json"),
                        "source_url": asset.get("source_url"),
                    }
                ]
                scene["evidence_authenticity"] = asset.get("evidence_authenticity") or (
                    "real_data" if asset.get("kind") in {"chart", "table"} else "source_screenshot"
                )
                scene["evidence_binding"] = {
                    "claim_id": cue.get("claim_id") or scene.get("id"),
                    "claim_text": cue.get("claim_text") or scene.get("title"),
                    "relation": cue.get("relation") or "context",
                    "confidence": cue.get("confidence") or "high",
                    "source_locator": {
                        "asset_id": asset_id,
                        "url": asset.get("source_url"),
                    },
                }
        if scene["template_id"] == "speaker-anchor" and scene.get("speaker_state") == "speaker_punch_in":
            scene["camera"] = {"scale": 1.08, "x": -0.015, "y": 0.0}

        if not scene.get("evidence_authenticity") and (
            scene.get("template_id") in {"logic-flow", "split-comparison", "recap-outro"}
            or "evidence" in str(scene.get("material_state") or "")
        ):
            scene["evidence_authenticity"] = "schematic"
        elif not scene.get("evidence_authenticity") and scene.get("beat_class") in {
            "evidence_data",
            "evidence_document",
        }:
            scene["evidence_authenticity"] = "user_claim_card"

        if scene.get("speaker_state") == "vertical_strip":
            scene["speaker_object_position"] = "78% 52%"

    break_repeated_compositions(output.get("scenes") or [])
    for scene in output.get("scenes") or []:
        if scene.get("speaker_state") == "vertical_strip":
            scene["speaker_object_position"] = "78% 52%"
    fill_visual_timeline(
        output.get("scenes") or [],
        float(output.get("duration_estimate_sec") or max((scene.get("end_sec", 0) for scene in output.get("scenes") or []), default=0)),
    )

    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply an editorial director brief to a scene plan.")
    parser.add_argument("--scene-plan", required=True)
    parser.add_argument("--brief", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = Path(args.output).expanduser().resolve()
    output = apply_brief(
        read_json(Path(args.scene_plan).expanduser().resolve()),
        read_json(Path(args.brief).expanduser().resolve()),
    )
    write_json(output_path, output)
    print(
        json.dumps(
            {
                "status": "ok",
                "output": str(output_path),
                "scene_count": len(output.get("scenes") or []),
                "speaker_object_position": output.get("speaker_object_position"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
