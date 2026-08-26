#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path


DEFAULT_RUNTIME_ROOT = Path.home() / "AI_MODELS" / "digital-human"


def digital_human_runtime_root() -> Path:
    configured = os.environ.get("DASHENG_DIGITAL_HUMAN_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    return DEFAULT_RUNTIME_ROOT.resolve()
