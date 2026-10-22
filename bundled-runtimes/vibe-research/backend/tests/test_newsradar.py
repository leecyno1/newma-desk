import json

import newsradar
from unittest.mock import Mock
from fastapi.testclient import TestClient
import app as app_module


def test_snapshot_does_not_start_collection_even_with_missing_or_stale_cache(monkeypatch):
    collector = Mock()
    monkeypatch.setattr(newsradar, "trigger_background_refresh", collector)
    monkeypatch.setattr(newsradar, "fetch_radar", collector)
    monkeypatch.setattr(app_module, "_API_KEY", "")
    monkeypatch.setattr(newsradar, "skeleton", lambda: {"generated_at": None, "industries": []})
    client = TestClient(app_module.app)
    for cached in (None, {"generated_at_iso": "2000-01-01T00:00:00Z", "industries": []}):
        monkeypatch.setattr(newsradar, "load_cache", lambda: cached)
        result = client.get("/api/radar/snapshot")
        assert result.status_code == 200
        assert result.json()["data"]["refresh"]["read_only"] is True
        assert result.json()["data"]["refresh"]["stale"] is True
    collector.assert_not_called()


def test_native_radar_retains_background_and_explicit_refresh(monkeypatch):
    background = Mock()
    forced = Mock(return_value={"generated_at": None})
    monkeypatch.setattr(newsradar, "load_cache", lambda: {"generated_at": None})
    monkeypatch.setattr(newsradar, "trigger_background_refresh", background)
    monkeypatch.setattr(newsradar, "fetch_radar", forced)
    newsradar.get_radar()
    background.assert_called_once()
    forced.assert_not_called()
    newsradar.get_radar(force=True)
    forced.assert_called_once()


def test_snapshot_errors_do_not_expose_cache_paths(monkeypatch):
    monkeypatch.setattr(app_module, "_API_KEY", "")
    monkeypatch.setattr(newsradar, "load_cache", Mock(side_effect=OSError("private-path")))
    result = TestClient(app_module.app).get("/api/radar/snapshot")
    assert result.status_code == 502
    assert "private-path" not in result.text


def test_radar_refresh_does_not_wait_for_remote_translation(monkeypatch, tmp_path):
    sources_file = tmp_path / "news_sources.json"
    sources_file.write_text(
        json.dumps(
            {
                "fetch": {"recent_days": 7, "per_source": 6},
                "redline_keywords": [],
                "sources": [],
                "industries": [
                    {"key": "technology", "name": "科技", "accent": "#000000"}
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(newsradar, "SOURCES_FILE", str(sources_file))
    monkeypatch.setattr(newsradar, "CACHE_FILE", str(tmp_path / "radar.json"))
    monkeypatch.setattr(newsradar, "classify_industries", lambda industries: {})
    monkeypatch.setattr(
        newsradar,
        "build_news_monitor",
        lambda industries, max_topics=10_000: {"topics": []},
    )

    calls = []
    monkeypatch.setattr(
        newsradar,
        "apply_chinese_titles",
        lambda industries, *, translate_missing: calls.append(translate_missing) or 0,
    )

    newsradar._fetch_radar_unlocked()

    assert calls == [False]
