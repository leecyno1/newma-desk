import hashlib
import os
import sys
import tempfile
import time
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.local_research_folder_service import (  # noqa: E402
    FolderValidationError,
    LocalResearchFolderService,
)
from services.research_memo_manager_matcher import ResearchMemoManagerMatcher  # noqa: E402


class MemoryResearchFolderRepo:
    def __init__(self):
        self.folders = {}
        self.documents = {}
        self.reports = {}
        self._sequence = 0

    def create_folder(self, folder):
        self._sequence += 1
        folder_id = f"folder-{self._sequence}"
        saved = {**deepcopy(folder), "id": folder_id}
        self.folders[folder_id] = saved
        return deepcopy(saved)

    def list_folders(self):
        return [deepcopy(folder) for folder in self.folders.values()]

    def get_folder(self, folder_id):
        folder = self.folders.get(folder_id)
        return deepcopy(folder) if folder else None

    def update_folder(self, folder_id, fields):
        self.folders[folder_id].update(deepcopy(fields))
        return deepcopy(self.folders[folder_id])

    def get_document(self, folder_id, relative_path):
        document = self.documents.get((folder_id, relative_path))
        return deepcopy(document) if document else None

    def find_document_by_hash(self, content_hash, exclude_folder_id=None, exclude_relative_path=None):
        for (folder_id, relative_path), document in self.documents.items():
            if folder_id == exclude_folder_id and relative_path == exclude_relative_path:
                continue
            if document.get("content_hash") == content_hash and document.get("report_id"):
                return deepcopy(document)
        return None

    def upsert_document(self, document):
        key = (document["folder_id"], document["relative_path"])
        saved = {**deepcopy(self.documents.get(key, {})), **deepcopy(document)}
        self.documents[key] = saved
        return deepcopy(saved)

    def create_report(self, report):
        self._sequence += 1
        report_id = f"report-{self._sequence}"
        saved = {**deepcopy(report), "id": report_id}
        self.reports[report_id] = saved
        return deepcopy(saved)

    def update_report(self, report_id, fields):
        self.reports[report_id].update(deepcopy(fields))
        return deepcopy(self.reports[report_id])

    def get_report(self, report_id):
        report = self.reports.get(report_id)
        if not report:
            return None
        saved = deepcopy(report)
        saved["manager_links"] = deepcopy(saved.get("manager_links") or [])
        saved["manager_ids"] = [item["manager_id"] for item in saved["manager_links"]]
        saved["manager_names"] = [item["manager_name"] for item in saved["manager_links"]]
        return saved

    def list_report_manager_links(self, report_id):
        return deepcopy(self.reports[report_id].get("manager_links") or [])

    def set_report_manager_link(self, report_id, manager_id, manager_name, source="research_memo_review", confirmed_at=None):
        links = [
            item for item in self.reports[report_id].get("manager_links") or []
            if item.get("manager_id") != manager_id
        ]
        links.append({
            "manager_id": manager_id,
            "manager_name": manager_name,
            "source": source,
            "confirmed_at": confirmed_at,
        })
        self.reports[report_id]["manager_links"] = links

    def remove_report_manager_link(self, report_id, manager_id):
        self.reports[report_id]["manager_links"] = [
            item for item in self.reports[report_id].get("manager_links") or []
            if item.get("manager_id") != manager_id
        ]

    def list_reports_for_fund(self, wind_code):
        return [
            deepcopy(report)
            for report in self.reports.values()
            if wind_code in report.get("fund_ids", [])
        ]

    def list_pending_reviews(self, folder_id=None):
        pending = []
        for report in self.reports.values():
            if folder_id and report.get("local_folder_id") != folder_id:
                continue
            for proposal in report.get("review_proposals", []):
                if proposal.get("review_status") == "pending":
                    if proposal.get("kind") == "fund" and proposal.get("extraction_source") == "tushare.fund_manager":
                        continue
                    pending.append({
                        "report_id": report["id"],
                        "report_title": report["title"],
                        "report_date": report.get("report_date"),
                        "report_date_source": report.get("report_date_source"),
                        "report_date_precision": report.get("report_date_precision"),
                        **deepcopy(proposal),
                    })
        return pending


def _write_pdf(path: Path, text: str) -> None:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode("ascii"))
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
    )
    path.write_bytes(bytes(output))


def _write_docx(path: Path, text: str) -> None:
    from docx import Document

    document = Document()
    document.add_paragraph(text)
    document.save(path)


def _proposal(report, kind, value):
    return next(
        proposal
        for proposal in report.get("review_proposals", [])
        if proposal.get("kind") == kind and proposal.get("value") == value
    )


def main() -> int:
    repo = MemoryResearchFolderRepo()
    projection_calls = []
    manager_matcher = ResearchMemoManagerMatcher([
        {"wind_code": "manager-zhang-san", "name": "张三", "company": "测试基金管理有限公司"},
        {"wind_code": "manager-li-si", "name": "李四", "company": "测试基金管理有限公司"},
        {"wind_code": "manager-fan-yan", "name": "范妍", "company": "富国基金管理有限公司"},
        {"wind_code": "manager-zhang-xiu-qi", "name": "章秀奇", "company": "趣时资产管理有限公司"},
        {"wind_code": "manager-zhang-zhong-wei", "name": "张仲维", "company": "示例基金管理有限公司"},
    ])

    def profile_projector(report, affected_fund_ids):
        projection_calls.append((deepcopy(report), list(affected_fund_ids)))
        return {"projected_count": len(affected_fund_ids)}

    def model_extractor(content, filename):
        if "张三" not in content:
            return {"status": "complete", "provider": "fake", "model": "fake-model", "proposals": []}
        return {
            "status": "complete",
            "provider": "fake",
            "model": "fake-model",
            "proposals": [
                {"kind": "manager", "value": "张三", "confidence": 0.96, "excerpt": "基金经理：张三"},
                {"kind": "fund", "value": "000001.OF", "confidence": 0.95, "excerpt": "代表基金：000001.OF"},
                {"kind": "style_label", "value": "成长", "confidence": 0.91, "excerpt": "风格：成长、大盘、低换手"},
            ],
        }

    def manager_fund_resolver(manager_name, report_date, report_title):
        if manager_name != "张三":
            return []
        return [{
            "wind_code": "000001.OF",
            "fund_name": "测试基金",
            "management_company": "测试基金管理有限公司",
            "source": "tushare.fund_manager",
        }]

    service = LocalResearchFolderService(
        repo=repo,
        metadata_extractor=model_extractor,
        manager_matcher=manager_matcher,
        manager_fund_resolver=manager_fund_resolver,
        profile_projector=profile_projector,
        max_files=20,
        max_file_bytes=2_000_000,
    )

    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory) / "调研纪要"
        manager_folder = root / "张三"
        manager_folder.mkdir(parents=True)

        filename_proposals = service._extract_proposals(
            "关注回撤与估值。",
            root,
            root / "范妍 富国基金 250218.docx",
        )
        if not any(item.get("kind") == "manager" and item.get("value") == "范妍" for item in filename_proposals):
            raise AssertionError(f"Manager name in a standard memo filename must be extracted: {filename_proposals}")
        private_manager_proposals = service._extract_proposals(
            "关注回撤与估值。",
            root,
            root / "章秀奇 趣时 240703.docx",
        )
        private_manager = next(
            (item for item in private_manager_proposals if item.get("kind") == "manager" and item.get("value") == "章秀奇"),
            None,
        )
        if not private_manager or private_manager.get("candidate_id") != "manager-zhang-xiu-qi":
            raise AssertionError(f"Dated manager memo filenames must resolve to the manager catalog: {private_manager_proposals}")
        generic_filename_proposals = service._extract_proposals(
            "普通会议内容。",
            root,
            root / "会议纪要 市场讨论 240703.docx",
        )
        if any(item.get("kind") == "manager" and item.get("confidence", 0) >= 0.88 for item in generic_filename_proposals):
            raise AssertionError(f"Generic dated titles must not become high-confidence managers: {generic_filename_proposals}")
        speaker_proposals = service._extract_proposals(
            "会议时间：2025年2月11日\n主讲人：张仲维先生，现任基金经理。",
            root,
            root / "机构交流纪要.pdf",
        )
        if not any(item.get("kind") == "manager" and item.get("value") == "张仲维" for item in speaker_proposals):
            raise AssertionError(f"Named speaker must be extracted as a manager candidate: {speaker_proposals}")
        year_folder_proposals = service._extract_proposals(
            "普通会议内容。",
            root,
            root / "2026" / "市场讨论.docx",
        )
        if any(item.get("kind") == "manager" for item in year_folder_proposals):
            raise AssertionError(f"Year folders must not become manager identities: {year_folder_proposals}")
        company_proposals = service._extract_proposals(
            "普通会议内容。",
            root,
            root / "汇丰晋信 交流纪要.docx",
        )
        if any(item.get("kind") == "manager" for item in company_proposals):
            raise AssertionError(f"Fund companies must not become manager identities: {company_proposals}")
        false_style_proposals = service._extract_proposals(
            "会议主题是估值分析，组合需要均衡配置，渠道讨论了FOF业务。",
            root,
            root / "普通市场讨论.md",
        )
        if any(item.get("kind") in {"classification", "style_label"} for item in false_style_proposals):
            raise AssertionError(f"Ordinary keywords must not become style or classification proposals: {false_style_proposals}")
        market_style_proposals = service._extract_proposals(
            "大小盘风格：21年大盘见顶后，小盘长期跑赢大盘；成长风格阶段性跑赢价值。",
            root,
            root / "市场风格讨论.md",
        )
        if any(item.get("kind") == "style_label" for item in market_style_proposals):
            raise AssertionError(f"Market-style commentary must not become manager style evidence: {market_style_proposals}")
        explicit_style_proposals = service._extract_proposals(
            "投资风格：大中盘成长，偏低换手。",
            root,
            root / "经理风格.md",
        )
        explicit_styles = {
            item.get("value") for item in explicit_style_proposals if item.get("kind") == "style_label"
        }
        if explicit_styles != {"大中盘", "成长", "低换手"}:
            raise AssertionError(f"Explicit manager styles must be preserved: {explicit_style_proposals}")
        product_profile_proposals = service._extract_proposals(
            "• 产品风格：质量价值型。逆向投资、深度研究、长期主义",
            root,
            root / "产品风格.md",
        )
        product_profile_styles = {
            item.get("value")
            for item in product_profile_proposals
            if item.get("kind") == "style_label"
        }
        if not {"质量", "价值"}.issubset(product_profile_styles):
            raise AssertionError(f"Explicit product profile must produce grounded styles: {product_profile_proposals}")
        self_described_proposals = service._extract_proposals(
            "我的投资风格就是偏好左侧投资，非常重视估值性价比，并重视行业和个股的分散。",
            root,
            root / "经理自述.md",
        )
        self_described_styles = {
            item.get("value")
            for item in self_described_proposals
            if item.get("kind") == "style_label"
        }
        if not {"价值", "分散持仓"}.issubset(self_described_styles):
            raise AssertionError(f"Manager self-description must produce grounded styles: {self_described_proposals}")
        question_only_proposals = service._extract_proposals(
            "Q：和大家分享一下您的投资理念和投资风格？\n市场风格切换后，成长跑赢价值。",
            root,
            root / "问句与行情.md",
        )
        if any(item.get("kind") == "style_label" for item in question_only_proposals):
            raise AssertionError(f"Questions and market commentary must not become manager style: {question_only_proposals}")
        framework_proposals = service._extract_proposals(
            "个人是看周期出身的，所以投资框架比较偏供需的角度来把握变化，重仓风格。",
            root,
            root / "投资框架.md",
        )
        framework_styles = {
            item.get("value")
            for item in framework_proposals
            if item.get("kind") == "style_label"
        }
        if not {"周期", "集中持仓"}.issubset(framework_styles):
            raise AssertionError(f"Explicit investment framework must produce grounded styles: {framework_proposals}")
        scoped = service._scope_profile_proposals([
            service._proposal("fund", "000001.OF", root / "产品.md", root, "示例成长混合（000001.OF）", 0.92),
            service._proposal("fund", "000002.OF", root / "产品.md", root, "另一只基金", 0.9),
            service._proposal("style_label", "成长", root / "产品.md", root, "示例成长混合（000001.OF）：大盘成长风格", 0.94),
        ], "示例成长混合（000001.OF）：大盘成长风格\n经理整体风格偏均衡")
        scoped[0]["source_ref"]["fund_name"] = "示例成长混合-A"
        scoped = service._scope_profile_proposals(scoped, "示例成长混合（000001.OF）：大盘成长风格\n经理整体风格偏均衡")
        scoped_style = next(item for item in scoped if item.get("kind") == "style_label")
        if scoped_style.get("scope") != "fund" or scoped_style.get("target_fund_ids") != ["000001.OF"]:
            raise AssertionError(f"Product-level style must target only the named fund: {scoped_style}")
        manager_scoped = service._scope_profile_proposals([
            service._proposal("fund", "000003.OF", root / "经理.md", root, "现管理甲乙丙三只产品", 0.9),
            service._proposal("style_label", "价值", root / "经理.md", root, "产品风格：质量价值型", 0.94),
        ], "现管理甲乙丙三只产品\n产品风格：质量价值型")
        manager_style = next(item for item in manager_scoped if item.get("kind") == "style_label")
        if manager_style.get("scope") != "manager" or manager_style.get("target_fund_ids"):
            raise AssertionError(f"A preceding product list must not spread manager style to every fund: {manager_style}")
        fund_name_collision = service._proposal(
            "fund", "000004.OF", root / "清单.md", root, "当前管理示例核心精选", 0.9,
        )
        fund_name_collision["source_ref"]["fund_name"] = "示例核心精选混合-A"
        another_fund = service._proposal(
            "fund", "000005.OF", root / "清单.md", root, "当前管理示例价值增长", 0.9,
        )
        another_fund["source_ref"]["fund_name"] = "示例价值增长混合-A"
        collision_style = service._proposal(
            "style_label", "价值", root / "清单.md", root, "产品风格：质量价值型", 0.94,
        )
        collision_scoped = service._scope_profile_proposals(
            [fund_name_collision, another_fund, collision_style],
            "当前管理示例核心精选、示例价值增长等产品\n投资风格\n产品风格：质量价值型",
        )
        collision_result = next(item for item in collision_scoped if item.get("kind") == "style_label")
        if collision_result.get("scope") != "manager" or collision_result.get("target_fund_ids"):
            raise AssertionError(f"Style words inside another fund name must not create product evidence: {collision_result}")
        if service._report_date(root / "路演纪要20250207.pdf", 0) != "2025-02-07":
            raise AssertionError("Compact memo date in filename must override file mtime")
        if service._report_date(root / "范妍 25年2月18日.docx", 0) != "2025-02-18":
            raise AssertionError("Chinese memo date in filename must override file mtime")
        if service._report_date(root / "万家基金叶勇-202508.pptx", 0) != "2025-08-01":
            raise AssertionError("Compact year-month in filename must resolve to the first day of that month")
        short_month_path = root / "2024" / "冯骋 广发基金 2406.pdf"
        if service._report_date(short_month_path, 0) != "2024-06-01":
            raise AssertionError("YYMM in filename must use the matching directory year")
        mismatched_short_month_path = root / "2026" / "1209叶勇单页.pdf"
        if service._report_date(mismatched_short_month_path, 0) != "":
            raise AssertionError("YYMM-like tokens must stay unknown when the directory year disagrees")
        if service._report_date(root / "【鹏华基金】伍旋-权益绩优基金经理介绍26Q1.pdf", 0) != "2026-01-01":
            raise AssertionError("Quarter in filename must resolve to the first day of that quarter")
        if service._report_date(root / "1209叶勇单页.pdf", 0, "数据截至2025/12/9") != "":
            raise AssertionError("File mtime and data-as-of dates must not pretend to be a memo date")
        if service._report_date(
            root / "投资理念及风格介绍.pptx",
            0,
            "投资理念及风格介绍\n2026年3月\n数据截至2025年12月31日",
        ) != "2026-03-01":
            raise AssertionError("Month-only date in memo content must override file mtime")

        markdown_content = "# 访谈纪要\n基金经理：张三\n风格：成长、大盘、低换手\n基金分类：主动权益\n- 重视现金流与长期竞争力\n"
        markdown_path = manager_folder / "2026-08-01-访谈.md"
        duplicate_path = manager_folder / "重复内容.txt"
        notes_path = root / "李四-补充.txt"
        pdf_path = root / "英文纪要.pdf"
        docx_path = root / "Word纪要.docx"

        markdown_path.write_text(markdown_content, encoding="utf-8")
        duplicate_path.write_text(markdown_content, encoding="utf-8")
        notes_path.write_text("基金经理：李四\n风格：价值、小盘\n关注回撤与估值。", encoding="utf-8")
        _write_pdf(pdf_path, "PDF research memo for parser verification")
        _write_docx(docx_path, "DOCX research memo for parser verification")
        (root / "不支持.csv").write_text("ignored", encoding="utf-8")

        original_bytes = {path: path.read_bytes() for path in (markdown_path, duplicate_path, notes_path, pdf_path, docx_path)}

        folder = service.add_folder(str(root))
        if folder.get("path") != str(root.resolve()):
            raise AssertionError(f"Folder path should be canonical: {folder}")

        first = service.scan_folder(folder["id"])
        expected_first = {"created": 4, "updated": 0, "unchanged": 1, "failed": 0, "supported": 5}
        if first.get("counts") != expected_first:
            raise AssertionError(f"Unexpected first scan counts: {first}")
        if len(repo.reports) != 4 or len(repo.documents) != 5:
            raise AssertionError(f"Content deduplication failed: reports={len(repo.reports)} documents={len(repo.documents)}")

        for path, before in original_bytes.items():
            if path.read_bytes() != before:
                raise AssertionError(f"Scanner rewrote source file: {path}")

        for document in repo.documents.values():
            if not document.get("relative_path") or not document.get("content_hash"):
                raise AssertionError(f"Document lacks audit identity: {document}")
            if document.get("size", 0) <= 0 or document.get("mtime_ns", 0) <= 0:
                raise AssertionError(f"Document lacks file metadata: {document}")

        parsed_contents = "\n".join(report.get("content", "") for report in repo.reports.values())
        if "PDF research memo" not in parsed_contents or "DOCX research memo" not in parsed_contents:
            raise AssertionError("PDF and DOCX files must be parsed into searchable text")

        manager_report = next(report for report in repo.reports.values() if "基金经理：张三" in report.get("content", ""))
        manager_proposal = _proposal(manager_report, "manager", "张三")
        fund_proposal = _proposal(manager_report, "fund", "000001.OF")
        style_proposal = _proposal(manager_report, "style_label", "成长")
        for proposal in (manager_proposal, fund_proposal, style_proposal):
            source_ref = proposal.get("source_ref", {})
            if proposal.get("review_status") != "pending":
                raise AssertionError(f"Extracted conclusions must await review: {proposal}")
            if not source_ref.get("relative_path") or not source_ref.get("excerpt"):
                raise AssertionError(f"Proposal lacks source evidence: {proposal}")
            confidence = proposal.get("confidence")
            if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
                raise AssertionError(f"Proposal confidence is invalid: {proposal}")
        if fund_proposal.get("extraction_source") != "tushare.fund_manager":
            raise AssertionError(f"Manager tenure relation must be sourced from Tushare: {fund_proposal}")
        visible_pending = service.list_pending_reviews(folder["id"])
        if any(item.get("id") == fund_proposal["id"] for item in visible_pending):
            raise AssertionError(f"Tushare fund links should be handled with manager confirmation: {visible_pending}")

        manager_review = service.review_proposal(manager_report["id"], manager_proposal["id"], "confirmed")
        fund_review = service.review_proposal(manager_report["id"], fund_proposal["id"], "confirmed")
        style_review = service.review_proposal(manager_report["id"], style_proposal["id"], "rejected")
        if len(projection_calls) != 3:
            raise AssertionError(f"Every review must rebuild affected profiles: {projection_calls}")
        if any(call[1] != ["000001.OF"] for call in projection_calls):
            raise AssertionError(f"Projection must receive old and new fund identities: {projection_calls}")
        if manager_review.get("linked_fund_count") != 1:
            raise AssertionError(f"Confirming a manager must confirm Tushare tenure links in one step: {manager_review}")
        if manager_review.get("profile_projection") is None or fund_review.get("profile_projection") is None or style_review.get("profile_projection") is None:
            raise AssertionError("Review response must expose profile projection status")
        reviewed = repo.get_report(manager_report["id"])
        if reviewed.get("manager_name") != "张三":
            raise AssertionError(f"Confirmed manager should control grouping: {reviewed}")
        if "成长" in reviewed.get("style_labels", []):
            raise AssertionError(f"Rejected style must not enter confirmed labels: {reviewed}")
        if reviewed.get("fund_ids") != ["000001.OF"]:
            raise AssertionError(f"Confirmed fund identity should enter the memo: {reviewed}")
        if reviewed.get("extraction_provider") != "fake" or reviewed.get("extraction_model") != "fake-model":
            raise AssertionError(f"Memo should retain model provenance: {reviewed}")

        pending = service.list_pending_reviews(folder["id"])
        if any(item.get("id") in {manager_proposal["id"], fund_proposal["id"], style_proposal["id"]} for item in pending):
            raise AssertionError(f"Reviewed proposals must leave pending queue: {pending}")

        for proposal in list(repo.get_report(manager_report["id"]).get("review_proposals", [])):
            if proposal.get("review_status") == "pending":
                service.review_proposal(manager_report["id"], proposal["id"], "rejected")
        if repo.get_report(manager_report["id"]).get("review_status") != "reviewed":
            raise AssertionError("Report should become reviewed after its last proposal is decided")

        second = service.scan_folder(folder["id"])
        if second.get("counts") != {"created": 0, "updated": 1, "unchanged": 4, "failed": 0, "supported": 5}:
            raise AssertionError(f"First rescan should attach Tushare verification to direct fund evidence: {second}")
        if second.get("profile_projection", {}).get("projected_count") != 1:
            raise AssertionError(f"A repeat scan should rebuild profiles from reviewed memos: {second}")
        if projection_calls[-1][1] != ["000001.OF"]:
            raise AssertionError(f"Scan projection should include confirmed fund identities: {projection_calls[-1]}")
        third = service.scan_folder(folder["id"])
        if third.get("counts") != {"created": 0, "updated": 0, "unchanged": 5, "failed": 0, "supported": 5}:
            raise AssertionError(f"Verified unchanged files should not be reparsed again: {third}")

        time.sleep(0.002)
        notes_path.write_text("基金经理：李四\n风格：均衡、大盘\n更新后的风险控制记录。", encoding="utf-8")
        os.utime(notes_path, None)
        third = service.scan_folder(folder["id"])
        if third.get("counts") != {"created": 0, "updated": 1, "unchanged": 4, "failed": 0, "supported": 5}:
            raise AssertionError(f"Changed file should update only one indexed memo: {third}")

        updated_document = repo.get_document(folder["id"], "李四-补充.txt")
        expected_hash = hashlib.sha256(notes_path.read_bytes()).hexdigest()
        if updated_document.get("content_hash") != expected_hash:
            raise AssertionError(f"Updated hash was not stored: {updated_document}")

    bulk_repo = MemoryResearchFolderRepo()
    bulk_repo.reports["report-high"] = {
        "id": "report-high",
        "title": "高置信经理纪要",
        "local_folder_id": "folder-bulk",
        "manager_id": "",
        "manager_name": "",
        "classifications": [],
        "style_labels": [],
        "tags": [],
        "fund_ids": [],
        "review_status": "pending",
        "review_proposals": [
            {
                "id": "manager-high",
                "kind": "manager",
                "value": "张三",
                "candidate_id": "manager-zhang-san",
                "identity_verification": {"status": "unique_exact_name"},
                "report_date_source": "filename",
                "confidence": 0.92,
                "review_status": "pending",
                "extraction_source": "manager_catalog_title",
                "source_ref": {"relative_path": "张三.docx", "excerpt": "文件名：张三.docx"},
            },
            {
                "id": "style-high",
                "kind": "style_label",
                "value": "价值",
                "confidence": 0.94,
                "review_status": "pending",
                "extraction_source": "explicit_field",
                "scope": "manager",
                "source_ref": {
                    "relative_path": "张三.docx",
                    "excerpt": "投资风格：价值",
                    "rule": "explicit_manager_profile",
                },
            },
            {
                "id": "style-llm-high",
                "kind": "style_label",
                "value": "成长",
                "confidence": 0.99,
                "review_status": "pending",
                "extraction_source": "llm",
                "source_ref": {"relative_path": "张三.docx", "excerpt": "组合主要聚焦高成长公司"},
            },
        ],
    }
    bulk_repo.reports["report-low"] = {
        "id": "report-low",
        "title": "低置信经理纪要",
        "local_folder_id": "folder-bulk",
        "manager_id": "",
        "manager_name": "",
        "classifications": [],
        "style_labels": [],
        "tags": [],
        "fund_ids": [],
        "review_status": "pending",
        "review_proposals": [{
            "id": "manager-low",
            "kind": "manager",
            "value": "李四",
            "confidence": 0.7,
            "review_status": "pending",
            "source_ref": {"relative_path": "访谈.docx", "excerpt": "疑似李四"},
        }],
    }
    bulk_repo.reports["report-no-id"] = {
        "id": "report-no-id",
        "title": "无规范ID的高置信经理纪要",
        "local_folder_id": "folder-bulk",
        "manager_id": "",
        "manager_name": "",
        "classifications": [],
        "style_labels": [],
        "tags": [],
        "fund_ids": [],
        "review_status": "pending",
        "review_proposals": [{
            "id": "manager-no-id",
            "kind": "manager",
            "value": "王五",
            "confidence": 0.98,
            "review_status": "pending",
            "extraction_source": "manager_catalog_title",
            "source_ref": {"relative_path": "王五.docx", "excerpt": "文件名：王五.docx"},
        }],
    }
    bulk_repo.reports["report-ambiguous"] = {
        "id": "report-ambiguous",
        "title": "多人经理纪要",
        "local_folder_id": "folder-bulk",
        "manager_id": "",
        "manager_name": "",
        "classifications": [],
        "style_labels": [],
        "tags": [],
        "fund_ids": [],
        "review_status": "pending",
        "review_proposals": [
            {
                "id": "manager-ambiguous-a",
                "kind": "manager",
                "value": "张三",
                "candidate_id": "manager-zhang-san",
                "identity_verification": {"status": "unique_exact_name"},
                "report_date_source": "filename",
                "confidence": 0.96,
                "review_status": "pending",
                "extraction_source": "manager_catalog_title",
                "source_ref": {
                    "relative_path": "张三、李四.docx",
                    "excerpt": "文件名：张三、李四.docx",
                },
            },
            {
                "id": "manager-ambiguous-b",
                "kind": "manager",
                "value": "李四",
                "candidate_id": "manager-li-si",
                "identity_verification": {"status": "unique_exact_name"},
                "report_date_source": "filename",
                "confidence": 0.96,
                "review_status": "pending",
                "extraction_source": "manager_catalog_title",
                "source_ref": {
                    "relative_path": "张三、李四.docx",
                    "excerpt": "文件名：张三、李四.docx",
                },
            },
        ],
    }
    bulk_service = LocalResearchFolderService(repo=bulk_repo)
    bulk_result = bulk_service.confirm_manager_proposals("folder-bulk", 0.88)
    if bulk_result.get("confirmed") != 2 or bulk_repo.reports["report-high"].get("manager_name") != "张三":
        raise AssertionError(f"High-confidence manager reviews must be confirmable in one action: {bulk_result}")
    if bulk_result.get("requested_reports") != 2 or bulk_result.get("multi_manager") != 1:
        raise AssertionError(f"Bulk review must report unique and multi-manager memo counts: {bulk_result}")
    ambiguous_report = bulk_repo.reports["report-ambiguous"]
    if ambiguous_report.get("manager_name") or {
        item.get("manager_id") for item in ambiguous_report.get("manager_links", [])
    } != {"manager-zhang-san", "manager-li-si"} or any(
        proposal.get("review_status") != "confirmed"
        for proposal in ambiguous_report.get("review_proposals", [])
    ):
        raise AssertionError(f"Multi-manager memos must keep every confirmed identity: {ambiguous_report}")
    if bulk_repo.reports["report-low"]["review_proposals"][0].get("review_status") != "pending":
        raise AssertionError("Low-confidence manager reviews must remain pending")
    if bulk_repo.reports["report-no-id"]["review_proposals"][0].get("review_status") != "pending":
        raise AssertionError("Manager reviews without a canonical candidate_id must remain pending")

    recovered = bulk_service._merge_review_state({
        "review_proposals": [{
            "id": "manager-recovered",
            "kind": "manager",
            "value": "张三",
            "candidate_id": "manager-zhang-san",
            "confidence": 0.96,
            "review_status": "pending",
            "source_ref": {"relative_path": "张三.docx", "excerpt": "文件名：张三.docx"},
        }],
        "viewpoint_topics": [],
        "research_domains": [],
        "created_at": "2026-01-02T00:00:00+00:00",
    }, {
        "review_proposals": [{
            "id": "style-retained",
            "kind": "style_label",
            "value": "价值",
            "confidence": 0.94,
            "review_status": "pending",
            "source_ref": {"relative_path": "张三.docx", "excerpt": "投资风格：价值"},
        }],
        "manager_links": [{
            "manager_id": "manager-zhang-san",
            "manager_name": "张三",
            "confirmed_at": "2026-01-01T00:00:00+00:00",
        }],
        "created_at": "2026-01-01T00:00:00+00:00",
        "viewpoint_topics": [],
        "research_domains": [],
    })
    recovered_manager = next(item for item in recovered["review_proposals"] if item.get("kind") == "manager")
    if recovered_manager.get("review_status") != "confirmed" or recovered.get("manager_id") != "manager-zhang-san":
        raise AssertionError(f"Authoritative manager links must restore reviewed state after rescans: {recovered}")
    if not any(item.get("id") == "style-retained" for item in recovered["review_proposals"]):
        raise AssertionError(f"Rescans must retain pending review evidence until a reviewer acts: {recovered}")
    label_result = bulk_service.confirm_label_proposals("folder-bulk", 0.9)
    if label_result.get("confirmed") != 1 or bulk_repo.reports["report-high"].get("style_labels") != ["价值"]:
        raise AssertionError(f"High-confidence labels must be confirmable in one action: {label_result}")
    if bulk_repo.reports["report-high"]["review_proposals"][2].get("review_status") != "pending":
        raise AssertionError("LLM style suggestions must remain pending for individual human review")

    for unsafe in ("/", str(Path.home()), "/path/that/does/not/exist"):
        try:
            service.add_folder(unsafe)
        except FolderValidationError:
            pass
        else:
            raise AssertionError(f"Unsafe or missing path should be rejected: {unsafe}")

    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory) / "too-large"
        root.mkdir()
        (root / "oversize.txt").write_bytes(b"x" * 33)
        strict_service = LocalResearchFolderService(repo=MemoryResearchFolderRepo(), max_file_bytes=32)
        folder = strict_service.add_folder(str(root))
        result = strict_service.scan_folder(folder["id"])
        if result.get("counts", {}).get("failed") != 1:
            raise AssertionError(f"Oversized file should fail without being read: {result}")

    fallback_repo = MemoryResearchFolderRepo()
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory) / "llm-fallback"
        root.mkdir()
        (root / "模型失效时仍可识别.md").write_text(
            "基金经理：赵六\n代表基金：000002.OF\n基金分类：主动权益",
            encoding="utf-8",
        )
        extractor_ready = {"value": False}

        def recovering_extractor(_content, _filename):
            if extractor_ready["value"]:
                return {
                    "status": "complete",
                    "provider": "fake",
                    "model": "fake-model",
                    "proposals": [{
                        "kind": "style_label",
                        "value": "价值",
                        "confidence": 0.9,
                        "excerpt": "基金分类：主动权益",
                    }],
                }
            return {
                "status": "failed",
                "provider": "siliconflow",
                "model": "deepseek-ai/DeepSeek-V4-Flash",
                "proposals": [],
                "error": "模型服务认证失败",
            }

        fallback_service = LocalResearchFolderService(
            repo=fallback_repo,
            metadata_extractor=recovering_extractor,
        )
        folder = fallback_service.add_folder(str(root))
        fallback_service.scan_folder(folder["id"])
        report = next(iter(fallback_repo.reports.values()))
        fund_proposals = [
            item for item in report.get("review_proposals", [])
            if item.get("kind") == "fund" and item.get("value") == "000002.OF"
        ]
        if len(fund_proposals) != 1:
            raise AssertionError(f"Rules must preserve fund identity when LLM is unavailable: {report}")
        if report.get("llm_extraction_status") != "failed" or not report.get("llm_extraction_error"):
            raise AssertionError(f"LLM fallback status must be auditable: {report}")
        extractor_ready["value"] = True
        quiet_rescan = fallback_service.scan_folder(folder["id"])
        if quiet_rescan.get("counts", {}).get("unchanged") != 1:
            raise AssertionError(f"Normal rescans must not retry failed LLM work: {quiet_rescan}")
        retry = fallback_service.scan_folder(folder["id"], retry_llm=True)
        retried_report = next(iter(fallback_repo.reports.values()))
        if retry.get("counts", {}).get("updated") != 1 or retried_report.get("llm_extraction_status") != "complete":
            raise AssertionError(f"Unchanged memos must retry LLM extraction after configuration recovers: {retry}")
        if not any(
            item.get("kind") == "style_label"
            and item.get("value") == "价值"
            and item.get("extraction_source") == "llm"
            for item in retried_report.get("review_proposals", [])
        ):
            raise AssertionError(f"Recovered LLM style evidence was not merged: {retried_report}")

    print("OK local research folders scan incrementally with auditable, reviewable extraction")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
