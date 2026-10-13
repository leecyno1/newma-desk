"""Bounded, opt-in consolidated note passages, never inferred capital amounts."""
import re

TOPICS = (
    ("现金与受限资金", ("货币资金", "受限资产", "使用权受到限制", "流量表补充资料", "现金和现金等价物")),
    ("债务与租赁", ("借款", "应付债券", "年内到期的非流动负债", "租赁负债")),
    ("股本", ("股本",)),
)
CHAPTER = re.compile(r"^([一二三四五六七八九十]+)、([\u4e00-\u9fff（）()、]+)$")
NOTE = re.compile(r"^\d{1,3}[、．.]\s*(?:1)?[\u4e00-\u9fff（）()、/ \t]+$")
NEXT_CHAPTER = re.compile(r"^(研发支出|合并范围|在其他主体|与金融工具|金融工具|公允价值|关联方|股份支付|承诺及|资产负债表日后|其他重要事项|母公司|补充资料)")


def capital_note_candidates(pages):
    scanned, passages = [], []
    active, title, topics, lines, page_no = False, "", [], [], 0
    budget, omitted = 36000, False

    def flush(incomplete=False):
        nonlocal lines, budget, omitted
        text = "\n".join(lines).strip()
        if text and topics:
            if budget <= 0 or len(passages) >= 24:
                omitted = True
            else:
                kept = text[:min(6000, budget)]
                passages.append({"id": f"capital-note:{page_no}:{len(passages)}", "page": page_no,
                                 "title": title, "topics": topics[:], "text": kept,
                                 "truncated": incomplete or len(kept) < len(text)})
                budget -= len(kept)
        lines = []

    for page in pages:
        if len(scanned) >= 200:
            break
        page_no = page["page"]
        scanned.append(page_no)
        for raw in page["text"].splitlines():
            clean = re.sub(r"\s+", "", raw)
            if re.fullmatch(r"\d+/\d+", clean) or re.fullmatch(r".*20\d{2}年年度报告", clean):
                continue
            if re.fullmatch(r"[一二三四五六七八九十]+、合并财务报表项目(?:注释|附注)", clean):
                active = True
                continue
            chapter = CHAPTER.fullmatch(clean)
            if active and chapter:
                # Note subtables use 一、二、三; consolidated chapter headings
                # end this section (研发支出/合并范围变更/母公司附注 etc.).
                if NEXT_CHAPTER.match(chapter[2]):
                    flush()
                    return result(passages, scanned, omitted)
            if not active:
                continue
            if NOTE.fullmatch(raw.strip()):
                flush()
                title = clean
                topics = [topic for topic, terms in TOPICS if any(term in clean for term in terms)]
            if topics:
                lines.append(re.sub(r"[ \t]{3,}", "  ", raw.strip()))
        flush()
    # A selected note at the scan boundary may continue beyond the supplied pages.
    if passages and topics and passages[-1]["page"] == page_no:
        passages[-1]["truncated"] = True
    return result(passages, scanned, omitted)


def result(passages, scanned, omitted):
    return {"capitalNotes": passages, "capitalNotesReadPages": scanned, "capitalNotesWarnings": [
        f"检索前 {len(scanned)} 页内明确标注的合并财务报表项目注释；候选按附注与物理页分段，最多 24 段、每段 6000 字符、合计 36000 字符。跨页内容须对照原报，未命中不代表未披露。",
        "仅保存原文，不提取或汇总债务、可用现金及稀释股数。现金等价物之外的受限资金不得重复扣减；一年内到期负债不得与附注明细重复相加。",
        *(["候选超过数量或文字限额，部分未列出，请查看原报补充。"] if omitted else []),
        *(["未定位到可用资本附注；可能超出扫描范围或版式不支持，请人工查阅原报。"] if not passages else []),
    ]}
