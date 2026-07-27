import json
import re
from typing import Any


ACTION_BLOCK = re.compile(
    r"<vibedesk_actions>\s*(\[.*?\])\s*</vibedesk_actions>",
    re.DOTALL,
)
ACTION_ID = re.compile(r"^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+$")

UI_ACTION_PROMPT = """7. 当前页面上下文中的 actions 是可执行 UI 动作。如果用户明确要求切换周期、修改指标、设置预警、保存布局或刷新页面，并且对应 action 已列出，可在正常中文回答末尾追加：
<vibedesk_actions>[{"actionId":"动作ID","input":{}}]</vibedesk_actions>
只允许使用页面 actions 中真实存在的 actionId；input 必须符合其 inputSchema；最多 8 个。没有需要执行的 UI 动作时不要输出该标签。不要把动作标签放进 Markdown 代码块。"""


def extract_ui_actions(answer: str) -> tuple[str, list[dict[str, Any]]]:
    matches = list(ACTION_BLOCK.finditer(answer))
    if not matches:
        return answer.strip(), []
    actions: list[dict[str, Any]] = []
    for match in matches[-2:]:
        try:
            parsed = json.loads(match.group(1))
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(parsed, list):
            continue
        for item in parsed:
            if not isinstance(item, dict):
                continue
            action_id = item.get("actionId")
            input_data = item.get("input", {})
            if (
                isinstance(action_id, str)
                and ACTION_ID.fullmatch(action_id)
                and isinstance(input_data, dict)
            ):
                actions.append({"actionId": action_id, "input": input_data})
            if len(actions) >= 8:
                break
    clean = ACTION_BLOCK.sub("", answer).strip()
    return clean, actions
