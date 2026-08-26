from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

from path_config import get_project_root


ROOT = get_project_root()
IMAGE_ENV_FILE = ROOT / "configs" / "image_generation" / "providers.local.env"


def load_env_pairs(path: Path) -> dict[str, str]:
    if not path.exists() or not path.is_file():
        return {}
    pairs: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        pairs[key.strip()] = value.strip()
    return pairs


def load_provider_env(extra_candidates: Iterable[Path] | None = None) -> tuple[dict[str, str], str | None]:
    for candidate in [*(extra_candidates or []), IMAGE_ENV_FILE]:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if not path.exists() or not path.is_file():
            continue
        return load_env_pairs(path), str(path)
    return {}, None


def normalize_chat_base_url(base_url: str) -> str:
    value = (base_url or "").strip().rstrip("/")
    if not value:
        return value
    if value.endswith("/chat/completions") or value.endswith("/v1/chat/completions"):
        return value
    if value.endswith("/v1"):
        return f"{value}/chat/completions"
    return f"{value}/v1/chat/completions"


def first_non_empty(env_values: dict[str, str], keys: Iterable[str], default: str = "") -> str:
    for key in keys:
        runtime_value = os.environ.get(key)
        if runtime_value:
            return str(runtime_value).strip()
        file_value = env_values.get(key)
        if file_value:
            return str(file_value).strip()
    return default.strip()


def resolve_chat_provider(
    *,
    custom_env_var: str | None = None,
    base_url_keys: list[str],
    api_key_keys: list[str],
    model_keys: list[str],
    timeout_keys: list[str],
    default_model: str = "gpt-4.1-mini",
    default_timeout_seconds: str = "90",
    default_base_url: str = "",
) -> dict[str, str]:
    extra_candidates: list[Path] = []
    if custom_env_var:
        custom_env = os.environ.get(custom_env_var, "").strip()
        if custom_env:
            extra_candidates.append(Path(custom_env))
    env_values, env_file = load_provider_env(extra_candidates)
    base_url = normalize_chat_base_url(first_non_empty(env_values, base_url_keys, default_base_url))
    api_key = first_non_empty(env_values, api_key_keys)
    if not base_url or not api_key:
        return {"_unavailable": True, "status": "api_key_missing"}
    return {
        "base_url": base_url,
        "api_key": api_key,
        "model": first_non_empty(env_values, model_keys, default_model) or default_model,
        "timeout_seconds": first_non_empty(env_values, timeout_keys, default_timeout_seconds) or default_timeout_seconds,
        "env_file": env_file or "",
    }


def extract_chat_content(response_payload: dict[str, Any]) -> str:
    choices = response_payload.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content") or ""
                if text:
                    parts.append(str(text))
        return "\n".join(parts).strip()
    return ""


def dump_provider_snapshot(snapshot: dict[str, Any]) -> str:
    return json.dumps(snapshot, ensure_ascii=False, indent=2)
