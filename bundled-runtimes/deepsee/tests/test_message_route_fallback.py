import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.services import llm_client


def test_messages_route_still_includes_explicit_api_key_channels():
    conf = llm_client.load_ai_config()
    targets = llm_client.resolve_chat_targets(
        conf,
        route_kind="tool",
        route_key="messages",
        model_override=conf.get("tool_model_messages"),
    )
    channel_ids = [str(t.get("channel_id") or "") for t in targets]
    assert "tool-minimax-cn-m27" in channel_ids or any(str(t.get("api_key") or "").strip() for t in targets)
    assert any(str(t.get("model") or "").strip() for t in targets)
