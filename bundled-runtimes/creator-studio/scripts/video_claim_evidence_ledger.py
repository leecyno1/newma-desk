#!/usr/bin/env python3
"""Build and audit a core Claim/Evidence Ledger for a video scene plan.

Micro-scenes are editing units, not independent factual claims. This module
groups them into reviewable claims before assets or renderer work starts.
"""

from __future__ import annotations

import argparse
import copy
import html
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


DIRECT_PROOF_TYPES = {"fact", "comparison", "causal", "historical"}
SPECULATIVE_TYPES = {"assumption", "forecast", "rumor", "opinion", "recommendation"}
STRONG_AUTHENTICITY = {"real_data", "source_screenshot"}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _scene_start(scene: dict[str, Any]) -> float:
    return float(scene.get("start_sec", scene.get("start", 0.0)) or 0.0)


def _scene_end(scene: dict[str, Any]) -> float:
    if scene.get("end_sec") is not None:
        return float(scene["end_sec"])
    if scene.get("end") is not None:
        return float(scene["end"])
    return _scene_start(scene) + float(scene.get("duration_sec", scene.get("duration", 0.0)) or 0.0)


def _normalize_requirements(values: list[Any]) -> list[dict[str, Any]]:
    requirements: list[dict[str, Any]] = []
    for index, value in enumerate(values):
        if isinstance(value, str):
            requirements.append({"id": f"requirement_{index + 1:02d}", "description": value, "required": True})
        elif isinstance(value, dict):
            item = dict(value)
            item.setdefault("id", f"requirement_{index + 1:02d}")
            item.setdefault("description", item["id"])
            item.setdefault("required", True)
            requirements.append(item)
    return requirements


def _evidence_items_for_scene(scene: dict[str, Any]) -> list[dict[str, Any]]:
    binding = scene.get("evidence_binding") or {}
    relation = str(binding.get("relation") or "")
    source_locator = binding.get("source_locator")
    asset_ids = [str(value) for value in scene.get("evidence_asset_ids") or [] if value]
    if not relation and not asset_ids and not source_locator:
        return []

    if not asset_ids:
        asset_ids = [""]
    return [
        {
            "scene_id": str(scene.get("id") or ""),
            "asset_id": asset_id or None,
            "relation": relation or "context",
            "verdict": str(binding.get("verdict") or ("supports" if relation == "direct" else "neutral")),
            "authenticity": str(scene.get("evidence_authenticity") or ""),
            "source_locator": source_locator,
            "confidence": str(binding.get("confidence") or ""),
            "claim_text": str(binding.get("claim_text") or scene.get("title") or scene.get("narration") or ""),
        }
        for asset_id in asset_ids
    ]


def _dedupe_evidence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in items:
        signature = json.dumps(
            {
                "asset_id": item.get("asset_id"),
                "relation": item.get("relation"),
                "source_locator": item.get("source_locator"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        if signature in seen:
            continue
        seen.add(signature)
        deduped.append(item)
    return deduped


def _has_direct_evidence(items: list[dict[str, Any]]) -> bool:
    return any(
        item.get("asset_id")
        and item.get("relation") == "direct"
        and item.get("verdict", "supports") == "supports"
        and item.get("source_locator")
        and item.get("authenticity") in STRONG_AUTHENTICITY
        for item in items
    )


def _resolve_requirements(
    requirements: list[dict[str, Any]], evidence_items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    direct_items = [
        item
        for item in evidence_items
        if item.get("relation") == "direct"
        and item.get("verdict", "supports") == "supports"
        and item.get("source_locator")
        and item.get("authenticity") in STRONG_AUTHENTICITY
    ]
    direct_asset_ids = {str(item.get("asset_id")) for item in direct_items if item.get("asset_id")}
    direct_scene_ids = {str(item.get("scene_id")) for item in direct_items if item.get("scene_id")}
    direct_locator_kinds = {
        str((item.get("source_locator") or {}).get("kind"))
        for item in direct_items
        if (item.get("source_locator") or {}).get("kind")
    }
    resolved: list[dict[str, Any]] = []
    for requirement in requirements:
        item = dict(requirement)
        asset_targets = {str(value) for value in item.get("satisfied_by_asset_ids") or [] if value}
        scene_targets = {str(value) for value in item.get("satisfied_by_scene_ids") or [] if value}
        locator_targets = {str(value) for value in item.get("satisfied_by_locator_kinds") or [] if value}
        has_explicit_matcher = bool(asset_targets or scene_targets or locator_targets)
        item["satisfied"] = (
            bool(asset_targets & direct_asset_ids)
            or bool(scene_targets & direct_scene_ids)
            or bool(locator_targets & direct_locator_kinds)
            if has_explicit_matcher
            else bool(direct_items)
        )
        resolved.append(item)
    return resolved


def _required_evidence_satisfied(requirements: list[dict[str, Any]]) -> bool:
    required = [item for item in requirements if item.get("required", True)]
    return all(item.get("satisfied") is True for item in required) if required else True


def _spoken_revision_applied(requirement: dict[str, Any], scene: dict[str, Any] | None) -> bool:
    if str(requirement.get("status") or "") == "applied":
        return True
    if not scene:
        return False
    approved = bool(scene.get("spoken_revision_approved"))
    action = str(requirement.get("action") or "replace")
    if action in {"remove", "cut", "exclude"}:
        return approved and (
            bool(scene.get("excluded_from_render"))
            or str(scene.get("render_action") or "") in {"remove", "cut", "exclude"}
        )
    if action in {"replace", "overdub", "rerecord"}:
        override = str(scene.get("narration_override") or "").strip()
        return approved and bool(override and override != str(scene.get("narration") or "").strip())
    if action == "disclose":
        return approved and bool(str(scene.get("on_screen_disclosure") or "").strip())
    return False


def _resolve_spoken_revisions(
    values: list[Any], scene_by_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    revisions: list[dict[str, Any]] = []
    for index, value in enumerate(values):
        if not isinstance(value, dict):
            continue
        item = dict(value)
        item.setdefault("id", f"spoken_revision_{index + 1:02d}")
        item.setdefault("action", "replace")
        scene_id = str(item.get("scene_id") or "")
        item["applied"] = _spoken_revision_applied(item, scene_by_id.get(scene_id))
        revisions.append(item)
    return revisions


def _evidence_status(
    claim_type: str,
    items: list[dict[str, Any]],
    requirements: list[dict[str, Any]],
) -> str:
    if claim_type in SPECULATIVE_TYPES:
        return "assumption"
    if _has_direct_evidence(items) and _required_evidence_satisfied(requirements):
        return "directly_proven"
    if any(item.get("relation") == "context" for item in items) and not _has_direct_evidence(items):
        return "context_only"
    return "missing_evidence"


def build_claim_ledger(
    scene_plan: dict[str, Any],
    claim_spec: dict[str, Any],
    *,
    source_scene_plan: str = "",
) -> dict[str, Any]:
    scenes = scene_plan.get("scenes") or scene_plan.get("segments") or []
    scene_by_id = {str(scene.get("id") or ""): scene for scene in scenes if scene.get("id")}
    claims: list[dict[str, Any]] = []

    for order, raw_claim in enumerate(claim_spec.get("claims") or [], start=1):
        scene_ids = [str(value) for value in raw_claim.get("scene_ids") or [] if value]
        known_scenes = [scene_by_id[scene_id] for scene_id in scene_ids if scene_id in scene_by_id]
        claim_level_items = []
        for raw_item in raw_claim.get("evidence_items") or []:
            if not isinstance(raw_item, dict):
                continue
            item = dict(raw_item)
            item.setdefault("scene_id", None)
            item.setdefault("asset_id", None)
            item.setdefault("relation", "context")
            item.setdefault("verdict", "supports" if item["relation"] == "direct" else "neutral")
            item.setdefault("authenticity", "")
            item.setdefault("source_locator", None)
            item.setdefault("confidence", "")
            item.setdefault("claim_text", str(raw_claim.get("claim_text") or raw_claim.get("title") or ""))
            claim_level_items.append(item)
        evidence_items = _dedupe_evidence(
            [item for scene in known_scenes for item in _evidence_items_for_scene(scene)] + claim_level_items
        )
        claim_type = str(raw_claim.get("claim_type") or "fact")
        starts = [_scene_start(scene) for scene in known_scenes]
        ends = [_scene_end(scene) for scene in known_scenes]
        requirements = _resolve_requirements(
            _normalize_requirements(list(raw_claim.get("evidence_requirements") or [])),
            evidence_items,
        )
        spoken_revisions = _resolve_spoken_revisions(
            list(raw_claim.get("spoken_revision_requirements") or []),
            scene_by_id,
        )
        status = _evidence_status(claim_type, evidence_items, requirements)
        gaps: list[str] = []
        if claim_type in DIRECT_PROOF_TYPES and status != "directly_proven":
            gaps.extend(
                item["description"]
                for item in requirements
                if item.get("required") and not item.get("satisfied")
            )
            if not gaps:
                gaps.append("缺少可直接证明该命题的真实数据、官方文件或精确网页区域。")
        if claim_type in SPECULATIVE_TYPES and not raw_claim.get("disclosure_label"):
            gaps.append("缺少画面内的观点、传闻或情景测算披露标签。")
        gaps.extend(
            str(item.get("reason") or f"分镜 {item.get('scene_id')} 的口播修订尚未应用。")
            for item in spoken_revisions
            if not item.get("applied")
        )

        claims.append(
            {
                "id": str(raw_claim.get("id") or f"claim_{order:02d}"),
                "order": order,
                "title": str(raw_claim.get("title") or raw_claim.get("claim_text") or f"命题 {order}"),
                "claim_text": str(raw_claim.get("claim_text") or raw_claim.get("title") or ""),
                "claim_type": claim_type,
                "scene_ids": scene_ids,
                "time_range": {
                    "start_sec": round(min(starts), 3) if starts else None,
                    "end_sec": round(max(ends), 3) if ends else None,
                },
                "spoken_excerpts": [
                    {
                        "scene_id": str(scene.get("id") or ""),
                        "text": str(scene.get("narration") or scene.get("title") or ""),
                    }
                    for scene in known_scenes
                ],
                "evidence_requirements": requirements,
                "evidence_items": evidence_items,
                "evidence_status": status,
                "spoken_revision_requirements": spoken_revisions,
                "disclosure_label": str(raw_claim.get("disclosure_label") or ""),
                "evidence_gaps": gaps,
                "director_note": str(raw_claim.get("director_note") or ""),
            }
        )

    target_range = claim_spec.get("target_claim_range") or {"minimum": 8, "maximum": 12}
    return {
        "schema_version": "dasheng.video.claim_evidence_ledger.v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "lane": str(scene_plan.get("lane") or "talking_head_video"),
        "source_scene_plan": source_scene_plan,
        "target_claim_range": {
            "minimum": int(target_range.get("minimum", 8)),
            "maximum": int(target_range.get("maximum", 12)),
        },
        "claims": claims,
    }


def audit_claim_ledger(ledger: dict[str, Any], scene_plan: dict[str, Any]) -> dict[str, Any]:
    scenes = scene_plan.get("scenes") or scene_plan.get("segments") or []
    scene_ids = [str(scene.get("id") or "") for scene in scenes if scene.get("id")]
    known_scene_ids = set(scene_ids)
    claims = ledger.get("claims") or []
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    claim_ids = [str(claim.get("id") or "") for claim in claims]
    duplicate_claim_ids = sorted(claim_id for claim_id, count in Counter(claim_ids).items() if claim_id and count > 1)
    if duplicate_claim_ids:
        failures.append(
            {
                "code": "duplicate_claim_id",
                "message": "核心命题 ID 必须唯一。",
                "claim_ids": duplicate_claim_ids,
            }
        )

    assignments: dict[str, list[str]] = defaultdict(list)
    for claim in claims:
        claim_id = str(claim.get("id") or "")
        for scene_id in claim.get("scene_ids") or []:
            assignments[str(scene_id)].append(claim_id)
    missing = sorted(known_scene_ids - set(assignments))
    overlap = [
        {"scene_id": scene_id, "claim_ids": claim_ids_for_scene}
        for scene_id, claim_ids_for_scene in sorted(assignments.items())
        if len(claim_ids_for_scene) > 1
    ]
    unknown = sorted(set(assignments) - known_scene_ids)
    if missing:
        failures.append(
            {
                "code": "scene_claim_assignment_missing",
                "message": "每个微分镜都必须归入一个核心命题。",
                "scene_ids": missing,
            }
        )
    if overlap:
        failures.append(
            {
                "code": "scene_claim_assignment_overlap",
                "message": "一个微分镜不能同时归入多个核心命题。",
                "scenes": overlap,
            }
        )
    if unknown:
        failures.append(
            {
                "code": "claim_assignment_unknown_scene",
                "message": "命题映射引用了 scene_plan 中不存在的分镜。",
                "scene_ids": unknown,
            }
        )

    asset_claims: dict[str, set[str]] = defaultdict(set)
    status_counts = Counter()
    pending_spoken_revision_count = 0
    for claim in claims:
        claim_id = str(claim.get("id") or "")
        claim_type = str(claim.get("claim_type") or "")
        status = str(claim.get("evidence_status") or "missing_evidence")
        status_counts[status] += 1
        items = claim.get("evidence_items") or []
        if claim_type in DIRECT_PROOF_TYPES and not (
            _has_direct_evidence(items)
            and _required_evidence_satisfied(list(claim.get("evidence_requirements") or []))
        ):
            failures.append(
                {
                    "code": "claim_not_directly_proven",
                    "message": "事实、比较、因果或历史命题必须由可定位的直接证据支持。",
                    "claim_id": claim_id,
                    "claim_type": claim_type,
                    "evidence_status": status,
                }
            )
        if claim_type in SPECULATIVE_TYPES and not str(claim.get("disclosure_label") or "").strip():
            failures.append(
                {
                    "code": "speculative_claim_missing_disclosure",
                    "message": "观点、传闻、预测和情景测算必须在画面中明确披露。",
                    "claim_id": claim_id,
                    "claim_type": claim_type,
                }
            )
        contradicting = [
            item
            for item in items
            if item.get("relation") == "direct" and item.get("verdict") == "contradicts"
        ]
        if contradicting:
            failures.append(
                {
                    "code": "claim_evidence_contradicts",
                    "message": "直接证据与核心命题方向相反，必须改写、降级或删除该命题，不能继续渲染。",
                    "claim_id": claim_id,
                    "asset_ids": sorted({str(item.get("asset_id")) for item in contradicting if item.get("asset_id")}),
                }
            )
        if not claim.get("evidence_requirements"):
            warnings.append(
                {
                    "code": "claim_evidence_requirement_missing",
                    "message": "命题未写明需要什么证据，素材搜集容易失焦。",
                    "claim_id": claim_id,
                }
            )
        pending_revisions = [
            item
            for item in claim.get("spoken_revision_requirements") or []
            if not item.get("applied")
        ]
        pending_spoken_revision_count += len(pending_revisions)
        if pending_revisions:
            failures.append(
                {
                    "code": "spoken_revision_pending",
                    "message": "被证据反驳、无法定义或过度确定的原口播必须先删除、替换或重录。",
                    "claim_id": claim_id,
                    "revisions": pending_revisions,
                }
            )
        for item in items:
            if item.get("relation") == "direct" and item.get("asset_id"):
                asset_claims[str(item["asset_id"])].add(claim_id)

    overused_assets = [
        {"asset_id": asset_id, "claim_ids": sorted(ids), "distinct_claim_count": len(ids)}
        for asset_id, ids in sorted(asset_claims.items())
        if len(ids) > 4
    ]
    if overused_assets:
        failures.append(
            {
                "code": "core_claim_evidence_asset_overused",
                "message": "同一素材不能直接证明超过四个不同核心命题。",
                "assets": overused_assets,
            }
        )

    target = ledger.get("target_claim_range") or {}
    minimum = int(target.get("minimum", 0) or 0)
    maximum = int(target.get("maximum", 0) or 0)
    if minimum and len(claims) < minimum or maximum and len(claims) > maximum:
        failures.append(
            {
                "code": "core_claim_count_out_of_range",
                "message": "核心命题数量不在导演设定范围内。",
                "actual": len(claims),
                "minimum": minimum,
                "maximum": maximum,
            }
        )

    return {
        "schema_version": "dasheng.video.claim_evidence_gate.v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": "pass" if not failures else "fail",
        "metrics": {
            "scene_count": len(scene_ids),
            "claim_count": len(claims),
            "assigned_scene_count": len(set(assignments) & known_scene_ids),
            "directly_proven_claim_count": status_counts["directly_proven"],
            "context_only_claim_count": status_counts["context_only"],
            "assumption_claim_count": status_counts["assumption"],
            "missing_evidence_claim_count": status_counts["missing_evidence"],
            "pending_spoken_revision_count": pending_spoken_revision_count,
        },
        "failures": failures,
        "warnings": warnings,
    }


def apply_claim_ids_to_scene_plan(scene_plan: dict[str, Any], ledger: dict[str, Any]) -> dict[str, Any]:
    enriched = copy.deepcopy(scene_plan)
    assignments: dict[str, list[str]] = defaultdict(list)
    for claim in ledger.get("claims") or []:
        for scene_id in claim.get("scene_ids") or []:
            assignments[str(scene_id)].append(str(claim.get("id") or ""))
    for scene in enriched.get("scenes") or enriched.get("segments") or []:
        claim_ids = assignments.get(str(scene.get("id") or ""), [])
        if len(claim_ids) == 1:
            scene["core_claim_id"] = claim_ids[0]
            if scene.get("evidence_binding"):
                binding = dict(scene["evidence_binding"])
                binding["micro_claim_id"] = str(binding.get("claim_id") or scene.get("id") or "")
                binding["claim_id"] = claim_ids[0]
                scene["evidence_binding"] = binding
        elif claim_ids:
            scene["core_claim_ids"] = claim_ids
    enriched["claim_evidence_ledger"] = {
        "schema_version": ledger.get("schema_version"),
        "claim_count": len(ledger.get("claims") or []),
        "source_scene_plan": ledger.get("source_scene_plan") or "",
    }
    return enriched


def build_review_html(ledger: dict[str, Any], scene_plan: dict[str, Any]) -> str:
    report = audit_claim_ledger(ledger, scene_plan)
    rows: list[str] = []
    for claim in ledger.get("claims") or []:
        evidence = claim.get("evidence_items") or []
        evidence_text = "<br>".join(
            html.escape(
                f"{item.get('relation')}/{item.get('verdict', 'neutral')}: {item.get('asset_id') or 'no asset'} | "
                f"{json.dumps(item.get('source_locator'), ensure_ascii=False)}"
            )
            for item in evidence
        ) or "<span class='missing'>待补</span>"
        excerpts = "<br>".join(
            html.escape(f"{item.get('scene_id')}: {item.get('text')}")
            for item in claim.get("spoken_excerpts") or []
        )
        requirements = "<br>".join(
            html.escape(str(item.get("description") or ""))
            for item in claim.get("evidence_requirements") or []
        ) or "未定义"
        revisions = "<br>".join(
            html.escape(
                f"{item.get('scene_id')} / {item.get('action')}: "
                f"{'applied' if item.get('applied') else 'pending'} | "
                f"替换为：{item.get('replacement_text') or '-'} | {item.get('reason') or ''}"
            )
            for item in claim.get("spoken_revision_requirements") or []
        ) or "-"
        disclosure = html.escape(str(claim.get("disclosure_label") or "")) or "-"
        rows.append(
            "<tr>"
            f"<td><b>{html.escape(str(claim.get('order')))}. {html.escape(str(claim.get('title')))}</b>"
            f"<div class='muted'>{html.escape(str(claim.get('id')))}</div></td>"
            f"<td><span class='type'>{html.escape(str(claim.get('claim_type')))}</span><br>"
            f"{html.escape(str(claim.get('claim_text')))}</td>"
            f"<td>{html.escape(str(claim.get('time_range')))}<div class='excerpts'>{excerpts}</div></td>"
            f"<td>{requirements}</td>"
            f"<td><span class='status {html.escape(str(claim.get('evidence_status')))}'>"
            f"{html.escape(str(claim.get('evidence_status')))}</span><br>{evidence_text}</td>"
            f"<td>{revisions}</td>"
            f"<td>{disclosure}</td>"
            "</tr>"
        )
    failures = "".join(
        f"<li><b>{html.escape(str(item.get('code')))}</b>: {html.escape(str(item.get('message')))}</li>"
        for item in report.get("failures") or []
    ) or "<li>无阻断项</li>"
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Claim / Evidence Ledger Review</title>
<style>
:root{{--ink:#172018;--paper:#f4f0e6;--line:#c8c1b2;--ok:#176b48;--warn:#a55b00;--bad:#a12b2b}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:14px/1.55 ui-sans-serif,"PingFang SC",sans-serif}}
main{{max-width:1600px;margin:auto;padding:28px}}h1{{font:700 34px/1.1 Georgia,"Songti SC",serif;margin:0 0 8px}}
.summary{{display:flex;gap:12px;flex-wrap:wrap;margin:18px 0}}.chip{{border:1px solid var(--line);background:#fff9;padding:8px 12px}}
.gate-pass{{color:var(--ok)}}.gate-fail{{color:var(--bad)}}table{{width:100%;border-collapse:collapse;background:#fff9}}
th,td{{border:1px solid var(--line);padding:10px;vertical-align:top;text-align:left}}th{{position:sticky;top:0;background:#ded7c8;z-index:1}}
.muted,.excerpts{{color:#666;font-size:12px;margin-top:6px}}.type{{font-weight:700}}.status{{display:inline-block;padding:2px 7px;border-radius:999px;background:#ddd}}
.directly_proven{{background:#d8f0e2;color:var(--ok)}}.context_only,.assumption{{background:#f5e3bd;color:var(--warn)}}.missing_evidence,.missing{{color:var(--bad)}}
</style></head><body><main>
<h1>Claim / Evidence Ledger</h1>
<div>微分镜不是独立事实。先审核核心命题，再生成素材和动画。</div>
<div class="summary"><span class="chip">命题 {len(ledger.get('claims') or [])}</span><span class="chip">分镜 {len(scene_plan.get('scenes') or [])}</span><span class="chip gate-{report['status']}">Gate: {report['status']}</span></div>
<details {'open' if report['status'] == 'fail' else ''}><summary>门禁结果</summary><ul>{failures}</ul></details>
<table><thead><tr><th>核心命题</th><th>类型 / 表述</th><th>时间与口播</th><th>证据要求</th><th>当前证据</th><th>口播修订</th><th>披露标签</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
</main></body></html>"""


def build_spoken_revision_sheet(ledger: dict[str, Any], scene_plan: dict[str, Any]) -> dict[str, Any]:
    scenes = scene_plan.get("scenes") or scene_plan.get("segments") or []
    scene_by_id = {str(scene.get("id") or ""): scene for scene in scenes if scene.get("id")}
    rows: list[dict[str, Any]] = []
    for claim in ledger.get("claims") or []:
        for requirement in claim.get("spoken_revision_requirements") or []:
            scene_id = str(requirement.get("scene_id") or "")
            scene = scene_by_id.get(scene_id) or {}
            rows.append(
                {
                    "claim_id": str(claim.get("id") or ""),
                    "claim_title": str(claim.get("title") or ""),
                    "scene_id": scene_id,
                    "start_sec": _scene_start(scene) if scene else None,
                    "end_sec": _scene_end(scene) if scene else None,
                    "action": str(requirement.get("action") or "replace"),
                    "original_text": str(scene.get("narration") or scene.get("title") or ""),
                    "replacement_text": str(requirement.get("replacement_text") or ""),
                    "reason": str(requirement.get("reason") or ""),
                    "approved": bool(scene.get("spoken_revision_approved")),
                    "applied": bool(requirement.get("applied")),
                }
            )
    return {
        "schema_version": "dasheng.video.spoken_revision_sheet.v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "pending_count": sum(not row["applied"] for row in rows),
        "rows": rows,
    }


def build_spoken_revision_html(sheet: dict[str, Any]) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(row.get('scene_id') or ''))}<br><span>{row.get('start_sec')}-{row.get('end_sec')}s</span></td>"
        f"<td>{html.escape(str(row.get('claim_title') or ''))}</td>"
        f"<td>{html.escape(str(row.get('original_text') or ''))}</td>"
        f"<td>{html.escape(str(row.get('replacement_text') or ''))}</td>"
        f"<td>{html.escape(str(row.get('reason') or ''))}</td>"
        f"<td class={'ok' if row.get('applied') else 'pending'}>{'applied' if row.get('applied') else 'pending'}</td>"
        "</tr>"
        for row in sheet.get("rows") or []
    )
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>口播修订审核表</title><style>
:root{{--paper:#f5f1e8;--ink:#172018;--line:#c8c1b2;--ok:#176b48;--warn:#a55b00}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:14px/1.55 "PingFang SC",sans-serif}}
main{{max-width:1500px;margin:auto;padding:28px}}h1{{font:700 34px/1.15 Georgia,"Songti SC",serif;margin:0 0 8px}}
table{{width:100%;border-collapse:collapse;background:#fff}}th,td{{border:1px solid var(--line);padding:10px;vertical-align:top;text-align:left}}
th{{position:sticky;top:0;background:#ddd5c6}}td span{{color:#666;font-size:12px}}.ok{{color:var(--ok);font-weight:700}}.pending{{color:var(--warn);font-weight:700}}
</style></head><body><main><h1>口播修订审核表</h1><p>待处理 {sheet.get('pending_count', 0)} 句。未应用前，渲染门禁保持关闭。</p>
<table><thead><tr><th>分镜 / 时间</th><th>核心命题</th><th>原口播</th><th>建议替换</th><th>原因</th><th>状态</th></tr></thead><tbody>{rows}</tbody></table>
</main></body></html>"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a core Claim/Evidence Ledger from a video scene plan.")
    parser.add_argument("--scene-plan", required=True)
    parser.add_argument("--claim-spec", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--allow-failing", action="store_true", help="Write review artifacts without returning a failing exit code.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scene_plan_path = Path(args.scene_plan).expanduser().resolve()
    claim_spec_path = Path(args.claim_spec).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    scene_plan = read_json(scene_plan_path)
    ledger = build_claim_ledger(scene_plan, read_json(claim_spec_path), source_scene_plan=str(scene_plan_path))
    report = audit_claim_ledger(ledger, scene_plan)
    enriched = apply_claim_ids_to_scene_plan(scene_plan, ledger)
    revision_sheet = build_spoken_revision_sheet(ledger, scene_plan)
    ledger["gate_status"] = report["status"]

    write_json(output_dir / "claim_evidence_ledger.json", ledger)
    write_json(output_dir / "claim_evidence_gate.json", report)
    write_json(output_dir / "scene_plan.claim_bound.json", enriched)
    review_path = output_dir / "claim_evidence_review.html"
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text(build_review_html(ledger, scene_plan), encoding="utf-8")
    revision_json_path = output_dir / "spoken_revision_sheet.json"
    revision_html_path = output_dir / "spoken_revision_sheet.html"
    write_json(revision_json_path, revision_sheet)
    revision_html_path.write_text(build_spoken_revision_html(revision_sheet), encoding="utf-8")

    print(
        json.dumps(
            {
                "status": report["status"],
                "claim_count": len(ledger["claims"]),
                "ledger": str(output_dir / "claim_evidence_ledger.json"),
                "gate": str(output_dir / "claim_evidence_gate.json"),
                "review": str(review_path),
                "scene_plan": str(output_dir / "scene_plan.claim_bound.json"),
                "spoken_revision_sheet": str(revision_html_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report["status"] == "pass" or args.allow_failing else 1


if __name__ == "__main__":
    raise SystemExit(main())
