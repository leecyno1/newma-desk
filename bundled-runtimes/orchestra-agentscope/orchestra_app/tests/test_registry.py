import json
from dataclasses import replace

from orchestra_app import registry
from orchestra_app.registry import load_profiles, registered_skill_names, required_skill_names
from orchestra_app.prompts import build_orchestra_system_prompt, research_prompt
from orchestra_app.settings import settings


def test_registry_contains_core_committee_roster() -> None:
    profiles = load_profiles()
    assert len(profiles) >= 19
    assert {profile.group for profile in profiles} == {
        "宏观组",
        "配置组",
        "股票组",
        "基金经理组",
    }
    assert sum(profile.group == "基金经理组" for profile in profiles) == 8


def test_every_seat_has_skill_binding() -> None:
    profiles = load_profiles()
    assert all(3 <= len(profile.skills) <= 5 for profile in profiles)
    assert all(profile.available_skills for profile in profiles)
    assert all(not profile.missing_skills for profile in profiles)


def test_research_seats_have_distinct_report_structures() -> None:
    profiles = [profile for profile in load_profiles() if profile.group != "基金经理组"]
    structures = {tuple(profile.outputs) for profile in profiles}
    assert len(structures) == len(profiles)

    policy = next(profile for profile in profiles if profile.id == "MACRO-01")
    quant = next(profile for profile in profiles if profile.id == "ALLOC-03")
    policy_prompt = research_prompt("测试议题", policy, "共享证据包")
    quant_prompt = research_prompt("测试议题", quant, "共享证据包")
    assert "【政策传导链】" in policy_prompt
    assert "【拥挤度诊断】" in quant_prompt
    assert policy_prompt != quant_prompt


def test_policy_researcher_requires_specialty_and_data_guardrails() -> None:
    profile = next(profile for profile in load_profiles() if profile.id == "MACRO-01")
    registered = registered_skill_names(profile)
    required = required_skill_names(profile)

    assert "policy-monitor" in registered
    assert required == registered
    assert len(required) == 5


def test_profile_update_persists_without_touching_live_registry(tmp_path, monkeypatch) -> None:
    temporary_registry = tmp_path / "agent_profiles.json"
    temporary_registry.write_text(
        settings.registry_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        registry,
        "settings",
        replace(settings, registry_path=temporary_registry),
    )
    registry.load_profiles.cache_clear()

    try:
        updated = registry.update_profile(
            "MACRO-01",
            {
                "name": "政策 测试席",
                "default_prompt": "只使用可核验的一手政策来源。",
                "skills": ["policy-monitor", "finance-sentiment", "market-news-analyst"],
            },
        )
        persisted = json.loads(temporary_registry.read_text(encoding="utf-8"))
        target = next(item for item in persisted["standing_agents"] if item["id"] == "MACRO-01")

        assert updated.name == "政策 测试席"
        assert updated.default_prompt == "只使用可核验的一手政策来源。"
        assert target["status_bar_name"] == "政策 测试席"
        assert target["skills"] == ["policy-monitor", "finance-sentiment", "market-news-analyst"]
        assert registry.get_profile("MACRO-01").name == "政策 测试席"
    finally:
        registry.load_profiles.cache_clear()


def test_orchestra_chair_is_not_a_voting_seat() -> None:
    profiles = load_profiles()
    prompt = build_orchestra_system_prompt()
    assert all(profile.id != "ORCHESTRA" for profile in profiles)
    assert "不占用常设研究与基金经理席位" in prompt
    assert "不替代任何席位投票" in prompt


def test_custom_agent_can_be_created_configured_and_deleted(tmp_path, monkeypatch) -> None:
    temporary_registry = tmp_path / "agent_profiles.json"
    temporary_registry.write_text(
        settings.registry_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        registry,
        "settings",
        replace(settings, registry_path=temporary_registry),
    )
    registry.load_profiles.cache_clear()

    try:
        created = registry.create_profile(
            {
                "name": "外部 测试席",
                "title": "外部 Agent",
                "group": "股票组",
                "focus": "外部研究服务",
                "persona": "使用外部服务进行独立研究",
                "style": "保留来源和反证",
                "default_prompt": "返回结构化结论",
                "skills": ["finance-data-router", "data-quality-checker", "buy-side-equity-research-memo"],
                "connection": {
                    "kind": "external_http",
                    "endpoint": "https://agent.example.test/research",
                    "timeout_seconds": 90,
                },
            },
        )
        assert created.is_custom is True
        assert created.connection.kind == "external_http"
        assert len(registry.load_profiles()) == 20

        registry.delete_profile(created.id)
        assert len(registry.load_profiles()) == 19
    finally:
        registry.load_profiles.cache_clear()


def test_core_agent_cannot_be_deleted() -> None:
    try:
        registry.delete_profile("MACRO-01")
    except ValueError as error:
        assert "常设核心席位" in str(error)
    else:
        raise AssertionError("应拒绝删除核心席位")
