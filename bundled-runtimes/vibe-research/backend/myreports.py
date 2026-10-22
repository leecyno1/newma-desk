"""我的研报 —— 用户上传/归档自己的研报文件，存本地、不上传、不进开源仓库。

设计取舍：
- 走 base64 JSON 上传（不引入 python-multipart 依赖，契合本项目「秒装必可用」）；研报文件不大，够用。
- 存到 `VR_REPORTS_DIR`（默认 ~/.vibe-research/myreports/，也可用 VR_DATA_DIR 换根目录）——用户私有资料，绝不进仓、不上传。
  放仓库外，重新下载/覆盖项目文件夹不会丢（issue #12）；≤v0.1.1 存 backend/.cache/myreports/，首次启动自动迁移（复制，旧目录保留作备份）。
- 元数据存目录内 index.json；按文件名关键词自动打「行业」标签（best-effort，未命中记「未分类」）。

合规/隐私：与「持仓 / 关注股只存本地」同一红线——研报是用户私有数据，只落本地磁盘。
"""

from __future__ import annotations

import base64
import binascii
import json
import hashlib
import math
import os
import re
import shutil
import sys
import threading
import time
import uuid
from pathlib import Path

_OLD_DEFAULT_DIR = Path(__file__).resolve().parent / ".cache" / "myreports"  # ≤v0.1.1 旧位置
_DATA_DIR = Path(os.environ.get("VR_DATA_DIR") or Path.home() / ".vibe-research")
_DEFAULT_DIR = _DATA_DIR / "myreports"
# 空串视同未设置（与 VR_DATA_DIR 语义一致，避免 Path("") 落到进程工作目录）
REPORTS_DIR = Path(os.environ.get("VR_REPORTS_DIR") or str(_DEFAULT_DIR))


def _migrate_legacy() -> None:
    """旧版研报在仓库内 .cache/ 里，重下载项目会丢；迁到用户目录（显式设了 VR_REPORTS_DIR 或新位置已有则不动）。"""
    try:
        if os.environ.get("VR_REPORTS_DIR") or REPORTS_DIR.exists() or not _OLD_DEFAULT_DIR.exists():
            return
        tmp = REPORTS_DIR.with_name(REPORTS_DIR.name + ".migrate.tmp")
        if tmp.exists():
            shutil.rmtree(tmp)  # 上次中断留下的半截目录，重来
        shutil.copytree(_OLD_DEFAULT_DIR, tmp)
        os.replace(tmp, REPORTS_DIR)  # 同盘原子改名：复制中断不会留半套研报挡住下次重试
    except OSError as e:
        # 迁移失败不阻塞启动，但要出声——旧数据原样保留在 _OLD_DEFAULT_DIR，可手工复制
        print(f"[vibe-research] 研报数据迁移失败（旧数据仍在 {_OLD_DEFAULT_DIR}）: {e}", file=sys.stderr)


_migrate_legacy()
_LOCK = threading.Lock()  # 索引读-改-写串行化（与 portfolio.py 同款），防并发上传/删除互相覆盖

MAX_BYTES = 25 * 1024 * 1024  # 单文件上限 25MB
# 允许的文档类型（白名单——不存可执行 / 网页等，避免下载回放风险）
ALLOWED_EXT = {
    ".pdf", ".doc", ".docx", ".txt", ".md", ".markdown",
    ".csv", ".xls", ".xlsx", ".ppt", ".pptx",
    ".png", ".jpg", ".jpeg", ".webp",
}

# 文件名关键词 → 行业标签（顺序即优先级，先命中先用）。纯文件名匹配、零依赖、离线可用。
_INDUSTRY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("人形机器人", ["人形", "机器人", "humanoid", "谐波", "丝杠", "滚柱", "灵巧手", "减速器", "optimus", "宇树", "特斯拉"]),
    ("光互联", ["光互联", "硅光", "cpo", "光模块", "磷化铟", "inp", "光芯片", "源杰", "中际旭创", "天孚"]),
    ("HBM存储", ["hbm", "存储", "内存", "dram", "长鑫", "美光", "海力士", "颗粒", "闪存", "nand"]),
    ("AI算力", ["算力", "gpu", "英伟达", "nvidia", "服务器", "液冷", "pcb", "交换机", "cowos", "沪电", "工业富联"]),
    ("半导体", ["半导体", "芯片", "晶圆", "光刻", "封测", "台积电", "刻蚀", "存储芯片"]),
    ("新能源", ["锂电", "电池", "光伏", "储能", "固态", "钠电", "宁德", "比亚迪"]),
    ("创新药", ["创新药", "医药", "生物", "cxo", "临床", "adc", "glp", "药明"]),
    ("商业航天", ["航天", "卫星", "火箭", "星链", "starlink", "spacex", "蓝箭"]),
    ("电力电网", ["电力", "电网", "特高压", "变压器", "输配电", "燃气轮机"]),
]


class ReportError(ValueError):
    """上传/校验类错误（对应 HTTP 400/413）。"""


class ReportStorageError(RuntimeError):
    """资料库不可读写；文案可返回用户，不包含磁盘路径。"""


def _directory(scope: tuple[str, str] | None = None) -> Path:
    # Only the verified in-process Desk adapter supplies scope. Native files
    # stay at their original location; never import them into a tenant.
    if scope is None:
        return REPORTS_DIR
    key = hashlib.sha256(json.dumps(scope, ensure_ascii=False).encode()).hexdigest()
    return REPORTS_DIR / "workspaces" / key


def _load_index(directory: Path) -> list[dict]:
    index = directory / "index.json"
    try:
        data = json.loads(index.read_text("utf-8"))
    except FileNotFoundError:
        # 新库可以为空，已有原文却丢失索引不能当作空库覆盖。
        try:
            if any(p.suffix.lower() in ALLOWED_EXT for p in directory.iterdir()):
                raise ReportStorageError("研报索引缺失，原文件仍保留；请先恢复索引后再操作。")
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise ReportStorageError("研报目录无法读取，请检查存储权限后重试。") from exc
        return []
    except (ValueError, UnicodeError, OSError) as exc:
        raise ReportStorageError("研报索引无法读取，请先检查或恢复索引；未覆盖原资料。") from exc
    if not isinstance(data, list):
        raise ReportStorageError("研报索引格式损坏，请先恢复索引；未覆盖原资料。")
    seen = set()
    for row in data:
        if (not isinstance(row, dict)
                or not isinstance(row.get("id"), str)
                or not re.fullmatch(r"[0-9a-f]{32}", row["id"])
                or row["id"] in seen
                or not isinstance(row.get("ext"), str) or row["ext"] not in ALLOWED_EXT
                or not isinstance(row.get("name"), str)
                or not isinstance(row.get("industry"), str)
                or type(row.get("size")) is not int or row["size"] < 0
                or type(row.get("ts")) not in (int, float)
                or not math.isfinite(row["ts"]) or row["ts"] < 0):
            raise ReportStorageError("研报索引条目损坏，请先恢复索引；未覆盖原资料。")
        seen.add(row["id"])
    return data


def _save_index(items: list[dict], directory: Path) -> None:
    index = directory / "index.json"
    tmp = index.with_suffix(".json.tmp")
    try:
        directory.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), "utf-8")
        os.replace(tmp, index)  # 原子替换；提交失败不破坏旧索引。
    except OSError as exc:
        raise ReportStorageError("研报索引保存失败，请检查磁盘空间和存储权限后重新核对。") from exc


def classify(filename: str) -> str:
    """按文件名关键词判行业；未命中记「未分类」。"""
    low = filename.lower()
    for industry, kws in _INDUSTRY_KEYWORDS:
        if any(kw.lower() in low for kw in kws):
            return industry
    return "未分类"


def _sanitize_name(name: str) -> str:
    """只保留基名，去掉路径分隔符；空名给个兜底。"""
    base = os.path.basename((name or "").replace("\\", "/")).strip()
    return base or "未命名"


def list_reports(*, scope: tuple[str, str] | None = None) -> list[dict]:
    """按上传时间倒序返回元数据列表。"""
    with _LOCK:
        return sorted(_load_index(_directory(scope)), key=lambda r: r["ts"], reverse=True)


def save_report(name: str, content_b64: str, *, scope: tuple[str, str] | None = None) -> dict:
    """解码 base64 存盘 + 打行业标签 + 记录元数据。返回该条元数据。"""
    fname = _sanitize_name(name)
    ext = os.path.splitext(fname)[1].lower()
    if ext not in ALLOWED_EXT:
        raise ReportError(f"不支持的文件类型 {ext or '（无扩展名）'}；支持：PDF / Word / txt / md / 表格 / 图片")
    # base64 可能带 data:URI 前缀（前端 FileReader.readAsDataURL），剥掉逗号前半段
    if content_b64.startswith("data:"):
        parts = content_b64.split(",", 1)
        if len(parts) < 2:
            raise ReportError("无效的 data URI（缺少逗号分隔的 base64 数据）")
        raw_b64 = parts[1]
    else:
        raw_b64 = content_b64
    try:
        blob = base64.b64decode(raw_b64, validate=True)
    except (binascii.Error, ValueError) as e:
        raise ReportError(f"文件内容解码失败：{e}") from e
    if not blob:
        raise ReportError("文件为空")
    if len(blob) > MAX_BYTES:
        raise ReportError(f"文件过大（{len(blob) // 1024 // 1024}MB），上限 {MAX_BYTES // 1024 // 1024}MB")

    directory = _directory(scope)
    rid = uuid.uuid4().hex
    path = directory / f"{rid}{ext}"
    meta = {
        "id": rid,
        "name": fname,
        "industry": classify(fname),
        "size": len(blob),
        "ext": ext,
        "ts": int(time.time() * 1000),
    }
    with _LOCK:
        items = _load_index(directory)
        try:
            directory.mkdir(parents=True, exist_ok=True)
            path.write_bytes(blob)
            _save_index([*items, meta], directory)
        except (OSError, ReportStorageError) as exc:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                raise ReportStorageError("上传未完成，残留文件无法清理；请先检查资料目录，不要重复上传。") from exc
            raise ReportStorageError("上传保存失败，未加入资料库；请检查磁盘空间和存储权限。") from exc
    return meta


def report_path(rid: str, *, scope: tuple[str, str] | None = None) -> tuple[Path, str] | None:
    """按 id 取 (磁盘路径, 原始文件名)；不存在返回 None。"""
    directory = _directory(scope)
    with _LOCK:
        for r in _load_index(directory):
            if r["id"] == rid:
                p = directory / f"{rid}{r['ext']}"
                return (p, r["name"]) if p.exists() else None
    return None


def delete_report(rid: str, *, scope: tuple[str, str] | None = None) -> bool:
    """删文件 + 移除索引条目。删成功（或本就不在）返回是否命中。"""
    with _LOCK:
        directory = _directory(scope)
        items = _load_index(directory)
        hit = next((r for r in items if r.get("id") == rid), None)
        if hit is None:
            return False
        fp = directory / f"{rid}{hit.get('ext', '')}"
        # 先提交索引，提交失败不删原文；删除失败恢复索引，不能报告成功。
        # 这是单进程内的失败回滚，不是多进程/断电事务。
        _save_index([r for r in items if r.get("id") != rid], directory)
        try:
            fp.unlink(missing_ok=True)
        except OSError as exc:
            try:
                _save_index(items, directory)
            except ReportStorageError:
                raise ReportStorageError("删除未完成，原文件仍保留但索引恢复失败；请先检查资料目录并恢复索引。") from exc
            raise ReportStorageError("删除失败，原文件和索引均已保留；请检查存储权限后重试。") from exc
    return True
