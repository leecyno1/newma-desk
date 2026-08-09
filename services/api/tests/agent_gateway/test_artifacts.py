from vibe_visualization_api.agent_gateway.artifacts import extract_artifacts


def test_report_artifact_is_extracted_without_leaking_protocol_markup() -> None:
    answer, artifacts = extract_artifacts(
        "先给出结论。\n"
        '<vibedesk_artifacts>[{"kind":"report","title":"海外流动性研究",'
        '"summary":"美元、利率与风险偏好","content":"第一部分\\n第二部分"}]'
        "</vibedesk_artifacts>"
    )

    assert answer == "先给出结论。"
    assert artifacts[0] | {"id": "ignored"} == {
        "id": "ignored",
        "kind": "report",
        "title": "海外流动性研究",
        "summary": "美元、利率与风险偏好",
        "content": "第一部分\n第二部分",
    }
    assert len(artifacts[0]["id"]) == 32


def test_report_content_may_contain_json_like_brackets() -> None:
    _, artifacts = extract_artifacts(
        '<vibedesk_artifacts>[{"kind":"report","title":"区间摘要",'
        '"content":"结论：[流动性改善]，但仍需核验。"}]</vibedesk_artifacts>'
    )

    assert artifacts[0]["content"] == "结论：[流动性改善]，但仍需核验。"


def test_internal_graph_and_replay_views_are_accepted() -> None:
    graph_id = "0123456789abcdef0123456789abcdef"
    replay_id = "abcdef0123456789abcdef0123456789"
    _, artifacts = extract_artifacts(
        "<vibedesk_artifacts>"
        f'[{{"kind":"graph","title":"产业链图谱","viewUrl":"/api/artifacts/{graph_id}/view"}},'
        f'{{"kind":"replay","title":"策略回放","viewUrl":"/api/artifacts/replays/{replay_id}/view"}}]'
        "</vibedesk_artifacts>"
    )

    assert [item["id"] for item in artifacts] == [graph_id, replay_id]


def test_unsafe_urls_raw_html_and_oversized_fields_are_rejected() -> None:
    too_long = "x" * 121
    _, artifacts = extract_artifacts(
        "<vibedesk_artifacts>"
        "["
        '{"kind":"graph","title":"外链","viewUrl":"https://evil.test/view"},'
        '{"kind":"graph","title":"脚本","viewUrl":"javascript:alert(1)"},'
        '{"kind":"graph","title":"穿越","viewUrl":"/api/artifacts/../secret/view"},'
        '{"kind":"report","title":"HTML","content":"<script>alert(1)</script>"},'
        f'{{"kind":"report","title":"{too_long}","content":"正文"}}'
        "]</vibedesk_artifacts>"
    )

    assert artifacts == []


def test_artifact_count_is_capped() -> None:
    payload = ",".join(
        f'{{"kind":"report","title":"报告 {index}","content":"正文"}}'
        for index in range(6)
    )
    _, artifacts = extract_artifacts(
        f"<vibedesk_artifacts>[{payload}]</vibedesk_artifacts>"
    )

    assert len(artifacts) == 4
