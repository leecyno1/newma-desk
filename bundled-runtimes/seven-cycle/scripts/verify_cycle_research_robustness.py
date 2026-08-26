from __future__ import annotations

"""Sanity checks for the robust cycle-research outputs."""

from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"
REPORT = OUTPUT / "cycle_research_robustness_verification.md"


REQUIRED_FILES = (
    "cycle_discovery_robust_profiles.csv",
    "cycle_discovery_robust_clusters.csv",
    "cycle_discovery_prior_validation.csv",
    "cycle_discovery_robust_report.md",
    "cycle_filter_robustness_summary.csv",
    "cycle_filter_reconstruction_summary.csv",
    "cycle_filter_robustness_report.md",
    "cycle_phase_timeline_robust_annual.parquet",
    "cycle_phase_timeline_robust_monthly.parquet",
    "cycle_phase_timeline_robust_hybrid.parquet",
    "cycle_historical_event_study_summary.csv",
    "cycle_historical_event_study.md",
)


def check(condition: bool, message: str, results: list[tuple[str, bool, str]]) -> None:
    results.append((message, bool(condition), "PASS" if condition else "FAIL"))


def main() -> None:
    results: list[tuple[str, bool, str]] = []
    for file_name in REQUIRED_FILES:
        check((OUTPUT / file_name).exists(), f"required file exists: {file_name}", results)

    annual = pd.read_parquet(OUTPUT / "cycle_phase_timeline_robust_annual.parquet")
    monthly = pd.read_parquet(OUTPUT / "cycle_phase_timeline_robust_monthly.parquet")
    hybrid = pd.read_parquet(OUTPUT / "cycle_phase_timeline_robust_hybrid.parquet")
    priors = pd.read_csv(OUTPUT / "cycle_discovery_prior_validation.csv")
    filter_summary = pd.read_csv(OUTPUT / "cycle_filter_robustness_summary.csv")
    reconstruction = pd.read_csv(OUTPUT / "cycle_filter_reconstruction_summary.csv")
    events = pd.read_csv(OUTPUT / "cycle_historical_event_study_summary.csv")

    check(annual.index.is_unique, "annual robust timeline has unique index", results)
    check(monthly.index.is_unique, "monthly robust timeline has unique index", results)
    check(hybrid.index.is_unique, "hybrid robust timeline has unique index", results)
    check(len(monthly) == 312, "monthly robust timeline covers 312 months (2000-2025)", results)
    check(len(hybrid) == len(monthly), "hybrid and monthly robust timelines align", results)
    check(
        {"Cycle_9y", "Cycle_14y", "Phase_9y", "Phase_14y"}.issubset(annual.columns),
        "annual robust timeline contains expected bands",
        results,
    )
    check(
        {"Cycle_16_5m", "Cycle_21m", "Cycle_42m", "Phase_16_5m", "Phase_21m", "Phase_42m"}.issubset(monthly.columns),
        "monthly robust timeline contains expected bands",
        results,
    )

    prior_map = priors.set_index("prior")["verdict"].to_dict()
    check(prior_map.get("100m") == "supported", "100m prior remains supported", results)
    check(prior_map.get("42m") == "supported", "42m prior remains supported", results)
    check(prior_map.get("200m") == "not_broadly_supported", "200m prior is not treated as a fixed universal period", results)
    check(prior_map.get("12m") == "seasonal_diagnostic", "12m is retained as seasonality diagnostic", results)

    correlations = pd.to_numeric(filter_summary["gaussian_butterworth_correlation"], errors="coerce").dropna()
    check(bool(correlations.between(-1.0, 1.0).all()), "filter correlations are bounded", results)
    r2_columns = ["gaussian_reconstruction_r2", "butterworth_reconstruction_r2"]
    r2_values = reconstruction[r2_columns].apply(pd.to_numeric, errors="coerce").stack().dropna()
    check(bool(r2_values.between(0.0, 1.0).all()), "reconstruction R-squared values are bounded", results)
    check(len(events) == 17, "historical event study contains 17 event windows", results)
    check(
        np.isfinite(hybrid.filter(like="Cycle_").to_numpy(dtype="float64")).mean() > 0.95,
        "robust hybrid cycle values are mostly finite",
        results,
    )

    failed = [row for row in results if not row[1]]
    table = pd.DataFrame(results, columns=["check", "passed", "status"])
    lines = [
        "# Robust cycle research verification",
        "",
        f"- Checks: {len(results)}",
        f"- Passed: {len(results) - len(failed)}",
        f"- Failed: {len(failed)}",
        "",
        table[["status", "check"]].to_markdown(index=False),
        "",
    ]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print("Wrote:", REPORT)
    if failed:
        raise SystemExit(f"{len(failed)} robustness checks failed")


if __name__ == "__main__":
    main()

