from __future__ import annotations

import math
import re
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from statistics import pstdev
from typing import Any, Callable, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    Contact,
    ContactFocusSetting,
    ContactPredictionEvaluation,
    ContactPredictionEvent,
    ContactScoringCase,
    ContactScoreSnapshot,
    ContactSignalCluster,
    ContactValueMetricSnapshot,
    Message,
)
from .ai_tools import _detect_entities
from .market_data import (
    DEFAULT_BENCHMARK_CODE,
    fetch_market_series,
    load_market_data_config,
    market_data_provider_order,
    market_provider_health,
    search_asset_in_text,
)


EXTRACTOR_VERSION = "contact-score-v1"
SCORING_VERSION = "contact-score-calibrated-v2"
DEFAULT_HORIZON_FLAGS = {"1m": True, "3m": True, "1y": True}
HORIZON_DAYS = {"1m": 30, "3m": 90, "1y": 365}
DEFAULT_BENCHMARK = DEFAULT_BENCHMARK_CODE
MANUAL_WEIGHT = 0.3
AUTO_WEIGHT = 0.7
SALES_ROLE_PATTERNS = (
    r"券商销售",
    r"机构销售",
    r"研究所销售",
    r"证券销售",
    r"销售$",
    r"[\s\-_/｜|（(]销售[）)]?$",
    r"销售[\s\-_/｜|]",
)
SALES_TEXT_HINT_PATTERNS = (
    r"(转发|分享|转载|群发|供参考|FYI|仅供参考|路演报名|欢迎报名|会议邀请)",
)

INDEX_ALIASES = {
    "沪深300": "sh000300",
    "上证综指": "sh000001",
    "上证指数": "sh000001",
    "创业板": "sz399006",
    "创业板指": "sz399006",
    "中证500": "sh000905",
    "科创50": "sh000688",
    "上证50": "sh000016",
    "中证1000": "sh000852",
    "北证50": "bj899050",
}

BENCHMARK_LABELS = {
    "sh000300": "沪深300",
    "sh000001": "上证指数",
    "sz399001": "深证成指",
    "sz399006": "创业板指",
    "sh000688": "科创50",
    "sh000905": "中证500",
    "sh000852": "中证1000",
    "bj899050": "北证50",
}

STOCK_BENCHMARK_RULES = (
    (("688",), "sh000688"),
    (("300", "301", "302"), "sz399006"),
    (("8", "4"), "bj899050"),
    (("000", "001", "002", "003"), "sz399001"),
)

INDUSTRY_PROXY_CODES = {
    "半导体": "512480",
    "芯片": "512480",
    "人工智能": "515980",
    "AI": "515980",
    "新能源": "516160",
    "光伏": "515790",
    "储能": "516730",
    "煤炭": "515220",
    "有色": "512400",
    "化工": "516020",
    "汽车": "516110",
    "银行": "512800",
    "券商": "512000",
    "保险": "512070",
    "白酒": "512690",
    "消费": "159928",
    "医药": "512010",
    "军工": "512660",
    "地产": "512200",
    "通信": "515880",
    "电力": "561560",
    "互联网": "159607",
    "游戏": "159869",
    "传媒": "512980",
    "航运": "159673",
}

FUND_OR_ETF_HINTS = ("etf", "基金", "联接", "场内", "场外", "lof")
ETF_PREFIXES = ("159", "160", "161", "162", "163", "164", "165", "166", "167", "168", "500", "501", "502", "503", "505", "506", "508", "510", "511", "512", "513", "515", "516", "517", "518", "519", "520", "560", "561", "562", "563", "588")

BULLISH_PATTERNS = [
    r"看好",
    r"推荐",
    r"建议加仓",
    r"建议关注",
    r"建议配置",
    r"跑赢",
    r"反弹",
    r"上涨",
    r"新高",
    r"超预期",
    r"做多",
    r"增配",
]

BEARISH_PATTERNS = [
    r"看空",
    r"回避",
    r"压力",
    r"风险",
    r"下跌",
    r"走弱",
    r"跑输",
    r"减仓",
    r"谨慎",
    r"悲观",
    r"做空",
]

ACCURACY_WEIGHT = 0.72
SERVICE_VALUE_WEIGHT = 0.28
DEFAULT_SERVICE_VALUE_SCORE = 50.0
HIT_RATE_PRIOR_STRENGTH = 4.0
HIT_RATE_PRIOR = 0.5
AUTO_FOCUS_RECENT_DAYS = 21
AUTO_FOCUS_MAX_CONTACTS = 120


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def _sample_confidence(sample_size: int | float, *, mature_sample: int = 24) -> float:
    """Evidence confidence used to avoid over-scoring 1-3 lucky samples."""
    size = max(0.0, float(sample_size or 0))
    if size <= 0:
        return 0.0
    return _clamp(math.log1p(size) / math.log1p(max(1, mature_sample)), 0.0, 1.0)


def _shrink_score(score: float, confidence: float, *, midpoint: float = 50.0) -> float:
    return _clamp(midpoint + (float(score or midpoint) - midpoint) * _clamp(confidence, 0.0, 1.0))


def _bayesian_rate(hits: float, samples: float) -> float:
    samples = max(0.0, float(samples or 0))
    hits = max(0.0, float(hits or 0))
    if samples <= 0:
        return HIT_RATE_PRIOR
    return (hits + HIT_RATE_PRIOR * HIT_RATE_PRIOR_STRENGTH) / (samples + HIT_RATE_PRIOR_STRENGTH)


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def _extract_text(message: dict[str, Any]) -> str:
    raw = str(message.get("content_text") or message.get("content") or "").strip()
    if raw:
        return raw
    derived = message.get("derived")
    if isinstance(derived, dict):
        return str(derived.get("summary_full") or derived.get("summary") or "").strip()
    return ""


def _identity_text(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("sender_name", "talker_name", "name", "alias", "display_name", "remark", "nickname"):
        value = payload.get(key)
        if value:
            parts.append(str(value))
    labels = payload.get("labels")
    if isinstance(labels, dict):
        for key in ("tags", "labels", "label_names", "names"):
            values = labels.get(key)
            if isinstance(values, list):
                parts.extend(str(item) for item in values if item)
            elif values:
                parts.append(str(values))
    elif isinstance(labels, list):
        parts.extend(str(item) for item in labels if item)
    return " ".join(parts)


def is_sales_contact_payload(payload: dict[str, Any]) -> bool:
    identity = _identity_text(payload)
    if not identity:
        return False
    return any(re.search(pattern, identity, re.IGNORECASE) for pattern in SALES_ROLE_PATTERNS)


def _is_sales_forward_payload(payload: dict[str, Any], text: str) -> bool:
    if not is_sales_contact_payload(payload):
        return False
    if any(re.search(pattern, text, re.IGNORECASE) for pattern in SALES_TEXT_HINT_PATTERNS):
        return True
    return True


def _find_direction(text: str) -> str | None:
    for pattern in BULLISH_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return "bullish"
    for pattern in BEARISH_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return "bearish"
    return None


def _normalize_event_direction(direction: str | None) -> str:
    value = str(direction or "").strip().lower()
    if value in {"bullish", "bearish"}:
        return value
    return "neutral"


def _detect_horizon_flags(text: str) -> dict[str, bool]:
    flags = dict(DEFAULT_HORIZON_FLAGS)
    if re.search(r"(一个月|1个月|1月|短期)", text):
        flags = {"1m": True, "3m": False, "1y": False}
    elif re.search(r"(三个月|3个月|3月|一个季度)", text):
        flags = {"1m": False, "3m": True, "1y": False}
    elif re.search(r"(半年|六个月|6个月|一年|1年|长期)", text):
        flags = {"1m": False, "3m": False, "1y": True}
    return flags


def _resolve_index(text: str) -> tuple[str | None, str | None]:
    for name, code in INDEX_ALIASES.items():
        if name in text:
            return code, name
    return None, None


def _resolve_industry(entities: dict[str, list[str]]) -> tuple[str | None, str | None]:
    for industry in entities.get("industries") or []:
        return INDUSTRY_PROXY_CODES.get(industry), industry
    return None, None


def _select_benchmark_code(
    asset_type: str | None,
    asset_code: str | None,
    text: str,
) -> str | None:
    explicit_code, _ = _resolve_index(text)
    if explicit_code:
        return explicit_code
    kind = str(asset_type or "").strip().lower()
    code = re.sub(r"\D", "", str(asset_code or ""))
    if kind == "index":
        return None
    if kind == "stock":
        for prefixes, benchmark_code in STOCK_BENCHMARK_RULES:
            if code.startswith(prefixes):
                return benchmark_code
        return DEFAULT_BENCHMARK
    if kind in {"industry", "etf", "fund"}:
        return DEFAULT_BENCHMARK
    return DEFAULT_BENCHMARK


def _benchmark_label(code: str | None) -> str:
    value = str(code or "").strip()
    return BENCHMARK_LABELS.get(value, value or "无基准")


def _find_six_digit_codes(text: str) -> list[str]:
    if not text:
        return []
    found = re.findall(r"(?<!\d)(\d{6})(?!\d)", text)
    out: list[str] = []
    seen: set[str] = set()
    for item in found:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _looks_like_fund_or_etf(text: str, code: str) -> bool:
    lower = text.lower()
    if any(flag in lower for flag in FUND_OR_ETF_HINTS):
        return True
    return str(code or "").startswith(ETF_PREFIXES)


def _resolve_asset_from_text(
    text: str,
    entities: dict[str, list[str]],
    asset_lookup_resolver: Callable[[str], dict[str, Any] | None] | None = None,
) -> tuple[str | None, str | None, str | None]:
    a_codes = entities.get("a") or []
    if a_codes:
        return "stock", str(a_codes[0]), str(a_codes[0])

    generic_codes = _find_six_digit_codes(text)
    if generic_codes:
        first_code = generic_codes[0]
        if _looks_like_fund_or_etf(text, first_code):
            return "etf", first_code, first_code
        return "stock", first_code, first_code

    if asset_lookup_resolver:
        matched = asset_lookup_resolver(text)
        if matched:
            return (
                str(matched.get("asset_type") or "").strip() or None,
                str(matched.get("asset_code") or "").strip() or None,
                str(matched.get("asset_name") or "").strip() or None,
            )

    index_code, index_name = _resolve_index(text)
    if index_code:
        return "index", index_code, index_name

    industry_code, industry_name = _resolve_industry(entities)
    if industry_name:
        return "industry", industry_code, industry_name

    return None, None, None


def _guess_confidence(text: str, direction: str | None) -> float:
    score = 0.45
    if direction:
        score += 0.12
    if re.search(r"(强烈|明确|继续|坚定|大概率|显著|明显)", text):
        score += 0.15
    if re.search(r"(建议|推荐|加仓|减仓|回避|配置)", text):
        score += 0.12
    if re.search(r"(也许|可能|观察|跟踪|待验证)", text):
        score -= 0.08
    return round(_clamp(score, 0.05, 0.98), 4)


def _derive_event_kind(text: str, direction: str | None) -> str:
    kind = _classify_contact_event_kind(text)
    if kind == "risk_alert":
        return "risk_alert"
    if kind in {"stock_pitch", "viewpoint_share"} and direction:
        return "price_call"
    if kind in {"roadshow_invite", "strategy_exchange"}:
        return kind
    if direction:
        return "price_call"
    return "other"


def _is_actionable_event(event_kind: str, direction: str | None, text: str) -> bool:
    kind = str(event_kind or "").strip()
    if kind in {"price_call", "risk_alert", "stock_pitch", "viewpoint_share"}:
        return True
    if kind in {"roadshow_invite", "strategy_exchange"}:
        return False
    if direction and re.search(r"(看好|看空|判断|预期|建议|推荐|回避|加仓|减仓|配置|跑赢|下跌|上涨)", str(text or ""), re.IGNORECASE):
        return True
    return False


def _derive_topic_key(asset_type: str | None, asset_code: str | None, asset_name: str | None, text: str) -> str:
    if asset_name:
        return str(asset_name).strip()
    if asset_code:
        return str(asset_code).strip()
    normalized = re.sub(r"\s+", "", text or "")
    return normalized[:24] if normalized else "unknown"


def _cluster_window_days(event_kind: str, horizon_flags: dict[str, bool] | None = None) -> int:
    flags = horizon_flags or {}
    if flags.get("1y"):
        return 30
    if flags.get("3m"):
        return 14
    if event_kind == "risk_alert":
        return 14
    return 7


def _build_cluster_id(
    contact_id: str,
    topic_key: str,
    direction: str | None,
    event_kind: str,
    source_time: datetime | None,
    horizon_flags: dict[str, bool] | None = None,
) -> str:
    days = _cluster_window_days(event_kind, horizon_flags)
    anchor = source_time or datetime.utcnow()
    bucket = anchor.date().toordinal() // max(days, 1)
    base = "|".join(
        [
            str(contact_id or "").strip(),
            str(topic_key or "").strip(),
            str(direction or "").strip(),
            str(event_kind or "").strip(),
            str(bucket),
        ]
    )
    return re.sub(r"[^a-zA-Z0-9_\-|]+", "-", base)[:120]


def _max_drawdown_from_records(records: list[dict[str, Any]]) -> float | None:
    peak = None
    max_drawdown = 0.0
    found = False
    for item in records:
        try:
            close = float(item.get("close"))
        except Exception:
            continue
        if peak is None or close > peak:
            peak = close
        if peak in (None, 0):
            continue
        drawdown = close / peak - 1.0
        max_drawdown = min(max_drawdown, drawdown)
        found = True
    return round(max_drawdown, 6) if found else None


def _dedupe_evaluation_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in rows:
        row = dict(item)
        cluster_id = str(row.get("cluster_id") or row.get("event_id") or "")
        horizon_code = str(row.get("horizon_code") or "")
        event_kind = str(row.get("event_kind") or "")
        key = (cluster_id, horizon_code, event_kind)
        current = deduped.get(key)
        if not current or float(row.get("event_score") or 0.0) >= float(current.get("event_score") or 0.0):
            deduped[key] = row
    return list(deduped.values())


def _filter_actionable_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for item in rows:
        row = dict(item)
        event_kind = str(row.get("event_kind") or "").strip()
        if not event_kind:
            filtered.append(row)
            continue
        inferred_actionable = _is_actionable_event(event_kind, str(row.get("direction") or "").strip() or None, str(row.get("normalized_text") or row.get("raw_text") or ""))
        if row.get("is_actionable") is False:
            continue
        if row.get("is_actionable") is None and not inferred_actionable:
            continue
        filtered.append(row)
    return filtered


def _dedupe_value_event_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for item in rows:
        row = dict(item)
        cluster_id = str(row.get("event_cluster_id") or row.get("cluster_id") or row.get("event_id") or "").strip()
        if not cluster_id:
            cluster_id = "|".join(
                [
                    str(row.get("topic_key") or row.get("asset_code") or "unknown").strip(),
                    str(row.get("event_kind") or "other").strip(),
                    str((_as_datetime(row.get("source_time")) or datetime.utcnow()).date()),
                ]
            )
        current = deduped.get(cluster_id)
        current_strength = float(current.get("signal_strength") or current.get("confidence") or 0.0) if current else -1.0
        row_strength = float(row.get("signal_strength") or row.get("confidence") or 0.0)
        if not current or row_strength >= current_strength:
            row["event_cluster_id"] = cluster_id
            deduped[cluster_id] = row
    return list(deduped.values())


def _compute_service_value_breakdown(
    event_rows: Iterable[dict[str, Any]] | None,
    evaluations: Iterable[dict[str, Any]] | None,
    *,
    as_of: datetime | None = None,
) -> dict[str, float]:
    as_of = as_of or datetime.utcnow()
    deduped_events = _dedupe_value_event_rows(event_rows or [])
    if not deduped_events:
        return {
            "roadshow_value_score": DEFAULT_SERVICE_VALUE_SCORE,
            "exchange_value_score": DEFAULT_SERVICE_VALUE_SCORE,
            "timeliness_score": DEFAULT_SERVICE_VALUE_SCORE,
            "coverage_depth_score": DEFAULT_SERVICE_VALUE_SCORE,
            "signal_cleanliness_score": DEFAULT_SERVICE_VALUE_SCORE,
        }

    evaluated_rows = _dedupe_evaluation_rows(evaluations or [])
    evaluated_cluster_ids = {
        str(item.get("cluster_id") or item.get("event_cluster_id") or "").strip()
        for item in evaluated_rows
        if str(item.get("cluster_id") or item.get("event_cluster_id") or "").strip()
    }

    total_clusters = max(len(deduped_events), 1)
    evidence_confidence = _sample_confidence(total_clusters, mature_sample=20)
    topic_keys = {str(item.get("topic_key") or "").strip() for item in deduped_events if str(item.get("topic_key") or "").strip()}
    asset_codes = {str(item.get("asset_code") or "").strip() for item in deduped_events if str(item.get("asset_code") or "").strip()}

    roadshow_count = 0
    exchange_count = 0
    strong_signal_count = 0
    ages: list[float] = []
    strengths: list[float] = []
    for item in deduped_events:
        kind = str(item.get("event_kind") or "other").strip()
        if kind == "roadshow_invite":
            roadshow_count += 1
            exchange_count += 1
        elif kind in {"strategy_exchange", "viewpoint_share"}:
            exchange_count += 1
        strength = float(item.get("signal_strength") or item.get("confidence") or 0.0)
        strengths.append(strength)
        if strength >= 0.72:
            strong_signal_count += 1
        source_time = _as_datetime(item.get("source_time"))
        if source_time:
            ages.append(max(0.0, (as_of - source_time).total_seconds() / 86400.0))

    avg_strength = sum(strengths) / len(strengths) if strengths else 0.0
    strong_ratio = strong_signal_count / total_clusters
    evaluated_ratio = len(evaluated_cluster_ids) / total_clusters if total_clusters else 0.0
    recent_ratio = 0.0
    if ages:
        recent_ratio = sum(1.0 for age in ages if age <= 90.0) / len(ages)
        avg_age = sum(ages) / len(ages)
    else:
        avg_age = 180.0

    raw_roadshow_value_score = _clamp(43.0 + min(22.0, roadshow_count * 10.0) + min(10.0, exchange_count * 2.5))
    raw_exchange_value_score = _clamp(45.0 + min(20.0, exchange_count * 5.5) + min(7.0, len(topic_keys) * 1.4))
    raw_timeliness_score = _clamp(42.0 + recent_ratio * 30.0 + max(0.0, 14.0 - min(avg_age, 180.0) / 12.0))
    raw_coverage_depth_score = _clamp(43.0 + min(22.0, len(topic_keys) * 5.5) + min(12.0, len(asset_codes) * 3.5))
    raw_signal_cleanliness_score = _clamp(40.0 + avg_strength * 24.0 + strong_ratio * 12.0 + evaluated_ratio * 12.0)
    roadshow_value_score = round(_shrink_score(raw_roadshow_value_score, evidence_confidence), 2)
    exchange_value_score = round(_shrink_score(raw_exchange_value_score, evidence_confidence), 2)
    timeliness_score = round(_shrink_score(raw_timeliness_score, evidence_confidence), 2)
    coverage_depth_score = round(_shrink_score(raw_coverage_depth_score, evidence_confidence), 2)
    signal_cleanliness_score = round(_shrink_score(raw_signal_cleanliness_score, evidence_confidence), 2)
    return {
        "roadshow_value_score": roadshow_value_score,
        "exchange_value_score": exchange_value_score,
        "timeliness_score": timeliness_score,
        "coverage_depth_score": coverage_depth_score,
        "signal_cleanliness_score": signal_cleanliness_score,
    }


def _build_thesis_card(event: ContactPredictionEvent) -> dict[str, Any]:
    evaluations = sorted(event.evaluations, key=lambda row: str(row.horizon_code or ""))
    if not evaluations:
        return {
            "thesis_status": "pending",
            "best_horizon_code": None,
            "best_score": None,
            "latest_horizon_code": None,
            "latest_score": None,
            "latest_absolute_return": None,
            "latest_excess_return": None,
            "validated_horizons": 0,
            "hit_horizons": 0,
        }

    best = max(evaluations, key=lambda row: float(row.event_score or 0.0))
    latest = max(evaluations, key=lambda row: str(row.evaluated_at or ""))
    hit_count = sum(1 for row in evaluations if bool(row.direction_hit))
    miss_count = len(evaluations) - hit_count
    if hit_count and miss_count:
        thesis_status = "mixed"
    elif hit_count:
        thesis_status = "validated"
    else:
        thesis_status = "disproved"
    return {
        "thesis_status": thesis_status,
        "best_horizon_code": best.horizon_code,
        "best_score": best.event_score,
        "latest_horizon_code": latest.horizon_code,
        "latest_score": latest.event_score,
        "latest_absolute_return": latest.absolute_return,
        "latest_excess_return": latest.excess_return,
        "validated_horizons": len(evaluations),
        "hit_horizons": hit_count,
    }


def _build_case_card(row: dict[str, Any], case_type: str) -> dict[str, Any]:
    thesis_status = "validated" if case_type == "hit" else "disproved"
    return {
        "case_type": case_type,
        "title": row.get("topic_key") or row.get("asset_name") or row.get("asset_code") or "观点案例",
        "asset_code": row.get("asset_code"),
        "asset_name": row.get("asset_name"),
        "event_kind": row.get("event_kind"),
        "direction": row.get("direction"),
        "horizon_code": row.get("horizon_code"),
        "event_score": row.get("event_score"),
        "absolute_return": row.get("absolute_return"),
        "excess_return": row.get("excess_return"),
        "source_time": row.get("source_time"),
        "summary": row.get("normalized_text") or "",
        "thesis_status": thesis_status,
    }


def _build_verification_schedule(
    event: ContactPredictionEvent,
    *,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    as_of = as_of or datetime.utcnow()
    source_time = event.source_time
    flags = event.horizon_flags if isinstance(event.horizon_flags, dict) else DEFAULT_HORIZON_FLAGS
    evaluated_horizons = {str(row.horizon_code or "") for row in event.evaluations}
    rows: list[dict[str, Any]] = []
    for horizon_code, days in HORIZON_DAYS.items():
        if not flags.get(horizon_code):
            continue
        due_at = source_time + timedelta(days=days) if source_time else None
        remaining_days = (due_at.date() - as_of.date()).days if due_at else None
        is_evaluated = horizon_code in evaluated_horizons
        rows.append(
            {
                "horizon_code": horizon_code,
                "due_at": due_at.isoformat() if due_at else None,
                "remaining_days": remaining_days,
                "is_due": bool(remaining_days is not None and remaining_days <= 0),
                "is_evaluated": is_evaluated,
                "status": "evaluated" if is_evaluated else "due" if remaining_days is not None and remaining_days <= 0 else "pending",
            }
        )
    pending_rows = [row for row in rows if not row["is_evaluated"]]
    next_row = None
    if pending_rows:
        next_row = sorted(
            pending_rows,
            key=lambda row: (
                not bool(row.get("is_due")),
                row["remaining_days"] is None,
                abs(int(row["remaining_days"] or 0)),
                str(row["horizon_code"]),
            ),
        )[0]
    return {
        "items": rows,
        "next": next_row,
        "benchmark_code": event.benchmark_code,
        "benchmark_name": _benchmark_label(event.benchmark_code),
    }


def _build_return_distribution(rows: list[dict[str, Any]]) -> dict[str, Any]:
    excess_values = [float(row.get("excess_return") or 0.0) for row in rows if row.get("excess_return") is not None]
    positive = [value for value in excess_values if value > 0]
    negative = [value for value in excess_values if value < 0]
    neutral = [value for value in excess_values if value == 0]
    avg_excess = (sum(excess_values) / len(excess_values)) if excess_values else 0.0
    return {
        "sample_count": len(excess_values),
        "positive_count": len(positive),
        "negative_count": len(negative),
        "neutral_count": len(neutral),
        "avg_excess_return": round(avg_excess, 6),
        "max_excess_return": round(max(excess_values), 6) if excess_values else None,
        "min_excess_return": round(min(excess_values), 6) if excess_values else None,
    }


def _score_tone(value: float, *, good: float = 65.0, bad: float = 45.0) -> str:
    if value >= good:
        return "good"
    if value < bad:
        return "bad"
    return "neutral"


def _build_score_explanation(
    score: dict[str, Any],
    *,
    asset_summary: list[dict[str, Any]],
    top_hits: list[dict[str, Any]],
    top_misses: list[dict[str, Any]],
    pending_predictions: list[dict[str, Any]],
    return_distribution: dict[str, Any],
) -> dict[str, Any]:
    final_rating = float(score.get("final_rating") or 0.0)
    accuracy_score = float(score.get("accuracy_score") or 0.0)
    service_value_score = float(score.get("service_value_score") or 0.0)
    sample_size = int(score.get("sample_size") or 0)
    hit_rate = float(score.get("hit_rate_overall") or 0.0)
    avg_excess = float(return_distribution.get("avg_excess_return") or score.get("excess_mean") or 0.0)
    top_asset = asset_summary[0] if asset_summary else {}
    best_hit = top_hits[0] if top_hits else {}
    worst_miss = top_misses[0] if top_misses else {}
    pending_count = len(pending_predictions)

    drivers = [
        {
            "label": "准确度",
            "value": round(accuracy_score, 1),
            "tone": _score_tone(accuracy_score),
            "detail": f"已验证样本 {sample_size} 条，方向命中率 {hit_rate * 100:.1f}%；准确度还会综合超额收益、风险提示和一致性",
        },
        {
            "label": "超额收益",
            "value": round(avg_excess * 100.0, 1),
            "suffix": "%",
            "tone": "good" if avg_excess > 0.03 else "bad" if avg_excess < -0.03 else "neutral",
            "detail": f"收益样本 {int(return_distribution.get('sample_count') or 0)} 条，平均超额 {avg_excess * 100:.1f}%",
        },
        {
            "label": "业务价值",
            "value": round(service_value_score, 1),
            "tone": _score_tone(service_value_score),
            "detail": "综合路演、交流、时效、覆盖深度和信号纯度",
        },
        {
            "label": "待验证",
            "value": pending_count,
            "tone": "bad" if pending_count >= 12 else "neutral" if pending_count else "good",
            "detail": "近期新观点尚未到达 1M/3M/1Y 验证窗口",
        },
    ]
    strengths: list[str] = []
    risks: list[str] = []
    next_steps: list[str] = []

    if top_asset:
        strengths.append(f"主线标的集中在 {top_asset.get('asset_name') or top_asset.get('asset_code')}")
    if best_hit:
        strengths.append(
            f"最佳案例：{best_hit.get('asset_name') or best_hit.get('asset_code') or '观点'} "
            f"{float(best_hit.get('event_score') or 0):.0f}分"
        )
    if service_value_score >= 65:
        strengths.append("交流和路演服务价值较高")
    if worst_miss:
        risks.append(
            f"失误案例：{worst_miss.get('asset_name') or worst_miss.get('asset_code') or '观点'} "
            f"{float(worst_miss.get('event_score') or 0):.0f}分"
        )
    if sample_size < 8:
        risks.append("已验证样本偏少，分数仍需更多周期确认")
    if pending_count:
        due_count = sum(1 for item in pending_predictions if (item.get("next_verification") or {}).get("is_due"))
        if due_count:
            next_steps.append(f"优先补跑 {due_count} 条已到期观点验证")
        else:
            next_steps.append(f"继续观察 {pending_count} 条待验证观点")
    if final_rating >= 75:
        next_steps.append("适合保持重点跟踪")
    elif final_rating < 50:
        next_steps.append("建议降低权重，仅保留少量样本观察")
    else:
        next_steps.append("维持观察，等待更多命中样本")

    return {
        "headline": f"综合分 {final_rating:.1f}，由准确度 {accuracy_score:.1f} 与业务价值 {service_value_score:.1f} 共同驱动",
        "drivers": drivers,
        "strengths": strengths[:4],
        "risks": risks[:4],
        "next_steps": next_steps[:4],
    }


def _normalize_event_key(event: dict[str, Any]) -> tuple[Any, ...]:
    source_time = event.get("source_time")
    day_key = source_time.date().isoformat() if isinstance(source_time, datetime) else ""
    return (
        str(event.get("contact_id") or ""),
        str(event.get("asset_type") or ""),
        str(event.get("asset_code") or event.get("asset_name") or ""),
        str(event.get("direction") or ""),
        day_key,
    )


def extract_prediction_events(
    messages: Iterable[dict[str, Any]],
    focus_contact_ids: set[str] | None = None,
    asset_lookup_resolver: Callable[[str], dict[str, Any] | None] | None = None,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for message in messages:
        contact_id = str(message.get("sender_id") or "").strip()
        if focus_contact_ids and contact_id not in focus_contact_ids:
            continue
        text = _extract_text(message)
        if len(text) < 8:
            continue
        if _is_sales_forward_payload(message, text):
            continue
        direction = _find_direction(text)
        event_direction = _normalize_event_direction(direction)
        event_kind_hint = _classify_contact_event_kind(text)
        if not direction and event_kind_hint not in {"roadshow_invite", "strategy_exchange"}:
            continue

        entities = _detect_entities(text)
        asset_type, asset_code, asset_name = _resolve_asset_from_text(text, entities, asset_lookup_resolver=asset_lookup_resolver)
        if not asset_type:
            continue

        benchmark_code = _select_benchmark_code(asset_type, asset_code, text)

        event = {
            "contact_id": contact_id,
            "source_message_id": message.get("id"),
            "source_chat_id": message.get("chat_id"),
            "source_time": message.get("timestamp") or message.get("time"),
            "asset_type": asset_type,
            "asset_code": asset_code,
            "asset_name": asset_name,
            "benchmark_code": benchmark_code,
            "topic": asset_name or asset_code,
            "direction": event_direction,
            "confidence": _guess_confidence(text, direction),
            "horizon_flags": _detect_horizon_flags(text),
            "raw_text": text,
            "normalized_text": re.sub(r"\s+", " ", text).strip(),
            "extractor_version": EXTRACTOR_VERSION,
            "status": "extracted",
        }
        event["event_kind"] = _derive_event_kind(text, direction)
        event["is_actionable"] = _is_actionable_event(str(event["event_kind"] or ""), direction, text)
        event["topic_key"] = _derive_topic_key(asset_type, asset_code, asset_name, text)
        event["signal_strength"] = round(float(event["confidence"]), 4)
        event["source_type"] = str(message.get("source_type") or "wechat")
        event["event_cluster_id"] = _build_cluster_id(
            contact_id,
            str(event["topic_key"] or ""),
            event_direction,
            str(event["event_kind"] or ""),
            event.get("source_time"),
            event.get("horizon_flags"),
        )
        event_key = _normalize_event_key(event)
        if event_key in seen:
            continue
        seen.add(event_key)
        events.append(event)
    return events


def _parse_record_date(record_date: str) -> date | None:
    try:
        return datetime.strptime(str(record_date)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _price_on_or_after(records: list[dict[str, Any]], target: date) -> float | None:
    if not records:
        return None
    dated: list[tuple[date, float]] = []
    for item in records:
        dt = _parse_record_date(str(item.get("date") or ""))
        if dt is None:
            continue
        try:
            close = float(item.get("close"))
        except Exception:
            continue
        dated.append((dt, close))
    if not dated:
        return None
    dated.sort(key=lambda x: x[0])
    for dt, close in dated:
        if dt >= target:
            return close
    return dated[-1][1]


def _compute_event_score(direction: str, direction_hit: bool, excess_return: float | None, absolute_return: float | None) -> float:
    relative = excess_return if excess_return is not None else (absolute_return or 0.0)
    directional_advantage = relative if direction == "bullish" else -relative
    score = 50.0
    score += 25.0 if direction_hit else -25.0
    score += 25.0 * max(-1.0, min(1.0, directional_advantage / 0.15))
    return round(_clamp(score), 2)


def _verification_strength(
    direction: str,
    absolute_return: float,
    excess_return: float | None,
    horizon_code: str,
    event_kind: str,
) -> dict[str, Any]:
    relative = excess_return if excess_return is not None else absolute_return
    signed_absolute = absolute_return if direction == "bullish" else -absolute_return
    signed_excess = relative if direction == "bullish" else -relative
    if event_kind == "risk_alert":
        signed_absolute = -absolute_return
        signed_excess = -relative
    strong_threshold = {"1m": 0.03, "3m": 0.06, "1y": 0.1}.get(horizon_code, 0.06)
    weak_threshold = {"1m": -0.02, "3m": -0.04, "1y": -0.08}.get(horizon_code, -0.04)
    if signed_excess >= strong_threshold:
        grade = "strong_confirmed"
        label = "强印证"
    elif signed_excess >= 0:
        grade = "confirmed"
        label = "方向印证"
    elif signed_excess <= weak_threshold:
        grade = "disproved"
        label = "明显证伪"
    else:
        grade = "weak"
        label = "弱印证"
    return {
        "verification_grade": grade,
        "verification_label": label,
        "signed_absolute_return": round(signed_absolute, 6),
        "signed_excess_return": round(signed_excess, 6),
        "threshold": strong_threshold,
    }


def _classify_contact_event_kind(text: str) -> str:
    s = str(text or "")
    if re.search(r"(路演|电话会|交流会|会议|参会|报名|预约|webinar|meeting)", s, re.IGNORECASE):
        return "roadshow_invite"
    if re.search(r"(风险|谨慎|警惕|回避|压力|利空|不确定|担忧|下跌)", s, re.IGNORECASE):
        return "risk_alert"
    if re.search(r"(推荐|看好|加仓|配置|跑赢|超配|继续买)", s, re.IGNORECASE):
        return "stock_pitch"
    if re.search(r"(策略|观点|判断|预期|看多|看空|展望)", s, re.IGNORECASE):
        return "viewpoint_share"
    if re.search(r"(交流|分享|讨论|沟通|探讨)", s, re.IGNORECASE):
        return "strategy_exchange"
    return "other"


def _build_contact_sub_scores(
    all_events: list[ContactPredictionEvent],
    recent_hits: list[dict[str, Any]],
    recent_misses: list[dict[str, Any]],
    *,
    as_of: datetime | None = None,
) -> dict[str, dict[str, Any]]:
    as_of = as_of or datetime.utcnow()
    recent_cutoff = as_of - timedelta(days=90)
    kind_to_events: dict[str, list[ContactPredictionEvent]] = defaultdict(list)
    for event in all_events:
        kind_to_events[_classify_contact_event_kind(event.normalized_text or event.raw_text or "")].append(event)

    def _score_from_events(
        kinds: list[str],
        *,
        default_base: float = 50.0,
        weight_per_sample: float = 6.0,
        hit_bonus: float = 18.0,
        miss_penalty: float = 15.0,
    ) -> dict[str, Any]:
        matched = [event for kind in kinds for event in kind_to_events.get(kind, [])]
        samples = len(matched)
        hit_rows = [row for row in recent_hits if row.get("event_kind") in kinds]
        miss_rows = [row for row in recent_misses if row.get("event_kind") in kinds]
        scored_rows = hit_rows + miss_rows

        recent_events = [
            event for event in matched
            if getattr(event, "source_time", None) is not None and event.source_time >= recent_cutoff
        ]
        recent_hit_rows = [
            row for row in hit_rows
            if row.get("source_time") and datetime.fromisoformat(str(row.get("source_time"))) >= recent_cutoff
        ]
        recent_miss_rows = [
            row for row in miss_rows
            if row.get("source_time") and datetime.fromisoformat(str(row.get("source_time"))) >= recent_cutoff
        ]

        def _calc_window_score(
            window_events: list[ContactPredictionEvent],
            window_hit_rows: list[dict[str, Any]],
            window_miss_rows: list[dict[str, Any]],
        ) -> tuple[float, int, int, int]:
            window_samples = len(window_events)
            window_scored_rows = window_hit_rows + window_miss_rows
            if window_scored_rows:
                avg_score = sum(float(row.get("event_score") or 50.0) for row in window_scored_rows) / len(window_scored_rows)
            else:
                avg_conf = (
                    sum(float(getattr(event, "confidence", 0.5) or 0.5) for event in window_events) / window_samples
                    if window_samples
                    else 0.5
                )
                avg_score = default_base + (avg_conf - 0.5) * 35.0
            final_score = _clamp(
                avg_score
                + min(12.0, window_samples * weight_per_sample * 0.35)
                + min(12.0, len(window_hit_rows) * hit_bonus * 0.2)
                - min(12.0, len(window_miss_rows) * miss_penalty * 0.2)
            )
            return round(final_score, 2), window_samples, len(window_hit_rows), len(window_miss_rows)

        score_all_time, samples_all_time, hit_all_time, miss_all_time = _calc_window_score(matched, hit_rows, miss_rows)
        score_recent, samples_recent, hit_recent, miss_recent = _calc_window_score(recent_events, recent_hit_rows, recent_miss_rows)
        return {
            "score": score_all_time,
            "samples": samples_all_time,
            "evaluated_samples": len(scored_rows),
            "hit_samples": hit_all_time,
            "miss_samples": miss_all_time,
            "recent_90d_score": score_recent,
            "recent_90d_samples": samples_recent,
            "recent_90d_hit_samples": hit_recent,
            "recent_90d_miss_samples": miss_recent,
            "delta_recent_90d": round(score_recent - score_all_time, 2),
        }

    return {
        "recommendation_accuracy": _score_from_events(["stock_pitch"], default_base=54.0, hit_bonus=20.0),
        "risk_alert_effectiveness": _score_from_events(["risk_alert"], default_base=52.0, hit_bonus=22.0),
        "exchange_activity": _score_from_events(["strategy_exchange", "viewpoint_share"], default_base=55.0, weight_per_sample=10.0),
        "roadshow_value": _score_from_events(["roadshow_invite"], default_base=53.0, weight_per_sample=12.0),
    }


def _build_contact_action_recommendation(sub_scores: dict[str, dict[str, Any]]) -> dict[str, Any]:
    values = [float(item.get("score") or 0.0) for item in sub_scores.values()]
    recent_values = [float(item.get("recent_90d_score") or 0.0) for item in sub_scores.values()]
    deltas = [float(item.get("delta_recent_90d") or 0.0) for item in sub_scores.values()]
    avg_score = sum(values) / len(values) if values else 50.0
    avg_recent = sum(recent_values) / len(recent_values) if recent_values else avg_score
    max_drop = min(deltas) if deltas else 0.0
    max_rise = max(deltas) if deltas else 0.0
    flags: list[str] = []
    if avg_score >= 68 and max_drop <= -8:
        flags.append("high_score_recent_drop")
    if max_rise >= 8:
        flags.append("recent_rising")
    if avg_recent < 55:
        flags.append("recent_weak")
    if float(sub_scores.get("roadshow_value", {}).get("score") or 0.0) >= 70:
        flags.append("roadshow_value")

    if "high_score_recent_drop" in flags:
        action = "观察恢复"
        reason = "全年基础仍可，但近3个月有明显回落，建议暂缓加权、观察后续观点质量。"
    elif avg_recent >= 72 and avg_score >= 65:
        action = "重点维护"
        reason = "全年与近3个月表现均较强，适合作为重点联系人持续维护。"
    elif "recent_rising" in flags:
        action = "继续跟踪"
        reason = "近3个月状态改善，建议提高跟踪频率验证持续性。"
    elif avg_recent < 55:
        action = "降低权重"
        reason = "近3个月综合表现偏弱，建议降低信息权重。"
    else:
        action = "继续跟踪"
        reason = "当前表现中性，建议维持常规跟踪。"
    return {
        "action": action,
        "reason": reason,
        "avg_score": round(avg_score, 2),
        "avg_recent_90d_score": round(avg_recent, 2),
        "max_drop": round(max_drop, 2),
        "max_rise": round(max_rise, 2),
        "flags": flags,
    }


def evaluate_prediction_event(
    event: dict[str, Any],
    *,
    as_of: datetime | None = None,
    price_fetcher: Callable[[str, str | None, datetime, datetime], list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    src_time = event.get("source_time")
    if not isinstance(src_time, datetime):
        return []
    asset_code = str(event.get("asset_code") or "").strip() or None
    if not asset_code:
        return []
    as_of = as_of or datetime.utcnow()
    horizon_flags = event.get("horizon_flags") if isinstance(event.get("horizon_flags"), dict) else DEFAULT_HORIZON_FLAGS
    matured_horizons = [code for code, days in HORIZON_DAYS.items() if horizon_flags.get(code) and as_of >= (src_time + timedelta(days=days))]
    if not matured_horizons:
        return []
    fetcher = price_fetcher or fetch_market_series
    start = src_time - timedelta(days=5)
    end = max(as_of, src_time + timedelta(days=max(HORIZON_DAYS.values()) + 5))
    asset_series = fetcher(str(event.get("asset_type") or ""), asset_code, start, end)
    entry_price = _price_on_or_after(asset_series, src_time.date())
    if entry_price in (None, 0):
        return []

    benchmark_code = str(event.get("benchmark_code") or "").strip() or None
    benchmark_series = fetcher("index", benchmark_code, start, end) if benchmark_code else []
    benchmark_entry = _price_on_or_after(benchmark_series, src_time.date()) if benchmark_code else None
    event_kind = str(event.get("event_kind") or "")
    max_drawdown = _max_drawdown_from_records(asset_series)

    out: list[dict[str, Any]] = []
    for horizon_code, days in HORIZON_DAYS.items():
        if not horizon_flags.get(horizon_code):
            continue
        target_dt = src_time + timedelta(days=days)
        if as_of < target_dt:
            continue
        evaluation_price = _price_on_or_after(asset_series, target_dt.date())
        if evaluation_price in (None, 0):
            continue
        absolute_return = float(evaluation_price / entry_price - 1.0)
        benchmark_eval = _price_on_or_after(benchmark_series, target_dt.date()) if benchmark_series else None
        benchmark_return = None
        excess_return = absolute_return
        if benchmark_entry not in (None, 0) and benchmark_eval not in (None, 0):
            benchmark_return = float(benchmark_eval / benchmark_entry - 1.0)
            excess_return = float(absolute_return - benchmark_return)
        direction = str(event.get("direction") or "bullish")
        direction_hit = absolute_return >= 0 if direction == "bullish" else absolute_return <= 0
        event_kind = str(event.get("event_kind") or "")
        meta = {
            "benchmark_return": round(benchmark_return, 6) if benchmark_return is not None else None,
            "verification_method": "asset_vs_benchmark" if benchmark_return is not None else "absolute_direction",
        }
        meta.update(_verification_strength(direction, absolute_return, excess_return, horizon_code, event_kind))
        if event_kind == "risk_alert":
            direction_hit = bool((absolute_return <= 0) or ((max_drawdown or 0.0) <= -0.15))
            meta["risk_rule"] = "drawdown_or_negative_return"
            meta["max_drawdown"] = max_drawdown
        out.append(
            {
                "event_id": event.get("id"),
                "horizon_code": horizon_code,
                "benchmark_code": benchmark_code,
                "entry_price": round(entry_price, 6),
                "evaluation_price": round(evaluation_price, 6),
                "benchmark_entry": round(benchmark_entry, 6) if benchmark_entry is not None else None,
                "benchmark_evaluation": round(benchmark_eval, 6) if benchmark_eval is not None else None,
                "absolute_return": round(absolute_return, 6),
                "excess_return": round(excess_return, 6) if excess_return is not None else None,
                "direction_hit": bool(direction_hit),
                "event_score": _compute_event_score(direction, bool(direction_hit), excess_return, absolute_return),
                "evaluated_at": as_of,
                "meta": meta,
            }
        )
    return out


def summarize_contact_score(
    *,
    contact_id: str,
    evaluations: Iterable[dict[str, Any]],
    manual_rating: float,
    event_rows: Iterable[dict[str, Any]] | None = None,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    all_rows = _dedupe_evaluation_rows(evaluations)
    rows = _filter_actionable_rows(all_rows)
    sample_size = len(rows)
    value_breakdown = _compute_service_value_breakdown(event_rows, all_rows, as_of=as_of)
    service_value_score = round(
        _clamp(
            value_breakdown["roadshow_value_score"] * 0.22
            + value_breakdown["exchange_value_score"] * 0.18
            + value_breakdown["timeliness_score"] * 0.2
            + value_breakdown["coverage_depth_score"] * 0.2
            + value_breakdown["signal_cleanliness_score"] * 0.2
        ),
        2,
    )
    if sample_size == 0:
        auto_rating = 50.0
        direction_accuracy_score = 50.0
        excess_return_score = 50.0
        risk_alert_score = 50.0
        consistency_score = 50.0
        accuracy_score = 50.0
        final_rating = round(_clamp(accuracy_score * ACCURACY_WEIGHT + service_value_score * SERVICE_VALUE_WEIGHT))
        return {
            "contact_id": contact_id,
            "manual_rating": round(_clamp(manual_rating), 2),
            "auto_rating": auto_rating,
            "final_rating": final_rating,
            "accuracy_score": accuracy_score,
            "service_value_score": service_value_score,
            "sample_size": 0,
            "hit_rate_overall": 0.0,
            "accuracy_by_horizon": {"1m": 0.0, "3m": 0.0, "1y": 0.0},
            "excess_mean": 0.0,
            "stability_score": 50.0,
            "frequency_penalty": 0.0,
            "score_breakdown": {
                "direction_accuracy_score": direction_accuracy_score,
                "excess_return_score": excess_return_score,
                "risk_alert_score": risk_alert_score,
                "consistency_score": consistency_score,
            },
            "value_breakdown": value_breakdown,
        }

    hit_values = [1.0 if bool(item.get("direction_hit")) else 0.0 for item in rows]
    raw_hit_rate_overall = sum(hit_values) / sample_size
    hit_rate_overall = _bayesian_rate(sum(hit_values), sample_size)
    accuracy_by_horizon: dict[str, float] = {}
    for horizon_code in HORIZON_DAYS:
        horizon_hits = [1.0 if bool(item.get("direction_hit")) else 0.0 for item in rows if item.get("horizon_code") == horizon_code]
        accuracy_by_horizon[horizon_code] = _bayesian_rate(sum(horizon_hits), len(horizon_hits)) if horizon_hits else 0.0

    excess_values = [float(item.get("excess_return") or 0.0) for item in rows]
    excess_mean = sum(excess_values) / len(excess_values)
    score_values = [float(item.get("event_score") or 50.0) for item in rows]
    volatility = pstdev(score_values) if len(score_values) > 1 else 0.0
    stability_score = round(_clamp(100.0 - volatility * 1.6), 2)
    frequency_penalty = round(max(0.0, (sample_size - 12) * 0.45) + max(0.0, (sample_size - 36) * 0.35), 2)
    risk_rows = [row for row in rows if str(row.get("event_kind") or "") == "risk_alert"]
    risk_hits = [1.0 if bool(item.get("direction_hit")) else 0.0 for item in risk_rows]

    direction_accuracy_score = round(_clamp(hit_rate_overall * 100.0), 2)
    excess_return_score = round(_clamp(50.0 + 50.0 * max(-1.0, min(1.0, excess_mean / 0.10))), 2)
    risk_alert_score = round(_clamp(_bayesian_rate(sum(risk_hits), len(risk_hits)) * 100.0), 2) if risk_hits else 50.0
    consistency_score = stability_score
    evidence_confidence = _sample_confidence(sample_size, mature_sample=24)
    raw_accuracy_score = _clamp(
        direction_accuracy_score * 0.48
        + excess_return_score * 0.28
        + risk_alert_score * 0.12
        + consistency_score * 0.12
        - frequency_penalty
    )
    accuracy_score = round(_shrink_score(raw_accuracy_score, evidence_confidence), 2)
    service_value_score = round(_shrink_score(service_value_score, min(1.0, 0.25 + evidence_confidence * 0.75)), 2)
    raw_final_rating = _clamp(accuracy_score * ACCURACY_WEIGHT + service_value_score * SERVICE_VALUE_WEIGHT)
    final_confidence = min(1.0, 0.2 + evidence_confidence * 0.8)
    final_rating = round(
        _clamp(
            _shrink_score(raw_final_rating, final_confidence)
            + max(-6.0, min(6.0, (raw_hit_rate_overall - 0.5) * 10.0 * evidence_confidence))
        ),
        2,
    )
    auto_rating = accuracy_score
    return {
        "contact_id": contact_id,
        "manual_rating": round(_clamp(manual_rating), 2),
        "auto_rating": auto_rating,
        "final_rating": final_rating,
        "accuracy_score": accuracy_score,
        "service_value_score": service_value_score,
        "sample_size": sample_size,
        "hit_rate_overall": hit_rate_overall,
        "accuracy_by_horizon": accuracy_by_horizon,
        "excess_mean": round(excess_mean, 6),
        "stability_score": stability_score,
        "frequency_penalty": frequency_penalty,
        "score_breakdown": {
            "direction_accuracy_score": direction_accuracy_score,
            "excess_return_score": excess_return_score,
            "risk_alert_score": risk_alert_score,
            "consistency_score": consistency_score,
        },
        "value_breakdown": value_breakdown,
    }


def resolve_contact_stats(contact: Contact) -> dict[str, Any]:
    raw = getattr(contact, "stats", None)
    return dict(raw or {})


def resolve_manual_rating(contact: Contact) -> float:
    stats = resolve_contact_stats(contact)
    try:
        return float(stats.get("manual_rating", contact.rating or 50))
    except Exception:
        return float(contact.rating or 50)


def resolve_auto_rating(contact: Contact) -> float | None:
    stats = resolve_contact_stats(contact)
    try:
        value = stats.get("auto_rating")
        return None if value is None else float(value)
    except Exception:
        return None


def resolve_contact_watch(contact: Contact) -> dict[str, Any]:
    stats = resolve_contact_stats(contact)
    raw_status = str(stats.get("watch_status") or "").strip().lower()
    enabled = raw_status == "watching" or bool(stats.get("watching"))
    return {
        "enabled": enabled,
        "status": "watching" if enabled else "none",
        "reason": str(stats.get("watch_reason") or "").strip() or None,
        "updated_at": str(stats.get("watch_updated_at") or "").strip() or None,
    }


def is_focus_contact(contact: Contact, focus_row: ContactFocusSetting | None = None) -> bool:
    if focus_row is not None:
        return bool(focus_row.enabled)
    stats = resolve_contact_stats(contact)
    if "auto_focus" in stats:
        return bool(stats.get("auto_focus"))
    return bool((contact.rating or 0) >= 70)


def set_contact_focus(db: Session, contact_id: str, enabled: bool) -> ContactFocusSetting:
    row = db.get(ContactFocusSetting, contact_id)
    if not row:
        row = ContactFocusSetting(contact_id=contact_id, enabled=enabled)
    else:
        row.enabled = enabled
    contact = db.get(Contact, contact_id)
    if contact:
        stats = resolve_contact_stats(contact)
        stats["auto_focus"] = bool(enabled)
        contact.stats = stats
        db.add(contact)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def set_contact_watch(db: Session, contact_id: str, enabled: bool, reason: str | None = None) -> dict[str, Any]:
    contact = db.get(Contact, contact_id)
    if not contact:
        raise ValueError("contact not found")
    stats = resolve_contact_stats(contact)
    watch_reason = str(reason or "").strip() or None
    stats["watch_status"] = "watching" if enabled else "none"
    stats["watching"] = bool(enabled)
    stats["watch_reason"] = watch_reason
    stats["watch_updated_at"] = datetime.utcnow().isoformat()
    contact.stats = stats
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return resolve_contact_watch(contact)


def get_focus_contact_ids(db: Session) -> set[str]:
    rows = db.execute(select(ContactFocusSetting).where(ContactFocusSetting.enabled.is_(True))).scalars().all()
    if rows:
        return {str(row.contact_id) for row in rows if row.contact_id}
    contacts = db.execute(select(Contact)).scalars().all()
    ids = {
        c.id
        for c in contacts
        if c.id and bool(resolve_contact_stats(c).get("auto_focus"))
    }
    if ids:
        return ids

    cutoff = datetime.utcnow() - timedelta(days=AUTO_FOCUS_RECENT_DAYS)
    recent_rows = db.execute(
        select(
            Message.sender_id,
            func.max(Message.sender_name),
            func.count(Message.id).label("message_count"),
            func.max(Message.timestamp).label("last_message_at"),
        )
        .where(Message.sender_id.is_not(None))
        .where(Message.timestamp >= cutoff)
        .group_by(Message.sender_id)
        .order_by(func.count(Message.id).desc())
        .limit(AUTO_FOCUS_MAX_CONTACTS * 3)
    ).all()
    selected: set[str] = set()
    for sender_id, sender_name, message_count, _last_message_at in recent_rows:
        cid = str(sender_id or "").strip()
        if not cid or cid.endswith("@chatroom") or cid.startswith("gh_") or cid in {"weixin", "filehelper"}:
            continue
        contact = db.get(Contact, cid)
        identity = {
            "name": contact.name if contact else sender_name,
            "alias": contact.alias if contact else None,
            "labels": contact.labels if contact else None,
        }
        if is_sales_contact_payload(identity):
            continue
        score_hint = int(getattr(contact, "rating", 50) or 50) if contact else 50
        if int(message_count or 0) < 3 and score_hint < 65:
            continue
        selected.add(cid)
        if len(selected) >= AUTO_FOCUS_MAX_CONTACTS:
            break
    return selected


def extract_prediction_events_to_db(
    db: Session,
    *,
    time_from: datetime | None = None,
    time_to: datetime | None = None,
    contact_ids: set[str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    focus_ids = contact_ids or get_focus_contact_ids(db)
    if not focus_ids:
        return {"contacts": 0, "messages": 0, "inserted": 0, "updated": 0}
    market_cfg = load_market_data_config(db)

    query = select(Message).where(Message.sender_id.in_(list(focus_ids)))
    if time_from:
        query = query.where(Message.timestamp >= time_from)
    if time_to:
        query = query.where(Message.timestamp <= time_to)
    rows = db.execute(query.order_by(Message.timestamp.asc())).scalars().all()
    messages = [
        {
            "id": row.id,
            "chat_id": row.chat_id,
            "sender_id": row.sender_id,
            "sender_name": row.sender_name,
            "timestamp": row.timestamp,
            "content_text": row.content_text,
                "derived": row.derived,
                "sender_name": row.sender_name,
            }
        for row in rows
    ]
    contact_payloads = {
        str(contact.id): {
            "name": contact.name,
            "alias": contact.alias,
            "labels": contact.labels,
        }
        for contact in db.execute(select(Contact).where(Contact.id.in_(list(focus_ids)))).scalars().all()
        if contact.id
    }
    for message in messages:
        identity = contact_payloads.get(str(message.get("sender_id") or ""))
        if identity:
            message.update(identity)
    extracted = extract_prediction_events(
        messages,
        focus_contact_ids=focus_ids,
        asset_lookup_resolver=lambda text: search_asset_in_text(text, market_cfg),
    )
    existing_by_source = {
        int(item.source_message_id): item
        for item in db.execute(select(ContactPredictionEvent).where(ContactPredictionEvent.source_message_id.is_not(None))).scalars().all()
        if item.source_message_id is not None
    }
    inserted = 0
    updated = 0
    cluster_updates: dict[str, dict[str, Any]] = {}
    for payload in extracted:
        payload["direction"] = _normalize_event_direction(payload.get("direction"))
        source_message_id = payload.get("source_message_id")
        row = existing_by_source.get(int(source_message_id)) if source_message_id is not None else None
        if row and not force:
            continue
        if not row:
            row = ContactPredictionEvent(**payload)
            db.add(row)
            inserted += 1
        else:
            for key, value in payload.items():
                setattr(row, key, value)
            db.add(row)
            updated += 1
        cluster_id = str(payload.get("event_cluster_id") or "").strip()
        if cluster_id:
            cluster_payload = cluster_updates.setdefault(
                cluster_id,
                {
                    "id": cluster_id,
                    "contact_id": payload.get("contact_id"),
                    "topic_key": payload.get("topic_key"),
                    "event_kind": payload.get("event_kind"),
                    "direction": payload.get("direction"),
                    "primary_asset_code": payload.get("asset_code"),
                    "message_count": 0,
                    "merged_event_count": 0,
                    "first_seen_at": payload.get("source_time"),
                    "last_seen_at": payload.get("source_time"),
                    "cluster_status": "active",
                },
            )
            cluster_payload["message_count"] += 1
            cluster_payload["merged_event_count"] += 1
            source_time = payload.get("source_time")
            if source_time and (cluster_payload["first_seen_at"] is None or source_time < cluster_payload["first_seen_at"]):
                cluster_payload["first_seen_at"] = source_time
            if source_time and (cluster_payload["last_seen_at"] is None or source_time > cluster_payload["last_seen_at"]):
                cluster_payload["last_seen_at"] = source_time
    for cluster_id, payload in cluster_updates.items():
        cluster = db.get(ContactSignalCluster, cluster_id)
        if not cluster:
            cluster = ContactSignalCluster(**payload)
        else:
            for key, value in payload.items():
                setattr(cluster, key, value)
        db.add(cluster)
    db.commit()
    return {"contacts": len(focus_ids), "messages": len(rows), "inserted": inserted, "updated": updated}


def backfill_prediction_event_metadata(
    db: Session,
    *,
    contact_ids: set[str] | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    query = select(ContactPredictionEvent)
    if contact_ids:
        query = query.where(ContactPredictionEvent.contact_id.in_(list(contact_ids)))
    query = query.order_by(ContactPredictionEvent.source_time.asc(), ContactPredictionEvent.id.asc())
    if limit is not None:
        query = query.limit(limit)
    events = db.execute(query).scalars().all()

    updated = 0
    cluster_updates: dict[str, dict[str, Any]] = {}
    for event in events:
        raw_text = str(event.normalized_text or event.raw_text or "").strip()
        if not raw_text:
            continue
        event_kind = _derive_event_kind(raw_text, event.direction)
        is_actionable = _is_actionable_event(event_kind, event.direction, raw_text)
        topic_key = _derive_topic_key(event.asset_type, event.asset_code, event.asset_name, raw_text)
        signal_strength = round(float(event.signal_strength or event.confidence or _guess_confidence(raw_text, event.direction)), 4)
        source_type = str(event.source_type or "wechat")
        benchmark_code = _select_benchmark_code(event.asset_type, event.asset_code, raw_text)
        cluster_id = _build_cluster_id(
            str(event.contact_id or ""),
            topic_key,
            str(event.direction or ""),
            event_kind,
            event.source_time,
            event.horizon_flags or DEFAULT_HORIZON_FLAGS,
        )

        changed = False
        if event.event_kind != event_kind:
            event.event_kind = event_kind
            changed = True
        if event.is_actionable is None or bool(event.is_actionable) != bool(is_actionable):
            event.is_actionable = is_actionable
            changed = True
        if event.topic_key != topic_key:
            event.topic_key = topic_key
            changed = True
        if float(event.signal_strength or 0.0) != float(signal_strength):
            event.signal_strength = signal_strength
            changed = True
        if event.source_type != source_type:
            event.source_type = source_type
            changed = True
        if event.benchmark_code != benchmark_code:
            event.benchmark_code = benchmark_code
            changed = True
        if event.event_cluster_id != cluster_id:
            event.event_cluster_id = cluster_id
            changed = True
        if changed:
            updated += 1
            db.add(event)

        cluster_payload = cluster_updates.setdefault(
            cluster_id,
            {
                "id": cluster_id,
                "contact_id": event.contact_id,
                "topic_key": topic_key,
                "event_kind": event_kind,
                "direction": event.direction,
                "primary_asset_code": event.asset_code,
                "message_count": 0,
                "merged_event_count": 0,
                "first_seen_at": event.source_time,
                "last_seen_at": event.source_time,
                "cluster_status": "active",
            },
        )
        cluster_payload["message_count"] += 1
        cluster_payload["merged_event_count"] += 1
        if event.source_time and (cluster_payload["first_seen_at"] is None or event.source_time < cluster_payload["first_seen_at"]):
            cluster_payload["first_seen_at"] = event.source_time
        if event.source_time and (cluster_payload["last_seen_at"] is None or event.source_time > cluster_payload["last_seen_at"]):
            cluster_payload["last_seen_at"] = event.source_time

    for cluster_id, payload in cluster_updates.items():
        cluster = db.get(ContactSignalCluster, cluster_id)
        if not cluster:
            cluster = ContactSignalCluster(**payload)
        else:
            for key, value in payload.items():
                setattr(cluster, key, value)
        db.add(cluster)

    db.commit()
    return {"events": len(events), "updated": updated, "clusters": len(cluster_updates)}


def evaluate_prediction_events_to_db(
    db: Session,
    *,
    contact_ids: set[str] | None = None,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    as_of = as_of or datetime.utcnow()
    query = select(ContactPredictionEvent)
    if contact_ids:
        query = query.where(ContactPredictionEvent.contact_id.in_(list(contact_ids)))
    events = db.execute(query.order_by(ContactPredictionEvent.source_time.asc())).scalars().all()
    market_cfg = load_market_data_config(db)
    eval_map: dict[tuple[int, str], ContactPredictionEvaluation] = {
        (row.event_id, row.horizon_code): row
        for row in db.execute(select(ContactPredictionEvaluation)).scalars().all()
    }
    series_cache: dict[tuple[str, str | None], list[dict[str, Any]]] = {}

    matured_events: list[ContactPredictionEvent] = []
    series_keys: set[tuple[str, str | None]] = set()
    if events:
        min_source_time = min((event.source_time for event in events if event.source_time), default=as_of) or as_of
        global_start = min_source_time - timedelta(days=5)
        global_end = as_of + timedelta(days=5)
        for event in events:
            if not event.source_time or not event.asset_code:
                continue
            raw_text = str(event.normalized_text or event.raw_text or "")
            event_kind = str(event.event_kind or _derive_event_kind(raw_text, event.direction) or "")
            if event.is_actionable is False:
                continue
            if event.is_actionable is None and not _is_actionable_event(event_kind, event.direction, raw_text):
                continue
            flags = event.horizon_flags or DEFAULT_HORIZON_FLAGS
            if not any(flags.get(code) and as_of >= (event.source_time + timedelta(days=days)) for code, days in HORIZON_DAYS.items()):
                continue
            matured_events.append(event)
            series_keys.add((event.asset_type, event.asset_code))
            if event.benchmark_code:
                series_keys.add(("index", event.benchmark_code))

        if series_keys:
            with ThreadPoolExecutor(max_workers=min(8, max(1, len(series_keys)))) as executor:
                future_map = {
                    executor.submit(fetch_market_series, asset_type, asset_code, global_start, global_end, config=market_cfg): (asset_type, asset_code)
                    for asset_type, asset_code in series_keys
                }
                for future in as_completed(future_map):
                    key = future_map[future]
                    try:
                        series_cache[key] = future.result()
                    except Exception:
                        series_cache[key] = []

    def cached_fetcher(asset_type: str, asset_code: str | None, start_date: datetime, end_date: datetime) -> list[dict[str, Any]]:
        key = (asset_type, asset_code)
        if key not in series_cache:
            series_cache[key] = fetch_market_series(asset_type, asset_code, start_date, end_date, config=market_cfg)
        return series_cache[key]

    evaluated = 0
    updated = 0
    for event in matured_events:
        payload = {
            "id": event.id,
            "source_time": event.source_time,
            "asset_type": event.asset_type,
            "asset_code": event.asset_code,
            "benchmark_code": event.benchmark_code,
            "direction": event.direction,
            "event_kind": event.event_kind,
            "horizon_flags": event.horizon_flags or DEFAULT_HORIZON_FLAGS,
        }
        results = evaluate_prediction_event(payload, as_of=as_of, price_fetcher=cached_fetcher)
        if not results:
            continue
        event.status = "evaluated"
        for item in results:
            key = (int(event.id), str(item["horizon_code"]))
            row = eval_map.get(key)
            if not row:
                row = ContactPredictionEvaluation(event_id=event.id, horizon_code=str(item["horizon_code"]))
                evaluated += 1
            else:
                updated += 1
            row.benchmark_code = item.get("benchmark_code")
            row.entry_price = item.get("entry_price")
            row.evaluation_price = item.get("evaluation_price")
            row.benchmark_entry = item.get("benchmark_entry")
            row.benchmark_evaluation = item.get("benchmark_evaluation")
            row.absolute_return = item.get("absolute_return")
            row.excess_return = item.get("excess_return")
            row.direction_hit = item.get("direction_hit")
            row.event_score = item.get("event_score")
            row.evaluated_at = item.get("evaluated_at")
            meta = dict(item.get("meta") or {})
            meta["market_provider_order"] = market_cfg.get("provider_preference")
            row.meta = meta
            db.add(row)
            eval_map[key] = row
        db.add(event)
    db.commit()
    return {"events": len(events), "evaluated": evaluated, "updated": updated}


def recompute_contact_scores(db: Session, *, contact_ids: set[str] | None = None, as_of: datetime | None = None) -> dict[str, Any]:
    as_of = as_of or datetime.utcnow()
    contacts_query = select(Contact)
    if contact_ids:
        contacts_query = contacts_query.where(Contact.id.in_(list(contact_ids)))
    contacts = db.execute(contacts_query).scalars().all()
    contact_id_set = {str(contact.id) for contact in contacts if getattr(contact, "id", None)}
    evaluations = db.execute(select(ContactPredictionEvaluation)).scalars().all()
    events = (
        db.execute(select(ContactPredictionEvent).where(ContactPredictionEvent.contact_id.in_(list(contact_id_set)))).scalars().all()
        if contact_id_set
        else []
    )
    evals_by_contact: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for evaluation in evaluations:
        event = evaluation.event
        if not event or not event.contact_id:
            continue
        evals_by_contact[str(event.contact_id)].append(
            {
                "horizon_code": evaluation.horizon_code,
                "direction_hit": evaluation.direction_hit,
                "excess_return": evaluation.excess_return,
                "event_score": evaluation.event_score,
                "cluster_id": event.event_cluster_id,
                "event_kind": event.event_kind,
                "is_actionable": event.is_actionable,
            }
        )
    events_by_contact: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        cid = str(event.contact_id or "").strip()
        if not cid:
            continue
        events_by_contact[cid].append(
            {
                "event_id": event.id,
                "source_time": event.source_time,
                "event_kind": event.event_kind,
                "is_actionable": event.is_actionable,
                "topic_key": event.topic_key,
                "confidence": event.confidence,
                "signal_strength": event.signal_strength,
                "asset_code": event.asset_code,
                "event_cluster_id": event.event_cluster_id,
            }
        )

    updated = 0
    for contact in contacts:
        manual_rating = resolve_manual_rating(contact)
        summary = summarize_contact_score(
            contact_id=contact.id,
            evaluations=evals_by_contact.get(contact.id, []),
            manual_rating=manual_rating,
            event_rows=events_by_contact.get(contact.id, []),
            as_of=as_of,
        )
        stats = resolve_contact_stats(contact)
        stats.update(
            {
                "manual_rating": summary["manual_rating"],
                "auto_rating": summary["auto_rating"],
                "final_rating": summary["final_rating"],
                "accuracy_score": summary["accuracy_score"],
                "service_value_score": summary["service_value_score"],
                "score_breakdown": summary["score_breakdown"],
                "value_breakdown": summary["value_breakdown"],
                "sample_size": summary["sample_size"],
                "hit_rate_overall": summary["hit_rate_overall"],
                "accuracy_by_horizon": summary["accuracy_by_horizon"],
                "excess_mean": summary["excess_mean"],
                "stability_score": summary["stability_score"],
                "frequency_penalty": summary["frequency_penalty"],
                "last_scored_at": as_of.isoformat(),
                "scoring_version": SCORING_VERSION,
            }
        )
        contact.stats = stats
        contact.rating = int(round(summary["final_rating"]))
        db.add(contact)
        db.add(
            ContactScoreSnapshot(
                contact_id=contact.id,
                score_total=float(summary["final_rating"]),
                score_auto=float(summary["auto_rating"]),
                score_manual=float(summary["manual_rating"]),
                accuracy_score=float(summary["accuracy_score"]),
                service_value_score=float(summary["service_value_score"]),
                direction_accuracy_score=float(summary["score_breakdown"]["direction_accuracy_score"]),
                excess_return_score=float(summary["score_breakdown"]["excess_return_score"]),
                risk_alert_score=float(summary["score_breakdown"]["risk_alert_score"]),
                consistency_score=float(summary["score_breakdown"]["consistency_score"]),
                hit_rate_overall=float(summary["hit_rate_overall"]),
                accuracy_1m=float(summary["accuracy_by_horizon"]["1m"]),
                accuracy_3m=float(summary["accuracy_by_horizon"]["3m"]),
                accuracy_1y=float(summary["accuracy_by_horizon"]["1y"]),
                excess_mean=float(summary["excess_mean"]),
                stability_score=float(summary["stability_score"]),
                frequency_penalty=float(summary["frequency_penalty"]),
                sample_size=int(summary["sample_size"]),
                as_of=as_of,
            )
        )
        db.add(
            ContactValueMetricSnapshot(
                contact_id=contact.id,
                roadshow_value_score=float(summary["value_breakdown"]["roadshow_value_score"]),
                exchange_value_score=float(summary["value_breakdown"]["exchange_value_score"]),
                timeliness_score=float(summary["value_breakdown"]["timeliness_score"]),
                coverage_depth_score=float(summary["value_breakdown"]["coverage_depth_score"]),
                signal_cleanliness_score=float(summary["value_breakdown"]["signal_cleanliness_score"]),
                as_of=as_of,
                meta={
                    "service_value_score": float(summary["service_value_score"]),
                    "sample_size": int(summary["sample_size"]),
                },
            )
        )
        updated += 1
    db.commit()
    return {"contacts": len(contacts), "updated": updated}


def run_full_scoring_cycle(
    db: Session,
    *,
    time_from: datetime | None = None,
    time_to: datetime | None = None,
    contact_ids: set[str] | None = None,
    force_extract: bool = False,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    focus_ids = contact_ids or get_focus_contact_ids(db)
    extracted = extract_prediction_events_to_db(db, time_from=time_from, time_to=time_to, contact_ids=focus_ids, force=force_extract)
    backfilled = backfill_prediction_event_metadata(db, contact_ids=focus_ids)
    evaluated = evaluate_prediction_events_to_db(db, contact_ids=focus_ids, as_of=as_of)
    recomputed = recompute_contact_scores(db, contact_ids=focus_ids, as_of=as_of)
    return {"focus_contacts": len(focus_ids), "extract": extracted, "backfill": backfilled, "evaluate": evaluated, "recompute": recomputed}


def build_contact_scorecard(db: Session, contact_id: str, *, limit: int = 50) -> dict[str, Any] | None:
    contact = db.get(Contact, contact_id)
    if not contact:
        return None
    latest_snapshot = db.execute(
        select(ContactScoreSnapshot)
        .where(ContactScoreSnapshot.contact_id == contact_id)
        .order_by(ContactScoreSnapshot.as_of.desc())
        .limit(1)
    ).scalars().first()
    timeline = db.execute(
        select(ContactScoreSnapshot)
        .where(ContactScoreSnapshot.contact_id == contact_id)
        .order_by(ContactScoreSnapshot.as_of.asc())
        .limit(30)
    ).scalars().all()
    all_events = db.execute(
        select(ContactPredictionEvent)
        .where(ContactPredictionEvent.contact_id == contact_id)
        .order_by(ContactPredictionEvent.source_time.desc())
    ).scalars().all()
    latest_message_time = db.execute(
        select(func.max(Message.timestamp)).where(Message.sender_id == contact_id)
    ).scalar()
    events = db.execute(
        select(ContactPredictionEvent)
        .where(ContactPredictionEvent.contact_id == contact_id)
        .order_by(ContactPredictionEvent.source_time.desc())
        .limit(limit)
    ).scalars().all()

    stats = resolve_contact_stats(contact)
    score_block = {
        "manual_rating": float(stats.get("manual_rating", resolve_manual_rating(contact))),
        "auto_rating": float(stats.get("auto_rating", resolve_auto_rating(contact) or 50.0)),
        "final_rating": float(contact.rating or stats.get("final_rating") or 50.0),
        "accuracy_score": float(stats.get("accuracy_score", latest_snapshot.accuracy_score if latest_snapshot and latest_snapshot.accuracy_score is not None else 50.0) or 50.0),
        "service_value_score": float(stats.get("service_value_score", latest_snapshot.service_value_score if latest_snapshot and latest_snapshot.service_value_score is not None else 50.0) or 50.0),
        "sample_size": int(stats.get("sample_size", latest_snapshot.sample_size if latest_snapshot else 0) or 0),
        "hit_rate_overall": float(stats.get("hit_rate_overall", latest_snapshot.hit_rate_overall if latest_snapshot else 0.0) or 0.0),
        "accuracy_by_horizon": stats.get(
            "accuracy_by_horizon",
            {
                "1m": float(latest_snapshot.accuracy_1m if latest_snapshot and latest_snapshot.accuracy_1m is not None else 0.0),
                "3m": float(latest_snapshot.accuracy_3m if latest_snapshot and latest_snapshot.accuracy_3m is not None else 0.0),
                "1y": float(latest_snapshot.accuracy_1y if latest_snapshot and latest_snapshot.accuracy_1y is not None else 0.0),
            },
        ),
        "excess_mean": float(stats.get("excess_mean", latest_snapshot.excess_mean if latest_snapshot else 0.0) or 0.0),
        "stability_score": float(stats.get("stability_score", latest_snapshot.stability_score if latest_snapshot else 50.0) or 50.0),
        "frequency_penalty": float(stats.get("frequency_penalty", latest_snapshot.frequency_penalty if latest_snapshot else 0.0) or 0.0),
        "last_scored_at": stats.get("last_scored_at") or (latest_snapshot.as_of.isoformat() if latest_snapshot else None),
        "score_breakdown": stats.get(
            "score_breakdown",
            {
                "direction_accuracy_score": float(latest_snapshot.direction_accuracy_score if latest_snapshot and latest_snapshot.direction_accuracy_score is not None else 50.0),
                "excess_return_score": float(latest_snapshot.excess_return_score if latest_snapshot and latest_snapshot.excess_return_score is not None else 50.0),
                "risk_alert_score": float(latest_snapshot.risk_alert_score if latest_snapshot and latest_snapshot.risk_alert_score is not None else 50.0),
                "consistency_score": float(latest_snapshot.consistency_score if latest_snapshot and latest_snapshot.consistency_score is not None else 50.0),
            },
        ),
        "value_breakdown": stats.get(
            "value_breakdown",
            {
                "roadshow_value_score": 50.0,
                "exchange_value_score": 50.0,
                "timeliness_score": 50.0,
                "coverage_depth_score": 50.0,
                "signal_cleanliness_score": 50.0,
            },
        ),
    }
    as_of = datetime.utcnow()

    prediction_rows = []
    for event in events:
        prediction_rows.append(
            {
                "id": event.id,
                "source_message_id": event.source_message_id,
                "source_time": event.source_time.isoformat() if event.source_time else None,
                "asset_type": event.asset_type,
                "asset_code": event.asset_code,
                "asset_name": event.asset_name,
                "direction": event.direction,
                "confidence": event.confidence,
                "benchmark_code": event.benchmark_code,
                "benchmark_name": _benchmark_label(event.benchmark_code),
                "event_kind": event.event_kind,
                "topic_key": event.topic_key,
                "event_cluster_id": event.event_cluster_id,
                "normalized_text": event.normalized_text,
                "raw_text": event.raw_text,
                "thesis_card": _build_thesis_card(event),
                "verification_schedule": _build_verification_schedule(event, as_of=as_of),
                "evaluations": [
                    {
                        "id": ev.id,
                        "horizon_code": ev.horizon_code,
                        "direction_hit": ev.direction_hit,
                        "absolute_return": ev.absolute_return,
                        "excess_return": ev.excess_return,
                        "event_score": ev.event_score,
                        "evaluated_at": ev.evaluated_at.isoformat() if ev.evaluated_at else None,
                        "entry_price": ev.entry_price,
                        "evaluation_price": ev.evaluation_price,
                    }
                    for ev in sorted(event.evaluations, key=lambda x: x.horizon_code or "")
                ],
            }
        )

    asset_buckets: dict[str, dict[str, Any]] = {}
    horizon_buckets: dict[str, dict[str, Any]] = {}
    recent_hits: list[dict[str, Any]] = []
    recent_misses: list[dict[str, Any]] = []
    pending_predictions: list[dict[str, Any]] = []
    horizon_event_groups: dict[str, dict[str, list[dict[str, Any]]]] = {key: {"hits": [], "misses": []} for key in ("1m", "3m", "1y")}
    event_timeline: list[dict[str, Any]] = []

    def _asset_bucket_key(ev: ContactPredictionEvent) -> str:
        return str(ev.asset_name or ev.asset_code or "未识别标的")

    def _fmt_event_row(ev: ContactPredictionEvent, evaluation: ContactPredictionEvaluation | None = None) -> dict[str, Any]:
        event_kind = _classify_contact_event_kind(ev.normalized_text or ev.raw_text or "")
        payload = {
            "event_id": ev.id,
            "source_time": ev.source_time.isoformat() if ev.source_time else None,
            "asset_type": ev.asset_type,
            "asset_code": ev.asset_code,
            "asset_name": ev.asset_name or ev.asset_code or "未识别标的",
            "direction": ev.direction,
            "confidence": ev.confidence,
            "source_message_id": ev.source_message_id,
            "benchmark_code": ev.benchmark_code,
            "benchmark_name": _benchmark_label(ev.benchmark_code),
            "normalized_text": ev.normalized_text or ev.raw_text or "",
            "event_kind": event_kind,
            "is_actionable": ev.is_actionable,
        }
        payload["verification_schedule"] = _build_verification_schedule(ev, as_of=as_of)
        payload["next_verification"] = payload["verification_schedule"].get("next")
        if evaluation is not None:
            payload.update(
                {
                    "horizon_code": evaluation.horizon_code,
                    "direction_hit": evaluation.direction_hit,
                    "absolute_return": evaluation.absolute_return,
                    "excess_return": evaluation.excess_return,
                    "event_score": evaluation.event_score,
                }
            )
        return payload

    for ev in all_events:
        base_row = _fmt_event_row(ev)
        event_timeline.append(base_row)
        evals = sorted(ev.evaluations, key=lambda row: row.horizon_code or "")
        if not evals:
            pending_predictions.append(base_row)
            continue
        bucket = asset_buckets.setdefault(
            _asset_bucket_key(ev),
            {
                "asset_name": ev.asset_name or ev.asset_code or "未识别标的",
                "asset_code": ev.asset_code,
                "asset_type": ev.asset_type,
                "event_count": 0,
                "hit_count": 0,
                "score_sum": 0.0,
                "excess_sum": 0.0,
                "excess_count": 0,
                "latest_source_time": ev.source_time,
            },
        )
        bucket["event_count"] += len(evals)
        if ev.source_time and (bucket["latest_source_time"] is None or ev.source_time > bucket["latest_source_time"]):
            bucket["latest_source_time"] = ev.source_time
        for evaluation in evals:
            hz = str(evaluation.horizon_code or "")
            hz_bucket = horizon_buckets.setdefault(
                hz,
                {"horizon_code": hz, "samples": 0, "hit_count": 0, "score_sum": 0.0, "excess_sum": 0.0, "excess_count": 0},
            )
            hz_bucket["samples"] += 1
            if bool(evaluation.direction_hit):
                hz_bucket["hit_count"] += 1
                bucket["hit_count"] += 1
                event_row = _fmt_event_row(ev, evaluation)
                recent_hits.append(event_row)
                if hz in horizon_event_groups:
                    horizon_event_groups[hz]["hits"].append(event_row)
            else:
                event_row = _fmt_event_row(ev, evaluation)
                recent_misses.append(event_row)
                if hz in horizon_event_groups:
                    horizon_event_groups[hz]["misses"].append(event_row)
            score_value = float(evaluation.event_score or 0.0)
            excess_value = evaluation.excess_return
            hz_bucket["score_sum"] += score_value
            bucket["score_sum"] += score_value
            if excess_value is not None:
                hz_bucket["excess_sum"] += float(excess_value)
                hz_bucket["excess_count"] += 1
                bucket["excess_sum"] += float(excess_value)
                bucket["excess_count"] += 1

    asset_summary = []
    for item in asset_buckets.values():
        samples = int(item["event_count"] or 0)
        hit_count = int(item["hit_count"] or 0)
        excess_count = int(item["excess_count"] or 0)
        asset_summary.append(
            {
                "asset_name": item["asset_name"],
                "asset_code": item["asset_code"],
                "asset_type": item["asset_type"],
                "samples": samples,
                "hit_rate": (hit_count / samples) if samples else 0.0,
                "avg_score": (float(item["score_sum"]) / samples) if samples else 0.0,
                "avg_excess": (float(item["excess_sum"]) / excess_count) if excess_count else None,
                "latest_source_time": item["latest_source_time"].isoformat() if item["latest_source_time"] else None,
            }
        )
    asset_summary.sort(key=lambda row: ((row["avg_score"] or 0.0), (row["samples"] or 0)), reverse=True)

    horizon_summary = []
    for key in ("1m", "3m", "1y"):
        item = horizon_buckets.get(key) or {"horizon_code": key, "samples": 0, "hit_count": 0, "score_sum": 0.0, "excess_sum": 0.0, "excess_count": 0}
        samples = int(item["samples"] or 0)
        hit_count = int(item["hit_count"] or 0)
        excess_count = int(item["excess_count"] or 0)
        horizon_summary.append(
            {
                "horizon_code": key,
                "samples": samples,
                "hit_rate": (hit_count / samples) if samples else 0.0,
                "avg_score": (float(item["score_sum"]) / samples) if samples else 0.0,
                "avg_excess": (float(item["excess_sum"]) / excess_count) if excess_count else None,
            }
        )

    def _sort_recent(rows: list[dict[str, Any]], reverse: bool) -> list[dict[str, Any]]:
        return sorted(
            rows,
            key=lambda row: (
                float(row.get("event_score") or 0.0),
                str(row.get("source_time") or ""),
            ),
            reverse=reverse,
        )[:6]

    bullish_count = sum(1 for ev in all_events if str(ev.direction or "") == "bullish")
    bearish_count = sum(1 for ev in all_events if str(ev.direction or "") == "bearish")
    market_curve = None
    market_curves: list[dict[str, Any]] = []
    market_curve_missing_assets: list[dict[str, Any]] = []
    curve_assets: list[dict[str, Any]] = []
    selected_curve_asset_keys: set[tuple[str, str]] = set()

    # New recommendations need to be visible immediately, before they have waited
    # long enough to receive a 1M/3M/1Y evaluation. De-duplicate repeated calls on
    # the same asset, then use the historical high-score list to fill remaining slots.
    for event in all_events:
        asset_code = str(event.asset_code or "").strip()
        asset_type = str(event.asset_type or "").strip()
        if not asset_code or not asset_type or event.evaluations:
            continue
        asset_key = (asset_type, asset_code)
        if asset_key in selected_curve_asset_keys:
            continue
        selected_curve_asset_keys.add(asset_key)
        curve_assets.append(
            {
                "asset_name": event.asset_name or asset_code,
                "asset_code": asset_code,
                "asset_type": asset_type,
                "latest_source_time": event.source_time.isoformat() if event.source_time else None,
                "is_pending": True,
            }
        )
        if len(curve_assets) >= 4:
            break

    if len(curve_assets) < 4:
        for item in asset_summary:
            asset_code = str(item.get("asset_code") or "").strip()
            asset_type = str(item.get("asset_type") or "").strip()
            if not asset_code or not asset_type:
                continue
            asset_key = (asset_type, asset_code)
            if asset_key in selected_curve_asset_keys:
                continue
            selected_curve_asset_keys.add(asset_key)
            curve_assets.append({**item, "is_pending": False})
            if len(curve_assets) >= 4:
                break
    market_config = None
    if curve_assets:
        try:
            market_config = load_market_data_config(db)
        except Exception:
            market_config = None

    def _build_curve_anchor_points(anchor_events: list[ContactPredictionEvent]) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        for ev in anchor_events:
            if not ev.source_time:
                continue
            source_date = ev.source_time.date().isoformat()
            direction = str(ev.direction or "neutral")
            key = (source_date, direction)
            row = grouped.setdefault(
                key,
                {
                    "date": source_date,
                    "source_time": ev.source_time.isoformat(),
                    "direction": direction,
                    "count": 0,
                    "labels": [],
                },
            )
            row["count"] += 1
            label_text = str(ev.normalized_text or ev.raw_text or "").strip()
            if label_text and len(row["labels"]) < 3:
                row["labels"].append(label_text)
            if ev.source_time.isoformat() < str(row.get("source_time") or ""):
                row["source_time"] = ev.source_time.isoformat()
        direction_label = {"bullish": "看好", "bearish": "看空", "neutral": "中性"}
        return [
            {
                "date": row["date"],
                "source_time": row["source_time"],
                "direction": row["direction"],
                "count": row["count"],
                "label": f"{direction_label.get(str(row['direction']), '观点')} ×{row['count']}" if int(row["count"]) > 1 else direction_label.get(str(row["direction"]), "观点"),
                "samples": row["labels"],
            }
            for row in sorted(grouped.values(), key=lambda item: (str(item.get("date") or ""), str(item.get("direction") or "")))
        ][:16]

    for primary_asset in curve_assets:
        anchor_events = [
            ev
            for ev in all_events
            if str(ev.asset_code or "") == str(primary_asset.get("asset_code") or "")
            and str(ev.asset_type or "") == str(primary_asset.get("asset_type") or "")
        ]
        curve_start = min(
            (ev.source_time for ev in anchor_events if ev.source_time is not None),
            default=datetime.utcnow() - timedelta(days=180),
        ) - timedelta(days=10)
        curve_end = datetime.utcnow()
        try:
            curve_items = fetch_market_series(
                str(primary_asset.get("asset_type") or ""),
                str(primary_asset.get("asset_code") or ""),
                curve_start,
                curve_end,
                config=market_config,
            )
        except Exception:
            curve_items = []
        if curve_items:
            latest_item = max(
                (
                    item
                    for item in curve_items
                    if str(item.get("date") or "").strip() and item.get("close") is not None
                ),
                key=lambda item: str(item.get("date") or ""),
                default=None,
            )
            latest_market_date = str((latest_item or {}).get("date") or "")[:10] or None
            latest_close = None
            if latest_item is not None:
                try:
                    latest_close = float(latest_item.get("close"))
                except (TypeError, ValueError):
                    latest_close = None
            market_date = _parse_record_date(latest_market_date or "")
            data_age_days = max(0, (as_of.date() - market_date).days) if market_date else None
            latest_recommendation_time = max(
                (event.source_time for event in anchor_events if event.source_time is not None),
                default=None,
            )
            curve_payload = {
                "asset_name": primary_asset.get("asset_name"),
                "asset_code": primary_asset.get("asset_code"),
                "asset_type": primary_asset.get("asset_type"),
                "count": len(curve_items),
                "items": curve_items[-180:],
                "anchor_points": _build_curve_anchor_points(anchor_events),
                "latest_recommendation_time": latest_recommendation_time.isoformat() if latest_recommendation_time else None,
                "is_pending": bool(primary_asset.get("is_pending")),
                "latest_market_date": latest_market_date,
                "latest_close": latest_close,
                "data_age_days": data_age_days,
            }
            market_curves.append(curve_payload)
            if market_curve is None:
                market_curve = curve_payload
        else:
            market_curve_missing_assets.append(
                {
                    "asset_name": primary_asset.get("asset_name"),
                    "asset_code": primary_asset.get("asset_code"),
                    "asset_type": primary_asset.get("asset_type"),
                    "reason": "行情源未返回有效日线",
                }
            )

    compact_horizon_groups = {
        key: {
            "hits": _sort_recent(value["hits"], True),
            "misses": _sort_recent(value["misses"], False),
        }
        for key, value in horizon_event_groups.items()
    }
    event_timeline = sorted(
        event_timeline,
        key=lambda row: str(row.get("source_time") or ""),
        reverse=True,
    )[:20]
    top_hits = _sort_recent(recent_hits, True)
    top_misses = _sort_recent(recent_misses, False)
    case_cards = [_build_case_card(row, "hit") for row in top_hits[:3]] + [_build_case_card(row, "miss") for row in top_misses[:3]]
    actionable_recent_hits = _filter_actionable_rows(recent_hits)
    annual_hit_list = sorted(
        [
            {
                "asset_code": row.get("asset_code"),
                "asset_name": row.get("asset_name"),
                "event_kind": row.get("event_kind"),
                "direction": row.get("direction"),
                "horizon_code": row.get("horizon_code"),
                "event_score": row.get("event_score"),
                "absolute_return": row.get("absolute_return"),
                "excess_return": row.get("excess_return"),
                "source_time": row.get("source_time"),
                "summary": row.get("normalized_text") or "",
            }
            for row in actionable_recent_hits
            if row.get("source_time")
        ],
        key=lambda item: (str(item.get("source_time") or ""), float(item.get("event_score") or 0.0)),
        reverse=True,
    )[:20]
    annual_asset_buckets: dict[str, dict[str, Any]] = {}
    for row in actionable_recent_hits:
        asset_code = str(row.get("asset_code") or "").strip() or str(row.get("asset_name") or "未识别标的")
        bucket = annual_asset_buckets.setdefault(
            asset_code,
            {
                "asset_code": row.get("asset_code"),
                "asset_name": row.get("asset_name"),
                "event_kind": row.get("event_kind"),
                "samples": 0,
                "score_sum": 0.0,
                "excess_sum": 0.0,
                "positive_count": 0,
            },
        )
        bucket["samples"] += 1
        bucket["score_sum"] += float(row.get("event_score") or 0.0)
        if row.get("excess_return") is not None:
            bucket["excess_sum"] += float(row.get("excess_return") or 0.0)
            if float(row.get("excess_return") or 0.0) > 0:
                bucket["positive_count"] += 1
    annual_asset_leaders = sorted(
        [
            {
                "asset_code": item.get("asset_code"),
                "asset_name": item.get("asset_name"),
                "event_kind": item.get("event_kind"),
                "samples": item.get("samples"),
                "avg_score": round(float(item.get("score_sum") or 0.0) / max(int(item.get("samples") or 1), 1), 2),
                "avg_excess_return": round(float(item.get("excess_sum") or 0.0) / max(int(item.get("samples") or 1), 1), 6),
                "positive_count": item.get("positive_count"),
            }
            for item in annual_asset_buckets.values()
        ],
        key=lambda item: (float(item.get("avg_score") or 0.0), float(item.get("avg_excess_return") or 0.0), int(item.get("samples") or 0)),
        reverse=True,
    )[:10]
    return_distribution = _build_return_distribution(recent_hits + recent_misses)
    score_explanation = _build_score_explanation(
        score_block,
        asset_summary=asset_summary,
        top_hits=top_hits,
        top_misses=top_misses,
        pending_predictions=pending_predictions,
        return_distribution=return_distribution,
    )
    sub_scores = _build_contact_sub_scores(all_events, recent_hits, recent_misses)
    recommended_action = _build_contact_action_recommendation(sub_scores)
    cluster_topics_map: dict[str, dict[str, Any]] = {}
    for ev in all_events:
        cluster_id = str(ev.event_cluster_id or "").strip() or str(ev.id)
        topic_row = cluster_topics_map.setdefault(
            cluster_id,
            {
                "cluster_id": cluster_id,
                "topic_key": ev.topic_key or ev.topic or ev.asset_name or ev.asset_code,
                "event_kind": ev.event_kind,
                "direction": ev.direction,
                "message_count": 0,
                "first_seen_at": ev.source_time,
                "last_seen_at": ev.source_time,
                "asset_code": ev.asset_code,
            },
        )
        topic_row["message_count"] += 1
        if ev.source_time and (topic_row["first_seen_at"] is None or ev.source_time < topic_row["first_seen_at"]):
            topic_row["first_seen_at"] = ev.source_time
        if ev.source_time and (topic_row["last_seen_at"] is None or ev.source_time > topic_row["last_seen_at"]):
            topic_row["last_seen_at"] = ev.source_time
    cluster_topics = [
        {
            **row,
            "first_seen_at": row["first_seen_at"].isoformat() if row.get("first_seen_at") else None,
            "last_seen_at": row["last_seen_at"].isoformat() if row.get("last_seen_at") else None,
        }
        for row in sorted(
            cluster_topics_map.values(),
            key=lambda item: (item.get("last_seen_at") or datetime.min, item.get("message_count") or 0),
            reverse=True,
        )[:10]
    ]

    try:
        db.query(ContactScoringCase).filter(ContactScoringCase.contact_id == contact_id).delete()
    except Exception:
        pass
    for row in top_hits[:3]:
        db.add(
            ContactScoringCase(
                contact_id=contact_id,
                case_type="hit",
                title=str(row.get("topic_key") or row.get("asset_name") or row.get("asset_code") or "命中案例"),
                summary=str(row.get("normalized_text") or ""),
                source_message_id=row.get("source_message_id"),
                topic_key=row.get("topic_key"),
                asset_code=row.get("asset_code"),
                horizon_code=row.get("horizon_code"),
                score_impact=row.get("event_score"),
                evidence_json=row,
            )
        )
    for row in top_misses[:3]:
        db.add(
            ContactScoringCase(
                contact_id=contact_id,
                case_type="miss",
                title=str(row.get("topic_key") or row.get("asset_name") or row.get("asset_code") or "失误案例"),
                summary=str(row.get("normalized_text") or ""),
                source_message_id=row.get("source_message_id"),
                topic_key=row.get("topic_key"),
                asset_code=row.get("asset_code"),
                horizon_code=row.get("horizon_code"),
                score_impact=row.get("event_score"),
                evidence_json=row,
            )
        )
    db.commit()

    return {
        "contact": {
            "id": contact.id,
            "name": contact.name,
            "alias": contact.alias,
            "rating": contact.rating,
            "labels": contact.labels,
            "focus": is_focus_contact(contact, db.get(ContactFocusSetting, contact.id)),
            "watch": resolve_contact_watch(contact),
        },
        "score": score_block,
        "analytics": {
            "total_predictions": len(all_events),
            "pending_predictions": len(pending_predictions),
            "bullish_predictions": bullish_count,
            "bearish_predictions": bearish_count,
            "horizon_summary": horizon_summary,
            "horizon_event_groups": compact_horizon_groups,
            "asset_summary": asset_summary[:10],
            "sub_scores": sub_scores,
            "score_explanation": score_explanation,
            "recommended_action": recommended_action,
            "recent_hits": top_hits,
            "recent_misses": top_misses,
            "top_hits": top_hits,
            "top_misses": top_misses,
            "case_cards": case_cards,
            "annual_hit_list": annual_hit_list,
            "annual_asset_leaders": annual_asset_leaders,
            "return_distribution": return_distribution,
            "cluster_topics": cluster_topics,
            "pending_items": pending_predictions[:8],
            "event_timeline": event_timeline,
        },
        "market_curve": market_curve,
        "market_curves": market_curves,
        "market_data_status": {
            "provider_order": market_data_provider_order(market_config),
            "provider_health": market_provider_health(market_config),
            "latest_message_time": latest_message_time.isoformat() if latest_message_time else None,
            "latest_prediction_time": all_events[0].source_time.isoformat() if all_events and all_events[0].source_time else None,
            "scoring_lag_days": (
                max(0, (latest_message_time - all_events[0].source_time).days)
                if latest_message_time and all_events and all_events[0].source_time
                else None
            ),
            "curve_assets_requested": len(curve_assets),
            "curve_assets_loaded": len(market_curves),
            "missing_assets": market_curve_missing_assets,
            "pending_not_in_score": len(pending_predictions),
        },
        "timeline": [
            {
                "as_of": row.as_of.isoformat() if row.as_of else None,
                "score_total": row.score_total,
                "score_auto": row.score_auto,
                "score_manual": row.score_manual,
                "accuracy_score": row.accuracy_score,
                "service_value_score": row.service_value_score,
                "sample_size": row.sample_size,
                "hit_rate_overall": row.hit_rate_overall,
            }
            for row in timeline
        ],
        "predictions": prediction_rows,
    }


def build_contact_score_summaries(db: Session, contact_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    ids = [str(item).strip() for item in contact_ids if str(item).strip()]
    if not ids:
        return {}

    contacts_by_id: dict[str, Contact] = {}
    for cid in ids:
        row = db.get(Contact, cid)
        if row:
            contacts_by_id[cid] = row

    summary_map: dict[str, dict[str, Any]] = {
        cid: {
                "total_predictions": 0,
                "pending_predictions": 0,
                "top_asset_name": None,
                "top_asset_code": None,
                "top_asset_type": None,
                "latest_view_at": None,
                "hit_rate_1m": None,
                "hit_rate_3m": None,
                "hit_rate_1y": None,
                "accuracy_score": None,
                "service_value_score": None,
                "sub_scores": {},
                "watching": bool(resolve_contact_watch(contacts_by_id[cid]).get("enabled")) if cid in contacts_by_id else False,
                "watch_status": resolve_contact_watch(contacts_by_id[cid]).get("status") if cid in contacts_by_id else "none",
                "watch_reason": resolve_contact_watch(contacts_by_id[cid]).get("reason") if cid in contacts_by_id else None,
                "watch_updated_at": resolve_contact_watch(contacts_by_id[cid]).get("updated_at") if cid in contacts_by_id else None,
            }
            for cid in ids
    }
    asset_buckets: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    horizon_buckets: dict[str, dict[str, dict[str, int]]] = defaultdict(dict)

    raw_events = db.execute(
        select(ContactPredictionEvent)
        .where(ContactPredictionEvent.contact_id.in_(ids))
        .order_by(ContactPredictionEvent.source_time.desc())
    ).scalars().all()
    events = [row for row in raw_events if getattr(row, "contact_id", None)]
    if not events:
        return summary_map

    event_ids = [int(row.id) for row in events if isinstance(getattr(row, "id", None), int)]
    evaluations = (
        db.execute(
            select(ContactPredictionEvaluation).where(ContactPredictionEvaluation.event_id.in_(event_ids))
        ).scalars().all()
        if event_ids
        else []
    )
    evals_by_event: dict[int, list[ContactPredictionEvaluation]] = defaultdict(list)
    for row in evaluations:
        evals_by_event[int(row.event_id)].append(row)

    for event in events:
        contact_id = str(event.contact_id or "")
        if not contact_id:
            continue
        summary = summary_map.setdefault(
            contact_id,
            {
                "total_predictions": 0,
                "pending_predictions": 0,
                "top_asset_name": None,
                "top_asset_code": None,
                "top_asset_type": None,
                "latest_view_at": None,
                "hit_rate_1m": None,
                "hit_rate_3m": None,
                "hit_rate_1y": None,
                "accuracy_score": None,
                "service_value_score": None,
            },
        )
        summary["total_predictions"] += 1
        if event.source_time and (
            summary["latest_view_at"] is None or str(event.source_time.isoformat()) > str(summary["latest_view_at"])
        ):
            summary["latest_view_at"] = event.source_time.isoformat()

        asset_key = str(event.asset_name or event.asset_code or "未识别标的")
        bucket = asset_buckets[contact_id].setdefault(
            asset_key,
            {
                "asset_name": event.asset_name or event.asset_code or "未识别标的",
                "asset_code": event.asset_code,
                "asset_type": event.asset_type,
                "mentions": 0,
                "samples": 0,
                "latest_view_at": event.source_time.isoformat() if event.source_time else "",
            },
        )
        bucket["mentions"] += 1
        if event.source_time and str(event.source_time.isoformat()) > str(bucket.get("latest_view_at") or ""):
            bucket["latest_view_at"] = event.source_time.isoformat()

        event_evals = evals_by_event.get(int(event.id), [])
        if not event_evals:
            summary["pending_predictions"] += 1
            continue
        for evaluation in event_evals:
            horizon_code = str(evaluation.horizon_code or "")
            if not horizon_code:
                continue
            hz_bucket = horizon_buckets[contact_id].setdefault(horizon_code, {"samples": 0, "hits": 0})
            hz_bucket["samples"] += 1
            if bool(evaluation.direction_hit):
                hz_bucket["hits"] += 1
            bucket["samples"] += 1

    events_by_contact: dict[str, list[ContactPredictionEvent]] = defaultdict(list)
    for event in events:
        if getattr(event, "contact_id", None):
            events_by_contact[str(event.contact_id)].append(event)

    for contact_id, summary in summary_map.items():
        contact = contacts_by_id.get(contact_id) or db.get(Contact, contact_id)
        watch_info = resolve_contact_watch(contact) if contact else {
            "enabled": False,
            "status": "none",
            "reason": None,
            "updated_at": None,
        }
        for horizon_code in ("1m", "3m", "1y"):
            hz_bucket = horizon_buckets.get(contact_id, {}).get(horizon_code)
            if hz_bucket and int(hz_bucket.get("samples") or 0) > 0:
                summary[f"hit_rate_{horizon_code}"] = float(hz_bucket["hits"] / hz_bucket["samples"])
        top_asset = None
        if asset_buckets.get(contact_id):
            ranked = sorted(
                asset_buckets[contact_id].values(),
                key=lambda row: (
                    int(row.get("samples") or 0),
                    int(row.get("mentions") or 0),
                    str(row.get("latest_view_at") or ""),
                ),
                reverse=True,
            )
            top_asset = ranked[0]
        if top_asset:
            summary["top_asset_name"] = top_asset.get("asset_name")
            summary["top_asset_code"] = top_asset.get("asset_code")
            summary["top_asset_type"] = top_asset.get("asset_type")
        summary["sub_scores"] = _build_contact_sub_scores(events_by_contact.get(contact_id, []), [], [], as_of=datetime.utcnow())
        action_payload = _build_contact_action_recommendation(summary["sub_scores"])
        summary["recommended_action"] = action_payload
        summary["warning_flags"] = action_payload.get("flags", [])
        contact_stats = resolve_contact_stats(contact) if contact else {}
        summary["accuracy_score"] = float(contact_stats.get("accuracy_score", contact_stats.get("auto_rating", contact.rating if contact else 50)) or 50.0) if contact else 50.0
        summary["service_value_score"] = float(contact_stats.get("service_value_score", 50.0) or 50.0) if contact else 50.0
        summary["watching"] = bool(watch_info.get("enabled"))
        summary["watch_status"] = watch_info.get("status")
        summary["watch_reason"] = watch_info.get("reason")
        summary["watch_updated_at"] = watch_info.get("updated_at")
    return summary_map


def build_scoring_overview(db: Session) -> dict[str, Any]:
    focus_ids = get_focus_contact_ids(db)
    total_events = db.execute(select(ContactPredictionEvent)).scalars().all()
    total_evals = db.execute(select(ContactPredictionEvaluation)).scalars().all()
    latest_snapshots = db.execute(select(ContactScoreSnapshot).order_by(ContactScoreSnapshot.as_of.desc())).scalars().all()
    latest_by_contact: dict[str, ContactScoreSnapshot] = {}
    for snap in latest_snapshots:
        if snap.contact_id not in latest_by_contact:
            latest_by_contact[snap.contact_id] = snap
    return {
        "focus_contacts": len(focus_ids),
        "prediction_events": len(total_events),
        "evaluations": len(total_evals),
        "scored_contacts": len(latest_by_contact),
        "top_contacts": [
            {
                "contact_id": snap.contact_id,
                "score_total": snap.score_total,
                "sample_size": snap.sample_size,
                "hit_rate_overall": snap.hit_rate_overall,
                "as_of": snap.as_of.isoformat() if snap.as_of else None,
            }
            for snap in sorted(latest_by_contact.values(), key=lambda x: (x.score_total or 0.0), reverse=True)[:10]
        ],
    }
