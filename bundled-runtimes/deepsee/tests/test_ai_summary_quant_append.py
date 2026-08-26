import os
import sys
import json
import uuid


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def test_ai_summary_market_appends_quant(monkeypatch):
    from app.routers import ai as ai_router
    from app.routers.ai import _run_summary_local

    def fake_chat(messages, temperature=0.3, model_override=None, force_json=False, **kwargs):
        return json.dumps(
            {
                "markdown": "# 市场观点总结\n- 贵金属观点：看好为主 #1\n",
                "quant": {
                    "topics": [
                        {
                            "topic": "贵金属",
                            "bullish_ids": ["1"],
                            "bearish_ids": [],
                            "neutral_ids": [],
                        }
                    ]
                },
            },
            ensure_ascii=False,
        )

    # ai.py imports siliconflow_chat into module scope, so patch there.
    monkeypatch.setattr(ai_router, "siliconflow_chat", fake_chat)

    out = _run_summary_local(
        {
            "messages": [
                {
                    "id": 1,
                    "time": "2026-01-31T00:00:00",
                    "sender_name": "A",
                    "content": "这是一个较长的市场观点摘要，包含观点与建议，确保不被短消息过滤。",
                    "derived": {"summary": "ai: 这是一个较长的市场观点摘要，包含观点与建议，确保不被短消息过滤。"},
                }
            ],
            "modules": ["market"],
            "temperature": 0.3,
            "prompts": {},
            "contact_ratings": {},
            # Avoid hitting persistent summary cache from previous runs.
            "snapshot_id": f"test-quant-market-{uuid.uuid4()}",
        }
    )
    md = (out.get("result") or {}).get("market_markdown", "")
    assert "## 量化分析" in md
    assert "quant-bar bullish" not in md
    assert "quant-tone-bullish" in md
