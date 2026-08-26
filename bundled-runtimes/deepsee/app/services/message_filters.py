from __future__ import annotations

from typing import Iterable


SYSTEM_PATTERNS = (
    "邀请你加入了群聊",
    "将你移出群聊",
    "拍了拍",
    "撤回了一条消息",
    "你已添加",
    "已添加你为朋友",
    "以上是打招呼内容",
    "开启了朋友验证",
    "修改群名为",
    "通过了你的朋友验证",
    "邀请\"",
    "加入群聊",
    "进入群聊",
    "已经成为朋友",
    "群主已开启",
    "系统消息",
    "红包已领取",
    "转账已接收",
    # WeChat XML system message patterns
    "<sysmsg",
    "<gamecenter",
    "<voipinvitemsg",
    "<voip",
    "<MSourceNote",
)

# WeChat-specific sender/chat IDs that are noise for the main WeChat message list
WECHAT_NOISE_SENDER_IDS = frozenset({"weixin"})
WECHAT_NOISE_CHAT_IDS = frozenset({"filehelper"})

# WeChat sender/chat ID prefixes for official accounts (公众号)
MP_SENDER_PREFIX = "gh_"


def is_outgoing(direction: str | None) -> bool:
    d = (direction or "").strip().lower()
    return d == "out"


def is_system_tip(text: str | None) -> bool:
    if not text:
        return False
    for p in SYSTEM_PATTERNS:
        if p in text:
            return True
    return False


def is_short_message(text: str | None) -> bool:
    if not text:
        return True
    compact = "".join(text.split())
    if not compact:
        return True
    chinese = sum(1 for ch in compact if "\u4e00" <= ch <= "\u9fff")
    if chinese > 0:
        # 定义：低于 15 个中文字视为短消息（垃圾）
        return chinese < 15
    return len(compact) <= 30


def filter_effective_messages(
    rows: Iterable[dict],
    *,
    external_only: bool = True,
    exclude_short: bool = True,
    exclude_system: bool = True,
):
    for r in rows:
        if external_only and is_outgoing(r.get("direction")):
            continue
        text = r.get("content_text") or r.get("content") or ""
        if exclude_system and is_system_tip(text):
            continue
        if exclude_short and is_short_message(text):
            continue
        yield r
