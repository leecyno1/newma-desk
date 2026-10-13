import json

import newsradar


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
