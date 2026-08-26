from vibe_visualization_api.creator_studio.lineage import ArtifactLineage


def test_parallel_slots_do_not_supersede_each_other():
    document = {
        "nodeStates": {
            "draft.article_draft": {
                "materials": [],
                "artifacts": [],
            }
        },
        "handoffs": [],
    }
    lineage = ArtifactLineage()

    first, _ = lineage.register_artifact(
        document,
        stage_id="draft",
        node_id="article_draft",
        artifact={
            "type": "article_markdown",
            "slot": "topic-a",
            "path": "/tmp/topic-a.md",
        },
        created_at="2026-08-24T00:00:00+00:00",
    )
    second, _ = lineage.register_artifact(
        document,
        stage_id="draft",
        node_id="article_draft",
        artifact={
            "type": "article_markdown",
            "slot": "topic-b",
            "path": "/tmp/topic-b.md",
        },
        created_at="2026-08-24T00:00:01+00:00",
    )

    assert first["status"] == "created"
    assert second["status"] == "created"
    assert first["version"] == 1
    assert second["version"] == 1

    replacement, _ = lineage.register_artifact(
        document,
        stage_id="draft",
        node_id="article_draft",
        artifact={
            "type": "article_markdown",
            "slot": "topic-a",
            "path": "/tmp/topic-a-v2.md",
        },
        created_at="2026-08-24T00:00:02+00:00",
    )

    assert first["status"] == "superseded"
    assert second["status"] == "created"
    assert replacement["status"] == "created"
    assert replacement["version"] == 2
