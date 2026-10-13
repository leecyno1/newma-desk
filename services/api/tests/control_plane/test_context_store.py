from vibe_visualization_api.control_plane.context_store import ModContextStore


def _context(symbol: str) -> dict[str, object]:
    return {
        "view": {"id": "stock-research", "title": symbol},
        "wiki": {
            "primarySubject": {
                "canonicalId": f"security:CN:{symbol}",
            }
        },
    }


def test_mod_context_store_isolates_instances_and_subjects(tmp_path) -> None:
    store = ModContextStore(tmp_path / "contexts.db")
    store.put(
        user_id="alice",
        workspace_id="desk-1",
        module_id="stock-research",
        instance_id="tab-a",
        revision=1,
        context=_context("600519"),
    )
    store.put(
        user_id="alice",
        workspace_id="desk-1",
        module_id="stock-research",
        instance_id="tab-b",
        revision=1,
        context=_context("300308"),
    )

    first = store.get(
        user_id="alice",
        workspace_id="desk-1",
        module_id="stock-research",
        instance_id="tab-a",
        subject_key="security:CN:600519",
    )
    second = store.get(
        user_id="alice",
        workspace_id="desk-1",
        module_id="stock-research",
        instance_id="tab-b",
        subject_key="security:CN:300308",
    )

    assert first is not None and first["context"]["view"]["title"] == "600519"
    assert second is not None and second["context"]["view"]["title"] == "300308"
    assert first["contextRevision"] != second["contextRevision"]
