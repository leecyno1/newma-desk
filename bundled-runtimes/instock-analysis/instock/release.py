"""Identity of the installed artifact, captured once when the process imports it."""

import json
import re
from pathlib import Path


def load_release(path):
    unknown = {"projectId": "instock-analysis", "packageVersion": None,
               "sourceCommit": None, "sourceDirty": None}
    try:
        release = json.loads(Path(path).read_text("utf-8"))
    except (OSError, ValueError):
        return unknown
    if not isinstance(release, dict) or release.get("projectId") != unknown["projectId"]:
        return unknown
    commit = release.get("sourceCommit")
    dirty = release.get("sourceDirty")
    return {**unknown,
            "packageVersion": release.get("packageVersion") if isinstance(release.get("packageVersion"), str) else None,
            "sourceCommit": commit.lower() if isinstance(commit, str) and re.fullmatch(r"[a-fA-F0-9]{40,64}", commit) else None,
            "sourceDirty": dirty if isinstance(dirty, bool) else None}


_PROCESS_RELEASE = load_release(Path(__file__).with_name("_release.json"))


def process_release():
    # Updating/reinstalling files or changing cwd does not relabel a live process.
    return dict(_PROCESS_RELEASE)

