import json
from pathlib import Path

from vibe_visualization_api.finance_pilots.policy import FinancePilotPolicy


def descriptor_path(tmp_path: Path) -> Path:
    descriptor = {
        "schemaVersion": "1.0",
        "pilots": [
            {
                "id": "daily-stock-analysis",
                "label": "Daily Stock Analysis",
                "mode": "analysis-only",
                "audit": {
                    "revision": "a" * 40,
                    "tag": "v1",
                    "reviewedAt": "2026-07-27",
                    "dependencyAudit": "blocked-unpinned-requirements",
                },
                "activation": {
                    "defaultEnabled": False,
                    "env": "NEWMA_DESK_DSA_TEST_ENABLED",
                },
                "workspace": {
                    "env": "NEWMA_DESK_DSA_TEST_WORKSPACE",
                    "candidates": ["finance-pilots/dsa"],
                },
                "runtime": {"origin": "http://127.0.0.1:39221"},
                "isolation": {
                    "environmentAllowlist": ["TZ", "LOG_LEVEL"]
                },
                "capabilities": {"allow": ["research.analysis-context.read"]},
            }
        ],
    }
    path = tmp_path / "pilots.json"
    path.write_text(json.dumps(descriptor), encoding="utf-8")
    return path


def test_policy_refuses_requested_pilot_until_dependency_audit_is_clean(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "finance-pilots" / "dsa"
    workspace.mkdir(parents=True)
    policy = FinancePilotPolicy(
        descriptor_path(tmp_path),
        project_root=tmp_path,
        environment={
            "NEWMA_DESK_DSA_TEST_ENABLED": "true",
            "TZ": "Asia/Shanghai",
            "OPENAI_API_KEY": "must-not-cross-pilot-seam",
        },
    )

    status = policy.status("daily-stock-analysis")

    assert status.state == "blocked"
    assert status.activatable is False
    assert status.reasons == [
        "dependency-audit:blocked-unpinned-requirements"
    ]
    assert policy.sanitized_environment("daily-stock-analysis") == {
        "TZ": "Asia/Shanghai"
    }


def test_policy_keeps_unrequested_pilot_disabled(tmp_path: Path) -> None:
    policy = FinancePilotPolicy(
        descriptor_path(tmp_path),
        project_root=tmp_path,
        environment={},
    )

    status = policy.status("daily-stock-analysis")

    assert status.state == "disabled"
    assert status.requested is False
    assert "activation-not-requested" in status.reasons
    assert "workspace-missing" in status.reasons
