"""Capture source identity only at build time, never from a running service."""

import json
import subprocess
from pathlib import Path


def source_release(root, package_version):
    root = Path(root).resolve()
    unknown = {"projectId": "instock-analysis", "packageVersion": package_version,
               "sourceCommit": None, "sourceDirty": None}
    try:
        def git(*args):
            return subprocess.check_output(
                ["git", "-C", str(root), *args], text=True, stderr=subprocess.DEVNULL,
                timeout=5).strip()
        # A Desk snapshot is inside Desk's repo, not the native stock repo.
        # Do not attribute that parent repository's commit to this project.
        if Path(git("rev-parse", "--show-toplevel")).resolve() == root:
            return {**unknown, "sourceCommit": git("rev-parse", "HEAD"),
                    "sourceDirty": bool(git("status", "--porcelain", "--untracked-files=normal"))}
    except (OSError, subprocess.SubprocessError):
        pass

    embedded = root / "instock/_release.json"
    if not embedded.is_file():
        return unknown
    release = json.loads(embedded.read_text("utf-8"))
    if release.get("projectId") != "instock-analysis":
        raise ValueError("Unexpected release projectId")
    if release.get("packageVersion") != package_version:
        raise ValueError("Embedded release packageVersion does not match the build")
    return {key: release.get(key) for key in unknown}

