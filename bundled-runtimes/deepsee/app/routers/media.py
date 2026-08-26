from __future__ import annotations

import json
import requests
from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.responses import FileResponse
from typing import Any

from ..config import settings
from ..db import SessionLocal
from sqlalchemy.orm import Session
from ..models import SyncState
from ..services.media_store import (
    list_media_items,
    list_media_meeting_records,
    resolve_media_meeting_audio_path,
)
from ..services.media_collector_store import list_all_items as list_collector_items, get_collector_status
from ..services.external_content_summaries import overlay_cached_summaries, summarize_external_items


router = APIRouter(prefix="/api/media", tags=["media"])

MEDIA_KEEP_EVENT_TERMS = (
    "时政", "政治", "政策", "新政", "监管", "财政", "央行", "国务院", "发改委", "工信部", "商务部", "证监会", "金融监管",
    "中央", "任命", "人事", "国家行政学院",
    "外交", "制裁", "关税", "贸易战", "地缘", "冲突", "战争", "军事", "军工", "导弹", "袭击", "停火",
    "俄乌", "中东", "以色列", "伊朗", "美国", "欧洲", "日本", "韩国", "台海", "大选", "选举", "峰会", "谈判",
    "通胀", "降息", "加息", "美联储", "汇率", "利率", "国债", "原油", "黄金", "能源", "粮食", "供应链",
    "投研", "投资", "研报", "策略", "宏观", "行业", "产业", "市场", "资本市场", "金融", "楼市", "房地产", "A股", "港股", "美股",
    "债券", "固收", "基金", "ETF", "股票", "个股", "上市公司", "财报", "业绩", "估值", "并购", "重组", "回购",
    "分红", "融资", "IPO", "北向", "资金流", "量化", "期货", "期权", "商品", "半导体", "芯片", "算力", "AI",
    "机器人", "新能源", "光伏", "储能", "电池", "汽车", "医药", "创新药", "地产", "银行", "券商", "保险",
)
MEDIA_NOISE_DROP_TERMS = (
    "明星", "娱乐", "综艺", "短剧", "电视剧", "电影", "演唱会", "八卦", "粉丝", "网红", "恋情", "离婚", "结婚",
    "婚礼", "直播间", "带货", "抽奖", "中奖", "福利", "红包", "优惠", "折扣", "秒杀", "团购", "下单", "购买",
    "购物", "快递", "包裹", "签收", "礼品", "优惠券", "美食", "探店", "餐厅", "菜谱", "旅游", "酒店", "民宿",
    "机票", "出行", "高铁", "宠物", "萌宠", "穿搭", "护肤", "美妆", "彩妆", "减肥", "瘦身", "养生",
    "育儿", "亲子", "婚恋", "星座", "情感", "心理学", "家装", "装修", "租房", "招聘", "求职", "二手",
    "闲置", "游戏", "小说", "校园", "考试", "放假", "节日", "端午", "天气", "奇闻", "搞笑", "段子", "热梗",
    "吃瓜", "社会新闻", "民生", "小区", "邻里", "物业", "交通事故", "车祸", "走失", "寻人", "纠纷", "投诉",
    "争议", "施救", "卡喉", "赤裸", "体育", "足球", "比赛", "不赢球", "葡萄牙", "中国队", "劫案", "被抢", "盗窃", "抢劫",
    "活动报名", "课程报名", "训练营", "招生", "扫码", "二维码", "加微信", "客服",
)
MEDIA_HARD_NOISE_TERMS = (
    "周星驰", "食神大片", "用AI打开端午", "端午的一百种方式", "AI食神", "明星官宣", "恋情", "八卦", "吃瓜",
)


def _media_item_text(item: dict) -> str:
    return " ".join(
        str(item.get(key) or "").strip()
        for key in ("platform", "author", "task_source", "source_keyword", "keyword", "title", "summary", "description", "url")
        if str(item.get(key) or "").strip()
    )


def _is_high_value_media_event(item: dict) -> bool:
    text = _media_item_text(item)
    return any(term in text for term in MEDIA_KEEP_EVENT_TERMS)


def _is_low_value_media_noise(item: dict) -> bool:
    text = _media_item_text(item)
    if not text:
        return False
    if any(term in text for term in MEDIA_HARD_NOISE_TERMS):
        return True
    platform = str(item.get("platform") or "").lower()
    source_type = str(item.get("source_type") or "").lower()
    title = str(item.get("title") or "").strip()
    if title and len(title) <= 8 and not _is_high_value_media_event(item):
        return True
    if platform in {"baidu", "weibo", "douyin"} and source_type == "hot" and not _is_high_value_media_event(item):
        return True
    if any(term in text for term in MEDIA_NOISE_DROP_TERMS):
        return not _is_high_value_media_event(item)
    return False


def _filter_low_value_media_items(items: list[dict]) -> tuple[list[dict], int]:
    filtered = [item for item in items if not _is_low_value_media_noise(item)]
    return filtered, max(0, len(items) - len(filtered))


def _collector_has_local_data(status: dict[str, Any]) -> bool:
    for key in ("hot", "search", "authors"):
        section = status.get(key) if isinstance(status.get(key), dict) else {}
        if section.get("latest_day") or section.get("latest_files") or section.get("keywords_count") or section.get("authors_count"):
            return True
    return False


def _summarize_bootstrap_result(result: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    summary: dict[str, Any] = {
        "ok": bool(result.get("ok")),
        "running": bool(result.get("running")),
        "message": result.get("message") or "",
        "tasks": result.get("tasks") or [],
        "started_at": result.get("started_at") or "",
        "finished_at": result.get("finished_at") or "",
    }
    results = result.get("results")
    if isinstance(results, list):
        summary["results"] = [
            {
                "name": item.get("name"),
                "ok": bool(item.get("ok")),
                "returncode": item.get("returncode"),
                "error": item.get("error") or "",
            }
            for item in results
            if isinstance(item, dict)
        ]
    return summary


def _maybe_bootstrap_media_collector(q: str | None) -> dict[str, Any] | None:
    if (q or "").strip():
        return None
    if not bool(settings.__dict__.get("MEDIA_COLLECTOR_AUTO_BOOTSTRAP", True)):
        return None

    status = get_collector_status()
    if _collector_has_local_data(status):
        return None

    from ..services.media_collector_runner import get_media_collector_run_state, run_media_collector_once

    run_state = get_media_collector_run_state()
    if bool(run_state.get("running")):
        return {
            "ok": False,
            "running": True,
            "message": "自媒体默认源正在初始化",
            "status": run_state.get("status") or status,
        }
    if run_state.get("last_run"):
        return {
            "ok": False,
            "skipped": True,
            "reason": "collector_already_attempted",
            "message": "已尝试初始化默认自媒体源，可在设置页手动刷新",
            "status": run_state.get("status") or status,
        }

    timeout = settings.__dict__.get("MEDIA_COLLECTOR_BOOTSTRAP_TIMEOUT_SECONDS", 60)
    return run_media_collector_once(
        hot=True,
        search=False,
        authors=False,
        timeout_seconds=timeout,
    )


def _default_collector_source_paths() -> dict[str, str]:
    root = _repo_root()
    collector_dir = root / "media-collector"
    return {
        "keywords": str(collector_dir / "keywords.json"),
        "authors": str(collector_dir / "authors.json"),
    }


def _repo_root():
    from pathlib import Path
    return Path(__file__).resolve().parent.parent.parent


def _adapt_collector_items(
    items: list[dict],
    *,
    limit: int,
    filter_noise: bool,
) -> tuple[list[dict], int]:
    adapted = []
    for it in items[:limit]:
        stats = it.get("stats") if isinstance(it.get("stats"), dict) else {}
        extra = stats.get("extra") if isinstance(stats.get("extra"), dict) else {}
        heat = it.get("heat") or stats.get("heat") or 0
        adapted.append({
            **it,
            "summary": it.get("description") or it.get("title") or "",
            "task_source": it.get("keyword") or it.get("source_file") or it.get("source_type") or "",
            "source_keyword": it.get("keyword") or "",
            "transcript_status": it.get("source_type") or "collector",
            "stats": {
                **stats,
                "like": extra.get("like") or extra.get("view") or extra.get("views") or heat or stats.get("rank") or 0,
                "comment": extra.get("comment") or extra.get("comments") or 0,
                "share": extra.get("share") or extra.get("shares") or 0,
                "collect": extra.get("collect") or extra.get("favorite") or extra.get("favorites") or 0,
            },
        })
    if filter_noise:
        return _filter_low_value_media_items(adapted)
    return adapted, 0


def _collector_response(
    items: list[dict],
    *,
    limit: int,
    filter_noise: bool,
    bootstrap: dict[str, Any] | None = None,
) -> dict[str, Any]:
    status = get_collector_status()
    adapted, removed_count = _adapt_collector_items(items, limit=limit, filter_noise=filter_noise)
    return {
        "items": adapted,
        "total": len(adapted),
        "source": {
            "kind": "media-collector",
            "latest_day": status.get("hot", {}).get("latest_day") or status.get("search", {}).get("latest_day"),
            "latest_files": status.get("hot", {}).get("latest_files", []),
            "project_dir": str(_repo_root()),
            "results_dir": str(status.get("data_dir") or ""),
            "noise_filtered": removed_count,
            "filter_mode": "major_event_keep",
            "default_sources": _default_collector_source_paths(),
            "bootstrap": _summarize_bootstrap_result(bootstrap),
        },
    }

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _get_media_config(db: Session) -> dict:
    row = db.get(SyncState, "media_config")
    if not row or not row.value:
        return {}
    try:
        data = json.loads(row.value)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _media_server_base() -> str:
    base = (settings.MEDIA_SERVER_BASE or "").strip()
    return base.rstrip("/")


def _proxy_media_server(method: str, path: str, *, json: dict | None = None, params: dict | None = None) -> dict:
    base = _media_server_base()
    if not base:
        raise HTTPException(
            status_code=503,
            detail="MEDIA_SERVER_BASE not configured (start MediaCrawlerPro server and set MEDIA_SERVER_BASE, e.g. http://127.0.0.1:8001)",
        )
    url = base + path
    try:
        r = requests.request(method.upper(), url, json=json, params=params, timeout=5)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"media server unreachable: {e}")
    if r.status_code >= 400:
        detail = (r.text or "").strip()
        raise HTTPException(status_code=502, detail=f"media server error {r.status_code}: {detail[:300]}")
    try:
        return r.json()
    except Exception:
        return {"ok": True, "raw": (r.text or "")[:2000]}


@router.get("/items")
def api_list_media_items(
    limit: int = Query(200, ge=1, le=500),
    q: str | None = None,
    filter_noise: bool = Query(True),
    db: Session = Depends(get_db),
):
    """自媒体列表数据。

    优先使用轻量 media-collector 的 data/hot + data/search。
    新安装且暂无数据时，自动用仓库自带默认源跑一次热榜初始化。
    若 collector 仍暂无数据，再回退到旧 MediaCrawlerPro data/results。
    """
    bootstrap: dict[str, Any] | None = None
    try:
        collector = list_collector_items(limit=limit, keyword=q)
        items = collector.get("items") or []
        if not items:
            bootstrap = _maybe_bootstrap_media_collector(q)
            if bootstrap and not bool(bootstrap.get("running")):
                collector = list_collector_items(limit=limit, keyword=q)
                items = collector.get("items") or []
        if items:
            response = _collector_response(
                items,
                limit=limit,
                filter_noise=filter_noise,
                bootstrap=bootstrap,
            )
            response["items"] = overlay_cached_summaries(db, "media", response.get("items") or [])
            return response
    except Exception:
        # 不中断旧数据源
        pass

    conf = _get_media_config(db)
    project_dir = str(conf.get("project_dir") or "").strip() or None
    payload = list_media_items(limit=limit, q=q, project_dir=project_dir)
    if bootstrap:
        source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
        payload["source"] = {
            **source,
            "default_sources": _default_collector_source_paths(),
            "media_collector_bootstrap": _summarize_bootstrap_result(bootstrap),
        }
    payload["items"] = overlay_cached_summaries(db, "media", payload.get("items") or [])
    return payload


@router.post("/items/summaries")
def api_summarize_media_items(payload: dict, db: Session = Depends(get_db)):
    items = payload.get("items") if isinstance(payload, dict) else []
    return summarize_external_items(
        db,
        "media",
        items if isinstance(items, list) else [],
        force=bool(payload.get("force", False)) if isinstance(payload, dict) else False,
    )


@router.get("/meeting-records")
def api_list_meeting_records(limit: int = Query(200, ge=1, le=500)):
    return list_media_meeting_records(limit=limit)


@router.get("/meeting/audio/{record_id}")
def api_get_meeting_audio(record_id: str):
    p = resolve_media_meeting_audio_path(record_id)
    if not p:
        raise HTTPException(404, "audio not found")
    return FileResponse(str(p), media_type="audio/wav", filename=p.name)


# ---- Meeting recorder controls (proxy to MediaCrawlerPro server, if running) ----
@router.get("/meeting/status")
def api_meeting_status():
    return _proxy_media_server("GET", "/api/meeting/status")


@router.post("/meeting/start_listen")
def api_meeting_start_listen(device_index: int | None = None):
    # MediaCrawlerPro expects optional query param device_index
    params = {"device_index": device_index} if device_index is not None else None
    return _proxy_media_server("POST", "/api/meeting/start_listen", params=params)


@router.post("/meeting/stop_listen")
def api_meeting_stop_listen():
    return _proxy_media_server("POST", "/api/meeting/stop_listen")
