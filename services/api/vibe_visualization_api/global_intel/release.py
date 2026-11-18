"""Installed artifact identity, fixed for the lifetime of this process."""
import json
import re
from pathlib import Path


def load_release(path):
    unknown = {"projectId": "global-intelligence", "packageVersion": None,
               "sourceCommit": None, "sourceDirty": None}
    try:
        identity = json.loads(Path(path).read_text("utf-8"))
    except (OSError, ValueError):
        return unknown
    if not isinstance(identity, dict) or identity.get("projectId") != unknown["projectId"]:
        return unknown
    commit, dirty = identity.get("sourceCommit"), identity.get("sourceDirty")
    return {**unknown,
            "packageVersion": identity.get("packageVersion") if isinstance(identity.get("packageVersion"), str) else None,
            "sourceCommit": commit.lower() if isinstance(commit, str) and re.fullmatch(r"[a-fA-F0-9]{40,64}", commit) else None,
            "sourceDirty": dirty if isinstance(dirty, bool) else None}


_PROCESS_RELEASE = load_release(Path(__file__).with_name("_release.json"))


def process_release():
    return dict(_PROCESS_RELEASE)
