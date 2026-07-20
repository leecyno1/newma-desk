import json
from typing import Any


MAX_CONTEXT_CHARACTERS = 16_000
MAX_USER_PROMPT_CHARACTERS = 1_000


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _scalar(value: object) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return None


def _project_rows(
    value: object,
    fields: tuple[str, ...],
) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    projected: list[dict[str, object]] = []
    for item in value:
        row = _mapping(item)
        projected.append({field: _scalar(row.get(field)) for field in fields})
    return projected


def _normalized_context(snapshot: dict[str, Any]) -> dict[str, object]:
    breadth = _mapping(snapshot.get("breadth"))
    return {
        "asOf": _scalar(snapshot.get("asOf")),
        "breadth": {
            "up": _scalar(breadth.get("up")),
            "down": _scalar(breadth.get("down")),
            "flat": _scalar(breadth.get("flat")),
        },
        "indices": _project_rows(
            snapshot.get("indices"),
            ("symbol", "name", "price", "changePct"),
        ),
        "globalIndices": _project_rows(
            snapshot.get("globalIndices"),
            ("symbol", "name", "region", "price", "changePct"),
        ),
        "leaders": _project_rows(
            snapshot.get("leaders"),
            (
                "symbol",
                "name",
                "price",
                "changePct",
                "amount",
                "market",
                "industry",
            ),
        ),
    }


def _serialized_context(snapshot: dict[str, Any]) -> str:
    serialized = json.dumps(
        _normalized_context(snapshot),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    suffix = "\n…上下文已截断"
    if len(serialized) <= MAX_CONTEXT_CHARACTERS:
        return serialized
    return serialized[: MAX_CONTEXT_CHARACTERS - len(suffix)] + suffix


def build_market_explain_prompt(
    *,
    snapshot: dict[str, Any],
    user_prompt: str,
) -> str:
    request = user_prompt.strip()[:MAX_USER_PROMPT_CHARACTERS]
    if not request:
        request = "解释当前市场行情"
    context = _serialized_context(snapshot)
    return f"""你正在解释一个已经规范化的市场快照，不得补造快照中没有的事实。

用户需求：{request}

请输出简洁 Markdown，并严格使用以下结构：
## 观察
- 只陈述快照直接支持的事实，并标注数据时间。
## 可能驱动
- 可以提出可能原因，但必须明确它们是推测；缺少新闻、资金或宏观证据时要直接说明。
## 风险
- 说明数据时效、样本范围和结论局限，不提供个股买卖建议。

规范化快照：
{context}
"""
