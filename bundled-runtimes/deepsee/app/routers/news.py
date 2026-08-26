from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from ..config import settings
from fastapi import Body
from ..services.news_engine import (
    collect_news,
    engine_payload,
    list_sources as builtin_sources,
)


def direct_from_sources_json(limit: int = 50, q: str | None = None):
    return engine_payload(limit=limit, q=q)


def normalize_items(raw, **_kwargs):
    if isinstance(raw, dict) and isinstance(raw.get("items"), list):
        return raw
    if isinstance(raw, list):
        return {"items": raw}
    return {"items": []}


router = APIRouter(prefix="/api/newsfeed", tags=["newsfeed"])


@router.get("/health")
def health():
    return {"status": "ok", "engine": "builtin-trend-radar-lite"}


@router.get("/sources")
def list_sources():
    return {"success": True, "data": builtin_sources()}


@router.get("/items")
def list_items(
    keyword: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    simple: bool = True,
    finance_only: bool = True,
    whitelist_only: bool = True,
):
    payload = engine_payload(limit=limit + offset, q=keyword, source=source)
    items = payload.get("items") or []
    page = items[offset: offset + limit]
    return {
        "success": True,
        "total": len(items),
        "items": page,
        "analysis": payload.get("analysis") or {},
        "sources": payload.get("sources") or [],
        "source": payload.get("source") or {},
        "engine": payload.get("engine"),
        "upstream_ok": True,
    }


@router.get("/search")
def search(q: str, limit: int = Query(20, ge=1, le=200), finance_only: bool = True, whitelist_only: bool = True):
    return engine_payload(limit=limit, q=q)


@router.post("/refresh")
def refresh():
    return engine_payload(limit=80, force=True)


@router.get("/by-ids")
def by_ids(ids: str, limit: int = Query(200, ge=1, le=1000)):
    """Fetch normalized news items by id list.

    IDs are matched as string equality on the normalized `id` field.
    """
    if not ids:
        return {"total": 0, "items": []}
    idset = {x.strip() for x in ids.split(',') if x.strip()}
    if not idset:
        return {"total": 0, "items": []}
    payload = collect_news(limit=limit)
    items = payload.get('items') or []
    out = [it for it in items if str(it.get('id')) in idset]
    # keep input order if single id; otherwise arbitrary order is fine
    return {"total": len(out), "items": out}


@router.get("/stats")
def stats():
    payload = engine_payload(limit=120)
    return {"success": True, "data": payload.get("analysis") or {}, "engine": payload.get("engine")}


@router.post("/ai/summarize")
def summarize_news(payload: dict = Body(default={})):  # accepts JSON body { ids?:[], q?:str, limit?:int, temperature?:float }
    """生成新闻舆情监测markdown（默认使用模块提示词 newswatch）。

    - 数据来源：若提供 q 则优先 search；否则从 /api/news 拉取 limit 条
    - 输出：{ status: ok, markdown: str, used: n, model: modelName }
    """
    from ..services.llm_client import load_ai_config, DEFAULT_MODULE_PROMPTS, siliconflow_chat
    import json as _json
    req_payload = payload if isinstance(payload, dict) else {}
    ids = req_payload.get('ids')
    q = req_payload.get('q')
    try:
        limit = int(req_payload.get('limit', 50))
    except Exception:
        limit = 50
    engine_result = normalize_items(direct_from_sources_json(limit=limit, q=q))
    raw_items = engine_result.get('items') or []
    # 仅保留近72小时新闻，避免模型被陈旧信息稀释
    from time import time as _time
    now_ms = int(_time() * 1000)
    cutoff = now_ms - 72 * 3600 * 1000
    items_72h = [it for it in raw_items if int(it.get('pub_ts') or 0) >= cutoff]
    items = items_72h or raw_items
    # 若传了 ids，仅过滤保留
    if ids and isinstance(ids, list):
        idset = {str(x) for x in ids if x is not None}
        items = [it for it in items if str(it.get('id')) in idset]
    # 组装 messages_data（尽量精简以提升信噪比）
    msgs = []
    for it in items:
        msgs.append({
            'id': str(it.get('id')),
            'source': it.get('source_name') or it.get('source_id') or '',
            'title': it.get('title') or '',
            'url': it.get('url') or '',
            'time': it.get('pub_ts') or None,
        })
    # 构建提示词
    conf = load_ai_config()
    mp = (conf.get('module_prompts') or {}).get('newswatch') or DEFAULT_MODULE_PROMPTS['newswatch']
    system_prompt = mp.get('system') or DEFAULT_MODULE_PROMPTS['newswatch']['system']
    user_template = mp.get('user') or DEFAULT_MODULE_PROMPTS['newswatch']['user']
    payload_json = _json.dumps({'messages': msgs}, ensure_ascii=False)
    if '{{messages_data}}' in user_template:
        user_content = user_template.replace('{{messages_data}}', payload_json)
    else:
        user_content = user_template + "\n\n数据：\n" + payload_json
    # 调模型（温度优先用参数，其次用配置中的 model_temperature，默认 0.6）
    try:
        temp = float(req_payload.get('temperature')) if req_payload.get('temperature') is not None else None
    except Exception:
        temp = None
    if temp is None:
        try:
            temp = float(conf.get('model_temperature')) if conf.get('model_temperature') is not None else 0.6
        except Exception:
            temp = 0.6
    try:
        out = siliconflow_chat([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ], temperature=temp, route_kind="main", route_key="newswatch")
        # 希望返回 {markdown: string, quant?: object}
        md = out
        q_md = ""
        try:
            j = _json.loads(out)
            if isinstance(j, dict):
                if 'markdown' in j:
                    md = j.get('markdown') or md
                if 'quant' in j:
                    try:
                        from ..services.quant_analysis import normalize_quant, render_quant_section_markdown

                        q_norm = normalize_quant(j.get("quant") if isinstance(j.get("quant"), dict) else None)
                        q_md = render_quant_section_markdown(q_norm, module="newswatch")
                    except Exception:
                        q_md = ""
        except Exception:
            pass
        if q_md and isinstance(md, str) and md.strip():
            md = md.rstrip() + "\n\n" + q_md
        # 保存数据集到 datasets 目录
        try:
            import os, time
            ds_dir = os.path.abspath(os.path.join(os.getcwd(), 'data', 'datasets'))
            os.makedirs(ds_dir, exist_ok=True)
            fname = f"news_direct_{int(time.time())}.json"
            with open(os.path.join(ds_dir, fname), 'w', encoding='utf-8') as f:
                _json.dump({'items': items}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return {"status": "ok", "markdown": md, "used": len(msgs), "model": conf.get('model')}
    except Exception as e:
        return {"status": "error", "error": str(e), "used": len(msgs)}
