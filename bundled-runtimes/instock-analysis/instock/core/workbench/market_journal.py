"""User-authored reviews are durable records, not expiring analysis cache."""
from datetime import date, datetime, timezone, timedelta
import json
from pathlib import Path
import sqlite3
import uuid

from instock.core.analysis_history import get_analysis_history_registry


NOTE_FIELDS = ("judgment", "support", "counter", "watch")
OUTCOMES = ("待观察", "支持", "削弱", "证伪")


def text_field(body, key, required=False):
    value = body.get(key, "")
    if not isinstance(value, str) or len(value) > 4000 or (required and not value.strip()):
        raise ValueError(f"{key}须为不超过4000字的文本，必填项不能为空")
    return value.strip()


class MarketJournalStore:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS market_reviews (
                    id TEXT PRIMARY KEY, as_of TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS market_review_checks (
                    id TEXT PRIMARY KEY, review_id TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS market_review_check_parent ON market_review_checks(review_id, created_at);
            """)

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def create(self, body):
        notes = {key: text_field(body, key, key in {"judgment", "watch"}) for key in NOTE_FIELDS}
        evidence = body.get("evidence")
        if not isinstance(evidence, dict):
            raise ValueError("缺少页面证据")
        for part in evidence.values():
            if not isinstance(part, dict) or (part.get("data") is not None and not isinstance(part["data"], dict)):
                raise ValueError("页面证据格式不正确")
        structure = evidence.get("marketStructure") or {}
        data = structure.get("data") or {}
        if data.get("schemaVersion") != "newma-desk.market-structure.v1":
            raise ValueError("请先读取市场结构，明确复盘日期")
        as_of = date.fromisoformat(data.get("expectedDate", "")).isoformat()
        for key, date_key in (("marketStructure", "expectedDate"), ("marketContinuity", "requestedDate"), ("marketEvidence", "requestedDate")):
            part = evidence.get(key) or {}
            if part.get("loading") or part.get("historical"):
                raise ValueError("证据正在加载或属于旧历史，请等待或刷新后保存")
            part_data = part.get("data")
            if part_data and part_data.get(date_key) != as_of:
                raise ValueError("证据日期不一致，请刷新后保存")
        packet = {"schemaVersion": "newma-desk.market-review.v1", "id": uuid.uuid4().hex,
                  "asOf": as_of, "createdAt": datetime.now(timezone.utc).isoformat(), "notes": notes,
                  "evidence": evidence, "captureBasis": "用户保存时的页面证据；保留原缺失/错误状态，不证明当时市场已知全量信息"}
        encoded = json.dumps(packet, ensure_ascii=False, allow_nan=False)
        if len(encoded.encode()) > 1_000_000:
            raise ValueError("复盘证据超过1MB，请缩小保存范围")
        with self.connect() as db:
            db.execute("INSERT INTO market_reviews VALUES (?, ?, ?, ?)", (packet["id"], as_of, packet["createdAt"], encoded))
        return {**json.loads(encoded), "checks": []}

    def get(self, review_id):
        with self.connect() as db:
            record = db.execute("SELECT payload FROM market_reviews WHERE id=?", (review_id,)).fetchone()
            if not record:
                return None
            checks = db.execute("SELECT payload FROM market_review_checks WHERE review_id=? ORDER BY created_at, rowid", (review_id,)).fetchall()
        return {**json.loads(record[0]), "checks": [json.loads(row[0]) for row in checks]}

    def list(self, offset=0, status="all"):
        if status not in {"all", "pending", "reviewed"}:
            raise ValueError("复核筛选须为全部、待跟进或已复核")
        latest = """WITH reviews AS (
            SELECT r.*, (SELECT c.payload FROM market_review_checks c WHERE c.review_id=r.id
                         ORDER BY c.created_at DESC, c.rowid DESC LIMIT 1) AS latest_check,
                   (SELECT COUNT(*) FROM market_review_checks c WHERE c.review_id=r.id) AS check_count,
                   r.rowid AS position
            FROM market_reviews r
        ) """
        pending = "(latest_check IS NULL OR json_extract(latest_check, '$.outcome')='待观察')"
        condition = {"all": "1", "pending": pending, "reviewed": f"NOT {pending}"}[status]
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN")
            counts = db.execute(latest + f"SELECT COUNT(*) AS total, COALESCE(SUM({pending}), 0) AS pending FROM reviews").fetchone()
            rows = db.execute(latest + f"SELECT payload, latest_check, check_count FROM reviews WHERE {condition} ORDER BY created_at DESC, position DESC LIMIT 21 OFFSET ?", (offset,)).fetchall()
        items = []
        for row in rows[:20]:
            record = json.loads(row["payload"])
            check = json.loads(row["latest_check"]) if row["latest_check"] else None
            notes = record["notes"]
            items.append({key: record[key] for key in ("id", "asOf", "createdAt")} | {
                "judgment": notes["judgment"][:100], "judgmentTruncated": len(notes["judgment"]) > 100,
                "watch": notes["watch"][:240], "watchTruncated": len(notes["watch"]) > 240,
                "checkCount": row["check_count"], "status": "pending" if not check or check["outcome"] == "待观察" else "reviewed",
                "latestCheck": {**check, "note": check["note"][:160], "noteTruncated": len(check["note"]) > 160} if check else None,
            })
        return {"items": items, "offset": offset, "hasMore": len(rows) > 20, "status": status,
                "counts": {"total": counts["total"], "pending": counts["pending"], "reviewed": counts["total"] - counts["pending"]},
                "statusBasis": "按最近一次录入的人工复核归类，不代表自动验证或策略胜率；列表仅为摘要，完整条件须打开记录",
                "storage": "sqlite", "expires": False}

    def add_check(self, review_id, body):
        record = self.get(review_id)
        if record is None:
            raise LookupError("复盘记录不存在")
        outcome = body.get("outcome")
        if outcome not in OUTCOMES:
            raise ValueError("请选择有效复核结论")
        observed = date.fromisoformat(body.get("observedDate", ""))
        today = datetime.now(timezone(timedelta(hours=8))).date()
        if not date.fromisoformat(record["asOf"]) <= observed <= today:
            raise ValueError("复核日期不得早于复盘截止日或晚于今天")
        check = {"id": uuid.uuid4().hex, "outcome": outcome, "observedDate": observed.isoformat(),
                 "note": text_field(body, "note", True), "createdAt": datetime.now(timezone.utc).isoformat()}
        with self.connect() as db:
            db.execute("INSERT INTO market_review_checks VALUES (?, ?, ?, ?)",
                       (check["id"], review_id, check["createdAt"], json.dumps(check, ensure_ascii=False)))
        return self.get(review_id)


def get_market_journal_store():
    # Separate tables deliberately escape AnalysisHistoryRegistry's TTL/capacity purge.
    return MarketJournalStore(get_analysis_history_registry().db_path)
