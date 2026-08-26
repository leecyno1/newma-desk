from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_contact_summary_titles_switched_to_analyst_wording():
    ai_router = (PROJECT_ROOT / "app" / "routers" / "ai.py").read_text(encoding="utf-8")
    llm_client = (PROJECT_ROOT / "app" / "services" / "llm_client.py").read_text(encoding="utf-8")
    artifacts = (PROJECT_ROOT / "app" / "services" / "report_artifacts.py").read_text(encoding="utf-8")

    assert "高评分分析师摘要" in ai_router
    assert "高评分分析师摘要" in llm_client
    assert "高评分分析师摘要" in artifacts
