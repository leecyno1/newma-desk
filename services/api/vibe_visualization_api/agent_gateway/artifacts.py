import json
import re
from typing import Any
from uuid import uuid4


ARTIFACT_BLOCK = re.compile(
    r"<vibedesk_artifacts>\s*(.*?)\s*</vibedesk_artifacts>",
    re.DOTALL,
)
ARTIFACT_VIEW_URL = re.compile(
    r"^/api/artifacts/(?:(?:replays/)?[0-9a-f]{32})/view$"
)
HTML_TAG = re.compile(r"<[a-zA-Z][^>]*>")

MAX_ARTIFACTS = 4
MAX_TITLE_CHARS = 120
MAX_SUMMARY_CHARS = 500
MAX_REPORT_CHARS = 60_000

ARTIFACT_PROMPT = """8. 只有当结果因完整报告、图谱或交易回放而明显更易理解时，才在正常回答末尾追加 Artifact：
<vibedesk_artifacts>[{"kind":"report","title":"报告标题","summary":"一句话摘要","content":"完整纯文本报告"}]</vibedesk_artifacts>
最多 4 个。短回答仍直接写在正文中。report 只允许纯文本，不得包含 HTML；graph 和 replay 必须引用已经由 Newma-Desk 创建并真实返回的 /api/artifacts/.../view 地址，不得编造地址。不要输出外部 URL，不要把该标签放进 Markdown 代码块。"""


def _text(value: object, *, limit: int, required: bool = False) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if (required and not text) or len(text) > limit or HTML_TAG.search(text):
        return None
    return text or None


def _view_url(value: object, kind: str) -> str | None:
    if not isinstance(value, str) or not ARTIFACT_VIEW_URL.fullmatch(value):
        return None
    is_replay = value.startswith("/api/artifacts/replays/")
    if (kind == "replay") != is_replay:
        return None
    return value


def _artifact(item: object) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    kind = item.get("kind")
    if kind not in {"report", "graph", "replay"}:
        return None
    title = _text(item.get("title"), limit=MAX_TITLE_CHARS, required=True)
    summary = _text(item.get("summary"), limit=MAX_SUMMARY_CHARS)
    if title is None:
        return None

    if kind == "report":
        content = _text(
            item.get("content"),
            limit=MAX_REPORT_CHARS,
            required=True,
        )
        if content is None:
            return None
        artifact: dict[str, Any] = {
            "id": uuid4().hex,
            "kind": kind,
            "title": title,
            "content": content,
        }
    else:
        view_url = _view_url(item.get("viewUrl"), kind)
        if view_url is None:
            return None
        artifact = {
            "id": view_url.removesuffix("/view").rsplit("/", 1)[-1],
            "kind": kind,
            "title": title,
            "viewUrl": view_url,
        }
    if summary is not None:
        artifact["summary"] = summary
    return artifact


def extract_artifacts(answer: str) -> tuple[str, list[dict[str, Any]]]:
    matches = list(ARTIFACT_BLOCK.finditer(answer))
    if not matches:
        return answer.strip(), []
    artifacts: list[dict[str, Any]] = []
    for match in matches[-2:]:
        try:
            parsed = json.loads(match.group(1))
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(parsed, list):
            continue
        for item in parsed:
            artifact = _artifact(item)
            if artifact is not None:
                artifacts.append(artifact)
            if len(artifacts) >= MAX_ARTIFACTS:
                break
        if len(artifacts) >= MAX_ARTIFACTS:
            break
    return ARTIFACT_BLOCK.sub("", answer).strip(), artifacts
