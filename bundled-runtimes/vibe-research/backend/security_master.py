"""Persistent A-share security master shared by all research Mods.

Only the light-weight identity catalogue is synchronized here.  Quotes, bars,
fund flows and filings remain on-demand in ``astock``/``market_terminal``.
"""

from __future__ import annotations

import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

import astock


_GROUPS = (
    ("m:0+t:81+s:2048", "BJ"),
)
_LAST_REFRESH: float | None = None
_REFRESH_THREAD: threading.Thread | None = None
_REFRESH_LOCK = threading.Lock()


def database_path() -> Path:
    root = os.environ.get("VR_DATA_DIR") or str(Path.home() / ".vibe-research")
    path = Path(root).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path / "a_share_security_master.db"


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(database_path(), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """CREATE TABLE IF NOT EXISTS securities (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            exchange TEXT NOT NULL,
            market TEXT NOT NULL DEFAULT 'CN',
            asset_type TEXT NOT NULL DEFAULT 'stock',
            security_type TEXT NOT NULL DEFAULT 'A股',
            industry TEXT NOT NULL DEFAULT '',
            list_date TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            source TEXT NOT NULL DEFAULT 'eastmoney-clist',
            updated_at TEXT NOT NULL
        )"""
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_security_name ON securities(name)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_security_exchange ON securities(exchange)")
    return connection


def _rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    diff = (payload.get("data") or {}).get("diff") or []
    return list(diff.values()) if isinstance(diff, dict) else list(diff)


def _is_stock(code: str, name: str, exchange: str) -> bool:
    # Keep ST and newly listed shares.  Exclude ETF/fund/index records if a
    # broad Eastmoney board filter happens to return one.
    if any(token in name.upper() for token in ("ETF", "LOF", "基金", "指数")):
        return False
    if exchange == "BJ":
        return bool(re.fullmatch(r"(?:43|83|87|88|92)\d{4}", code))
    if exchange == "SH":
        return bool(re.fullmatch(r"(?:600|601|603|605|688|689)\d{3}", code))
    return bool(re.fullmatch(r"(?:000|001|002|003|300|301)\d{3}", code))


def _normalize(row: dict[str, Any], exchange: str) -> dict[str, str] | None:
    code = str(row.get("f12") or row.get("Code") or "").strip().zfill(6)
    name = str(row.get("f14") or row.get("Name") or code).strip()
    if not _is_stock(code, name, exchange):
        return None
    return {
        "code": code,
        "name": name,
        "exchange": exchange,
        "market": "CN",
        "asset_type": "stock",
        "security_type": "A股",
        "industry": str(row.get("f100") or "").strip(),
        "list_date": str(row.get("f26") or "").strip(),
    }


def _tdx_catalog() -> dict[str, dict[str, str]]:
    """Read SH/SZ security lists in one local TCP catalogue pass."""
    try:
        from mootdx.quotes import Quotes

        client = Quotes.factory(market="std", multithread=True, heartbeat=True)
        collected: dict[str, dict[str, str]] = {}
        for market, exchange in ((0, "SZ"), (1, "SH")):
            frame = client.stocks(market)
            for row in frame.to_dict("records"):
                item = _normalize({"f12": row.get("code"), "f14": str(row.get("name") or "").replace("\x00", "")}, exchange)
                if item:
                    collected[item["code"]] = item
        return collected
    except Exception:
        return {}


def _eastmoney_group(fs: str, exchange: str) -> tuple[dict[str, dict[str, str]], int, str | None]:
    """Fetch a filtered Eastmoney board, paging its 100-row response cap."""
    collected: dict[str, dict[str, str]] = {}
    total = 0
    try:
        for page in range(1, 100):
            response = astock.em_get(
                "https://push2delay.eastmoney.com/api/qt/clist/get",
                params={
                    "pn": page, "pz": 100, "po": 1, "np": 1, "fltt": 2, "invt": 2,
                    "fid": "f12", "fs": fs, "fields": "f12,f14,f26,f100",
                },
                headers={"User-Agent": astock.UA, "Referer": "https://quote.eastmoney.com/"},
                timeout=20,
            )
            response.raise_for_status()
            data = response.json().get("data") or {}
            total = int(data.get("total") or 0)
            rows = _rows({"data": data})
            for row in rows:
                item = _normalize(row, exchange)
                if item:
                    collected[item["code"]] = item
            if not rows or page * 100 >= total:
                break
        return collected, total, None
    except Exception as error:
        return collected, total, str(error)


def refresh() -> dict[str, Any]:
    """Refresh the complete active A-share catalogue from Eastmoney boards."""
    global _LAST_REFRESH
    collected: dict[str, dict[str, str]] = {}
    group_counts: dict[str, int] = {}
    errors: list[str] = []
    mainland = _tdx_catalog()
    if mainland:
        collected.update(mainland)
        group_counts["mootdx:SZ"] = sum(item["exchange"] == "SZ" for item in mainland.values())
        group_counts["mootdx:SH"] = sum(item["exchange"] == "SH" for item in mainland.values())
    else:
        errors.append("mootdx: security list unavailable")

    for fs, exchange in _GROUPS:
        rows, total, error = _eastmoney_group(fs, exchange)
        collected.update(rows)
        group_counts[fs] = len(rows)
        if error:
            errors.append(f"{fs}: {error}")

    # Do not replace a healthy catalogue with a partial upstream response.
    if len(collected) < 3000 or len(errors) == len(_GROUPS):
        return {"ok": False, "count": count(), "groups": group_counts, "errors": errors, "source": "mootdx+eastmoney-clist"}

    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    with _connect() as connection:
        connection.execute("DELETE FROM securities")
        connection.executemany(
            """INSERT INTO securities
            (code, name, exchange, market, asset_type, security_type, industry, list_date, status, source, updated_at)
            VALUES (:code, :name, :exchange, :market, :asset_type, :security_type, :industry, :list_date, 'active', 'eastmoney-clist', :updated_at)""",
            [{**item, "updated_at": now} for item in collected.values()],
        )
    _LAST_REFRESH = time.time()
    return {"ok": True, "count": len(collected), "groups": group_counts, "errors": errors, "updatedAt": now, "source": "mootdx+eastmoney-clist"}


def _needs_refresh(max_age_seconds: int = 72_000) -> bool:
    path = database_path()
    return count() < 3000 or not path.exists() or time.time() - path.stat().st_mtime > max_age_seconds


def _refresh_loop() -> None:
    while True:
        if _needs_refresh() and _REFRESH_LOCK.acquire(blocking=False):
            try:
                refresh()
            finally:
                _REFRESH_LOCK.release()
        time.sleep(3600)


def start_scheduler() -> None:
    """Keep the local catalogue current without delaying API startup."""
    global _REFRESH_THREAD
    if _REFRESH_THREAD and _REFRESH_THREAD.is_alive():
        return
    _REFRESH_THREAD = threading.Thread(target=_refresh_loop, name="a-share-security-master", daemon=True)
    _REFRESH_THREAD.start()


def count() -> int:
    with _connect() as connection:
        return int(connection.execute("SELECT COUNT(*) FROM securities WHERE status = 'active'").fetchone()[0])


def status() -> dict[str, Any]:
    with _connect() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS count, MAX(updated_at) AS updated_at FROM securities WHERE status = 'active'"
        ).fetchone()
        exchanges = {
            item["exchange"]: int(item["count"])
            for item in connection.execute(
                "SELECT exchange, COUNT(*) AS count FROM securities WHERE status = 'active' GROUP BY exchange"
            ).fetchall()
        }
    return {
        "count": int(row["count"] or 0),
        "exchanges": exchanges,
        "updatedAt": row["updated_at"] or "",
        "database": str(database_path()),
        "source": "mootdx+eastmoney-clist",
    }


def search(query: str, limit: int = 20) -> list[dict[str, Any]]:
    clean = query.strip()
    if not clean:
        return []
    pattern = f"%{clean}%"
    with _connect() as connection:
        rows = connection.execute(
            """SELECT code, name, exchange, security_type, industry, list_date
            FROM securities
            WHERE status = 'active' AND (code LIKE ? OR name LIKE ?)
            ORDER BY CASE WHEN code = ? THEN 0 WHEN name = ? THEN 1 ELSE 2 END, code
            LIMIT ?""",
            (pattern, pattern, clean, clean, max(1, min(limit, 100))),
        ).fetchall()
    return [
        {
            "symbol": row["code"],
            "name": row["name"],
            "market": "CN",
            "exchange": row["exchange"],
            "currency": "CNY",
            "timezone": "Asia/Shanghai",
            "assetType": "stock",
            "securityType": row["security_type"],
            "industry": row["industry"],
            "listDate": row["list_date"],
            "quoteId": f"CN:{row['code']}",
            "source": "a-share-security-master",
        }
        for row in rows
    ]
