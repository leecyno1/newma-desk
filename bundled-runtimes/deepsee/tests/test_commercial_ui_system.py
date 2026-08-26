from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX_HTML = PROJECT_ROOT / "static" / "index.html"


def test_commercial_ui_tokens_and_state_components_exist():
    source = INDEX_HTML.read_text(encoding="utf-8")
    for token in [
        "--status-success-bg",
        "--status-warning-bg",
        "--status-error-bg",
        "--status-info-bg",
        "--card-radius",
        "--card-padding",
        "--table-density-compact",
    ]:
        assert token in source
    for cls in [
        ".commercial-state",
        ".commercial-state.success",
        ".commercial-state.warning",
        ".commercial-state.error",
        ".commercial-state.loading",
        ".commercial-empty",
        ".commercial-retry",
    ]:
        assert cls in source


def test_commercial_state_helper_normalizes_status_markup():
    source = INDEX_HTML.read_text(encoding="utf-8")
    assert "function renderCommercialState" in source
    assert "function setCommercialStatus" in source
    assert "data-commercial-state" in source
    assert "role=\"status\"" in source


def test_key_status_setters_use_commercial_status_helper():
    source = INDEX_HTML.read_text(encoding="utf-8")
    assert "setCommercialStatus(statusEl, text, tone" in source
    assert "setCommercialStatus(el, text, tone" in source


def test_high_frequency_empty_states_use_commercial_components():
    source = INDEX_HTML.read_text(encoding="utf-8")
    assert "function renderCommercialEmpty" in source
    assert "function renderCommercialEmptyRow" in source
    assert "renderCommercialEmptyRow(text, 9" in source
    assert "renderCommercialEmpty('暂无素材" in source
    assert "renderCommercialEmpty('暂无历史活动" in source
    assert "renderCommercialEmptyRow('暂无群发任务', 5" in source


def test_settings_failure_states_use_commercial_status_helper():
    source = INDEX_HTML.read_text(encoding="utf-8")
    assert "setCommercialStatus(statusEl, `已刷新" in source
    assert "setCommercialStatus(statusEl, '加载失败', 'error'" in source
    assert "setCommercialStatus(el, '能力加载失败', 'error'" in source
    assert "setCommercialStatus(msg, '行情配置加载失败', 'error'" in source
