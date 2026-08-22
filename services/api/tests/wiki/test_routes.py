def manifest(
    module_id: str,
    name: str,
    *,
    subject_types: list[str],
    entrypoint_id: str,
    intent: str,
    label: str,
    concepts: list[str] | None = None,
) -> dict[str, object]:
    return {
        "schemaVersion": "1.1",
        "id": module_id,
        "name": name,
        "version": "1.0.0",
        "category": "market",
        "entry": {"type": "static", "url": f"/mods/{module_id}/"},
        "compatibility": {"level": 2, "bridgeProtocol": "1.0"},
        "permissions": [],
        "dataServices": [],
        "wiki": {
            "contractVersion": "1.0",
            "subjectTypes": subject_types,
            "concepts": concepts or [],
            "entrypoints": [
                {
                    "id": entrypoint_id,
                    "intent": intent,
                    "label": label,
                    "contextContract": "newma.wiki.subject.v1",
                    "defaults": {"period": "daily"},
                }
            ],
        },
        "actions": {},
        "events": {"emits": [], "accepts": []},
    }


def publish(client, mod_manifest: dict[str, object]) -> None:
    draft = client.post("/api/mods/drafts", json=mod_manifest)
    assert draft.status_code == 201, draft.text
    stored = draft.json()
    response = client.post(
        f"/api/mods/{stored['moduleId']}/revisions/{stored['revision']}/publish"
    )
    assert response.status_code == 200, response.text


def stock_context() -> dict[str, object]:
    return {
        "primarySubject": {
            "type": "security",
            "canonicalId": "security:CN:300308",
            "displayName": "中际旭创",
            "market": "CN",
            "symbol": "300308",
            "assetType": "stock",
        },
        "relatedSubjects": [],
        "conceptIds": ["concept:CN:cpo"],
        "intent": "market.overview",
        "timeframe": "daily",
        "snapshotId": "market-daily:snapshot-1",
    }


def test_resolves_only_mods_that_accept_the_current_subject(client) -> None:
    publish(
        client,
        manifest(
            "wiki-market-source",
            "市场概览",
            subject_types=["security", "etf"],
            entrypoint_id="overview",
            intent="market.overview",
            label="市场概览",
        ),
    )
    publish(
        client,
        manifest(
            "wiki-czsc-target",
            "CZSC 结构",
            subject_types=["security", "etf"],
            entrypoint_id="structure",
            intent="technical.structure",
            label="CZSC 结构",
            concepts=["cpo", "technical-analysis"],
        ),
    )
    publish(
        client,
        manifest(
            "wiki-fund-target",
            "基金研究",
            subject_types=["fund"],
            entrypoint_id="fund-overview",
            intent="fund.research",
            label="基金研究",
        ),
    )

    profiles = client.get("/api/wiki/mod-profiles")
    assert profiles.status_code == 200
    ids = {item["moduleId"] for item in profiles.json()}
    assert {"wiki-market-source", "wiki-czsc-target", "wiki-fund-target"} <= ids

    response = client.post(
        "/api/wiki/link-resolutions",
        json={
            "sourceModId": "wiki-market-source",
            "context": stock_context(),
            "limit": 5,
        },
    )
    assert response.status_code == 200, response.text
    links = response.json()["links"]
    assert [item["targetModId"] for item in links] == ["wiki-czsc-target"]
    assert links[0]["intent"] == "technical.structure"
    assert links[0]["match"]["concepts"] == ["cpo"]


def test_topic_resolution_omits_non_applicable_trading_fields(client) -> None:
    publish(
        client,
        manifest(
            "wiki-news-source",
            "新闻与舆情",
            subject_types=["topic"],
            entrypoint_id="monitor",
            intent="news.monitor",
            label="新闻监测",
        ),
    )
    response = client.post(
        "/api/wiki/link-resolutions",
        json={
            "sourceModId": "wiki-news-source",
            "context": {
                "primarySubject": {
                    "type": "topic",
                    "canonicalId": "topic:news:tesla-solar-roof",
                    "displayName": "Tesla Solar Roof",
                },
                "intent": "news.monitor",
            },
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["subject"] == {
        "type": "topic",
        "canonicalId": "topic:news:tesla-solar-roof",
        "displayName": "Tesla Solar Roof",
    }


def test_creates_scoped_handoff_and_keeps_asset_type(client) -> None:
    publish(
        client,
        manifest(
            "wiki-etf-source",
            "ETF 概览",
            subject_types=["etf"],
            entrypoint_id="overview",
            intent="market.overview",
            label="ETF 概览",
        ),
    )
    publish(
        client,
        manifest(
            "wiki-etf-target",
            "ETF 结构",
            subject_types=["etf"],
            entrypoint_id="structure",
            intent="technical.structure",
            label="ETF 结构",
        ),
    )
    headers = {"X-User-Id": "alice", "X-Workspace-Id": "desk-1"}
    response = client.post(
        "/api/wiki/handoffs",
        headers=headers,
        json={
            "sourceModId": "wiki-etf-source",
            "targetModId": "wiki-etf-target",
            "entrypointId": "structure",
            "context": {
                "primarySubject": {
                    "type": "etf",
                    "canonicalId": "etf:CN:512010",
                    "displayName": "医药 ETF",
                    "market": "CN",
                    "symbol": "512010",
                    "assetType": "etf",
                },
                "relatedSubjects": [],
                "conceptIds": ["concept:CN:医药"],
                "intent": "market.overview",
                "timeframe": "daily",
            },
            "parameters": {"bars": 480},
        },
    )
    assert response.status_code == 201, response.text
    handoff = response.json()
    assert handoff["subject"]["canonicalId"] == "etf:CN:512010"
    assert handoff["subject"]["assetType"] == "etf"
    assert handoff["intent"] == "technical.structure"
    assert handoff["parameters"] == {"period": "daily", "bars": 480}
    assert "sourceSnapshotId" not in handoff

    handoff_id = handoff["id"]
    stored = client.get(f"/api/wiki/handoffs/{handoff_id}", headers=headers)
    assert stored.status_code == 200
    assert "sourceSnapshotId" not in stored.json()
    assert client.get(
        f"/api/wiki/handoffs/{handoff_id}",
        headers={"X-User-Id": "alice", "X-Workspace-Id": "other"},
    ).status_code == 404
    assert client.delete(f"/api/wiki/handoffs/{handoff_id}", headers=headers).status_code == 204
    assert client.get(f"/api/wiki/handoffs/{handoff_id}", headers=headers).status_code == 404


def test_rejects_stock_fund_identity_mismatch(client) -> None:
    response = client.post(
        "/api/wiki/link-resolutions",
        json={
            "sourceModId": "market-daily",
            "context": {
                "primarySubject": {
                    "type": "fund",
                    "canonicalId": "security:CN:300308",
                    "displayName": "错误标的",
                    "market": "CN",
                    "symbol": "300308",
                    "assetType": "fund",
                },
                "intent": "market.overview",
            },
        },
    )
    assert response.status_code == 422


def test_subject_search_normalizes_name_code_alias_and_asset_type(client) -> None:
    class SubjectSearchClient:
        async def invoke(self, service, capability_id, input_data):
            assert capability_id == "market.symbol-search"
            if input_data["query"] == "zjxc":
                return {
                    "data": {
                        "items": [
                            {
                                "symbol": "300308",
                                "name": "中际旭创",
                                "market": "CN",
                                "assetType": "stock",
                            },
                            {
                                "symbol": "03308",
                                "name": "中际旭创",
                                "market": "HK",
                                "assetType": "stock",
                            },
                            {
                                "symbol": "003562",
                                "name": "诺德成长精选C",
                                "market": "CN",
                                "assetType": "fund",
                            },
                        ]
                    }
                }
            return {
                "data": {
                    "items": [{
                        "symbol": "110022",
                        "name": "易方达消费行业股票",
                        "market": "CN",
                        "assetType": "fund",
                    }]
                }
            }

    client.app.state.data_service_client = SubjectSearchClient()

    stock = client.get("/api/wiki/subjects", params={"query": "zjxc"})
    assert stock.status_code == 200, stock.text
    assert stock.json()[0]["subject"] == {
        "type": "security",
        "canonicalId": "security:CN:300308",
        "displayName": "中际旭创",
        "market": "CN",
        "symbol": "300308",
        "assetType": "stock",
    }
    assert "zjxc" in stock.json()[0]["aliases"]

    fund = client.get(
        "/api/wiki/subjects",
        params={"query": "110022", "type": "fund", "market": "CN"},
    )
    assert fund.status_code == 200, fund.text
    assert fund.json()[0]["subject"]["canonicalId"] == "fund:CN:110022"
    assert fund.json()[0]["subject"]["assetType"] == "fund"


def test_fund_research_is_recommended_only_for_fund_subjects(client) -> None:
    publish(
        client,
        manifest(
            "wiki-event-source",
            "日线事件",
            subject_types=["security", "etf", "fund"],
            entrypoint_id="timeline",
            intent="event.timeline",
            label="日线事件",
        ),
    )
    publish(
        client,
        manifest(
            "wiki-fund-research",
            "基金与 ETF 研究",
            subject_types=["etf", "fund"],
            entrypoint_id="research",
            intent="fund.research",
            label="基金与 ETF 研究",
        ),
    )
    response = client.post(
        "/api/wiki/link-resolutions",
        json={
            "sourceModId": "wiki-event-source",
            "context": {
                "primarySubject": {
                    "type": "fund",
                    "canonicalId": "fund:CN:110022",
                    "displayName": "易方达消费行业股票",
                    "market": "CN",
                    "symbol": "110022",
                    "assetType": "fund",
                },
                "intent": "event.timeline",
            },
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["links"][0]["targetModId"] == "wiki-fund-research"
    assert response.json()["links"][0]["match"]["intentScore"] == 25
