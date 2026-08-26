import json
import importlib.util
import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_paradigm_profile.py"


def load_script_module():
    scripts_dir = str(SCRIPT.parent)
    inserted = False
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
        inserted = True
    spec = importlib.util.spec_from_file_location("build_paradigm_profile_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["build_paradigm_profile_test"] = module
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop("build_paradigm_profile_test", None)
        if inserted:
            sys.path.remove(scripts_dir)


def test_build_paradigm_profile_outputs_contract(tmp_path):
    sample = tmp_path / "sample.md"
    sample.write_text(
        "# 标准文章样本\n\n"
        "开头先提出一个反常识判断。\n\n"
        "## 第一部分：为什么现在重要\n\n"
        "这里放事实和背景。\n\n"
        "## 第二部分：真正的结构变化\n\n"
        "这里放论证和案例。\n\n"
        "## 第三部分：普通人怎么理解\n\n"
        "这里收束到行动建议。\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "out"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(sample),
            "--run-id",
            "2026-05-06_120000",
            "--profile-name",
            "结构变化解读",
            "--scenario",
            "行业解读",
            "--channel",
            "公众号",
            "--channel",
            "小红书",
            "--output-dir",
            str(output_dir),
            "--no-ai",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    result = json.loads(completed.stdout)
    assert result["success"] is True
    assert Path(result["profile_md"]).exists()
    assert Path(result["profile_yaml"]).exists()
    assert Path(result["prompt_block"]).exists()
    assert Path(result["manifest"]).exists()

    profile = yaml.safe_load((output_dir / "paradigm_profile.yaml").read_text(encoding="utf-8"))
    assert profile["stage"] == "paradigm"
    assert profile["run_id"] == "2026-05-06_120000"
    assert profile["boundaries"]["not_fact_source"] is True
    assert profile["boundaries"]["separate_from_style_dna"] is True
    assert "公众号" in profile["paradigm"]["channel_adaptation"]

    manifest = json.loads((output_dir / "paradigm_manifest.json").read_text(encoding="utf-8"))
    assert manifest["stage"] == "paradigm"
    assert manifest["status"] == "pending_editor_calibration"
    assert manifest["analysis_mode"] == "heuristic_fallback"
    assert manifest["next_recommended_stage"] == "brief"


def test_build_paradigm_profile_defaults_to_optional_asset_dir(tmp_path, monkeypatch):
    sample = tmp_path / "sample.md"
    sample.write_text("# 默认路径样本\n\n## 结构\n\n默认输出应落到可选资产目录。\n", encoding="utf-8")
    module = load_script_module()
    monkeypatch.setattr(module, "optional_asset_dir", lambda asset, run_id: tmp_path / "optional" / asset / run_id)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(SCRIPT),
            str(sample),
            "--run-id",
            "2026-05-06_140000",
            "--profile-name",
            "默认路径范式",
            "--no-ai",
        ],
    )

    assert module.main() == 0

    output_dir = tmp_path / "optional" / "paradigm" / "2026-05-06_140000" / "默认路径范式"
    assert (output_dir / "00_范式画像.md").exists()
    assert (output_dir / "paradigm_profile.yaml").exists()
    assert (output_dir / "paradigm_manifest.json").exists()


def test_build_paradigm_profile_accepts_ai_enrichment(tmp_path, monkeypatch):
    sample = tmp_path / "sample.md"
    sample.write_text("# 样本\n\n## 开场\n\n先制造认知错位。\n", encoding="utf-8")
    output_dir = tmp_path / "out"
    fake_response = {
        "one_line_definition": "用反常识开场，把表面事件推进成结构判断。",
        "opening_mechanism": ["先抛出读者熟悉但可能误判的表面现象"],
        "section_framework": ["表面事件", "结构变量", "行动判断"],
        "argument_model": ["先给判断", "再拆变量", "最后给边界"],
        "information_density": {"facts": "40%", "opinions": "30%", "cases": "20%", "data": "10%"},
        "paragraph_recipe": ["关键判断单句成段", "解释段控制在 120 字以内"],
        "scenario_fit": {
            "best_fit": ["行业解读"],
            "misfit": ["纯新闻快讯"],
            "preconditions": ["至少有两个独立证据来源"],
        },
        "channel_adaptation": {"公众号": "保留完整论证链，标题突出结构误判"},
        "style_boundary": ["保留推进顺序，不复用样本语气"],
        "misfit_risks": ["证据不足会变成空泛判断"],
    }
    monkeypatch.setenv("DASHENG_PARADIGM_FAKE_RESPONSE", json.dumps(fake_response, ensure_ascii=False))

    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(sample),
            "--run-id",
            "2026-05-06_130000",
            "--profile-name",
            "AI范式",
            "--scenario",
            "行业解读",
            "--channel",
            "公众号",
            "--output-dir",
            str(output_dir),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    profile = yaml.safe_load((output_dir / "paradigm_profile.yaml").read_text(encoding="utf-8"))
    assert profile["analysis_mode"] == "ai_enriched"
    assert profile["paradigm"]["one_line_definition"] == fake_response["one_line_definition"]
    assert profile["paradigm"]["scenario_fit"]["misfit"] == ["纯新闻快讯"]
    manifest = json.loads((output_dir / "paradigm_manifest.json").read_text(encoding="utf-8"))
    assert manifest["analysis_mode"] == "ai_enriched"
