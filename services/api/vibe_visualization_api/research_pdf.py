"""Bounded PDF text worker. Physical page numbers are not printed page labels."""
from __future__ import annotations

from io import BytesIO
import json
import sys

from pypdf import PdfReader

MAX_PDF_BYTES = 20_000_000
MAX_TEXT = 60_000


def extract_pdf(data: bytes, start: int, count: int) -> dict:
    base = {"documentType": "pdf", "extractionScope": "pdf-pages", "publishedAt": None,
            "paragraphs": [], "text": "", "readPages": [], "textLayerMissingPages": [],
            "truncated": False, "claimVerified": False}
    if not data.startswith(b"%PDF-"):
        return {**base, "status": "unreadable"}
    reader = PdfReader(BytesIO(data))
    if reader.is_encrypted:
        return {**base, "status": "encrypted"}
    total = len(reader.pages)
    base.update(pageCount=total, title=str((reader.metadata or {}).get("/Title", ""))[:500])
    if start > total:
        return {**base, "status": "page_out_of_range"}
    size = 0
    for page_number in range(start, min(start + count, total + 1)):
        text = (reader.pages[page_number - 1].extract_text(extraction_mode="layout") or "").strip()
        base["readPages"].append(page_number)
        if not text:
            base["textLayerMissingPages"].append(page_number)
            continue
        # Blocks are extraction locators, not inferred semantic paragraphs or table rows.
        for offset in range(0, len(text), 1500):
            block = text[offset:offset + 1500]
            locator = f"PDF 物理第 {page_number} 页 · 文本块 {offset // 1500 + 1}"
            rendered = f"[{locator}]\n{block}\n"
            if size + len(rendered) > MAX_TEXT:
                base["truncated"] = True
                break
            base["paragraphs"].append({"page": page_number, "locator": locator, "text": block})
            base["text"] += rendered
            size += len(rendered)
        if base["truncated"]:
            break
    base["partialDocument"] = start != 1 or len(base["readPages"]) < total or base["truncated"]
    base["nextPage"] = base["readPages"][-1] + 1 if base["readPages"] and base["readPages"][-1] < total else None
    return {**base, "status": "readable" if base["paragraphs"] else "no_text"}


def main() -> None:
    # A remote PDF cannot keep the API worker busy after the caller times out.
    if sys.platform == "linux":
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (1_500_000_000, 1_500_000_000))
    try:
        data = sys.stdin.buffer.read(MAX_PDF_BYTES + 1)
        result = ({"status": "too_large"} if len(data) > MAX_PDF_BYTES
                  else extract_pdf(data, int(sys.argv[1]), int(sys.argv[2])))
    except Exception:
        result = {"status": "unreadable", "documentType": "pdf", "claimVerified": False}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
