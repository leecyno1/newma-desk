"""Report governed gains from the fixed strong-shrink asset challenger."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = PROJECT_ROOT / "output" / "asset_cycle_state_forecast.json"
OUTPUT_PATH = PROJECT_ROOT / "output" / "asset_forecast_strong_shrink_report.md"
BASE_MODELS = (
    "state_analog",
    "state_analog_shrunk",
    "state_analog_recency",
    "state_ridge",
    "category_context_ridge",
    "state_model_consensus",
)
CHALLENGER_MODELS = (*BASE_MODELS, "state_analog_strong_shrink")


def _model_rank(validation: dict[str, object]) -> tuple[object, ...]:
    recent = validation.get("recentValidation")
    recent_passed = (
        int(recent.get("passedGateCount", 0)) if isinstance(recent, dict) else 0
    )
    governed = bool(validation.get("qualified")) and bool(
        validation.get("robustnessStable", True)
    )
    return (
        governed,
        bool(validation.get("recentStable")),
        int(validation.get("passedGateCount", 0)),
        recent_passed,
        float(validation.get("oosR2") or -1e9),
        float(validation.get("baseBrier") or 0.0)
        - float(validation.get("brier") or 1e9),
        float(validation.get("baseMae") or 0.0)
        - float(validation.get("mae") or 1e9),
    )


def _selected_result(
    asset: dict[str, object],
    horizon: str,
    model_ids: tuple[str, ...],
    *,
    ignore_materiality: bool = False,
) -> tuple[str, dict[str, object]]:
    models = asset["horizons"][horizon]["models"]
    available: dict[str, dict[str, object]] = {}
    fallback: dict[str, dict[str, object]] = {}
    for model in model_ids:
        if model not in models:
            continue
        result = deepcopy(models[model])
        if ignore_materiality and model == "state_analog_strong_shrink":
            result["validation"]["robustnessStable"] = True
        fallback[model] = result
        if result["forecast"] is not None:
            available[model] = result
    candidates = available or fallback
    if not candidates:
        raise RuntimeError("no forecast candidate available")
    champion = max(
        candidates,
        key=lambda model: _model_rank(candidates[model]["validation"]),
    )
    return champion, candidates[champion]


def _published(asset: dict[str, object], result: dict[str, object]) -> bool:
    validation = result["validation"]
    return bool(
        asset["currentDataAvailable"]
        and result["forecast"] is not None
        and validation["qualified"]
        and validation.get("robustnessStable", True)
        and validation.get("recentStable")
    )


def build_report() -> str:
    payload = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    lines = [
        "# 资产预测强收缩挑战者",
        "",
        "## 结论",
        "",
        "- 挑战者把24个局部近邻向固定144期历史先验收缩，局部权重固定为14.3%，不按资产调参。",
        "- 除原五项样本外门槛外，额外要求R²至少0.5%、MAE相对改善至少0.1%、Brier改善至少0.001。",
        "- 原始五门槛产生的万分级优势不会直接发布。",
        "",
        "## 样本外增量",
        "",
        "| 期限 | 基础正式通过 | 忽略增益幅度 | 最终正式通过 | 可信净增量 |",
        "|---:|---:|---:|---:|---:|",
    ]
    details = ["", "## 新增正式结果", ""]
    for horizon in ("1", "3", "6"):
        base_ids: set[str] = set()
        raw_ids: set[str] = set()
        final_ids: set[str] = set()
        for asset in payload["assets"]:
            _, base = _selected_result(asset, horizon, BASE_MODELS)
            _, raw = _selected_result(
                asset,
                horizon,
                CHALLENGER_MODELS,
                ignore_materiality=True,
            )
            _, final = _selected_result(asset, horizon, CHALLENGER_MODELS)
            if _published(asset, base):
                base_ids.add(asset["assetId"])
            if _published(asset, raw):
                raw_ids.add(asset["assetId"])
            if _published(asset, final):
                final_ids.add(asset["assetId"])
        lines.append(
            f"| {horizon}个月 | {len(base_ids)} | {len(raw_ids)} | "
            f"{len(final_ids)} | {len(final_ids) - len(base_ids):+d} |"
        )
        for asset_id in sorted(final_ids - base_ids):
            asset = next(
                item for item in payload["assets"] if item["assetId"] == asset_id
            )
            _, result = _selected_result(asset, horizon, CHALLENGER_MODELS)
            validation = result["validation"]
            materiality = validation["challengerMateriality"]
            details.append(
                f"- {horizon}个月 · {asset_id}：R² {validation['oosR2']:.3f}，"
                f"MAE相对改善 {materiality['relativeMaeImprovement']:.2%}，"
                f"Brier改善 {materiality['brierImprovement']:.3f}。"
            )
    lines.extend(details)
    lines.extend(
        [
            "",
            "## 治理边界",
            "",
            "- 强收缩是预测稳健化，不是经济因果归因。",
            "- 3个月期限没有可信净增量，继续维持原发布数量。",
            "- 本报告不包含组合回测、配置权重或交易建议。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    OUTPUT_PATH.write_text(build_report(), encoding="utf-8")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
