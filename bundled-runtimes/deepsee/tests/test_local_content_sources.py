import json
import sqlite3
from pathlib import Path


def test_news_engine_uses_local_snapshot_before_remote(monkeypatch, tmp_path):
    from app.services import news_engine

    data_dir = tmp_path / "datasets"
    data_dir.mkdir()
    (data_dir / "news_snapshot_1.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "id": "local-1",
                        "source_id": "local-wire",
                        "source_name": "本地新闻",
                        "title": "本地新闻源已经更新",
                        "summary": "本地快照摘要",
                        "pub_ts": 1782822250000,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEWS_DATASET_DIR", str(data_dir))
    monkeypatch.setenv("NEWS_REMOTE_ENABLED", "0")
    news_engine._CACHE.clear()

    def fail_remote(*_args, **_kwargs):
        raise AssertionError("remote news source should not be called when local snapshot exists")

    monkeypatch.setattr(news_engine.requests, "get", fail_remote)

    payload = news_engine.collect_news(limit=10, force=True)

    assert payload["total"] == 1
    assert payload["source"]["kind"] == "local-news-snapshot"
    assert payload["items"][0]["source_id"] == "local-wire"


def test_mp_rss_store_uses_local_db_before_remote(monkeypatch, tmp_path):
    from app.services import mp_rss_store

    db_path = tmp_path / "db.db"
    con = sqlite3.connect(db_path)
    try:
        con.executescript(
            """
            CREATE TABLE feeds (id TEXT PRIMARY KEY, mp_name TEXT);
            CREATE TABLE article_insights (article_id TEXT PRIMARY KEY, summary TEXT, key_points_json TEXT);
            CREATE TABLE articles (
              id TEXT PRIMARY KEY,
              mp_id TEXT,
              title TEXT,
              url TEXT,
              description TEXT,
              publish_time INTEGER,
              created_at INTEGER,
              updated_at INTEGER,
              is_read INTEGER,
              read_count INTEGER,
              like_count INTEGER,
              share_count INTEGER,
              recommend_count INTEGER,
              status INTEGER,
              content TEXT
            );
            INSERT INTO feeds (id, mp_name) VALUES ('mp-a', '本地公众号');
            INSERT INTO article_insights (article_id, summary, key_points_json)
              VALUES ('a1', '本地洞察摘要', '[]');
            INSERT INTO articles (
              id, mp_id, title, url, description, publish_time, created_at, updated_at,
              is_read, read_count, like_count, share_count, recommend_count, status, content
            ) VALUES (
              'a1', 'mp-a', '本地公众号文章', 'https://example.com/a1', '本地描述',
              1782822250, 1782822250, 1782822250, 0, 1, 2, 3, 4, 1, '正文'
            );
            """
        )
        con.commit()
    finally:
        con.close()

    monkeypatch.setenv("MP_REMOTE_ENABLED", "0")

    def fail_remote(*_args, **_kwargs):
        raise AssertionError("remote mp source should not be called when local db exists")

    monkeypatch.setattr(mp_rss_store.requests, "get", fail_remote)

    payload = mp_rss_store.list_mp_articles(limit=5, db_path=str(db_path))

    assert payload["total"] == 1
    assert payload["source"]["db"] == str(db_path)
    assert payload["items"][0]["channel_name"] == "本地公众号"
    assert payload["items"][0]["summary"] == "本地洞察摘要"


def test_media_items_bootstraps_builtin_sources_when_empty(monkeypatch, tmp_path):
    from app.routers import media
    from app.services import media_collector_runner

    list_calls = {"count": 0}
    run_calls = []

    def fake_list_collector_items(*, limit=200, keyword=None):
        list_calls["count"] += 1
        if list_calls["count"] == 1:
            return {"items": [], "total": 0}
        return {
            "items": [
                {
                    "id": "hot_bilibili_1",
                    "platform": "bilibili",
                    "source_type": "hot",
                    "time": "2026-07-01T09:00:00+08:00",
                    "title": "A股政策观察",
                    "description": "A股政策与科技板块联动升温",
                    "stats": {"rank": 1, "extra": {"view": 1200}},
                    "source_file": "bilibili.json",
                    "source_mtime": 1782867600,
                }
            ],
            "total": 1,
        }

    status_calls = {"count": 0}

    def fake_status():
        status_calls["count"] += 1
        if status_calls["count"] == 1:
            return {
                "data_dir": str(tmp_path),
                "hot": {"exists": False},
                "search": {"exists": False},
                "authors": {"exists": False},
            }
        return {
            "data_dir": str(tmp_path),
            "hot": {"exists": True, "latest_day": "2026-07-01", "latest_files": ["bilibili.json"]},
            "search": {"exists": False},
            "authors": {"exists": False},
        }

    def fake_run_media_collector_once(**kwargs):
        run_calls.append(kwargs)
        return {
            "ok": True,
            "running": False,
            "tasks": ["hot"],
            "started_at": "2026-07-01T01:00:00+00:00",
            "finished_at": "2026-07-01T01:00:03+00:00",
            "results": [{"name": "hot", "ok": True, "returncode": 0}],
            "status": fake_status(),
        }

    monkeypatch.setattr(media, "list_collector_items", fake_list_collector_items)
    monkeypatch.setattr(media, "get_collector_status", fake_status)
    monkeypatch.setattr(media.settings, "MEDIA_COLLECTOR_AUTO_BOOTSTRAP", True)
    monkeypatch.setattr(media.settings, "MEDIA_COLLECTOR_BOOTSTRAP_TIMEOUT_SECONDS", 7)
    monkeypatch.setattr(
        media_collector_runner,
        "get_media_collector_run_state",
        lambda: {"running": False, "last_run": None, "status": fake_status()},
    )
    monkeypatch.setattr(media_collector_runner, "run_media_collector_once", fake_run_media_collector_once)

    payload = media.api_list_media_items(limit=10, q=None, filter_noise=False, db=None)

    assert payload["total"] == 1
    assert payload["source"]["kind"] == "media-collector"
    assert payload["source"]["latest_day"] == "2026-07-01"
    assert payload["source"]["bootstrap"]["ok"] is True
    assert payload["source"]["bootstrap"]["tasks"] == ["hot"]
    assert "media-collector/keywords.json" in payload["source"]["default_sources"]["keywords"]
    assert payload["items"][0]["title"] == "A股政策观察"
    assert run_calls == [
        {
            "hot": True,
            "search": False,
            "authors": False,
            "timeout_seconds": 7,
        }
    ]


def test_media_collector_runner_writes_to_configured_data_dir(monkeypatch, tmp_path):
    from app.services import media_collector_runner

    calls = []

    def fake_run_script(name, script, *, timeout_seconds, pretty=False, env_overrides=None):
        calls.append(
            {
                "name": name,
                "script": script,
                "timeout_seconds": timeout_seconds,
                "pretty": pretty,
                "env_overrides": env_overrides or {},
            }
        )
        return {"name": name, "ok": True, "returncode": 0}

    monkeypatch.setenv("COLLECTOR_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(media_collector_runner, "_run_script", fake_run_script)
    monkeypatch.setattr(
        media_collector_runner,
        "get_collector_status",
        lambda: {"data_dir": str(tmp_path), "hot": {}, "search": {}, "authors": {}},
    )
    monkeypatch.setattr(media_collector_runner, "_LAST_RUN", None)
    monkeypatch.setattr(media_collector_runner, "_CURRENT_RUN", None)

    payload = media_collector_runner.run_media_collector_once(
        hot=True,
        search=True,
        authors=True,
        timeout_seconds=31,
        pretty=True,
    )

    assert payload["ok"] is True
    assert (tmp_path / "collector_runs" / "last.json").exists()
    assert [call["name"] for call in calls] == ["hot", "search", "authors"]
    assert calls[0]["env_overrides"]["OUTPUT_BASE"] == str(tmp_path / "hot")
    assert calls[1]["env_overrides"]["OUTPUT_BASE"] == str(tmp_path / "search")
    assert calls[2]["env_overrides"]["OUTPUT_BASE"] == str(tmp_path / "authors")


def test_collector_status_exposes_builtin_source_metadata(monkeypatch, tmp_path):
    from app.routers import collector_api

    keywords_path = tmp_path / "keywords.json"
    authors_path = tmp_path / "authors.json"
    keywords_path.write_text(
        json.dumps({"keywords": ["A股", "AI agent"], "updated": "2026-07-01"}, ensure_ascii=False),
        encoding="utf-8",
    )
    authors_path.write_text(
        json.dumps({"authors": ["财经作者"], "updated": "2026-07-01"}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(collector_api, "_keywords_path", lambda: keywords_path)
    monkeypatch.setattr(collector_api, "_authors_path", lambda: authors_path)
    monkeypatch.setattr(collector_api.settings, "MEDIA_COLLECTOR_AUTO_BOOTSTRAP", True)
    monkeypatch.setattr(collector_api.settings, "MEDIA_COLLECTOR_BOOTSTRAP_TIMEOUT_SECONDS", 9)

    from app.services import media_collector_store, media_collector_runner

    monkeypatch.setattr(
        media_collector_store,
        "get_collector_status",
        lambda: {
            "data_dir": str(tmp_path),
            "hot": {"latest_day": "2026-07-01", "latest_files": ["bilibili.json"]},
            "search": {},
            "authors": {},
        },
    )
    monkeypatch.setattr(
        media_collector_runner,
        "get_media_collector_run_state",
        lambda: {"running": False, "current_run": None, "last_run": None},
    )

    payload = collector_api.collector_status()

    assert payload["default_sources"]["ready"] is True
    assert payload["default_sources"]["keywords_count"] == 2
    assert payload["default_sources"]["authors_count"] == 1
    assert payload["auto_bootstrap"] is True
    assert payload["bootstrap_timeout_seconds"] == 9


def test_frontend_renders_content_source_status_panel():
    html = Path("static/index.html").read_text(encoding="utf-8")

    assert 'id="collectorSourceGrid"' in html
    assert "function renderCollectorSourceGrid" in html
    assert "默认源已初始化" in html
    assert "首次自动初始化" in html
