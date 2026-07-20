import math
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


SHANGHAI = ZoneInfo("Asia/Shanghai")
INDEX_SYMBOLS = {
    "上证指数": "000001",
    "深证成指": "399001",
    "创业板指": "399006",
    "沪深300": "000300",
}


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _integer(value: object) -> int:
    return int(_number(value))


def _field(row: dict[str, Any], *names: str) -> object:
    for name in names:
        if name in row:
            return row[name]
    return None


def _as_of(value: object) -> str:
    if isinstance(value, datetime):
        timestamp = value
    elif isinstance(value, str) and value.strip():
        try:
            timestamp = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            timestamp = datetime.now(SHANGHAI)
    else:
        timestamp = datetime.now(SHANGHAI)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=SHANGHAI)
    return timestamp.isoformat()


def _normalize_indices(rows: object) -> list[dict[str, object]]:
    if not isinstance(rows, list):
        return []

    normalized: list[dict[str, object]] = []
    for value in rows:
        row = _mapping(value)
        name = str(_field(row, "name") or "")
        symbol = str(
            _field(row, "symbol", "code") or INDEX_SYMBOLS.get(name, "")
        )
        normalized.append(
            {
                "symbol": symbol,
                "name": name,
                "price": _number(_field(row, "price")),
                "changePct": _number(
                    _field(row, "changePct", "change_pct", "pct")
                ),
            }
        )
    return normalized


def _normalize_global_indices(rows: object) -> list[dict[str, object]]:
    if not isinstance(rows, list):
        return []

    normalized: list[dict[str, object]] = []
    for value in rows:
        row = _mapping(value)
        normalized.append(
            {
                "symbol": str(_field(row, "symbol", "code", "key") or ""),
                "name": str(_field(row, "name") or ""),
                "region": str(_field(row, "region") or ""),
                "price": _number(_field(row, "price")),
                "changePct": _number(
                    _field(row, "changePct", "change_pct", "pct")
                ),
            }
        )
    return normalized


def _normalize_leaders(value: object) -> list[dict[str, object]]:
    if isinstance(value, dict):
        rows = value.get("stocks")
    else:
        rows = value
    if not isinstance(rows, list):
        return []

    normalized: list[dict[str, object]] = []
    for value in rows:
        row = _mapping(value)
        normalized.append(
            {
                "symbol": str(_field(row, "symbol", "code") or ""),
                "name": str(_field(row, "name") or ""),
                "price": _number(_field(row, "price")),
                "changePct": _number(
                    _field(row, "changePct", "change_pct", "pct")
                ),
                "amount": _number(_field(row, "amount")),
                "market": str(_field(row, "market") or "CN"),
                "industry": str(_field(row, "industry") or ""),
            }
        )
    return normalized


def normalize_market_snapshot(
    *,
    overview: object,
    indices: object,
    global_indices: object,
    leaders: object,
    as_of: object | None,
) -> dict[str, Any]:
    overview_row = _mapping(overview)
    sentiment = _mapping(overview_row.get("sentiment")) or overview_row
    normalized_indices = _normalize_indices(indices)
    normalized_global = _normalize_global_indices(global_indices)
    normalized_leaders = _normalize_leaders(leaders)
    timestamp = as_of or overview_row.get("updated")
    if timestamp is None and isinstance(leaders, dict):
        timestamp = leaders.get("updated")

    return {
        "asOf": _as_of(timestamp),
        "breadth": {
            "up": _integer(_field(sentiment, "up", "rise")),
            "down": _integer(_field(sentiment, "down", "fall")),
            "flat": _integer(_field(sentiment, "flat")),
        },
        "indices": normalized_indices,
        "globalIndices": normalized_global,
        "leaders": normalized_leaders,
        "charts": {
            "indexTrend": {
                "tooltip": {"trigger": "axis"},
                "xAxis": {
                    "type": "category",
                    "data": [item["name"] for item in normalized_indices],
                },
                "yAxis": {
                    "type": "value",
                    "axisLabel": {"formatter": "{value}%"},
                },
                "series": [
                    {
                        "name": "涨跌幅",
                        "type": "bar",
                        "data": [
                            item["changePct"] for item in normalized_indices
                        ],
                    }
                ],
            }
        },
    }
