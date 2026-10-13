"""Opt-in local model settings; never load an arbitrary external environment."""
import os


MODEL_ENV_KEYS = (
    "LLM_PROVIDER", "LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL",
    "LLM_TIMEOUT_SECONDS", "LLM_EVALUATION_TIMEOUT_SECONDS",
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL",
    "OPENAI_COMPATIBLE_API_KEY", "OPENAI_COMPATIBLE_BASE_URL", "OPENAI_COMPATIBLE_MODEL",
    "SILICONFLOW_API_KEY", "SILICONFLOW_BASE_URL", "SILICONFLOW_MODEL",
)


def load_shared_model_environment() -> None:
    env_file = os.environ.get("NEWMA_DESK_FUND_MODEL_ENV_FILE")
    if not env_file:
        return
    from pathlib import Path
    from dotenv import dotenv_values
    if not Path(env_file).is_file():
        raise RuntimeError("基金模型配置文件不存在")
    values = dotenv_values(env_file, interpolate=False)
    for key in MODEL_ENV_KEYS:
        if values.get(key) is not None:
            os.environ.setdefault(key, values[key])
