"""Build provenance survives packaging and never follows the running cwd."""

import json
import runpy
import shutil
import subprocess
from pathlib import Path

from build_release import source_release
from instock.release import load_release

ROOT = Path(__file__).resolve().parents[1]


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def repository(root):
    git(root, "init", "-q")
    (root / "source.py").write_text("value = 1\n")
    git(root, "add", "source.py")
    git(root, "-c", "user.name=Build Test", "-c", "user.email=build@example.invalid",
        "commit", "-qm", "baseline")
    return git(root, "rev-parse", "HEAD")


def test_build_records_clean_dirty_and_untracked_source(tmp_path):
    commit = repository(tmp_path)
    release = source_release(tmp_path, "1.0")
    assert release == {"projectId": "instock-analysis", "packageVersion": "1.0",
                       "sourceCommit": commit, "sourceDirty": False}
    (tmp_path / "source.py").write_text("value = 2\n")
    assert source_release(tmp_path, "1.0")["sourceDirty"] is True
    git(tmp_path, "restore", "source.py")
    (tmp_path / "new.py").write_text("new = True\n")
    assert source_release(tmp_path, "1.0")["sourceDirty"] is True


def test_sdist_preserves_release_without_borrowing_parent_git(tmp_path):
    repository(tmp_path)
    source = tmp_path / "extracted"
    (source / "instock").mkdir(parents=True)
    embedded = {"projectId": "instock-analysis", "packageVersion": "1.0",
                "sourceCommit": "a" * 40, "sourceDirty": True}
    (source / "instock/_release.json").write_text(json.dumps(embedded))
    assert source_release(source, "1.0") == embedded
    (source / "instock/_release.json").unlink()
    assert source_release(source, "1.0") == {
        **embedded, "sourceCommit": None, "sourceDirty": None}


def test_own_repository_does_not_reuse_stale_embedded_release(tmp_path):
    commit = repository(tmp_path)
    (tmp_path / "instock").mkdir()
    (tmp_path / "instock/_release.json").write_text(json.dumps({
        "projectId": "instock-analysis", "packageVersion": "1.0",
        "sourceCommit": "b" * 40, "sourceDirty": False}))
    release = source_release(tmp_path, "1.0")
    assert release["sourceCommit"] == commit
    assert release["sourceDirty"] is True


def test_sdist_package_version_cannot_be_silently_changed(tmp_path):
    (tmp_path / "instock").mkdir()
    (tmp_path / "instock/_release.json").write_text(json.dumps({
        "projectId": "instock-analysis", "packageVersion": "old",
        "sourceCommit": "a" * 40, "sourceDirty": False}))
    import pytest
    with pytest.raises(ValueError, match="packageVersion"):
        source_release(tmp_path, "new")


def test_missing_or_invalid_runtime_metadata_stays_unknown(tmp_path):
    path = tmp_path / "_release.json"
    assert load_release(path)["sourceCommit"] is None
    path.write_text(json.dumps({"projectId": "other", "sourceCommit": "a" * 40,
                                "sourceDirty": False}))
    assert load_release(path)["sourceCommit"] is None
    path.write_text("broken")
    assert load_release(path)["sourceCommit"] is None


def test_process_keeps_startup_identity_after_artifact_changes(tmp_path):
    shutil.copyfile(ROOT / "instock/release.py", tmp_path / "release.py")
    path = tmp_path / "_release.json"
    before = {"projectId": "instock-analysis", "packageVersion": "1.0",
              "sourceCommit": "a" * 40, "sourceDirty": False}
    path.write_text(json.dumps(before))
    module = runpy.run_path(str(tmp_path / "release.py"))
    path.write_text(json.dumps({**before, "sourceCommit": "b" * 40}))
    assert module["process_release"]() == before
    returned = module["process_release"]()
    returned["sourceCommit"] = "c" * 40
    assert module["process_release"]() == before


def test_source_execution_never_claims_current_git_as_loaded_release(tmp_path):
    repository(tmp_path)
    shutil.copyfile(ROOT / "instock/release.py", tmp_path / "release.py")
    module = runpy.run_path(str(tmp_path / "release.py"))
    assert module["process_release"]()["sourceCommit"] is None
    assert module["process_release"]()["sourceDirty"] is None

