#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = [
    ROOT / "README.md",
    ROOT / "INSTALLATION.md",
    ROOT / "scripts" / "install.sh",
    ROOT / "scripts" / "verify_installation.py",
    ROOT / "skills" / "dasheng-media-sop" / "SKILL.md",
]
REQUIRED_DIRS = [
    ROOT / "docs",
    ROOT / "scripts",
    ROOT / "skills",
]


def main() -> int:
    missing = [str(path) for path in REQUIRED_FILES if not path.exists()]
    missing += [str(path) for path in REQUIRED_DIRS if not path.exists()]
    if missing:
        print("❌ 安装验证失败，缺少以下路径:")
        for item in missing:
            print(f" - {item}")
        return 1

    print("✅ 安装验证通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
