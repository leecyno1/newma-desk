#!/usr/bin/env python3
"""Run AI summary against a stored snapshot or selected period."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.db import SessionLocal, init_db
from app.services.snapshot_service import upsert_snapshot
from app.routers.ai import _run_summary_local  # type: ignore


def _parse_message_ids(raw: Optional[str]) -> List[int]:
    if not raw:
        return []
    ids: List[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError:
            continue
    return sorted(set(ids))


def load_prompts(path: Optional[Path]) -> Dict[str, Any]:
    if not path:
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        return data
    raise ValueError("prompts file must contain a JSON object")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local AI summary via snapshot pipeline")
    parser.add_argument("--period", default="1day", help="time window period (1day/3days/1week/1month)")
    parser.add_argument("--message-ids", dest="message_ids", help="comma separated message ids", default=None)
    parser.add_argument("--prompts", type=Path, help="optional prompts JSON file", default=None)
    parser.add_argument("--output", type=Path, help="optional output JSON path", default=None)
    parser.add_argument("--print-html", action="store_true", help="print module html snippets")

    args = parser.parse_args()

    init_db()
    session = SessionLocal()
    try:
        message_ids = _parse_message_ids(args.message_ids)
        filters: Dict[str, Any] = {"period": args.period} if args.period else {}
        snapshot = upsert_snapshot(session, message_ids=message_ids, filters=filters, options={})
        session.commit()

        prompts = load_prompts(args.prompts)

        contact_ratings: Dict[str, Any] = {}
        contacts_full = snapshot.contact_ratings or {}
        for cid, val in contacts_full.items():
            if isinstance(val, dict) and "rating" in val:
                try:
                    contact_ratings[str(cid)] = float(val["rating"])
                except (TypeError, ValueError):
                    continue
            else:
                try:
                    contact_ratings[str(cid)] = float(val)
                except (TypeError, ValueError):
                    continue

        payload = {
            "messages": snapshot.messages or [],
            "prompts": prompts,
            "contact_ratings": contact_ratings,
            "contact_details": contacts_full,
            "meta": snapshot.meta or {},
        }

        result = _run_summary_local(payload)

        output = {
            "status": result.get("status"),
            "snapshot_id": snapshot.id,
            "filters": snapshot.filters,
            "meta": snapshot.meta,
            "result": result.get("result"),
        }

        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Summary written to {args.output}")
        else:
            print(json.dumps(output, ensure_ascii=False, indent=2))

        if args.print_html and isinstance(output.get("result"), dict):
            modules = output["result"]
            for key, value in modules.items():
                if isinstance(value, str):
                    snippet = value.strip()
                    print("\n===", key, "===")
                    print(snippet[:2000] + ("..." if len(snippet) > 2000 else ""))
    finally:
        session.close()


if __name__ == "__main__":
    main()
