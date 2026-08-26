"""Report the governed incremental value of the asset consensus challenger."""

from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = PROJECT_ROOT / "output" / "asset_cycle_state_forecast.json"
OUTPUT_PATH = (
    PROJECT_ROOT / "output" / "asset_forecast_consensus_challenger_report.md"
)
BASE_MODELS = (
    "state_analog",
    "state_analog_shrunk",
    "state_analog_recency",
    "state_ridge",
    "category_context_ridge",
)
CONSENSUS_MODELS = (*BASE_MODELS, "state_model_consensus")


def _model_rank(validation: dict[str, object]) -> tuple[object, ...]:
    recent_validation = validation.get("recentValidation")
    recent_passed = (
        int(recent_validation.get("passedGateCount", 0))
        if isinstance(recent_validation, dict)
        else 0
    )
    governed_qualified = bool(validation.get("qualified")) and bool(
        validation.get("robustnessStable", True)
    )
    return (
        governed_qualified,
        bool(validation.get("recentStable")),
        int(validation.get("passedGateCount", 0)),
        recent_passed,
        float(validation.get("oosR2") or -1e9),
        float(validation.get("baseBrier") or 0.0)
        - float(validation.get("brier") or 1e9),
        float(validation.get("baseMae") or 0.0)
        - float(validation.get("mae") or 1e9),
    )


def _publication_qualified(
    asset: dict[str, object],
    result: dict[str, object],
) -> bool:
    validation = result["validation"]
    return bool(
        asset["currentDataAvailable"]
        and result["forecast"] is not None
        and validation["qualified"]
        and validation.get("robustnessStable", True)
        and validation.get("recentStable")
    )


def _selected_result(
    asset: dict[str, object],
    horizon: str,
    model_ids: tuple[str, ...],
) -> tuple[str, dict[str, object]]:
    models = asset["horizons"][horizon]["models"]
    available = {
        model: models[model]
        for model in model_ids
        if model in models and models[model]["forecast"] is not None
    }
    candidates = available or {
        model: models[model]
        for model in model_ids
        if model in models
    }
    champion = max(
        candidates,
        key=lambda model: _model_rank(candidates[model]["validation"]),
    )
    return champion, candidates[champion]


def build_report() -> str:
    payload = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    lines = [
        "# 资产预测固定规则共识挑战者",
        "",
        "## 结论",
        "",
        "- 挑战者固定等权合成稳健状态近邻、资产Ridge与可用的类别上下文Ridge；不按单项资产选择权重。",
        "- 所有模型继续使用扩展窗口递归检验，并保持方向、概率、收益误差、样本外R²和近期稳定性原门槛。",
        "- 数据源正常滞后或过期的资产继续禁止作为当前正式预测。",
        "",
        "## 样本外增量",
        "",
        "| 期限 | 基础模型正式通过 | 加入共识后正式通过 | 净增量 | 基础模型全历史通过 | 加入共识后全历史通过 | 共识冠军数 |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    detail_lines = ["", "## 新增正式结果", ""]
    for horizon in ("1", "3", "6"):
        base_published: set[str] = set()
        base_full: set[str] = set()
        actual_published: set[str] = set()
        actual_full: set[str] = set()
        consensus_champions = 0
        for asset in payload["assets"]:
            _, base = _selected_result(asset, horizon, BASE_MODELS)
            if (
                asset["currentDataAvailable"]
                and base["forecast"] is not None
                and base["validation"]["qualified"]
                and base["validation"].get("robustnessStable", True)
            ):
                base_full.add(asset["assetId"])
            if _publication_qualified(asset, base):
                base_published.add(asset["assetId"])
            challenger_model, actual = _selected_result(
                asset,
                horizon,
                CONSENSUS_MODELS,
            )
            if challenger_model == "state_model_consensus":
                consensus_champions += 1
            if (
                asset["currentDataAvailable"]
                and actual["forecast"] is not None
                and actual["validation"]["qualified"]
                and actual["validation"].get("robustnessStable", True)
            ):
                actual_full.add(asset["assetId"])
            if _publication_qualified(asset, actual):
                actual_published.add(asset["assetId"])
        lines.append(
            f"| {horizon}个月 | {len(base_published)} | {len(actual_published)} | "
            f"{len(actual_published) - len(base_published):+d} | {len(base_full)} | "
            f"{len(actual_full)} | {consensus_champions} |"
        )
        unlocked = sorted(actual_published - base_published)
        if unlocked:
            detail_lines.append(f"### {horizon}个月")
            detail_lines.append("")
            for asset_id in unlocked:
                asset = next(
                    item for item in payload["assets"] if item["assetId"] == asset_id
                )
                _, selected = _selected_result(
                    asset,
                    horizon,
                    CONSENSUS_MODELS,
                )
                validation = selected["validation"]
                detail_lines.append(
                    f"- {asset_id}：样本外R² {validation['oosR2']:.3f}，"
                    f"方向准确率 {validation['directionAccuracy']:.1%}，"
                    f"MAE {validation['mae']:.4f} 对基准 {validation['baseMae']:.4f}，"
                    f"Brier {validation['brier']:.3f} 对基准 {validation['baseBrier']:.3f}。"
                )
            detail_lines.append("")
    lines.extend(detail_lines)
    lines.extend(
        [
            "## 治理边界",
            "",
            "- 共识模型是预测组合，不是周期或资产收益的经济因果归因。",
            "- 共识冠军数量不等于正式发布数量；未同时通过全部门槛的资产继续保持阻断。",
            "- 本报告不包含组合回测、配置权重或交易建议。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    report = build_report()
    OUTPUT_PATH.write_text(report, encoding="utf-8")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
