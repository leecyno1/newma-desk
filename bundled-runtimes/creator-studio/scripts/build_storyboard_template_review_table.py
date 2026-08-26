#!/usr/bin/env python3
"""Build a pre-render storyboard/template review table with template previews."""

from __future__ import annotations

import argparse
import html
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PREVIEW_ROOTS = [
    Path(os.environ.get("HTML_VIDEO_ROOT", str(PROJECT_ROOT / "vendor/reserved/render/html-video"))).expanduser() / "templates",
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def scene_template(scene: dict[str, Any]) -> str:
    return str(scene.get("template_id") or scene.get("template") or scene.get("templateId") or "")


def scene_index(scene: dict[str, Any], fallback: int) -> Any:
    return scene.get("index") or scene.get("scene_index") or scene.get("sceneNo") or fallback


def scene_time(scene: dict[str, Any]) -> str:
    if "start_sec" in scene and "end_sec" in scene:
        return f"{float(scene['start_sec']):.1f}-{float(scene['end_sec']):.1f}s"
    if "startSec" in scene and "endSec" in scene:
        return f"{float(scene['startSec']):.1f}-{float(scene['endSec']):.1f}s"
    if "duration_sec" in scene:
        return f"{float(scene['duration_sec']):.1f}s"
    if "durationSec" in scene:
        return f"{float(scene['durationSec']):.1f}s"
    return ""


def scene_voice(scene: dict[str, Any]) -> str:
    return str(scene.get("voiceover_text") or scene.get("voiceover") or scene.get("narration") or scene.get("caption") or "")


def scene_title(scene: dict[str, Any]) -> str:
    return str(scene.get("title") or scene.get("scene_title") or scene.get("id") or scene.get("scene_id") or "")


def scene_evidence(scene: dict[str, Any]) -> str:
    refs = scene.get("evidence_refs") or scene.get("evidenceRefs") or scene.get("original_refs") or []
    if isinstance(refs, list):
        return ", ".join(str(item.get("asset_refs") or item) if isinstance(item, dict) else str(item) for item in refs)
    return str(refs)


def scene_risks(scene: dict[str, Any]) -> str:
    risks = scene.get("qc_notes") or scene.get("qcNotes") or scene.get("risk_notes") or []
    if isinstance(risks, list):
        return "；".join(str(item) for item in risks)
    return str(risks)


def scene_tool_routing(scene: dict[str, Any]) -> str:
    routing = scene.get("tool_routing") or {}
    primary = [str(item.get("name") or item.get("id") or "") for item in routing.get("primary_stack") or []]
    fallback = [str(item.get("name") or item.get("id") or "") for item in routing.get("fallback_stack") or []]
    unresolved = [str(item) for item in routing.get("unresolved_capabilities") or []]
    if not primary and not fallback and not unresolved:
        return "未生成路由"
    parts = []
    if primary:
        parts.append("主：" + "、".join(primary))
    if fallback:
        parts.append("备：" + "、".join(fallback[:5]))
    if unresolved:
        parts.append("缺：" + "、".join(unresolved))
    return "；".join(parts)


def scene_id(scene: dict[str, Any], fallback: int) -> str:
    return str(scene.get("scene_id") or scene.get("id") or f"scene_{fallback:03d}")


def editable_input(field: str, value: Any, *, label: str | None = None) -> str:
    label_html = f'<span class="field-label">{esc(label)}</span>' if label else ""
    return (
        '<div class="edit-stack">'
        f"{label_html}"
        f'<input class="editable-field" data-field="{esc(field)}" type="text" value="{esc(value)}">'
        "</div>"
    )


def editable_textarea(
    field: str,
    value: Any,
    *,
    label: str | None = None,
    rows: int = 3,
    kind: str = "text",
) -> str:
    label_html = f'<span class="field-label">{esc(label)}</span>' if label else ""
    return (
        '<div class="edit-stack">'
        f"{label_html}"
        f'<textarea class="editable-field" data-field="{esc(field)}" data-kind="{esc(kind)}" rows="{rows}">{esc(value)}</textarea>'
        "</div>"
    )


def editable_list(field: str, values: Any, *, label: str, rows: int = 3) -> str:
    if isinstance(values, list):
        text = "\n".join(str(item) for item in values)
    else:
        text = str(values or "")
    return editable_textarea(field, text, label=label, rows=rows, kind="list")


def template_preview_path(template_id: str, roots: list[Path]) -> Path | None:
    if not template_id:
        return None
    candidates: list[Path] = []
    for root in roots:
        candidates.extend(
            [
                root / template_id / "preview.png",
                root / template_id / "preview.jpg",
                root / template_id / "preview.webp",
                root / template_id / "assets" / "screenshot-1.png",
                root / f"{template_id}.png",
                root / f"{template_id}.jpg",
                root / f"{template_id}.webp",
            ]
        )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def template_preview_cell(template_id: str, roots: list[Path]) -> str:
    preview = template_preview_path(template_id, roots)
    if preview:
        return f'<img class="template-shot" src="{preview.resolve().as_uri()}" alt="{esc(template_id)}">'
    return (
        '<div class="missing-shot">'
        '<b>暂无模板截图</b>'
        f"<code>{esc(template_id)}</code>"
        '<small>应补：templates/&lt;id&gt;/preview.png 或 template_previews/&lt;id&gt;.png</small>'
        "</div>"
    )


def review_controls_cell(scene_identifier: str, template_id: str, *, narrative: bool = False) -> str:
    if narrative:
        return f"""
      <div class="decision-box" data-for="{esc(scene_identifier)}">
        <label><input type="radio" name="decision-{esc(scene_identifier)}" value="approved"> 通过</label>
        <label><input type="radio" name="decision-{esc(scene_identifier)}" value="edit_content"> 改内容</label>
        <label><input type="radio" name="decision-{esc(scene_identifier)}" value="delete"> 删除本段</label>
        <textarea class="review-note" rows="3" placeholder="口吻、论证、证据或留存修改点"></textarea>
      </div>
    """
    return f"""
      <div class="decision-box" data-for="{esc(scene_identifier)}">
        <label><input type="radio" name="decision-{esc(scene_identifier)}" value="approved"> 通过</label>
        <label><input type="radio" name="decision-{esc(scene_identifier)}" value="change_template"> 换模板</label>
        <label><input type="radio" name="decision-{esc(scene_identifier)}" value="edit_content"> 改内容</label>
        <label><input type="radio" name="decision-{esc(scene_identifier)}" value="delete"> 删</label>
        <input class="template-override" type="text" placeholder="替换模板 ID" value="{esc(template_id)}">
        <textarea class="review-note" rows="2" placeholder="审核意见 / 修改点"></textarea>
      </div>
    """


def review_page_script(
    scenes_payload: list[dict[str, Any]],
    storyboard: dict[str, Any],
    source_storyboard: Path | None,
    *,
    approved_label: str = "可进入素材生成",
) -> str:
    payload = json.dumps(scenes_payload, ensure_ascii=False)
    storyboard_payload = json.dumps(storyboard, ensure_ascii=False)
    source = str(source_storyboard.resolve()) if source_storyboard else ""
    return f"""
  <script>
    const REVIEW_SCENES = {payload};
    const STORYBOARD_PAYLOAD = {storyboard_payload};
    const SOURCE_STORYBOARD = {json.dumps(source, ensure_ascii=False)};
    const APPROVED_LABEL = {json.dumps(approved_label, ensure_ascii=False)};
    const STORAGE_KEY = 'dasheng_storyboard_review:' + (SOURCE_STORYBOARD || location.pathname);

    function sceneRow(sceneId) {{
      return document.querySelector(`[data-scene-id="${{CSS.escape(sceneId)}}"]`);
    }}

    function collectSceneEdits(scene) {{
      const row = sceneRow(scene.scene_id);
      const edits = {{}};
      row?.querySelectorAll('.editable-field[data-field]').forEach(field => {{
        const key = field.dataset.field;
        const raw = String(field.value || '').trim();
        edits[key] = field.dataset.kind === 'list'
          ? raw.split(/\\n+/).map(item => item.trim()).filter(Boolean)
          : raw;
      }});
      return edits;
    }}

    function getSceneDecision(scene) {{
      const row = sceneRow(scene.scene_id);
      const selected = row?.querySelector(`input[name="decision-${{CSS.escape(scene.scene_id)}}"]:checked`);
      const override = row?.querySelector('.template-override')?.value?.trim() || scene.template_id;
      const notes = row?.querySelector('.review-note')?.value?.trim() || '';
      const decision = selected?.value || 'pending';
      const edits = collectSceneEdits(scene);
      return {{
        scene_id: scene.scene_id,
        index: scene.index,
        title: edits.title || scene.title,
        template_id: scene.template_id,
        decision,
        approved: decision === 'approved',
        template_override: override,
        notes,
        edits
      }};
    }}

    function buildDecisionPayload() {{
      const decisions = REVIEW_SCENES.map(getSceneDecision);
      const approved = decisions.filter(item => item.decision === 'approved').length;
      const pending = decisions.filter(item => item.decision === 'pending').length;
      const blockers = decisions.filter(item => item.decision !== 'approved');
      return {{
        schema_version: 'dasheng.storyboard_review_decision.v1',
        created_at: new Date().toISOString(),
        source_storyboard: SOURCE_STORYBOARD,
        status: blockers.length === 0 ? 'approved' : 'changes_requested',
        scene_count: decisions.length,
        approved_count: approved,
        pending_count: pending,
        blocker_count: blockers.length,
        decisions
      }};
    }}

    function buildUpdatedStoryboard() {{
      const decisionPayload = buildDecisionPayload();
      const storyboard = JSON.parse(JSON.stringify(STORYBOARD_PAYLOAD));
      const decisions = new Map(decisionPayload.decisions.map(item => [item.scene_id, item]));
      const scenes = storyboard.scenes || storyboard.timeline || [];
      for (const scene of scenes) {{
        const identifier = String(scene.scene_id || scene.id || '');
        const item = decisions.get(identifier);
        if (!item) continue;
        Object.assign(scene, item.edits || {{}});
        if (item.template_override) scene.template_id = item.template_override;
        scene.review = {{decision: item.decision, notes: item.notes}};
        if (item.decision === 'delete') scene.enabled = false;
      }}
      storyboard.updated_at = new Date().toISOString();
      storyboard.status = decisionPayload.status;
      storyboard.review_summary = {{
        approved_count: decisionPayload.approved_count,
        pending_count: decisionPayload.pending_count,
        blocker_count: decisionPayload.blocker_count
      }};
      return storyboard;
    }}

    function updateSummary() {{
      const payload = buildDecisionPayload();
      document.querySelector('#approvedCount').textContent = payload.approved_count;
      document.querySelector('#pendingCount').textContent = payload.pending_count;
      document.querySelector('#blockerCount').textContent = payload.blocker_count;
      document.querySelector('#gateStatus').textContent = payload.status === 'approved' ? APPROVED_LABEL : '仍需修改';
      document.querySelector('#gateStatus').className = payload.status === 'approved' ? 'ok' : 'warn';
    }}

    function markDirty() {{
      const state = document.querySelector('#saveState');
      state.textContent = '有未保存修改';
      state.className = 'save-state warn';
    }}

    function saveChanges() {{
      const savedAt = new Date().toISOString();
      localStorage.setItem(STORAGE_KEY, JSON.stringify({{
        schema_version: 'dasheng.storyboard_review_bundle.v1',
        saved_at: savedAt,
        decision: buildDecisionPayload(),
        storyboard: buildUpdatedStoryboard()
      }}));
      const state = document.querySelector('#saveState');
      state.textContent = '已保存 ' + new Date(savedAt).toLocaleTimeString();
      state.className = 'save-state ok';
    }}

    function restoreFromStorage() {{
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      try {{
        const payload = JSON.parse(raw);
        applyDecisionPayload(payload.decision || payload);
        const state = document.querySelector('#saveState');
        state.textContent = '已恢复上次保存';
        state.className = 'save-state ok';
      }} catch (err) {{
        console.warn('review restore failed', err);
      }}
    }}

    function applyDecisionPayload(payload) {{
      const byScene = new Map((payload.decisions || []).map(item => [item.scene_id, item]));
      for (const scene of REVIEW_SCENES) {{
        const item = byScene.get(scene.scene_id);
        if (!item) continue;
        const row = sceneRow(scene.scene_id);
        const radio = row?.querySelector(`input[name="decision-${{CSS.escape(scene.scene_id)}}"][value="${{CSS.escape(item.decision || 'pending')}}"]`);
        if (radio) radio.checked = true;
        const override = row?.querySelector('.template-override');
        if (override && item.template_override) override.value = item.template_override;
        const note = row?.querySelector('.review-note');
        if (note && item.notes) note.value = item.notes;
        for (const [field, value] of Object.entries(item.edits || {{}})) {{
          const control = row?.querySelector(`.editable-field[data-field="${{CSS.escape(field)}}"]`);
          if (!control) continue;
          control.value = Array.isArray(value) ? value.join('\\n') : String(value ?? '');
        }}
      }}
      updateSummary();
    }}

    function downloadJson(payload, filename) {{
      const blob = new Blob([JSON.stringify(payload, null, 2) + '\\n'], {{type: 'application/json'}});
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      a.click();
      URL.revokeObjectURL(a.href);
    }}

    function downloadDecision() {{
      downloadJson(buildDecisionPayload(), 'storyboard_review_decision.json');
    }}

    function downloadStoryboard() {{
      downloadJson(buildUpdatedStoryboard(), 'storyboard.updated.json');
    }}

    async function copyDecision() {{
      const text = JSON.stringify(buildDecisionPayload(), null, 2);
      await navigator.clipboard.writeText(text);
      alert('已复制审核 JSON');
    }}

    function markAllApproved() {{
      for (const scene of REVIEW_SCENES) {{
        const radio = document.querySelector(`input[name="decision-${{CSS.escape(scene.scene_id)}}"][value="approved"]`);
        if (radio) radio.checked = true;
      }}
      updateSummary();
      markDirty();
    }}

    function importDecision(file) {{
      const reader = new FileReader();
      reader.onload = () => {{
        const payload = JSON.parse(String(reader.result || '{{}}'));
        applyDecisionPayload(payload.decision || payload);
        markDirty();
      }};
      reader.readAsText(file);
    }}

    document.addEventListener('change', () => {{ updateSummary(); markDirty(); }});
    document.addEventListener('input', () => {{ updateSummary(); markDirty(); }});
    document.querySelector('#saveChanges').addEventListener('click', saveChanges);
    document.querySelector('#exportStoryboard').addEventListener('click', downloadStoryboard);
    document.querySelector('#exportDecision').addEventListener('click', downloadDecision);
    document.querySelector('#copyDecision').addEventListener('click', copyDecision);
    document.querySelector('#markAllApproved').addEventListener('click', markAllApproved);
    document.querySelector('#importDecision').addEventListener('change', event => {{
      const file = event.target.files?.[0];
      if (file) importDecision(file);
    }});
    restoreFromStorage();
    updateSummary();
  </script>
"""


def build_html(storyboard: dict[str, Any], *, output: Path, preview_roots: list[Path], source_storyboard: Path | None = None) -> str:
    scenes = storyboard.get("scenes") or storyboard.get("timeline") or []
    title = storyboard.get("title") or storyboard.get("name") or "视频分镜模板审核表"
    narrative = storyboard.get("review_mode") == "narrative"
    rows = []
    scene_payload = []
    for fallback, scene in enumerate(scenes, 1):
        template_id = scene_template(scene)
        identifier = scene_id(scene, fallback)
        index = scene_index(scene, fallback)
        core = scene.get("core_meaning_lock") or scene.get("subtitle") or scene.get("summary") or ""
        visual = scene.get("visual_intent") or scene.get("templateReason") or scene.get("shot_type") or ""
        motion = scene.get("motion") or {}
        if isinstance(motion, dict):
            motion_text = " → ".join(str(motion.get(key) or "") for key in ["entrance", "focus_change", "exit"]).strip(" →")
        else:
            motion_text = str(motion or "")
        scene_payload.append(
            {
                "scene_id": identifier,
                "index": index,
                "title": scene_title(scene),
                "template_id": template_id,
            }
        )
        if narrative:
            coverage = "、".join(map(str, [*(scene.get("core_claim_refs") or []), *(scene.get("evidence_refs") or [])]))
            rows.append(
                f'<tr data-scene-id="{esc(identifier)}">'
                f"<td class=\"num\">{esc(index)}</td>"
                f"<td class=\"time\">{esc(scene_time(scene))}</td>"
                f"<td><b>{esc(scene.get('narrative_function') or scene.get('beat_class') or '')}</b>{editable_input('title', scene_title(scene), label='镜头标题')}</td>"
                f"<td>{editable_textarea('narration', scene_voice(scene), label='完整口播', rows=7)}</td>"
                f"<td>{esc(coverage)}</td>"
                f"<td>{editable_textarea('main_visual', scene.get('main_visual') or visual, label='主画面', rows=5)}{editable_list('real_insert_plan', scene.get('real_insert_plan') or [], label='真实素材', rows=3)}</td>"
                f"<td>{editable_textarea('emphasis_text', scene.get('emphasis_text') or '', label='重点花字', rows=2)}{editable_list('entity_labels', scene.get('entity_labels') or [], label='人物/机构标签', rows=3)}</td>"
                f"<td>{editable_list('interaction_or_retention', scene.get('interaction_or_retention') or [], label='互动/留存', rows=3)}</td>"
                f"<td>{editable_list('risk_notes', scene.get('risk_notes') or [], label='风险说明', rows=3)}</td>"
                f'<td class="decision">{review_controls_cell(identifier, template_id, narrative=True)}</td>'
                "</tr>"
            )
        else:
            rows.append(
                f'<tr data-scene-id="{esc(identifier)}">'
                f"<td class=\"num\">{esc(index)}</td>"
                f"<td class=\"time\">{esc(scene_time(scene))}</td>"
                f"<td>{template_preview_cell(template_id, preview_roots)}</td>"
                f"<td><code>{esc(template_id)}</code><br><small>{esc(scene.get('content_part') or scene.get('visualFamily') or scene.get('beat_class') or '')}</small></td>"
                f"<td>{editable_input('title', scene_title(scene), label='镜头标题')}{editable_textarea('narration', scene_voice(scene), label='完整口播', rows=6)}</td>"
                f"<td>{editable_textarea('core_meaning_lock', core, label='核心结论', rows=3)}{editable_textarea('visual_intent', visual, label='画面设计', rows=4)}<small>{esc(motion_text)}</small></td>"
                f"<td>{editable_list('evidence_refs', scene.get('evidence_refs') or [], label='证据引用', rows=4)}</td>"
                f"<td class=\"routing\">{esc(scene_tool_routing(scene))}</td>"
                f"<td>{editable_list('risk_notes', scene.get('risk_notes') or [], label='风险说明', rows=4)}</td>"
                f'<td class="decision">{review_controls_cell(identifier, template_id)}</td>'
                "</tr>"
            )

    page_label = "叙事分镜审核表" if narrative else "分镜模板审核表"
    page_note = (
        "先确认完整口播、论点、证据、画面方向、花字和留存，再拆生产镜并生成视觉资产。"
        if narrative
        else "先确认每个分镜的模板、口播、证据和风险，再进入配音、素材生成、渲染。"
    )
    table_head = (
        "<tr><th>#</th><th>时间</th><th>叙事作用</th><th>完整口播</th><th>观点/证据</th><th>主画面/真实素材</th><th>花字/标签</th><th>互动/留存</th><th>风险点</th><th>审核</th></tr>"
        if narrative
        else "<tr><th>#</th><th>时间</th><th>模板截图</th><th>模板/类型</th><th>分镜与口播</th><th>核心/画面/动效</th><th>证据资产</th><th>工具路由</th><th>风险点</th><th>审核</th></tr>"
    )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)} · {page_label}</title>
  <style>
    :root {{
      --bg:#08111f; --panel:#101d30; --line:rgba(215,168,79,.24);
      --text:#edf2f7; --muted:#9fb2ca; --gold:#d7a84f; --red:#c45b4b;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; padding:28px; background:linear-gradient(135deg,#050912,var(--bg)); color:var(--text); font-family:"PingFang SC","Noto Sans CJK SC",sans-serif; }}
    header {{ margin:0 auto 20px; max-width:1680px; }}
    h1 {{ margin:0 0 8px; font-size:34px; }}
    .note {{ color:var(--muted); line-height:1.7; }}
    .toolbar {{ width:min(1680px,100%); margin:18px auto; padding:14px; border:1px solid var(--line); border-radius:16px; background:rgba(16,29,48,.88); display:flex; gap:10px; align-items:center; flex-wrap:wrap; }}
    .toolbar b {{ color:var(--gold); }}
    button, .file-label {{ border:1px solid var(--line); background:#142842; color:var(--text); border-radius:999px; padding:8px 13px; cursor:pointer; font:inherit; }}
    button:hover, .file-label:hover {{ background:#1d3656; }}
    .file-label input {{ display:none; }}
    .ok {{ color:#7ee2a8; font-weight:800; }}
    .warn {{ color:#f1b66d; font-weight:800; }}
    table {{ width:min(1680px,100%); margin:auto; border-collapse:separate; border-spacing:0; background:rgba(16,29,48,.94); border:1px solid var(--line); border-radius:18px; overflow:hidden; }}
    th, td {{ border-bottom:1px solid rgba(255,255,255,.08); padding:10px 12px; vertical-align:top; text-align:left; font-size:13px; }}
    th {{ position:sticky; top:0; z-index:2; color:var(--gold); background:#10243a; }}
    td p {{ margin:6px 0 0; color:#fff5dc; line-height:1.55; }}
    small {{ color:var(--muted); line-height:1.45; display:inline-block; margin-top:4px; }}
    code {{ color:#ffe6a3; font-family:Menlo,monospace; white-space:normal; word-break:break-all; }}
    .num {{ color:var(--gold); font-weight:800; font-size:18px; }}
    .time {{ color:var(--muted); white-space:nowrap; }}
    .template-shot {{ width:170px; height:96px; object-fit:cover; border-radius:12px; border:1px solid var(--line); background:#000; display:block; }}
    .missing-shot {{ width:170px; min-height:96px; border:1px dashed rgba(215,168,79,.45); border-radius:12px; padding:10px; color:var(--muted); background:rgba(0,0,0,.18); }}
    .missing-shot b {{ display:block; color:var(--red); margin-bottom:4px; }}
    .decision {{ min-width:180px; color:#fff4d6; line-height:1.8; }}
    .decision-box label {{ display:block; white-space:nowrap; }}
    .template-override, .review-note, .editable-field {{ width:100%; margin-top:6px; border:1px solid rgba(215,168,79,.28); border-radius:10px; background:#091423; color:var(--text); padding:8px; font:inherit; line-height:1.5; }}
    textarea.editable-field, .review-note {{ resize:vertical; }}
    .review-note {{ min-height:54px; }}
    .edit-stack + .edit-stack {{ margin-top:9px; }}
    .field-label {{ display:block; color:var(--gold); font-size:11px; font-weight:700; margin-top:4px; }}
    .primary {{ background:var(--gold); color:#15100a; border-color:var(--gold); font-weight:800; }}
    .primary:hover {{ background:#edc46e; }}
    .save-state {{ margin-left:auto; }}
    @media (max-width: 980px) {{ body{{padding:12px}} th,td{{font-size:12px;padding:8px}} .template-shot,.missing-shot{{width:120px;height:72px}} }}
  </style>
</head>
<body>
  <header>
    <h1>{esc(title)} · {page_label}</h1>
    <div class="note">生成时间：{esc(datetime.now().astimezone().isoformat(timespec="seconds"))}。这是视频生成前的审核门禁表：{page_note}</div>
  </header>
  <section class="toolbar">
    <b>审核门禁：</b><span id="gateStatus" class="warn">仍需修改</span>
    <span>通过 <b id="approvedCount">0</b></span>
    <span>待审 <b id="pendingCount">0</b></span>
    <span>阻塞 <b id="blockerCount">0</b></span>
    <button id="saveChanges" class="primary" type="button">保存修改</button>
    <button id="exportStoryboard" type="button">导出修改后分镜</button>
    <button id="markAllApproved" type="button">全部标记通过</button>
    <button id="exportDecision" type="button">导出 storyboard_review_decision.json</button>
    <button id="copyDecision" type="button">复制 JSON</button>
    <label class="file-label">导入 JSON<input id="importDecision" type="file" accept="application/json"></label>
    <span id="saveState" class="save-state">尚未保存</span>
  </section>
  <table>
    <thead>
      {table_head}
    </thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
  {review_page_script(scene_payload, storyboard, source_storyboard, approved_label="可拆生产镜" if narrative else "可进入素材生成")}
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build storyboard/template pre-render review HTML.")
    parser.add_argument("--storyboard", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--template-preview-root", action="append", default=[])
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    storyboard_path = Path(args.storyboard).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    preview_roots = [Path(item).expanduser().resolve() for item in args.template_preview_root] + DEFAULT_PREVIEW_ROOTS
    html_doc = build_html(load_json(storyboard_path), output=output, preview_roots=preview_roots, source_storyboard=storyboard_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html_doc, encoding="utf-8")
    print(json.dumps({"status": "ok", "output": str(output), "previewRoots": [str(p) for p in preview_roots]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
