#!/usr/bin/env python3
"""Incrementally learn reusable video style DNA from tracked creators.

The repository stores only code and configuration. Downloaded videos, CRV
outputs, notes, rolling profiles, and logs stay under the desktop creation root.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from path_config import get_output_root


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "configs" / "video" / "creator_learning_watchlist.json"
DEFAULT_OUTPUT_ROOT = get_output_root("video_training") / "每日博主自学习"


class CreatorLearningError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def run_day() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d")


def safe_slug(value: str, max_len: int = 80) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", value).strip("._-")
    return (cleaned or "item")[:max_len]


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def load_json_safe(path: Path, default: Any = None) -> Any:
    try:
        return load_json(path, default)
    except (json.JSONDecodeError, OSError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def append_once(path: Path, marker: str, content: str) -> None:
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if marker in current:
        return
    prefix = "\n" if current and not current.endswith("\n\n") else ""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(current + prefix + content.rstrip() + "\n", encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def emit_progress(path: Path, event: str, **payload: Any) -> None:
    item = {"at": now_iso(), "event": event, **payload}
    append_jsonl(path, item)
    print(json.dumps(item, ensure_ascii=False), flush=True)


def acquire_run_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    handle.seek(0)
    handle.truncate()
    handle.write(json.dumps({"pid": os.getpid(), "started_at": now_iso()}, ensure_ascii=False))
    handle.flush()
    return handle


def run_command(
    command: list[str],
    *,
    cwd: Path = ROOT,
    timeout: int = 300,
    check: bool = True,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
        env=os.environ.copy(),
        input=input_text,
    )
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "command failed").strip()
        raise CreatorLearningError(f"command failed ({proc.returncode}): {' '.join(command)}\n{detail[-4000:]}")
    return proc


def resolve_repo_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def load_config(path: Path) -> dict[str, Any]:
    config = load_json(path)
    if not isinstance(config, dict):
        raise CreatorLearningError(f"invalid config: {path}")
    if config.get("schema_version") != "dasheng.video_creator_learning_watchlist.v1":
        raise CreatorLearningError("unsupported creator learning config schema")
    creators = config.get("creators") or []
    ids = [str(item.get("creator_id") or "") for item in creators]
    if not ids or any(not creator_id for creator_id in ids) or len(ids) != len(set(ids)):
        raise CreatorLearningError("creator IDs must be present and unique")
    return config


def build_paths(output_root: Path) -> dict[str, Path]:
    return {
        "root": output_root,
        "state": output_root / "state" / "learning_state.json",
        "runs": output_root / "runs",
        "notes": output_root / "notes",
        "profiles": output_root / "creator_profiles",
        "knowledge": output_root / "knowledge",
        "media_cache": output_root / "_media_cache",
        "logs": output_root / "logs",
        "codex_queue": output_root / "state" / "codex_review_queue.json",
    }


def initial_state() -> dict[str, Any]:
    return {
        "schema_version": "dasheng.video_creator_learning_state.v1",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "creators": {},
    }


def creator_state(state: dict[str, Any], creator: dict[str, Any]) -> dict[str, Any]:
    creators = state.setdefault("creators", {})
    creator_id = str(creator["creator_id"])
    return creators.setdefault(
        creator_id,
        {
            "creator_id": creator_id,
            "label": creator.get("label") or creator_id,
            "homepage": creator.get("homepage") or "",
            "initialized_at": None,
            "last_checked_at": None,
            "last_error": None,
            "videos": {},
        },
    )


def ytdlp_base(config: dict[str, Any]) -> list[str]:
    discovery = config.get("discovery") or {}
    command = [str(Path(discovery.get("yt_dlp") or "yt-dlp").expanduser()), "--no-update"]
    cookies = str(discovery.get("cookies_from_browser") or "").strip()
    if cookies:
        command.extend(["--cookies-from-browser", cookies])
    impersonate = str(discovery.get("impersonate") or "").strip()
    if impersonate:
        command.extend(["--impersonate", impersonate])
    return command


def parse_json_stdout(proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    raw = proc.stdout.strip()
    if raw:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            pass
        else:
            if isinstance(payload, dict):
                return payload
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    for line in reversed(lines):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise CreatorLearningError("command did not return a JSON object")


def normalize_metadata(payload: dict[str, Any], creator: dict[str, Any], video_id: str) -> dict[str, Any]:
    creator_id = str(payload.get("uploader_id") or creator["creator_id"])
    return {
        "platform": "bilibili",
        "creator_id": creator_id,
        "creator_name": payload.get("uploader") or creator.get("label") or creator_id,
        "video_id": payload.get("id") or video_id,
        "title": payload.get("title") or video_id,
        "url": payload.get("webpage_url") or f"https://www.bilibili.com/video/{video_id}",
        "duration_sec": round(float(payload.get("duration") or 0.0), 3),
        "timestamp": payload.get("timestamp"),
        "upload_date": str(payload.get("upload_date") or ""),
        "description": payload.get("description") or "",
        "thumbnail": payload.get("thumbnail") or "",
    }


def decode_json_fragment(value: str) -> str:
    try:
        return json.loads(f'"{value}"')
    except json.JSONDecodeError:
        return value


def html_metadata_fallback(
    creator: dict[str, Any],
    video_id: str,
    metadata_error: str,
) -> dict[str, Any]:
    url = f"https://www.bilibili.com/video/{video_id}"
    proc = run_command(
        [
            "/usr/bin/curl",
            "-L",
            "--compressed",
            "-A",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/140.0.0.0 Safari/537.36",
            "-sS",
            url,
        ],
        timeout=60,
    )
    page = proc.stdout
    video_data: dict[str, Any] = {}
    state_marker = "window.__INITIAL_STATE__="
    state_start = page.find(state_marker)
    if state_start >= 0:
        state_start += len(state_marker)
        state_end = page.find(";(function()", state_start)
        if state_end > state_start:
            try:
                initial_state_payload = json.loads(page[state_start:state_end])
                candidate = initial_state_payload.get("videoData") or {}
                if isinstance(candidate, dict):
                    video_data = candidate
            except json.JSONDecodeError:
                video_data = {}
    title_match = re.search(r"<title>(.*?)_哔哩哔哩", page, re.DOTALL)
    owner_match = re.search(rf'"owner":\{{"mid":{re.escape(str(creator["creator_id"]))},"name":"(.*?)"', page)
    duration_match = re.search(r'"duration":(\d+)', page)
    pubdate_match = re.search(r'"pubdate":(\d+)', page)
    owner = video_data.get("owner") if isinstance(video_data.get("owner"), dict) else {}
    timestamp = int(video_data.get("pubdate") or (pubdate_match.group(1) if pubdate_match else 0)) or None
    upload_date = datetime.fromtimestamp(timestamp).astimezone().strftime("%Y%m%d") if timestamp else ""
    return {
        "platform": "bilibili",
        "creator_id": str(creator["creator_id"]),
        "creator_name": owner.get("name") or (decode_json_fragment(owner_match.group(1)) if owner_match else creator.get("label") or str(creator["creator_id"])),
        "video_id": video_id,
        "title": video_data.get("title") or (decode_json_fragment(title_match.group(1)) if title_match else video_id),
        "url": url,
        "duration_sec": float(video_data.get("duration") or (duration_match.group(1) if duration_match else 0)),
        "timestamp": timestamp,
        "upload_date": upload_date,
        "description": video_data.get("desc") or "",
        "thumbnail": video_data.get("pic") or "",
        "metadata_source": "bilibili_html_fallback",
        "metadata_warning": metadata_error[-1200:],
    }


def discover_creator(
    config: dict[str, Any],
    creator: dict[str, Any],
    known_videos: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    discovery = config.get("discovery") or {}
    limit = int(discovery.get("playlist_items") or 3)
    flat_command = [
        *ytdlp_base(config),
        "--flat-playlist",
        "--playlist-end",
        str(limit),
        "--dump-single-json",
        str(creator["homepage"]),
    ]
    flat = parse_json_stdout(run_command(flat_command, timeout=120))
    entries = flat.get("entries") or []
    video_ids = [str(item.get("id") or "") for item in entries if item.get("id")]
    results: list[dict[str, Any]] = []
    known_videos = known_videos or {}
    for playlist_index, video_id in enumerate(video_ids):
        known = known_videos.get(video_id) or {}
        known_metadata = known.get("metadata") if isinstance(known, dict) else None
        if isinstance(known_metadata, dict) and known_metadata.get("title"):
            item = dict(known_metadata)
            item["playlist_index"] = playlist_index
            item["metadata_source"] = item.get("metadata_source") or "learning_state_cache"
            results.append(item)
            continue
        metadata_command = [
            *ytdlp_base(config),
            "--skip-download",
            "--dump-single-json",
            f"https://www.bilibili.com/video/{video_id}",
        ]
        try:
            metadata = parse_json_stdout(run_command(metadata_command, timeout=120))
            item = normalize_metadata(metadata, creator, video_id)
            item["metadata_source"] = "yt-dlp"
        except Exception as exc:
            item = html_metadata_fallback(creator, video_id, str(exc))
        item["playlist_index"] = playlist_index
        results.append(item)
    return results


def select_candidates(
    creator_record: dict[str, Any],
    discovered: list[dict[str, Any]],
    *,
    bootstrap_mode: str,
    max_new: int,
    backfill_latest: int,
) -> tuple[list[dict[str, Any]], bool]:
    first_run = creator_record.get("initialized_at") is None
    videos = creator_record.setdefault("videos", {})
    if first_run and bootstrap_mode == "baseline_only" and backfill_latest <= 0:
        for item in discovered:
            videos[item["video_id"]] = {
                "metadata": item,
                "status": "baseline_seen",
                "discovered_at": now_iso(),
            }
        creator_record["initialized_at"] = now_iso()
        return [], True

    candidates: list[dict[str, Any]] = []
    forced_ids = {item["video_id"] for item in discovered[: max(0, backfill_latest)]}
    retryable = {
        "discovered",
        "downloading",
        "downloaded",
        "crv_complete",
        "download_failed",
        "crv_failed",
        "agent_failed",
        "analysis_partial",
    }
    for item in discovered:
        record = videos.get(item["video_id"])
        if item["video_id"] in forced_ids and (record or {}).get("status") != "analysis_complete":
            candidates.append(item)
        elif record is None or record.get("status") in retryable:
            candidates.append(item)
        if len(candidates) >= max_new:
            break
    if first_run:
        creator_record["initialized_at"] = now_iso()
    return candidates, first_run


def download_video(config: dict[str, Any], metadata: dict[str, Any], media_cache: Path) -> Path:
    discovery = config.get("discovery") or {}
    video_dir = media_cache / metadata["creator_id"] / metadata["video_id"]
    video_dir.mkdir(parents=True, exist_ok=True)
    template = video_dir / f"{metadata['video_id']}.%(ext)s"
    command = [
        *ytdlp_base(config),
        "--no-playlist",
        "--no-progress",
        "--merge-output-format",
        "mp4",
        "--max-filesize",
        f"{int(discovery.get('max_filesize_mb') or 1500)}M",
        "-f",
        str(discovery.get("video_format") or "bv*[height<=720]+ba/b[height<=720]"),
        "-o",
        str(template),
        "--print",
        "after_move:filepath",
        metadata["url"],
    ]
    proc = run_command(command, timeout=3600)
    for line in reversed([line.strip() for line in proc.stdout.splitlines() if line.strip()]):
        candidate = Path(line).expanduser()
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()
    candidates = sorted(video_dir.glob(f"{metadata['video_id']}.*"))
    videos = [path for path in candidates if path.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}]
    if not videos:
        raise CreatorLearningError(f"download completed without a video file: {metadata['video_id']}")
    return videos[0].resolve()


def run_crv(config: dict[str, Any], metadata: dict[str, Any], video_path: Path, note_dir: Path) -> dict[str, Any]:
    analysis = config.get("analysis") or {}
    crv_dir = note_dir / "crv"
    command = [
        sys.executable,
        str(ROOT / "scripts" / "read_video_with_crv.py"),
        str(video_path),
        "--output-dir",
        str(crv_dir),
        "--crv-root",
        str(Path(analysis.get("crv_root") or ROOT / "vendor/reserved/video/claude-real-video").expanduser()),
        "--why",
        f"持续学习 {metadata.get('creator_name')} 的导演、设计、分镜、转场、制作、图表和审美 DNA",
        "--max-frames",
        str(int(analysis.get("max_frames") or 140)),
        "--fps-floor",
        str(float(analysis.get("fps_floor") or 1.0)),
        "--scene",
        str(float(analysis.get("scene_threshold") or 0.3)),
        "--dedup-threshold",
        str(float(analysis.get("dedup_threshold") or 8.0)),
    ]
    if analysis.get("report", True):
        command.append("--report")
    if analysis.get("transcribe", False):
        command.append("--transcribe")
    proc = run_command(command, timeout=3600)
    return parse_json_stdout(proc)


def trim_text(value: str, limit: int = 24000) -> str:
    return value if len(value) <= limit else value[:limit] + "\n...[truncated]"


def contact_sheet_images(crv_result: dict[str, Any], limit: int) -> list[Path]:
    outputs = crv_result.get("outputs") or {}
    grids_value = outputs.get("grids_dir")
    if not grids_value:
        return []
    grids_dir = Path(grids_value)
    if not grids_dir.is_dir():
        return []
    return sorted(grids_dir.glob("*.jpg"))[:limit]


def build_agent_prompt(
    metadata: dict[str, Any],
    crv_result: dict[str, Any],
    taxonomy_path: Path,
    tool_registry_path: Path,
    reference_registry_path: Path,
    existing_profile: Path,
) -> str:
    outputs = crv_result.get("outputs") or {}
    manifest_path = Path(outputs.get("manifest") or "")
    manifest_text = trim_text(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else ""
    profile_text = trim_text(existing_profile.read_text(encoding="utf-8"), 12000) if existing_profile.is_file() else ""
    return f"""你是 Newma 视频自学习模块的资深导演分析 Agent。请分析附件中的联系表，并结合以下本地读片信息输出严格符合 JSON Schema 的单个 JSON 对象。

分析目标：把观察转换为可执行的导演、设计、分镜、转场、制作、图表和审美语言，供未来真人口播与无头口播使用。

硬约束：
1. 不复制原作者脚本、Logo、字幕造型、专属包装或受版权保护画面。
2. 观察到的画面现象与复现技术建议分开。不得宣称原作者使用了 Hyperframes、HTML Anything、Remotion、GSAP、Lottie 或 html-video；只能说明我们可用什么技术复现某类效果。
3. 镜头越多不等于越好。必须评价主题完整性、核心场景保持、证据可读时长和切换是否打断理解。
4. 图表必须评价数据语义、标签、单位、动态揭示顺序、可读时长和证据来源，而不只评价颜色。
5. reusable_rules 只写候选规则，每条都要标注 applies_to、confidence、evidence 和 review_required=true。
6. 使用专业术语，但语言必须清楚、具体、能转成分镜参数。

视频元数据：
{json.dumps(metadata, ensure_ascii=False, indent=2)}

CRV MANIFEST：
{manifest_text}

现有滚动画像（可能为空）：
{profile_text}

专业词汇表：{taxonomy_path}
当前技术栈注册表：{tool_registry_path}
历史参考 DNA 注册表：{reference_registry_path}

输出时重点回答：
- 内容如何分章，开场如何建立问题，核心证据场景如何保持，何时才值得切镜。
- 真人、资料、网页、表格、图表、漫画、动态排版分别承担什么叙事功能。
- 转场由什么语义变化触发，是否存在装饰性切换、频繁来回切换或同一镜头反复进出。
- 审美调性、色彩、字体、构图、留白和信息密度有什么可复用规律及不应复制项。
- 用 Hyperframes、HTML Anything、Remotion、GSAP、Lottie、html-video、FFmpeg 如何复现这些表达，并说明适用镜头。
"""


def prepare_codex_review_packet(
    config: dict[str, Any],
    paths: dict[str, Path],
    metadata: dict[str, Any],
    crv_result: dict[str, Any],
    note_dir: Path,
    existing_profile: Path,
) -> dict[str, Any]:
    """Prepare local evidence for direct review by the active Codex Agent."""
    knowledge = config.get("knowledge") or {}
    taxonomy_path = resolve_repo_path(str(knowledge["professional_taxonomy"]))
    schema_path = resolve_repo_path(str(knowledge["analysis_schema"]))
    tool_registry_path = resolve_repo_path(str(knowledge["tool_registry"]))
    reference_registry_path = resolve_repo_path(str(knowledge["reference_registry"]))
    outputs = crv_result.get("outputs") or {}
    contact_sheets = [str(path) for path in contact_sheet_images(crv_result, 10000)]
    review_id = f"{metadata['creator_id']}:{metadata['video_id']}"
    output_path = note_dir / "analysis.json"
    request_path = note_dir / "analysis_request.md"
    packet_path = note_dir / "codex_review_packet.json"
    prompt = build_agent_prompt(
        metadata,
        crv_result,
        taxonomy_path,
        tool_registry_path,
        reference_registry_path,
        existing_profile,
    )
    prompt += (
        "\n\n直接读取要求：\n"
        "- 使用 Codex 的本地图像读取能力按顺序查看下面列出的全部联系表。\n"
        "- 同时读取 MANIFEST、可用转录稿和现有滚动画像。\n"
        "- 不调用 MiniMax 或其他外部视觉/文本模型。\n"
        f"- 最终 JSON 写入：{output_path}\n\n"
        "联系表：\n"
        + "\n".join(f"- {path}" for path in contact_sheets)
        + f"\n\n输出 Schema：{schema_path}\n"
    )
    write_text(request_path, prompt)
    packet = {
        "schema_version": "dasheng.codex_video_review_packet.v1",
        "review_id": review_id,
        "status": "awaiting_codex_analysis",
        "created_at": now_iso(),
        "analysis_provider": "codex-native",
        "video": metadata,
        "evidence": {
            "crv_manifest": crv_result.get("dasheng_manifest"),
            "llm_manifest": outputs.get("manifest"),
            "contact_sheets": contact_sheets,
            "transcript": outputs.get("transcript"),
            "report_html": outputs.get("report_html"),
            "existing_profile": str(existing_profile) if existing_profile.exists() else None,
        },
        "instructions": str(request_path),
        "output_schema": str(schema_path),
        "output_analysis": str(output_path),
    }
    write_json(packet_path, packet)
    queue = load_json(paths["codex_queue"], {"schema_version": "dasheng.codex_video_review_queue.v1", "items": {}})
    if not isinstance(queue, dict):
        queue = {"schema_version": "dasheng.codex_video_review_queue.v1", "items": {}}
    queue.setdefault("items", {})[review_id] = {**packet, "packet": str(packet_path)}
    queue["updated_at"] = now_iso()
    write_json(paths["codex_queue"], queue)
    return packet


def mark_codex_review_complete(paths: dict[str, Path], metadata: dict[str, Any], analysis_path: Path) -> None:
    queue = load_json(paths["codex_queue"], None)
    if not isinstance(queue, dict):
        return
    review_id = f"{metadata['creator_id']}:{metadata['video_id']}"
    item = (queue.get("items") or {}).get(review_id)
    if not isinstance(item, dict):
        return
    item.update({"status": "analysis_complete", "completed_at": now_iso(), "output_analysis": str(analysis_path)})
    queue["updated_at"] = now_iso()
    write_json(paths["codex_queue"], queue)


def load_agent_json(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.DOTALL)
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise CreatorLearningError("agent output is not an object")
    required = {
        "content_architecture",
        "director_analysis",
        "design_analysis",
        "storyboard_analysis",
        "transition_analysis",
        "production_analysis",
        "chart_analysis",
        "aesthetic_profile",
        "reproduction_stack",
        "reusable_rules",
        "anti_patterns",
        "confidence_notes",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise CreatorLearningError(f"agent output missing fields: {missing}")
    return payload


def run_agent_analysis(
    config: dict[str, Any],
    metadata: dict[str, Any],
    crv_result: dict[str, Any],
    note_dir: Path,
    existing_profile: Path,
) -> dict[str, Any]:
    analysis = config.get("analysis") or {}
    agent = analysis.get("agent") or {}
    if not agent.get("enabled", True):
        raise CreatorLearningError("agent analysis is disabled")
    provider = str(agent.get("provider") or "codex-native")
    if provider != "codex-native":
        raise CreatorLearningError(
            f"external video-analysis provider is disabled: {provider}; "
            "prepare a Codex native review packet instead"
        )
    raise CreatorLearningError("codex-native analysis must be completed by the active Codex Agent")


def markdown_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)) or value is None:
        return str(value)
    return "```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```"


def render_analysis_markdown(payload: dict[str, Any]) -> str:
    video = payload.get("video") or {}
    sections = [
        ("内容架构", "content_architecture"),
        ("导演分析", "director_analysis"),
        ("设计分析", "design_analysis"),
        ("分镜分析", "storyboard_analysis"),
        ("转场分析", "transition_analysis"),
        ("制作分析", "production_analysis"),
        ("图表分析", "chart_analysis"),
        ("审美与调性", "aesthetic_profile"),
        ("技术栈复现建议", "reproduction_stack"),
        ("候选进化规则", "reusable_rules"),
        ("禁止复用的问题", "anti_patterns"),
        ("置信度说明", "confidence_notes"),
    ]
    lines = [
        f"# {video.get('creator_name') or video.get('creator_id')}：{video.get('title')}",
        "",
        f"- 视频：[{video.get('video_id')}]({video.get('url')})",
        f"- 发布时间：{video.get('upload_date') or 'unknown'}",
        f"- 时长：{video.get('duration_sec') or 0} 秒",
        f"- 分析时间：{payload.get('analyzed_at')}",
        "- 状态：自动学习候选，未经人工审核不得覆盖已批准 DNA。",
    ]
    for title, key in sections:
        lines.extend(["", f"## {title}", "", markdown_value(payload.get(key))])
    return "\n".join(lines) + "\n"


def dedupe_rules(analyses: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for analysis in reversed(list(analyses)):
        for item in analysis.get("reusable_rules") or []:
            if not isinstance(item, dict):
                continue
            rule = str(item.get("rule") or "").strip()
            key = re.sub(r"\s+", "", rule).lower()
            if not key or key in seen:
                continue
            seen.add(key)
            result.append(item)
    return result[:80]


def update_creator_profile(paths: dict[str, Path], metadata: dict[str, Any]) -> Path:
    creator_id = metadata["creator_id"]
    analysis_paths = sorted((paths["notes"] / creator_id).glob("*/analysis.json"))
    analyses = [load_json_safe(path) for path in analysis_paths if path.is_file()]
    analyses = [item for item in analyses if isinstance(item, dict)]
    stack_counter: Counter[str] = Counter()
    anti_patterns: list[str] = []
    for item in analyses:
        for stack in item.get("reproduction_stack") or []:
            if isinstance(stack, dict) and stack.get("tool"):
                stack_counter[str(stack["tool"])] += 1
        for anti in item.get("anti_patterns") or []:
            if isinstance(anti, str) and anti not in anti_patterns:
                anti_patterns.append(anti)
    profile = {
        "schema_version": "dasheng.video_creator_rolling_profile.v1",
        "status": "candidate_not_approved",
        "creator_id": creator_id,
        "creator_name": metadata.get("creator_name") or creator_id,
        "updated_at": now_iso(),
        "source_count": len(analyses),
        "source_videos": [item.get("video") for item in analyses],
        "candidate_rules": dedupe_rules(analyses),
        "reproduction_stack_frequency": dict(stack_counter.most_common()),
        "anti_patterns": anti_patterns[:80],
        "latest_analysis": str(analysis_paths[-1]) if analysis_paths else None,
        "promotion_policy": "Human review is required before writing to approved reference_video_dna_registry profiles.",
    }
    profile_dir = paths["profiles"] / creator_id
    profile_path = profile_dir / "style_profile.rolling.json"
    write_json(profile_path, profile)
    lines = [
        f"# {profile['creator_name']}：滚动风格画像",
        "",
        f"- 样本数：{profile['source_count']}",
        f"- 更新时间：{profile['updated_at']}",
        "- 状态：候选规则，必须人工审核后才能进入正式导演 DNA。",
        "",
        "## 候选规则",
        "",
    ]
    lines.extend(f"- {item.get('rule')}（置信度 {item.get('confidence')}）" for item in profile["candidate_rules"])
    lines.extend(["", "## 技术栈出现频率", ""])
    lines.extend(f"- `{tool}`：{count}" for tool, count in stack_counter.most_common())
    lines.extend(["", "## 禁止照搬", ""])
    lines.extend(f"- {item}" for item in profile["anti_patterns"])
    write_text(profile_dir / "style_profile.rolling.md", "\n".join(lines))
    return profile_path


def initialize_knowledge_base(paths: dict[str, Path], taxonomy: dict[str, Any]) -> None:
    for path in paths.values():
        if path.suffix:
            continue
        path.mkdir(parents=True, exist_ok=True)
    readme = """# 每日博主视频自学习

本目录由 `dasheng-video-self-learning` 管理，用于增量跟踪目标博主的新视频。

- `notes/`：逐视频专业分析、CRV 联系表和分析请求。
- `creator_profiles/`：每个博主的滚动候选画像，不自动覆盖已批准 DNA。
- `knowledge/`：导演、审美、技术栈和进化知识库。
- `runs/`：每次定时执行的清单与错误记录。
- `_media_cache/`：临时下载缓存，成功分析后自动删除源视频。
- `state/`：按 BVID 去重和断点续跑状态。
"""
    write_text(paths["root"] / "README.md", readme)
    defaults = {
        "director_playbook.md": "# 导演候选手册\n\n这里只收录自动学习得到的候选规则，正式生产前需要导演审核。\n",
        "aesthetic_design_playbook.md": "# 审美与设计候选手册\n\n记录调性、构图、色彩、字体、留白和信息密度规律。\n",
        "technical_stack_mapping.md": "# 技术栈复现映射\n\n记录如何用现有工具复现表达，不推断原作者真实技术实现。\n",
        "evolution_log.md": "# 自我进化日志\n\n按新视频记录可复用能力和应阻止的回归。\n",
        "index.md": "# 知识库索引\n",
    }
    for filename, content in defaults.items():
        path = paths["knowledge"] / filename
        if not path.exists():
            write_text(path, content)
    taxonomy_lines = ["# 专业分析词汇表", ""]
    for dimension, terms in (taxonomy.get("professional_dimensions") or {}).items():
        taxonomy_lines.extend([f"## {dimension}", "", *[f"- {term}" for term in terms], ""])
    write_text(paths["knowledge"] / "professional_taxonomy.md", "\n".join(taxonomy_lines))


def render_summary(value: Any, limit: int = 8) -> list[str]:
    if isinstance(value, list):
        result = []
        for item in value[:limit]:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                result.append(str(item.get("rule") or item.get("tool") or json.dumps(item, ensure_ascii=False)))
        return result
    if isinstance(value, dict):
        return [f"{key}: {item}" for key, item in list(value.items())[:limit] if isinstance(item, (str, int, float, bool))]
    return [str(value)] if value else []


def update_global_knowledge(paths: dict[str, Path], analysis: dict[str, Any], note_path: Path) -> None:
    video = analysis.get("video") or {}
    video_id = video.get("video_id") or safe_slug(video.get("title") or "video")
    marker = f"<!-- video:{video_id} -->"
    heading = f"## {video.get('creator_name')}：{video.get('title')}"
    rules = [item.get("rule") for item in analysis.get("reusable_rules") or [] if isinstance(item, dict) and item.get("rule")]
    director_lines = [marker, heading, "", f"来源：[{video_id}]({video.get('url')})", ""]
    director_lines.extend(f"- {rule}" for rule in rules[:12])
    append_once(paths["knowledge"] / "director_playbook.md", marker, "\n".join(director_lines))

    aesthetic_lines = [marker, heading, ""]
    aesthetic_lines.extend(f"- {item}" for item in render_summary(analysis.get("aesthetic_profile"), 12))
    aesthetic_lines.extend(f"- 设计：{item}" for item in render_summary(analysis.get("design_analysis"), 8))
    append_once(paths["knowledge"] / "aesthetic_design_playbook.md", marker, "\n".join(aesthetic_lines))

    stack_lines = [marker, heading, ""]
    for item in analysis.get("reproduction_stack") or []:
        if not isinstance(item, dict):
            continue
        stack_lines.append(
            f"- `{item.get('tool')}`：{', '.join(item.get('use_for') or [])}；置信度 {item.get('confidence')}；{item.get('reason')}"
        )
    append_once(paths["knowledge"] / "technical_stack_mapping.md", marker, "\n".join(stack_lines))

    anti = [item for item in analysis.get("anti_patterns") or [] if isinstance(item, str)]
    evolution_lines = [
        marker,
        heading,
        "",
        f"- 分析笔记：`{note_path}`",
        f"- 新增候选规则：{len(rules)}",
        f"- 新增反模式：{len(anti)}",
    ]
    evolution_lines.extend(f"- 阻止回归：{item}" for item in anti[:8])
    append_once(paths["knowledge"] / "evolution_log.md", marker, "\n".join(evolution_lines))


def rebuild_index(paths: dict[str, Path], state: dict[str, Any] | None = None) -> None:
    lines = ["# 知识库索引", "", f"更新时间：{now_iso()}", "", "## 跟踪博主", ""]
    for creator_id, record in sorted(((state or {}).get("creators") or {}).items()):
        videos = list((record.get("videos") or {}).values())
        latest_titles = [
            str((item.get("metadata") or {}).get("title") or "")
            for item in videos
            if isinstance(item, dict)
        ][:3]
        lines.append(
            f"- **{record.get('label') or creator_id}** (`{creator_id}`)：已登记 {len(videos)} 条；"
            f"最近检查 {record.get('last_checked_at') or 'never'}"
        )
        lines.extend(f"  - {title}" for title in latest_titles if title)
    lines.extend(["", "## 博主滚动画像", ""])
    for profile in sorted(paths["profiles"].glob("*/style_profile.rolling.md")):
        lines.append(f"- [{profile.parent.name}]({profile})")
    lines.extend(["", "## 最近视频笔记", ""])
    notes = sorted(paths["notes"].glob("*/*/analysis.md"), reverse=True)[:100]
    lines.extend(f"- [{path.parent.name}]({path})" for path in notes)
    write_text(paths["knowledge"] / "index.md", "\n".join(lines))


def safe_delete_source(video_path: Path, media_cache: Path) -> None:
    try:
        video_path.resolve().relative_to(media_cache.resolve())
    except ValueError as exc:
        raise CreatorLearningError(f"refusing to delete source outside media cache: {video_path}") from exc
    if video_path.exists() and video_path.is_file():
        video_path.unlink()
    parent = video_path.parent
    if parent.exists() and not any(parent.iterdir()):
        parent.rmdir()


def process_video(
    config: dict[str, Any],
    paths: dict[str, Path],
    metadata: dict[str, Any],
    record: dict[str, Any],
    *,
    skip_agent: bool,
) -> dict[str, Any]:
    note_dir = paths["notes"] / metadata["creator_id"] / f"{metadata.get('upload_date') or run_day()}_{metadata['video_id']}"
    note_dir.mkdir(parents=True, exist_ok=True)
    write_json(note_dir / "video_metadata.json", metadata)
    video_path: Path | None = None
    try:
        existing_crv = load_json(note_dir / "crv_result.json")
        if isinstance(existing_crv, dict) and (existing_crv.get("outputs") or {}).get("grids_dir"):
            crv_result = existing_crv
            source_value = record.get("source_video") or ((crv_result.get("outputs") or {}).get("source_video"))
            video_path = Path(source_value) if source_value else None
            record.update({"status": "crv_complete", "crv_manifest": crv_result.get("dasheng_manifest"), "updated_at": now_iso()})
        else:
            cached = sorted((paths["media_cache"] / metadata["creator_id"] / metadata["video_id"]).glob(f"{metadata['video_id']}.*"))
            cached_videos = [path for path in cached if path.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}]
            record.update({"metadata": metadata, "status": "downloading", "updated_at": now_iso()})
            video_path = cached_videos[0].resolve() if cached_videos else download_video(config, metadata, paths["media_cache"])
            record.update({"status": "downloaded", "source_video": str(video_path), "updated_at": now_iso()})
            crv_result = run_crv(config, metadata, video_path, note_dir)
            write_json(note_dir / "crv_result.json", crv_result)
            record.update({"status": "crv_complete", "crv_manifest": crv_result.get("dasheng_manifest"), "updated_at": now_iso()})
        if skip_agent:
            record.update({"status": "analysis_partial", "updated_at": now_iso()})
            return {"status": "analysis_partial", "note_dir": str(note_dir)}
        profile_path = paths["profiles"] / metadata["creator_id"] / "style_profile.rolling.json"
        existing_analysis_path = note_dir / "analysis.json"
        try:
            analysis = load_agent_json(existing_analysis_path) if existing_analysis_path.is_file() else None
        except Exception:
            analysis = None
        if not isinstance(analysis, dict):
            provider = str((((config.get("analysis") or {}).get("agent") or {}).get("provider") or "codex-native"))
            if provider == "codex-native":
                packet = prepare_codex_review_packet(config, paths, metadata, crv_result, note_dir, profile_path)
                record.update(
                    {
                        "status": "awaiting_codex_analysis",
                        "codex_review_packet": str(note_dir / "codex_review_packet.json"),
                        "updated_at": now_iso(),
                        "last_error": None,
                    }
                )
                return {
                    "status": "awaiting_codex_analysis",
                    "note_dir": str(note_dir),
                    "review_packet": str(note_dir / "codex_review_packet.json"),
                    "contact_sheet_count": len((packet.get("evidence") or {}).get("contact_sheets") or []),
                }
            analysis = run_agent_analysis(config, metadata, crv_result, note_dir, profile_path)
        analysis["schema_version"] = "dasheng.video_creator_learning_analysis.v1"
        analysis["video"] = {
            "platform": metadata["platform"],
            "creator_id": metadata["creator_id"],
            "creator_name": metadata.get("creator_name") or metadata["creator_id"],
            "video_id": metadata["video_id"],
            "title": metadata["title"],
            "url": metadata["url"],
            "duration_sec": float(metadata.get("duration_sec") or 0),
            "upload_date": str(metadata.get("upload_date") or ""),
        }
        analysis["analyzed_at"] = analysis.get("analyzed_at") or now_iso()
        write_json(existing_analysis_path, analysis)
        mark_codex_review_complete(paths, metadata, existing_analysis_path)
        note_path = note_dir / "analysis.md"
        write_text(note_path, render_analysis_markdown(analysis))
        rolling_profile = update_creator_profile(paths, metadata)
        update_global_knowledge(paths, analysis, note_path)
        record.update(
            {
                "status": "analysis_complete",
                "analysis_json": str(note_dir / "analysis.json"),
                "analysis_note": str(note_path),
                "rolling_profile": str(rolling_profile),
                "completed_at": now_iso(),
                "updated_at": now_iso(),
                "last_error": None,
            }
        )
        if (config.get("discovery") or {}).get("delete_source_after_success", True):
            if video_path and video_path.is_file():
                try:
                    video_path.resolve().relative_to(paths["media_cache"].resolve())
                except ValueError:
                    pass
                else:
                    safe_delete_source(video_path, paths["media_cache"])
                    record["source_video"] = None
                    record["source_deleted_after_success"] = True
            crv_source = Path(((crv_result.get("outputs") or {}).get("source_video") or ""))
            if crv_source.is_file():
                safe_delete_source(crv_source, note_dir / "crv")
                record["crv_source_deleted_after_success"] = True
        return {"status": "analysis_complete", "note_dir": str(note_dir), "note": str(note_path)}
    except Exception as exc:
        current = str(record.get("status") or "")
        if current == "downloading":
            status = "download_failed"
        elif current == "downloaded":
            status = "crv_failed"
        else:
            status = "agent_failed"
        record.update({"status": status, "last_error": str(exc), "updated_at": now_iso()})
        return {"status": status, "note_dir": str(note_dir), "error": str(exc)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Track creator updates and build a reusable video-learning knowledge base.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output-root", default="")
    parser.add_argument("--creator-id", action="append", default=[])
    parser.add_argument("--discover-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--backfill-latest", type=int, default=0)
    parser.add_argument("--skip-agent", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = Path(args.config).expanduser().resolve()
    config = load_config(config_path)
    if not config.get("enabled", True):
        print(json.dumps({"status": "disabled", "config": str(config_path)}, ensure_ascii=False, indent=2))
        return 0
    output_root = Path(args.output_root or config.get("output_root") or DEFAULT_OUTPUT_ROOT).expanduser().resolve()
    paths = build_paths(output_root)
    run_lock = acquire_run_lock(paths["state"].parent / "run.lock")
    if run_lock is None:
        print(
            json.dumps(
                {
                    "status": "already_running",
                    "output_root": str(output_root),
                    "lock": str(paths["state"].parent / "run.lock"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    taxonomy = load_json(resolve_repo_path(str((config.get("knowledge") or {})["professional_taxonomy"])), {})
    initialize_knowledge_base(paths, taxonomy)
    state = load_json(paths["state"], initial_state())
    if not isinstance(state, dict):
        state = initial_state()
    selected_ids = set(args.creator_id)
    creators = [item for item in config.get("creators") or [] if not selected_ids or str(item["creator_id"]) in selected_ids]
    run_id = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    run_dir = paths["runs"] / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    progress_log = run_dir / "progress.jsonl"
    run_report: dict[str, Any] = {
        "schema_version": "dasheng.video_creator_learning_run.v1",
        "run_id": run_id,
        "started_at": now_iso(),
        "config": str(config_path),
        "output_root": str(output_root),
        "discover_only": bool(args.discover_only),
        "dry_run": bool(args.dry_run),
        "creators": [],
    }
    bootstrap_mode = str((config.get("discovery") or {}).get("bootstrap_mode") or "baseline_only")
    max_new = max(
        int((config.get("discovery") or {}).get("max_new_per_creator") or 2),
        max(0, args.backfill_latest),
    )
    if args.backfill_latest > 0:
        config.setdefault("discovery", {})["playlist_items"] = max(
            int((config.get("discovery") or {}).get("playlist_items") or 3),
            args.backfill_latest,
        )

    emit_progress(progress_log, "run_started", run_id=run_id, creator_count=len(creators), backfill_latest=args.backfill_latest)

    for creator in creators:
        creator_id = str(creator["creator_id"])
        record = creator_state(state, creator)
        creator_report: dict[str, Any] = {"creator_id": creator_id, "homepage": creator["homepage"], "videos": []}
        emit_progress(progress_log, "creator_discovery_started", creator_id=creator_id, label=record.get("label"))
        try:
            discovered = discover_creator(config, creator, known_videos=record.get("videos") or {})
            creator_report["discovered"] = discovered
            if discovered:
                record["label"] = discovered[0].get("creator_name") or record.get("label")
            record["last_checked_at"] = now_iso()
            record["last_error"] = None
            candidates, baselined = select_candidates(
                record,
                discovered,
                bootstrap_mode=bootstrap_mode,
                max_new=max_new,
                backfill_latest=max(0, args.backfill_latest),
            )
            creator_report["baselined"] = baselined
            creator_report["candidate_ids"] = [item["video_id"] for item in candidates]
            emit_progress(
                progress_log,
                "creator_discovery_completed",
                creator_id=creator_id,
                discovered=len(discovered),
                candidates=len(candidates),
            )
            for metadata in candidates:
                video_record = record.setdefault("videos", {}).setdefault(
                    metadata["video_id"],
                    {"metadata": metadata, "status": "discovered", "discovered_at": now_iso()},
                )
                if args.dry_run or args.discover_only:
                    creator_report["videos"].append({"video_id": metadata["video_id"], "status": "planned"})
                    continue
                emit_progress(
                    progress_log,
                    "video_processing_started",
                    creator_id=creator_id,
                    video_id=metadata["video_id"],
                    title=metadata.get("title"),
                )
                result = process_video(config, paths, metadata, video_record, skip_agent=args.skip_agent)
                creator_report["videos"].append({"video_id": metadata["video_id"], **result})
                emit_progress(
                    progress_log,
                    "video_processing_finished",
                    creator_id=creator_id,
                    video_id=metadata["video_id"],
                    status=result.get("status"),
                    error=result.get("error"),
                )
                state["updated_at"] = now_iso()
                write_json(paths["state"], state)
        except Exception as exc:
            record["last_checked_at"] = now_iso()
            record["last_error"] = str(exc)
            creator_report["error"] = str(exc)
            emit_progress(progress_log, "creator_failed", creator_id=creator_id, error=str(exc))
        run_report["creators"].append(creator_report)
        if not args.dry_run:
            state["updated_at"] = now_iso()
            write_json(paths["state"], state)

    rebuild_index(paths, state)
    run_report["finished_at"] = now_iso()
    creator_errors = any(item.get("error") for item in run_report["creators"])
    pending_reviews = any(
        video.get("status") == "awaiting_codex_analysis"
        for creator_item in run_report["creators"]
        for video in creator_item.get("videos") or []
    )
    video_errors = any(
        video.get("status") not in {"analysis_complete", "planned", "awaiting_codex_analysis"}
        for creator_item in run_report["creators"]
        for video in creator_item.get("videos") or []
    )
    if creator_errors or video_errors:
        run_report["status"] = "completed_with_errors"
    elif pending_reviews:
        run_report["status"] = "awaiting_codex_analysis"
    else:
        run_report["status"] = "completed"
    run_manifest = run_dir / "run_manifest.json"
    write_json(run_manifest, run_report)
    latest_manifest = paths["runs"] / "latest_run_manifest.json"
    write_json(latest_manifest, run_report)
    emit_progress(progress_log, "run_finished", run_id=run_id, status=run_report["status"])
    print(
        json.dumps(
            {
                "status": run_report["status"],
                "run_id": run_id,
                "manifest": str(run_manifest),
                "knowledge_index": str(paths["knowledge"] / "index.md"),
                "state": str(paths["state"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if run_report["status"] in {"completed", "awaiting_codex_analysis"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
