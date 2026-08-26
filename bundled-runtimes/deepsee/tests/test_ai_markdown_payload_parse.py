import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.routers.ai import _unwrap_markdown_payload


def test_unwrap_markdown_payload_plain_json():
    s = '{"markdown":"# 标题\\n- 要点","quant":{"topics":[]}}'
    md, html, quant = _unwrap_markdown_payload(s)
    assert md and md.startswith("# 标题")
    assert html is None
    assert isinstance(quant, dict)


def test_unwrap_markdown_payload_fenced_json():
    s = "```json\n{\"markdown\":\"# A\"}\n```"
    md, html, quant = _unwrap_markdown_payload(s)
    assert md == "# A"
    assert html is None
    assert quant is None


def test_unwrap_markdown_payload_with_prose_wrapper():
    s = '请按要求输出：\n{"markdown":"# M","html":"<h1>M</h1>"}\n以上。'
    md, html, quant = _unwrap_markdown_payload(s)
    assert md == "# M"
    assert html == "<h1>M</h1>"
    assert quant is None


def test_unwrap_markdown_payload_non_json_returns_none():
    md, html, quant = _unwrap_markdown_payload("普通 markdown 文本")
    assert md is None
    assert html is None
    assert quant is None

