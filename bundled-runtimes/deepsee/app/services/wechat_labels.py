"""Account-scoped label names; current memberships come from contact details."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ..models import SyncState

LABEL_CACHE_KEY = "wechat_label_names_v1"


def label_account(client: Any) -> str:
    if getattr(client, "device_key_mode", False):
        try:
            data = client.get_device_profile().get("data") or {}
            name = (data.get("userInfo") or {}).get("userName")
            if isinstance(name, dict):
                name = name.get("str") or name.get("string")
            return str(name or "").strip()
        except (RuntimeError, AttributeError):
            return ""
    return str(getattr(client, "app_id", "") or "").strip()


def save_label_names(db: Session, account: str, names: dict[str, str]) -> None:
    if not account:
        return
    payload = {"account": account, "names": names, "saved_at": datetime.utcnow().isoformat()}
    state = db.get(SyncState, LABEL_CACHE_KEY) or SyncState(key=LABEL_CACHE_KEY)
    state.value = json.dumps(payload, ensure_ascii=False)
    db.add(state)


def resolve_label_names(db: Session, client: Any) -> dict[str, Any]:
    account = label_account(client)
    try:
        response = client.list_labels()
        data = response.get("data") or {}
        rows = data.get("labelList")
        if not isinstance(rows, list):
            raise RuntimeError("标签接口未返回标签列表")
        names = {
            str(row["labelId"]): str(row["labelName"]).strip()
            for row in rows if isinstance(row, dict) and row.get("labelId") is not None
            and str(row.get("labelName") or "").strip()
        }
        save_label_names(db, account, names)
        return {"names": names, "source": "wechatapi_gateway", "upstream_available": True}
    except RuntimeError:
        state = db.get(SyncState, LABEL_CACHE_KEY)
        cache = json.loads(state.value or "{}") if state else {}
        names = cache.get("names") if account and cache.get("account") == account else {}
        return {
            "names": names or {}, "source": "local_name_cache" if names else "unavailable",
            "upstream_available": False,
            "warning": "服务暂不提供标签名称；使用原名称缓存，成员以本次通讯录为准。" if names
            else "服务暂不提供标签名称，且当前账号没有名称缓存。",
        }
