import os
import sys
from contextlib import contextmanager

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.ai_report import ClaudeReportGenerator, LlmGenerationError  # noqa: E402


@contextmanager
def model_environment(**values):
    names = {
        "LLM_PROVIDER",
        "LLM_API_KEY",
        "SILICONFLOW_API_KEY",
        "OPENAI_COMPATIBLE_API_KEY",
        "OPENAI_API_KEY",
    }
    original = {name: os.environ.get(name) for name in names}
    try:
        for name in names:
            os.environ.pop(name, None)
        for name, value in values.items():
            os.environ[name] = value
        yield
    finally:
        for name in names:
            os.environ.pop(name, None)
        for name, value in original.items():
            if value is not None:
                os.environ[name] = value


def main() -> int:
    openai_key = "sk-openai-" + "x" * 40
    siliconflow_key = "sk-siliconflow-" + "y" * 40

    with model_environment(LLM_PROVIDER="siliconflow", OPENAI_API_KEY=openai_key):
        generator = ClaudeReportGenerator()
        if generator.api_key is not None:
            raise AssertionError("SiliconFlow must not reuse OPENAI_API_KEY")
        try:
            generator.extract_research_memo_metadata("基金经理：张三", "访谈.md")
        except LlmGenerationError as error:
            if "API Key 未配置" not in str(error):
                raise AssertionError(f"Missing provider key must be reported honestly: {error}")
        else:
            raise AssertionError("Strict metadata extraction must fail when the provider key is missing")

    with model_environment(LLM_PROVIDER="siliconflow", SILICONFLOW_API_KEY=siliconflow_key):
        generator = ClaudeReportGenerator()
        if generator.api_key != siliconflow_key:
            raise AssertionError("SiliconFlow must use its own configured key")

    with model_environment(LLM_PROVIDER="openai-compatible", OPENAI_API_KEY=openai_key):
        generator = ClaudeReportGenerator()
        if generator.api_key != openai_key:
            raise AssertionError("Generic OpenAI-compatible providers may use OPENAI_API_KEY")

    print("OK LLM credentials are isolated by provider and metadata errors remain explicit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
