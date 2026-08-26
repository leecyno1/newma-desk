#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
from pathlib import Path

from runtime_paths import digital_human_runtime_root


def command_version(command: str, args: list[str]) -> str | None:
    path = shutil.which(command)
    if not path:
        return None
    try:
        result = subprocess.run(
            [path, *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return "present"
    text = (result.stdout or result.stderr or "present").strip().splitlines()
    return text[0] if text else "present"


def memory_gb() -> float | None:
    if platform.system() != "Darwin":
        return None
    try:
        raw = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip()
        return round(int(raw) / (1024**3), 1)
    except Exception:
        return None


def mps_status(python: Path | None = None) -> dict[str, object]:
    if python and python.is_file():
        probe = (
            "import json, torch; "
            "print(json.dumps({"
            "'torch': str(torch.__version__), "
            "'mps_available': bool(torch.backends.mps.is_available()), "
            "'cuda_available': bool(torch.cuda.is_available())}))"
        )
        try:
            result = subprocess.run(
                [str(python), "-c", probe],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            payload = json.loads(result.stdout)
            payload["python"] = str(python)
            return payload
        except Exception as exc:
            return {
                "torch": None,
                "mps_available": False,
                "cuda_available": False,
                "python": str(python),
                "error": str(exc),
            }
    try:
        import torch

        return {
            "torch": str(torch.__version__),
            "mps_available": bool(torch.backends.mps.is_available()),
            "cuda_available": bool(torch.cuda.is_available()),
            "python": str(Path(__import__("sys").executable).resolve()),
        }
    except Exception as exc:
        return {"torch": None, "mps_available": False, "cuda_available": False, "error": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local digital-human runtime readiness.")
    parser.add_argument("--json", action="store_true", help="Print JSON only.")
    parser.add_argument("--runtime-root", default=str(digital_human_runtime_root()))
    args = parser.parse_args()

    runtime_root = Path(args.runtime_root).expanduser().resolve()
    runtime_python = runtime_root / ".venv" / "bin" / "python"
    joyvasa_repo = runtime_root / "JoyVASA"
    required_weights = [
        joyvasa_repo / "pretrained_weights/JoyVASA/motion_generator/motion_generator_hubert_chinese.pt",
        joyvasa_repo / "pretrained_weights/TencentGameMate:chinese-hubert-base/config.json",
        joyvasa_repo / "pretrained_weights/liveportrait/base_models/appearance_feature_extractor.pth",
        joyvasa_repo / "pretrained_weights/liveportrait/base_models/motion_extractor.pth",
        joyvasa_repo / "pretrained_weights/liveportrait/base_models/spade_generator.pth",
        joyvasa_repo / "pretrained_weights/liveportrait/base_models/warping_module.pth",
        joyvasa_repo / "pretrained_weights/liveportrait/landmark.onnx",
        joyvasa_repo / "pretrained_weights/insightface/models/buffalo_l/det_10g.onnx",
        joyvasa_repo / "pretrained_weights/insightface/models/buffalo_l/2d106det.onnx",
    ]
    tools = {
        "git": command_version("git", ["--version"]),
        "ffmpeg": command_version("ffmpeg", ["-version"]),
        "ffprobe": command_version("ffprobe", ["-version"]),
        "uv": command_version("uv", ["--version"]),
        "mmx": command_version("mmx", ["--version"]),
    }
    is_apple_silicon = platform.system() == "Darwin" and platform.machine() == "arm64"
    base_ready = all(tools[name] for name in ("git", "ffmpeg", "ffprobe", "uv", "mmx"))
    runtime_installed = runtime_python.is_file() and joyvasa_repo.is_dir()
    torch = mps_status(runtime_python if runtime_installed else None)
    weights_ready = all(path.is_file() for path in required_weights)
    recommendations: list[str] = []
    if not is_apple_silicon:
        recommendations.append("默认安装器面向 Apple Silicon；其他平台需单独适配 CUDA 或 CPU。")
    if not base_ready:
        recommendations.append("先安装缺失的 git、ffmpeg/ffprobe、uv 或 mmx。")
    if is_apple_silicon and not bool(torch.get("mps_available")):
        recommendations.append("JoyVASA 运行环境未检测到 MPS。")
    if not runtime_installed:
        recommendations.append("运行 setup_joyvasa_macos.sh 安装 JoyVASA 和依赖。")
    elif not weights_ready:
        recommendations.append("运行 setup_joyvasa_macos.sh 下载完整模型权重。")
    recommendations.append("默认选择 avatar_head；半身手势档不在当前 Mac 自动部署范围内。")

    payload = {
        "schema_version": "dasheng.digital_human_preflight.v1",
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "apple_silicon": is_apple_silicon,
            "memory_gb": memory_gb(),
        },
        "python": platform.python_version(),
        "torch": torch,
        "tools": tools,
        "runtime": {
            "root": str(runtime_root),
            "installed": runtime_installed,
            "weights_ready": weights_ready,
            "missing_weights": [str(path) for path in required_weights if not path.is_file()],
            "python": str(runtime_python),
            "joyvasa_repo": str(joyvasa_repo),
        },
        "routes": {
            "avatar_head": "ready" if runtime_installed and weights_ready and base_ready else "setup_required",
            "avatar_semi_body": "not_recommended_on_current_mac",
            "video_generation_api": "forbidden_by_workflow",
            "audio": "minimax_mmx" if tools["mmx"] else "missing_mmx",
        },
        "recommendations": recommendations,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Apple Silicon: {'yes' if is_apple_silicon else 'no'}")
        print(f"Memory: {payload['platform']['memory_gb']} GB")
        print(f"MPS: {'yes' if torch.get('mps_available') else 'no'}")
        print(f"Runtime installed: {'yes' if runtime_installed else 'no'}")
        for item in recommendations:
            print(f"- {item}")
    return 0 if base_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
