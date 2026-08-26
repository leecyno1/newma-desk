#!/usr/bin/env python3
"""Build traceable evidence assets from official PDF filings.

The request supplies human-selected facts, while this module verifies every
quoted excerpt against the referenced PDF page before emitting an asset.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_source_text(value: str) -> str:
    value = value.translate(
        str.maketrans(
            {
                "\u2018": "'",
                "\u2019": "'",
                "\u201c": '"',
                "\u201d": '"',
                "\u2013": "-",
                "\u2014": "-",
            }
        )
    )
    value = value.replace("\u00ad", "")
    value = re.sub(r"-\s*\n\s*", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip().casefold()


def extract_pdf_pages(path: Path) -> list[str]:
    completed = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.split("\f")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_excerpt(page_text: str, excerpt: str) -> bool:
    page_normalized = normalize_source_text(page_text).replace("-", "")
    excerpt_normalized = normalize_source_text(excerpt).replace("-", "")
    return excerpt_normalized in page_normalized


def validate_document(document: dict[str, Any]) -> dict[str, Any]:
    pdf_path = Path(str(document["local_pdf"])).expanduser().resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"Official PDF does not exist: {pdf_path}")
    pages = extract_pdf_pages(pdf_path)
    facts: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for raw_fact in document.get("facts") or []:
        fact = dict(raw_fact)
        page_number = int(fact.get("page") or 0)
        excerpt = str(fact.get("source_excerpt") or "").strip()
        valid_page = 1 <= page_number <= len(pages)
        excerpt_verified = bool(excerpt and valid_page and verify_excerpt(pages[page_number - 1], excerpt))
        fact["source_verified"] = excerpt_verified
        facts.append(fact)
        if not excerpt_verified:
            failures.append(
                {
                    "fact_id": str(fact.get("id") or "unknown"),
                    "page": page_number,
                    "reason": "source_excerpt_not_found_on_page" if valid_page else "page_out_of_range",
                }
            )

    return {
        "id": str(document["id"]),
        "company": str(document.get("company") or document["id"]),
        "period": str(document.get("period") or ""),
        "source_url": str(document.get("source_url") or ""),
        "published_at": str(document.get("published_at") or ""),
        "local_pdf": str(pdf_path),
        "sha256": sha256_file(pdf_path),
        "page_count": len([page for page in pages if page.strip()]),
        "facts": facts,
        "status": "ok" if not failures else "fail",
        "failures": failures,
    }


def _write_csv(path: Path, documents: list[dict[str, Any]]) -> None:
    columns = [
        "document_id",
        "company",
        "period",
        "fact_id",
        "category",
        "metric",
        "display_value",
        "yoy_pct",
        "page",
        "source_verified",
        "source_url",
        "source_excerpt",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for document in documents:
            for fact in document["facts"]:
                writer.writerow(
                    {
                        "document_id": document["id"],
                        "company": document["company"],
                        "period": document["period"],
                        "fact_id": fact.get("id"),
                        "category": fact.get("category"),
                        "metric": fact.get("metric"),
                        "display_value": fact.get("display_value"),
                        "yoy_pct": fact.get("yoy_pct"),
                        "page": fact.get("page"),
                        "source_verified": fact.get("source_verified"),
                        "source_url": document.get("source_url"),
                        "source_excerpt": fact.get("source_excerpt"),
                    }
                )


def build_review_html(asset: dict[str, Any]) -> str:
    rows: list[str] = []
    for document in asset["documents"]:
        for fact in document["facts"]:
            verified = bool(fact.get("source_verified"))
            rows.append(
                "<tr>"
                f"<td><b>{html.escape(document['company'])}</b><br><span>{html.escape(document['period'])}</span></td>"
                f"<td>{html.escape(str(fact.get('metric') or fact.get('id') or ''))}</td>"
                f"<td>{html.escape(str(fact.get('display_value') or ''))}</td>"
                f"<td>{html.escape(str(fact.get('yoy_pct') if fact.get('yoy_pct') is not None else '-'))}</td>"
                f"<td>P{html.escape(str(fact.get('page') or '-'))}</td>"
                f"<td class={'ok' if verified else 'bad'}>{'verified' if verified else 'failed'}</td>"
                f"<td>{html.escape(str(fact.get('source_excerpt') or ''))}</td>"
                "</tr>"
            )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(asset['title'])}</title><style>
:root{{--paper:#f5f1e8;--ink:#18201b;--line:#c9c1b2;--ok:#176b48;--bad:#a12b2b}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:14px/1.55 "PingFang SC",sans-serif}}
main{{max-width:1500px;margin:auto;padding:28px}}h1{{font:700 34px/1.15 Georgia,"Songti SC",serif;margin:0 0 8px}}
table{{width:100%;border-collapse:collapse;background:#fff}}th,td{{border:1px solid var(--line);padding:10px;text-align:left;vertical-align:top}}
th{{background:#ddd5c6;position:sticky;top:0}}td:last-child{{max-width:620px}}.ok{{color:var(--ok);font-weight:700}}.bad{{color:var(--bad);font-weight:700}}
</style></head><body><main><h1>{html.escape(asset['title'])}</h1>
<p>Only excerpts verified against the exact official PDF page can pass.</p>
<table><thead><tr><th>Company</th><th>Metric</th><th>Value</th><th>YoY %</th><th>Page</th><th>Check</th><th>Official excerpt</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></main></body></html>"""


def build_asset(request: dict[str, Any], output_dir: Path, created_at: str) -> dict[str, Any]:
    asset_id = str(request["id"])
    asset_dir = output_dir / asset_id
    asset_dir.mkdir(parents=True, exist_ok=True)
    documents = [validate_document(document) for document in request.get("documents") or []]
    failures = [
        {"document_id": document["id"], **failure}
        for document in documents
        for failure in document.get("failures") or []
    ]
    payload = {
        "schema_version": "dasheng.video.official_evidence_asset.v1",
        "id": asset_id,
        "title": str(request.get("title") or asset_id),
        "created_at": created_at,
        "status": "ok" if documents and not failures else "fail",
        "documents": documents,
        "failures": failures,
    }
    json_path = asset_dir / f"{asset_id}.json"
    csv_path = asset_dir / f"{asset_id}.csv"
    html_path = asset_dir / f"{asset_id}.review.html"
    write_json(json_path, payload)
    _write_csv(csv_path, documents)
    html_path.write_text(build_review_html(payload), encoding="utf-8")
    return {
        "id": asset_id,
        "title": payload["title"],
        "status": payload["status"],
        "json_path": str(json_path),
        "csv_path": str(csv_path),
        "review_html": str(html_path),
        "source_documents": [
            {
                "id": document["id"],
                "source_url": document["source_url"],
                "local_pdf": document["local_pdf"],
                "sha256": document["sha256"],
            }
            for document in documents
        ],
        "failures": failures,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build verified evidence assets from official PDF filings.")
    parser.add_argument("--request", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--allow-failing", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    request_path = Path(args.request).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    request = read_json(request_path)
    created_at = datetime.now().astimezone().isoformat(timespec="seconds")
    assets = [build_asset(item, output_dir, created_at) for item in request.get("assets") or []]
    failures = [failure for asset in assets for failure in asset.get("failures") or []]
    manifest = {
        "schema_version": "dasheng.video.official_evidence_manifest.v1",
        "created_at": created_at,
        "request": str(request_path),
        "status": "pass" if assets and not failures else "fail",
        "assets": assets,
        "failures": failures,
    }
    manifest_path = output_dir / "official_evidence_manifest.json"
    write_json(manifest_path, manifest)
    print(json.dumps({**manifest, "manifest": str(manifest_path)}, ensure_ascii=False, indent=2))
    return 0 if manifest["status"] == "pass" or args.allow_failing else 1


if __name__ == "__main__":
    raise SystemExit(main())
