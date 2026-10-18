"""Read model catalogs without leaking or forwarding credentials to a different service."""
from __future__ import annotations

import subprocess
import json
import os
import re
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

import requests
import yaml
from dotenv import dotenv_values
from pydantic import BaseModel, Field
from typing import Literal

from .ai_execution import find_cli, execution_config


class CatalogRequest(BaseModel):
    source: Literal["models", "agent"] = "models"
    lane: Literal["main", "mid", "tool"] = "main"
    channel_id: str = Field(default="", max_length=160)
    provider: str = Field(default="", max_length=40)
    api_url: str = Field(default="", max_length=2000)
    api_key: str = Field(default="", max_length=4000)


def agent_inventory() -> list[dict]:
    out = []
    for name in ("codex", "hermes", "claude", "qoder"):
        executable = find_cli(name)
        row = {"provider": name, "installed": bool(executable), "version": "", "status": "not_installed"}
        if executable:
            row["status"] = "installed_untested"
            try:
                p = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=5)
                if p.returncode == 0:
                    row["version"] = p.stdout.strip().splitlines()[0][:100]
                else:
                    row["status"] = "version_unavailable"
            except (OSError, subprocess.TimeoutExpired, IndexError):
                row["status"] = "version_unavailable"
        out.append(row)
    return out


def model_catalog(payload: CatalogRequest, conf: dict) -> dict:
    if payload.source != "agent":
        return {"models": _api_models(payload, conf), "source": "provider_api", "note": "来自服务的 /models 接口，调用权限以测试结果为准。"}
    provider = payload.provider or execution_config(conf).provider
    if provider not in {"codex", "hermes", "claude", "qoder", "http"}:
        raise ValueError("不支持的 Agent")
    executable = find_cli(provider)
    if provider != "http" and not executable:
        raise ValueError(f"未安装 {provider} CLI")
    if provider == "qoder":
        if not executable:
            raise ValueError("未安装 Qoder CLI")
        try:
            p = subprocess.run([executable, "--list-models"], capture_output=True, text=True, timeout=20)
            if p.returncode:
                raise ValueError("Qoder 模型列表获取失败，请检查登录")
            models = sorted({s.strip() for s in p.stdout.splitlines() if s.strip() and s.strip() != "MODEL"})
            return {"models": models, "source": "cli", "note": "来自 Qoder CLI 模型列表，保存后可分别测试两档模型。"}
        except (OSError, subprocess.TimeoutExpired):
            raise ValueError("Qoder 模型列表读取超时") from None
    if provider == "codex":
        home = Path(os.getenv("CODEX_HOME") or Path.home()/".codex")
        models = set()
        try:
            cfg = tomllib.loads((home/"config.toml").read_text()) if (home/"config.toml").exists() else {}
            if cfg.get("model"):
                models.add(str(cfg["model"]))
            custom = cfg.get("model_provider") not in (None, "", "openai")
            cache = home/"models_cache.json"
            if cache.exists() and not custom:
                data = json.loads(cache.read_text())
                models.update(str(m["slug"]) for m in data.get("models", []) if isinstance(m, dict) and m.get("slug") and m.get("visibility") != "hide")
        except (OSError, ValueError, TypeError):
            raise ValueError("Codex 本地模型列表无法读取；可自定义模型 ID 后测试") from None
        return {"models": sorted(models), "source": "local_cache", "note": "来自 Codex 本地配置/缓存，不代表当前账号实时权限；自定义 provider 只展示配置模型。请保存后测试。"}
    if provider == "claude":
        try:
            result = subprocess.run([executable, "--help"], capture_output=True, text=True, timeout=10)
            section = result.stdout.split("--model <model>", 1)[-1].split("\n  --", 1)[0] if "--model <model>" in result.stdout else ""
            models = sorted(set(re.findall(r"'([a-z][a-z0-9.-]*)'", section)))
            return {"models": models, "source": "cli_aliases", "note": "来自已安装 Claude CLI 帮助中的模型别名，并非账号完整模型列表；也可自定义完整模型 ID。"}
        except (OSError, subprocess.TimeoutExpired):
            raise ValueError("Claude 模型别名读取超时；可自定义模型 ID 后测试") from None
    saved = execution_config(conf).model_dump()
    if saved["provider"] != provider:
        saved = {}
    if provider == "hermes":
        # Discovery and execution must use the same CLI-owned connection.
        saved = _hermes_connection()
        payload = payload.model_copy(update={"api_url": "", "api_key": ""})
    elif "api_url" in payload.model_fields_set and not payload.api_url:
        saved = {**saved, "api_url": "", "api_key": ""}
    try:
        models = _api_models(payload, saved)
    except ValueError:
        if provider != "hermes" or not saved.get("default_model"):
            raise
        return {"models": [saved["default_model"]], "source": "local_config", "note": "远端模型列表暂不可用；仅显示 Hermes 本地已配置模型，仍可自定义并测试。"}
    return {"models": models, "source": "provider_api", "note": "来自该 Agent 模型服务的 /models 接口。请选择支持对话的模型，实际调用权限以测试结果为准。"}


def _hermes_connection() -> dict:
    home = Path(os.getenv("HERMES_HOME") or Path.home()/".hermes").expanduser()
    try:
        cfg = yaml.safe_load((home/"config.yaml").read_text()) or {}
        model = cfg.get("model") or {}
        if not isinstance(model, dict):
            return {"default_model": str(model)}
        provider = str(model.get("provider") or "").removeprefix("custom:")
        entry = (cfg.get("providers") or {}).get(provider) or {}
        values = dotenv_values(home/".env", interpolate=False) if (home/".env").exists() else {}
        key_env = entry.get("key_env") or entry.get("api_key_env") or model.get("key_env") or model.get("api_key_env")
        # Use only the selected provider's credentials, never an unrelated API key.
        key_env = key_env or {"openai": "OPENAI_API_KEY", "openrouter": "OPENROUTER_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}.get(provider)
        key = model.get("api_key") or entry.get("api_key") or (os.getenv(key_env) or values.get(key_env) if key_env else "")
        return {"api_url": model.get("base_url") or entry.get("base_url") or "",
                "api_key": key or "", "default_model": model.get("default") or entry.get("default_model") or ""}
    except (OSError, ValueError, TypeError, AttributeError, yaml.YAMLError):
        raise ValueError("Hermes 本地模型配置无法读取；请先在 Hermes CLI 中配置模型服务并登录") from None


def list_provider_models(payload: CatalogRequest, conf: dict) -> list[str]:
    return model_catalog(payload, conf)["models"]


def _api_models(payload: CatalogRequest, conf: dict) -> list[str]:
    saved = conf
    if payload.source == "models" and payload.channel_id:
        lane = "main" if payload.lane == "mid" else payload.lane
        channels = (conf.get("model_router") or {}).get(lane + "_channels", [])
        saved = next((x for x in channels if x.get("id") == payload.channel_id), {})
    def base(value):
        value = str(value or "").strip().rstrip("/")
        for suffix in ("/chat/completions", "/responses"):
            if value.endswith(suffix):
                value = value[:-len(suffix)]
        return value
    saved_url = base(saved.get("api_url") or conf.get("api_url"))
    url = base(payload.api_url or saved_url)
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("请填写有效的模型 API Base，例如 https://服务地址/v1")
    key = payload.api_key
    if not key and url == saved_url:
        key = saved.get("api_key") or ""
        if not key and payload.source == "models" and saved_url == str(conf.get("api_url") or "").rstrip("/"):
            key = conf.get("api_key") or ""
    try:
        response = requests.get(url + "/models", headers={"Authorization": f"Bearer {key}"} if key else {},
                                timeout=(5, 20), allow_redirects=False)
        if response.status_code in (401, 403):
            raise ValueError("模型列表鉴权失败，请检查该服务的 API Key")
        response.raise_for_status()
        body = response.json()
        entries = body.get("data", body.get("models", [])) if isinstance(body, dict) else body
        models = {str(x.get("id") or x.get("name") or "").strip() for x in entries if isinstance(x, dict)}
        models.discard("")
        if not models:
            raise ValueError("服务未返回模型列表；可继续手填模型 ID 并进行连通测试")
        return sorted(models)[:2000]
    except (requests.RequestException, TypeError):
        raise ValueError("无法读取模型列表；请确认 API Base 支持 /models，或手填模型 ID 后测试") from None
