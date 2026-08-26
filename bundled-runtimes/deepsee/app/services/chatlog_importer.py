from __future__ import annotations

"""
Directory importer skeleton for offline/incremental ingestion from CHATLOG_DIR.

Future work:
- Walk files under CHATLOG_DIR
- Parse supported formats (e.g., JSON/SQLite) and map to models.Message/Chat/Contact
- Upsert into DB and refresh FTS
- Provide a CLI or scheduled task
"""

from typing import Optional
from ..config import settings


def scan_once(path: Optional[str] = None):
    path = path or settings.CHATLOG_DIR
    if not path:
        return {"status": "skipped", "reason": "CHATLOG_DIR not set"}
    # TODO: implement parsing logic
    return {"status": "ok", "dir": path, "imported": 0}

