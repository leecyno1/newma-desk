from vibe_visualization_api.agent_gateway.ui_actions import extract_ui_actions


def test_ui_actions_are_extracted_without_leaking_protocol_markup() -> None:
    answer, actions = extract_ui_actions(
        "已切换到 15 分钟。\n"
        '<vibedesk_actions>[{"actionId":"market.set-timeframe","input":{"timeframe":"15m"}}]</vibedesk_actions>'
    )

    assert answer == "已切换到 15 分钟。"
    assert actions == [
        {"actionId": "market.set-timeframe", "input": {"timeframe": "15m"}}
    ]


def test_ui_actions_ignore_invalid_ids_and_non_object_inputs() -> None:
    _, actions = extract_ui_actions(
        '<vibedesk_actions>[{"actionId":"bad","input":{}},{"actionId":"market.refresh","input":[]}]</vibedesk_actions>'
    )

    assert actions == []
