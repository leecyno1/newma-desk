import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from vibe_visualization_api.control_plane.repository import (
    InvalidModuleStateError,
    ModuleNotFoundError,
    ModuleRepository,
)


MANIFEST = {
    "schemaVersion": "1.0",
    "id": "market-daily",
    "name": "每日股票行情",
    "version": "0.1.0",
    "category": "market",
    "entry": {"type": "structured", "url": "/modules/market-daily/"},
    "permissions": ["market.read"],
    "dataServices": ["market-data"],
    "agentCapabilities": [],
    "events": {"emits": [], "accepts": []},
}


def test_draft_publish_and_rollback(tmp_path: Path) -> None:
    repo = ModuleRepository(tmp_path / "registry.db")
    draft = repo.create_draft(MANIFEST)
    assert draft.status == "draft"

    published = repo.publish("market-daily", draft.revision)
    assert published.status == "published"

    second = repo.create_draft({**MANIFEST, "version": "0.2.0"})
    repo.publish("market-daily", second.revision)
    rolled_back = repo.rollback("market-daily", draft.revision)
    assert rolled_back.manifest["version"] == "0.1.0"


def test_revisions_increment_per_module_and_preserve_unicode_json(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "nested" / "registry.db"
    repo = ModuleRepository(database_path)

    first = repo.create_draft(MANIFEST)
    second = repo.create_draft({**MANIFEST, "version": "0.2.0"})
    other = repo.create_draft({**MANIFEST, "id": "research", "name": "研究"})

    assert (first.revision, second.revision, other.revision) == (1, 2, 1)
    assert first.manifest["name"] == "每日股票行情"
    assert datetime.fromisoformat(first.created_at).utcoffset() == timedelta(0)

    with sqlite3.connect(database_path) as connection:
        manifest_json = connection.execute(
            "SELECT manifest_json FROM module_revisions "
            "WHERE module_id = ? AND revision = ?",
            (first.module_id, first.revision),
        ).fetchone()[0]

    assert "每日股票行情" in manifest_json
    assert "\\u6bcf" not in manifest_json
    assert manifest_json == json.dumps(MANIFEST, ensure_ascii=False, sort_keys=True)


def test_publish_missing_revision_does_not_disable_current_published(
    tmp_path: Path,
) -> None:
    repo = ModuleRepository(tmp_path / "registry.db")
    published = repo.publish(
        "market-daily", repo.create_draft(MANIFEST).revision
    )

    with pytest.raises(ModuleNotFoundError):
        repo.publish("market-daily", 999)

    assert repo.list_published() == [published]


def test_disable_without_published_revision_raises_invalid_state(
    tmp_path: Path,
) -> None:
    repo = ModuleRepository(tmp_path / "registry.db")
    repo.create_draft(MANIFEST)

    with pytest.raises(InvalidModuleStateError):
        repo.disable("market-daily")


def test_rollback_to_current_published_revision_raises_invalid_state(
    tmp_path: Path,
) -> None:
    repo = ModuleRepository(tmp_path / "registry.db")
    published = repo.publish(
        "market-daily", repo.create_draft(MANIFEST).revision
    )

    with pytest.raises(InvalidModuleStateError):
        repo.rollback("market-daily", published.revision)

    assert repo.list_published() == [published]


def test_list_published_is_deterministic_with_one_revision_per_module(
    tmp_path: Path,
) -> None:
    repo = ModuleRepository(tmp_path / "registry.db")
    research = repo.create_draft({**MANIFEST, "id": "research"})
    market_v1 = repo.create_draft(MANIFEST)
    market_v2 = repo.create_draft({**MANIFEST, "version": "0.2.0"})

    repo.publish("research", research.revision)
    repo.publish("market-daily", market_v1.revision)
    repo.publish("market-daily", market_v2.revision)

    published = repo.list_published()
    assert [(module.module_id, module.revision) for module in published] == [
        ("market-daily", market_v2.revision),
        ("research", research.revision),
    ]


def test_disable_and_rollback_write_audit_events(tmp_path: Path) -> None:
    database_path = tmp_path / "registry.db"
    repo = ModuleRepository(database_path)
    first = repo.create_draft(MANIFEST)
    repo.publish("market-daily", first.revision)
    repo.disable("market-daily")
    second = repo.create_draft({**MANIFEST, "version": "0.2.0"})
    repo.publish("market-daily", second.revision)
    repo.rollback("market-daily", first.revision)

    with sqlite3.connect(database_path) as connection:
        events = connection.execute(
            "SELECT event_type, module_id, revision, detail_json "
            "FROM audit_events ORDER BY id"
        ).fetchall()

    assert [event[0] for event in events] == [
        "create_draft",
        "publish",
        "disable",
        "create_draft",
        "publish",
        "rollback",
    ]
    assert all(event[1] == "market-daily" for event in events)
    rollback = events[-1]
    assert rollback[2] == first.revision
    assert json.loads(rollback[3]) == {"source_revision": second.revision}


def test_two_repository_instances_allocate_unique_revisions(tmp_path: Path) -> None:
    database_path = tmp_path / "registry.db"
    first_repo = ModuleRepository(database_path)
    second_repo = ModuleRepository(database_path)

    first = first_repo.create_draft(MANIFEST)
    second = second_repo.create_draft({**MANIFEST, "version": "0.2.0"})

    assert (first.revision, second.revision) == (1, 2)


@pytest.mark.parametrize(
    "manifest",
    [
        {},
        {"id": ""},
        {"id": "   "},
        {"id": 1},
        {"id": "A"},
        {"id": "ab"},
        {"id": "foo/bar"},
        {"id": "-foo"},
        {"id": "foo-"},
        {"id": "foo_bar"},
        {"id": "a" * 65},
    ],
)
def test_create_draft_rejects_missing_or_invalid_module_id(
    tmp_path: Path, manifest: dict[str, object]
) -> None:
    repo = ModuleRepository(tmp_path / "registry.db")

    with pytest.raises(ValueError, match=r"manifest\['id'\]"):
        repo.create_draft(manifest)


@pytest.mark.parametrize("module_id", ["abc", "a-b", "a" * 64])
def test_create_draft_accepts_valid_module_id_boundaries(
    tmp_path: Path, module_id: str
) -> None:
    repo = ModuleRepository(tmp_path / "registry.db")

    stored = repo.create_draft({**MANIFEST, "id": module_id})

    assert stored.module_id == module_id
