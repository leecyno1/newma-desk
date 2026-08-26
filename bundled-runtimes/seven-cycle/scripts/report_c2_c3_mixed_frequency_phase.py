"""Report the governed C2/C3 mixed-frequency phase validation."""

from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LONG_PANEL_PATH = PROJECT_ROOT / "output" / "c2_c3_long_panel_research.json"
PHASE_PATH = PROJECT_ROOT / "output" / "c2_c3_historical_mapping.json"
OUTPUT_PATH = PROJECT_ROOT / "output" / "c2_c3_mixed_frequency_phase_report.md"

PHASE_LABELS = {
    "recovery": "复苏",
    "expansion": "扩张",
    "slowdown": "放缓",
    "contraction": "收缩",
}


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def build_report() -> str:
    long_panel = json.loads(LONG_PANEL_PATH.read_text(encoding="utf-8"))
    phase_payload = json.loads(PHASE_PATH.read_text(encoding="utf-8"))
    lines = [
        "# C2/C3 混频相位挑战者",
        "",
        "## 结论",
        "",
        "- C2/C3 的当前四相位候选已增加历史Q1混频截点验证，不再只依赖完整年度因子或滤波器追加稳定性。",
        "- 跨源尺度校准只使用每个历史截点当时可见的重叠数据，移除了全样本对齐带来的隐含未来信息。",
        "- 两个周期均通过研究层相位门槛，但转相年份样本少且准确率偏低，正式精确相位、精确拐点和固定周期长度继续阻断。",
        "",
        "## 验证结果",
        "",
        "| 周期 | 当前候选 | 历史条件年终保留率 | 因子方向准确率 | Q1四相位准确率 | 转相年份准确率 | 概率Brier改善 |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    details = ["", "## 周期识别", ""]
    for cycle_id in ("C2", "C3"):
        long_cycle = long_panel["cycles"][cycle_id]
        phase_cycle = phase_payload["cycles"][cycle_id]["currentPhaseCandidate"]
        phase_probability = phase_cycle["phaseProbability"]
        factor_validation = long_cycle["partialNowcast"]["validation"]
        mixed = phase_cycle["validation"]["mixedFrequencyPhase"]
        identification = phase_cycle["periodIdentification"]
        current = phase_cycle["current"]
        lines.append(
            f"| {cycle_id} | {PHASE_LABELS[current['phase']]} | "
            f"{_percent(phase_probability['primaryProbability'])} | "
            f"{_percent(factor_validation['directionAccuracy'])} | "
            f"{_percent(mixed['phaseAccuracy'])} | "
            f"{_percent(mixed['transitionPhaseAccuracy'])} "
            f"({mixed['transitionObservations']}次) | "
            f"{_percent(phase_probability['validation']['relativeBrierImprovement'])} |"
        )
        details.extend(
            [
                f"- {cycle_id}：当前治理带候选 {current['periodYears']:.1f}年，"
                f"状态为 `{identification['status']}`；{identification['conclusion']}",
                f"- {cycle_id}：混频验证覆盖 {mixed['startYear']}—{mixed['endYear']}，"
                f"相位角平均误差 {mixed['angleMaeDegrees']:.1f}°；该指标只作误差诊断，不发布精确角度。",
                f"- {cycle_id}：相邻备选为{PHASE_LABELS[phase_probability['alternativePhase']]}，"
                f"历史校准概率 {_percent(phase_probability['alternativeProbability'])}；"
                "概率只描述部分年度数据的年终修订风险。",
            ]
        )
    lines.extend(details)
    lines.extend(
        [
            "",
            "## 概率加权资产风险收益",
            "",
            "| 周期 | 资产数 | 优于硬相位 | 优于无条件均值 | 样本外R²为正 | 相对硬相位MAE | 正式资产预测 |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for cycle_id in ("C2", "C3"):
        scenario = phase_payload["cycles"][cycle_id]["assetMapping"][
            "currentProbabilityWeightedScenario"
        ]
        summary = scenario["summary"]
        validation = scenario["validation"]
        lines.append(
            f"| {cycle_id} | {summary['assets']} | "
            f"{summary['assetsBeatingHardPhase']} ({_percent(validation['assetShareBeatingHardPhase'])}) | "
            f"{summary['assetsBeatingUnconditional']} ({_percent(validation['assetShareBeatingUnconditional'])}) | "
            f"{summary['positiveOosR2']} ({_percent(validation['positiveOosR2Share'])}) | "
            f"{_percent(validation['maeImprovementVsHardPhase'])} | "
            f"{'研究可用' if scenario['assetForecastStatus'] == 'limited' else '阻断'} |"
        )
    lines.extend(
        [
            "",
            "- 概率加权分布计算条件收益、条件波动、正收益率、20%分位和尾部20%平均收益。",
            "- 两个周期均相对硬相位映射更稳，但未整体战胜无条件均值；因此这些结果是历史条件情景，不是绝对收益预测。",
            "",
            "## 平方收益风险挑战者",
            "",
            "| 周期 | 开发期权重 | 独立留出段 | 风险MAE改善 | 资产胜率 | 正收益年份占比 | 年份块Bootstrap改善概率 | 风险层状态 |",
            "|---|---:|---|---:|---:|---:|---:|---|",
        ]
    )
    for cycle_id in ("C2", "C3"):
        scenario = phase_payload["cycles"][cycle_id]["assetMapping"][
            "currentProbabilityWeightedScenario"
        ]
        risk = scenario["validation"]["risk"]
        lines.append(
            f"| {cycle_id} | "
            f"{_percent(risk['phaseWeight'])} | "
            f"{risk['holdout']['startYear']}—{risk['holdout']['endYear']} · {risk['holdout']['assets']}资产 | "
            f"{_percent(risk['maeImprovementVsUnconditional'])} | "
            f"{_percent(risk['assetShareBeatingUnconditional'])} | "
            f"{_percent(risk['positiveYearShare'])} | "
            f"{_percent(risk['yearBlockBootstrapProbability'])} | "
            f"{'有限通过' if scenario['riskForecastStatus'] == 'limited' else '阻断'} |"
        )
    lines.extend(
        [
            "",
            "- 风险目标为年度平方收益。C2/C3共用权重只在2020年前联合开发样本的0%/10%/25%保守网格中选择，严格同优时取更小权重；2021—2025 Ken French 73条资产为独立留出段。",
            "- C2风险层通过有限门槛；C3风险层继续阻断。两者的资产收益预测均未解锁。",
            "",
            "## 治理边界",
            "",
            "- 因果追加稳定率只说明新增观测不会改写旧滤波状态，不等于预测准确率。",
            "- 当前验证使用历史数据库的现行修订版，不是真实发布vintage。",
            "- 相位候选可用于研究展示和条件资产统计，不能表述为经济因果归因。",
            "- 不输出组合回测、配置权重或交易建议。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    OUTPUT_PATH.write_text(build_report(), encoding="utf-8")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
