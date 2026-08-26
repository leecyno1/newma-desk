#!/usr/bin/env python3
"""Build reproducible model-price and benchmark evidence assets."""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def extract_gpt4_8k_price(page_text: str) -> dict[str, float]:
    match = re.search(
        r"每\s*1K\s*提示令牌\s*([0-9.]+)\s*美元，每\s*1K\s*补全令牌\s*([0-9.]+)\s*美元",
        page_text,
    )
    if not match:
        raise ValueError("OpenAI GPT-4 8K pricing excerpt was not found.")
    return {
        "input_usd_per_1m": float(match.group(1)) * 1000,
        "output_usd_per_1m": float(match.group(2)) * 1000,
    }


def extract_deepseek_prices(payload: dict[str, Any]) -> list[dict[str, Any]]:
    wanted = {"DeepSeek-V4-Flash", "DeepSeek-V4-Pro"}
    models = [model for model in payload.get("models") or [] if model.get("model") in wanted]
    if {model.get("model") for model in models} != wanted:
        raise ValueError("DeepSeek pricing asset is missing V4 Flash or V4 Pro.")
    return models


def build_cost_comparison(
    baseline: dict[str, float],
    current_models: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for model in current_models:
        prices = model["price_per_1m_tokens_usd"]
        input_price = float(prices["input_cache_miss"])
        output_price = float(prices["output"])
        rows.append(
            {
                "model": model["model"],
                "input_cache_miss_usd_per_1m": input_price,
                "output_usd_per_1m": output_price,
                "input_vs_gpt4_pct": round(input_price / baseline["input_usd_per_1m"] * 100, 4),
                "output_vs_gpt4_pct": round(output_price / baseline["output_usd_per_1m"] * 100, 4),
            }
        )
    return rows


def extract_artificial_analysis_scores(page_text: str) -> dict[str, int]:
    match = re.search(
        r"DeepSeek V4 Flash \(high\)\s+Hy3-preview\s+(\d+)\*?\s+(\d+)\*?",
        page_text,
    )
    if not match:
        raise ValueError("Artificial Analysis Hy3/V4 Flash score pair was not found.")
    return {"deepseek_v4_flash": int(match.group(1)), "hy3_preview": int(match.group(2))}


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Cannot write empty CSV: {path}")
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def build_assets(
    openai_snapshot_path: Path,
    deepseek_pricing_path: Path,
    benchmark_snapshot_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    created_at = datetime.now().astimezone().isoformat(timespec="seconds")
    openai_snapshot = read_json(openai_snapshot_path)
    deepseek_pricing = read_json(deepseek_pricing_path)
    benchmark_snapshot = read_json(benchmark_snapshot_path)

    baseline = extract_gpt4_8k_price(str(openai_snapshot["text"]))
    current_rows = build_cost_comparison(baseline, extract_deepseek_prices(deepseek_pricing))
    cost_dir = output_dir / "model_token_cost_history_table"
    cost_asset = {
        "schema_version": "dasheng.video.model_cost_evidence.v1",
        "id": "model_token_cost_history_table",
        "title": "从 2023 GPT-4 到 2026 DeepSeek V4 的 Token 价格比较",
        "status": "ok",
        "created_at": created_at,
        "comparison_basis": "Official list price, USD per 1 million uncached input/output tokens",
        "baseline": {
            "model": "GPT-4 8K (gpt-4-0314)",
            "date": "2023-03-14",
            **baseline,
            "source_url": openai_snapshot.get("url"),
            "local_source": str(openai_snapshot_path),
            "source_excerpt": "每 1K 提示令牌 0.03 美元，每 1K 补全令牌 0.06 美元",
        },
        "current_models": current_rows,
        "current_source": {
            "source_url": deepseek_pricing.get("source_url"),
            "local_source": str(deepseek_pricing_path),
            "fetched_at": deepseek_pricing.get("fetched_at"),
        },
        "claim_assessment": {
            "verdict": "supports_with_defined_baseline",
            "supported_wording": "若以 2023 年 GPT-4 8K 官方公开价为基准，DeepSeek V4 Flash 约为 0.47%，V4 Pro 约为 1.45%，已进入约 1% 的量级。",
            "unsupported_wording": "不得把 1% 泛化为相对所有模型、所有缓存状态和所有任务成本。",
        },
    }
    write_json(cost_dir / "model_token_cost_history_table.json", cost_asset)
    _write_rows(
        cost_dir / "model_token_cost_history_table.csv",
        [
            {
                "model": cost_asset["baseline"]["model"],
                "input_usd_per_1m": baseline["input_usd_per_1m"],
                "output_usd_per_1m": baseline["output_usd_per_1m"],
                "input_vs_gpt4_pct": 100.0,
                "output_vs_gpt4_pct": 100.0,
            }
        ]
        + [
            {
                "model": row["model"],
                "input_usd_per_1m": row["input_cache_miss_usd_per_1m"],
                "output_usd_per_1m": row["output_usd_per_1m"],
                "input_vs_gpt4_pct": row["input_vs_gpt4_pct"],
                "output_vs_gpt4_pct": row["output_vs_gpt4_pct"],
            }
            for row in current_rows
        ],
    )

    scores = extract_artificial_analysis_scores(str(benchmark_snapshot["text"]))
    benchmark_dir = output_dir / "hunyuan_model_benchmark_table"
    benchmark_asset = {
        "schema_version": "dasheng.video.model_benchmark_evidence.v1",
        "id": "hunyuan_model_benchmark_table",
        "title": "Artificial Analysis：Hy3-preview 与 DeepSeek V4 Flash 同榜比较",
        "status": "ok",
        "created_at": created_at,
        "provider": "Artificial Analysis",
        "benchmark": "Artificial Analysis Intelligence Index v4.1",
        "fetched_at": benchmark_snapshot.get("fetchedAt"),
        "models": [
            {"model": "DeepSeek V4 Flash (Reasoning, High Effort)", "score": scores["deepseek_v4_flash"], "evaluation_status": "estimate"},
            {"model": "Hy3-preview (Reasoning)", "score": scores["hy3_preview"], "evaluation_status": "estimate"},
        ],
        "comparison": {
            "absolute_gap": scores["deepseek_v4_flash"] - scores["hy3_preview"],
            "hy3_as_pct_of_v4_flash": round(scores["hy3_preview"] / scores["deepseek_v4_flash"] * 100, 2),
            "verdict": "supports_close_but_not_equal",
        },
        "source_locator": {
            "kind": "third_party_same_leaderboard_snapshot",
            "url": benchmark_snapshot.get("url"),
            "local_source": str(benchmark_snapshot_path),
            "source_excerpt": "DeepSeek V4 Flash (high) 37; Hy3-preview 34; estimate pending independent evaluation.",
        },
        "claim_assessment": {
            "verdict": "supports_with_disclosure",
            "supported_wording": "在同榜估算中，Hy3-preview 为 34，DeepSeek V4 Flash high 为 37，分数接近但后者仍领先。",
            "disclosure": "页面标注为估算，独立评测尚待完成；‘日常使用够用’仍是作者判断。",
        },
    }
    write_json(benchmark_dir / "hunyuan_model_benchmark_table.json", benchmark_asset)
    _write_rows(
        benchmark_dir / "hunyuan_model_benchmark_table.csv",
        [
            {
                "model": model["model"],
                "score": model["score"],
                "evaluation_status": model["evaluation_status"],
                "benchmark": benchmark_asset["benchmark"],
            }
            for model in benchmark_asset["models"]
        ],
    )

    manifest = {
        "schema_version": "dasheng.video.model_evidence_manifest.v1",
        "created_at": created_at,
        "status": "pass",
        "assets": [
            {"id": cost_asset["id"], "json_path": str(cost_dir / "model_token_cost_history_table.json"), "csv_path": str(cost_dir / "model_token_cost_history_table.csv")},
            {"id": benchmark_asset["id"], "json_path": str(benchmark_dir / "hunyuan_model_benchmark_table.json"), "csv_path": str(benchmark_dir / "hunyuan_model_benchmark_table.csv")},
        ],
    }
    write_json(output_dir / "model_evidence_manifest.json", manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build model pricing and benchmark evidence.")
    parser.add_argument("--openai-snapshot", required=True)
    parser.add_argument("--deepseek-pricing", required=True)
    parser.add_argument("--benchmark-snapshot", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = build_assets(
        Path(args.openai_snapshot).expanduser().resolve(),
        Path(args.deepseek_pricing).expanduser().resolve(),
        Path(args.benchmark_snapshot).expanduser().resolve(),
        Path(args.output_dir).expanduser().resolve(),
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
