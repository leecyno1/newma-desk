import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from project_run_manifest import build_manifest, save_manifest  # noqa: E402
from run_mainline_stage import update_project_manifest_stage  # noqa: E402


class Args:
    project_manifest: str
    no_project_manifest = False

    def __init__(self, project_manifest: Path):
        self.project_manifest = str(project_manifest)


def creator_output(tmp_path: Path) -> Path:
    return tmp_path / "自媒体创作" / "run_mainline"


def test_update_project_manifest_stage_registers_artifact(tmp_path):
    output_root = creator_output(tmp_path)
    manifest = build_manifest(
        title="主链回写测试",
        pipeline_id="mainline",
        output_root=output_root,
        run_id="run_mainline",
    )
    manifest_path = output_root / "project_run_manifest.json"
    save_manifest(manifest, manifest_path)
    artifact = output_root / "draft_manifest.json"
    artifact.write_text('{"stage":"draft","run_id":"run_mainline"}', encoding="utf-8")

    update_project_manifest_stage(
        args=Args(manifest_path),
        run_id="run_mainline",
        stage="draft",
        status="complete",
        artifact_paths=[("draft_manifest", artifact)],
    )

    updated = manifest_path.read_text(encoding="utf-8")
    assert '"status": "complete"' in updated
    assert '"type": "draft_manifest"' in updated


def test_update_project_manifest_stage_can_be_disabled(tmp_path):
    output_root = creator_output(tmp_path)
    manifest = build_manifest(
        title="主链跳过测试",
        pipeline_id="mainline",
        output_root=output_root,
        run_id="run_mainline",
    )
    manifest_path = output_root / "project_run_manifest.json"
    save_manifest(manifest, manifest_path)

    args = Args(manifest_path)
    args.no_project_manifest = True
    update_project_manifest_stage(
        args=args,
        run_id="run_mainline",
        stage="draft",
        status="complete",
        artifact_paths=[],
    )

    assert '"status": "pending"' in manifest_path.read_text(encoding="utf-8")
