#!/usr/bin/env python3
"""
同步 Tushare 基金数据并生成本地基金研究报告。

配置从环境变量或 backend/.env 读取，不在代码中保存密钥。
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime
from datetime import UTC
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List

BASE_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BASE_DIR.parent
sys.path.insert(0, str(BASE_DIR))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT_DIR / ".env.local")
    load_dotenv(ROOT_DIR / ".env")
    load_dotenv(BASE_DIR / ".env")
except Exception:
    pass

from database import init_database, get_engine
from repositories import get_fund_repo, get_manager_repo, get_nav_repo
from services.evidence_report import build_fund_research_report
from services.ai_report import get_report_generator
from services.fund_classification_ingestion_service import FundClassificationIngestionService
from services.fund_nav_evidence_service import FundNavDataEnrichmentService
from services.tushare_service import TushareDataService


def log(message: str) -> None:
    print(message, flush=True)


def json_safe(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def sanitize_research_language(content: str) -> str:
    replacements = {
        "投资建议": "研究跟踪建议",
        "建议" + "买入": "建议进入后续研究",
        "建议" + "卖出": "建议降低后续研究优先级",
        "建议" + "加仓": "建议提高后续跟踪优先级",
        "建议" + "减仓": "建议降低后续跟踪优先级",
        "重仓" + "买入": "提高研究优先级",
        "投资决策流程": "投资研究流程",
        "投资决策结论": "下游结论",
        "投资决策": "研究结论",
        "投决": "研究结论",
    }
    sanitized = content
    for source, target in replacements.items():
        sanitized = sanitized.replace(source, target)
    return sanitized


def _clean_scalar(value: Any) -> Any:
    if value is None:
        return None
    try:
        if value != value:
            return None
    except Exception:
        pass
    text = str(value).strip()
    if text.lower() in {"", "none", "nan", "nat"}:
        return None
    return value


def _format_tushare_date(value: Any) -> str | None:
    text = str(_clean_scalar(value) or "").strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return None


def _years_since(value: Any) -> float:
    date_text = _format_tushare_date(value)
    if not date_text:
        return 0.0
    try:
        started = datetime.fromisoformat(date_text)
        return round(max(0, (datetime.now() - started).days) / 365.25, 2)
    except ValueError:
        return 0.0


def _manager_id_from_row(row: Dict[str, Any]) -> str:
    name = str(_clean_scalar(row.get("name")) or "未知经理").strip()
    gender = str(_clean_scalar(row.get("gender")) or "").strip()
    education = str(_clean_scalar(row.get("edu")) or "").strip()
    return f"{name}|{gender}|{education}"


def sync_fund_managers(data_service: TushareDataService, wind_code: str) -> List[str]:
    manager_repo = get_manager_repo()
    try:
      manager_df = data_service.pro.fund_manager(ts_code=wind_code)
    except Exception as error:
      log(f"manager unavailable {wind_code}: {error}")
      return []

    if manager_df is None or manager_df.empty:
        return []

    active_manager_ids: List[str] = []
    for _, row_obj in manager_df.iterrows():
        row = {key: _clean_scalar(value) for key, value in row_obj.to_dict().items()}
        manager_id = _manager_id_from_row(row)
        begin_date = _format_tushare_date(row.get("begin_date"))
        end_date = _format_tushare_date(row.get("end_date"))
        is_active = end_date is None
        if is_active and manager_id not in active_manager_ids:
            active_manager_ids.append(manager_id)

        manager_repo.upsert_manager(
            manager_id,
            {
                "name": row.get("name") or manager_id.split("|")[0],
                "company": "",
                "education": row.get("edu") or "",
                "experience_years": _years_since(row.get("begin_date")),
                "management_years": _years_since(row.get("begin_date")),
                "current_funds": [wind_code] if is_active else [],
                "historical_performance": {
                    "fund_code": wind_code,
                    "fund_tenure_start": begin_date,
                    "fund_tenure_end": end_date,
                    "is_current_manager": is_active,
                },
                "raw_data": {
                    "source": "tushare.fund_manager",
                    "synced_at": datetime.now(UTC).isoformat(),
                    "manager_id": manager_id,
                    "fund_code": wind_code,
                    "fund_manager_row": row,
                },
            },
        )

    return active_manager_ids


def _sync_one_fund(
    data_service: TushareDataService,
    wind_code: str,
    throttle_seconds: float,
) -> bool:
    fund_repo = get_fund_repo()
    nav_repo = get_nav_repo()
    data_quality = {
        "basic_info": "ok",
        "performance": "ok",
        "risk": "ok",
        "nav_series": "ok",
    }

    try:
        info = data_service.get_fund_info(wind_code)
    except Exception as info_error:
        log(f"skip {wind_code}: basic info unavailable: {info_error}")
        if throttle_seconds > 0:
            time.sleep(throttle_seconds)
        return False

    try:
        ingestion_service = FundClassificationIngestionService()
        ingestion_plan = ingestion_service.build_plan([{**info, "wind_code": wind_code}])
        if ingestion_plan.get("groups"):
            ingestion_service.apply_plan(ingestion_plan)
    except Exception as ingestion_error:
        data_quality["classification_ingestion"] = "unavailable"
        data_quality["classification_ingestion_reason"] = str(ingestion_error)

    try:
        performance = data_service.get_fund_performance(wind_code)
    except Exception as performance_error:
        performance = {}
        data_quality["performance"] = "unavailable"
        data_quality["performance_reason"] = str(performance_error)

    try:
        risk = data_service.get_fund_risk_metrics(wind_code)
    except Exception as risk_error:
        risk = {}
        data_quality["risk"] = "unavailable"
        data_quality["risk_reason"] = str(risk_error)

    nav_points = 0
    enrichment = {
        "benchmark_data_status": "not_checked",
        "benchmark_observations": 0,
        "money_market_metric_status": "not_checked",
    }
    try:
        end_date = datetime.now(UTC).date()
        start_date = end_date - timedelta(days=365 * 3)
        nav_series = data_service.get_fund_nav(
            wind_code,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        )
        enrichment = FundNavDataEnrichmentService(data_service).enrich(
            wind_code=wind_code,
            fund_type=info.get("type"),
            nav_series=nav_series,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        )
        nav_series = enrichment["nav_series"]
        if enrichment.get("nav_data_status") != "valid":
            data_quality["nav_series"] = "invalid"
            data_quality["nav_series_reason"] = enrichment.get("nav_validation")
            nav_points = 0
        else:
            performance.update(enrichment.get("performance_facts") or {})
            nav_points = len(nav_series)
        if nav_series and enrichment.get("nav_data_status") == "valid":
            nav_repo.upsert_nav_series(wind_code, nav_series, replace_range=True)
        elif enrichment.get("nav_data_status") == "valid":
            data_quality["nav_series"] = "empty"
    except Exception as nav_error:
        data_quality["nav_series"] = "unavailable"
        data_quality["nav_series_reason"] = str(nav_error)

    manager_ids = sync_fund_managers(data_service, wind_code)
    data_quality["manager"] = "ok" if manager_ids else "unavailable"

    raw_data = {
        "source": "tushare",
        "synced_at": datetime.now(UTC).isoformat(),
        "data_quality": data_quality,
        "nav_points": nav_points,
        "info": info,
    }
    if performance:
        raw_data["performance"] = performance
    if risk:
        raw_data["risk"] = risk
    if enrichment.get("benchmark_data_status") != "not_checked":
        raw_data["nav_evidence"] = {
            "benchmark_code": enrichment.get("benchmark_code"),
            "benchmark_source": enrichment.get("benchmark_source"),
            "benchmark_data_status": enrichment.get("benchmark_data_status"),
            "benchmark_data_kind": enrichment.get("benchmark_data_kind"),
            "benchmark_observations": enrichment.get("benchmark_observations", 0),
            "benchmark_nav_observations": enrichment.get("benchmark_nav_observations", 0),
            "benchmark_rate_observations": enrichment.get("benchmark_rate_observations", 0),
            "money_market_metric_status": enrichment.get("money_market_metric_status"),
            "nav_data_status": enrichment.get("nav_data_status"),
            "nav_validation": enrichment.get("nav_validation"),
        }

    ok = fund_repo.upsert_fund(
        wind_code,
        {
            "name": info.get("name", wind_code),
            "type": info.get("type", ""),
            "manager_ids": manager_ids,
            "nav": info.get("nav"),
            "nav_date": info.get("nav_date"),
            "total_asset": info.get("total_asset"),
            "establishment_date": info.get("establishment_date"),
            "management_company": info.get("management_company", ""),
            "performance_data": performance,
            "risk_metrics": risk,
            "raw_data": raw_data,
        },
    )
    if throttle_seconds > 0:
        time.sleep(throttle_seconds)
    return ok


def sync_universe(max_funds: int) -> int:
    data_service = TushareDataService(strict_no_mock=True)
    if data_service.mock_mode:
        raise RuntimeError("Tushare 未连接真实 API。请配置 TUSHARE_TOKEN 后重试。")

    fund_repo = get_fund_repo()
    all_funds = data_service.get_all_funds()
    if max_funds > 0:
        all_funds = all_funds[:max_funds]

    synced = 0
    for item in all_funds:
        wind_code = item.get("wind_code")
        if not wind_code:
            continue
        ok = fund_repo.upsert_fund(
            wind_code,
            {
                "name": item.get("name") or wind_code,
                "type": item.get("type") or "",
                "establishment_date": item.get("establishment_date"),
                "raw_data": {
                    "source": "tushare",
                    "universe": item,
                    "data_quality": {
                        "basic_info": "ok",
                        "detail_level": "universe_only",
                        "note": "全市场基础库，仅用于浏览、搜索和后续精同步排队；净值、风险、报告需详细同步补齐。",
                    },
                    "synced_at": datetime.now(UTC).isoformat(),
                },
            },
        )
        if ok:
            synced += 1
        if synced and synced % 500 == 0:
            log(f"universe synced: {synced}/{len(all_funds)}")
    log(f"universe done: synced={synced} total_source={len(all_funds)}")
    return synced


def sync_specific_funds(codes: List[str], throttle_seconds: float) -> List[str]:
    data_service = TushareDataService(strict_no_mock=True)
    if data_service.mock_mode:
        raise RuntimeError("Tushare 未连接真实 API。请配置 TUSHARE_TOKEN 后重试。")

    synced_codes: List[str] = []
    for index, code in enumerate(codes, start=1):
        if _sync_one_fund(data_service, code, throttle_seconds):
            synced_codes.append(code)
            log(f"synced {index:>3}/{len(codes)}: {code}")
    return synced_codes


def sync_funds(max_funds: int, batch_size: int, throttle_seconds: float) -> List[str]:
    data_service = TushareDataService(strict_no_mock=True)
    if data_service.mock_mode:
        raise RuntimeError("Tushare 未连接真实 API。请配置 TUSHARE_TOKEN 后重试。")

    synced_codes: List[str] = []
    page = 1

    while len(synced_codes) < max_funds:
        result = data_service.get_fund_list(page=page, page_size=batch_size)
        codes = result.get("list", [])
        if not codes:
            break

        for code in codes:
            if len(synced_codes) >= max_funds:
                break
            if _sync_one_fund(data_service, code, throttle_seconds):
                synced_codes.append(code)
                log(f"synced {len(synced_codes):>3}/{max_funds}: {code}")

        if len(codes) < batch_size:
            break
        page += 1

    return synced_codes


def load_fund_from_db(wind_code: str) -> Dict[str, Any]:
    fund = get_fund_repo().get_fund(wind_code)
    if not fund:
        raise RuntimeError(f"基金未入库: {wind_code}")
    return fund


def _is_unusable_llm_report(content: str) -> bool:
    stripped = content.lstrip()
    return (
        stripped.startswith("## 报告生成失败")
        or "当前使用模拟数据" in content
        or "配置模型 API Key 后" in content
    )


def save_report_to_postgres(
    wind_code: str,
    content: str,
    data_sources: Dict[str, Any],
    provider: str,
    model: str,
    generation_mode: str,
) -> None:
    from sqlalchemy import text

    sql = text(
        """
        INSERT INTO ai_analysis_reports (
            target_type, target_id, report_type, content, data_sources,
            research_reports_used, generation_params, created_at
        ) VALUES (
            'fund', :target_id, 'fund_research_report', :content, CAST(:data_sources AS jsonb),
            ARRAY[]::text[], CAST(:generation_params AS jsonb), NOW()
        )
        """
    )
    with get_engine().begin() as conn:
        conn.execute(
            sql,
            {
                "target_id": wind_code,
                "content": content,
                "data_sources": json_safe(data_sources),
                "generation_params": json_safe({"provider": provider, "model": model, "mode": generation_mode}),
            },
        )


def generate_reports(codes: List[str], report_count: int, output_dir: Path) -> List[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    generator = get_report_generator()
    generated_files: List[Path] = []

    for code in codes[:report_count]:
        fund = load_fund_from_db(code)
        performance = fund.get("performance_data") or {}
        risk = fund.get("risk_metrics") or {}
        style = {
            "data_status": "unavailable",
            "reason": "本批处理仅使用 Tushare 基础信息、净值绩效与风险字段；持仓/Barra 风格需接入可靠持仓接口后补充。",
        }
        holdings = []

        scoring = {
            "overall_score": None,
            "note": "本批处理脚本聚焦真实数据同步与研究报告生成，评分可在系统评分模块中单独刷新。",
        }
        generation_mode = "llm"
        if generator.api_key:
            content = generator.generate_fund_analysis(
                fund_data=fund,
                performance_data=performance,
                risk_data=risk,
                holdings_data=holdings,
                style_data=style,
                scoring_result=scoring,
                research_reports=[],
            )
        else:
            content = ""
        if not content or _is_unusable_llm_report(content):
            content = build_fund_research_report(
                fund_data=fund,
                performance_data=performance,
                risk_data=risk,
                style_data=style,
                scoring_result=scoring,
                holdings_data=holdings,
            )
            generation_mode = "deterministic_evidence_backed"
        else:
            content = sanitize_research_language(content)
        header = (
            f"<!-- source=tushare provider={generator.provider} model={generator.model} mode={generation_mode} "
            f"generated_at={datetime.now(UTC).isoformat()} -->\n\n"
        )
        report = header + content.strip() + "\n"
        safe_code = code.replace("/", "_").replace(".", "_")
        output_file = output_dir / f"{safe_code}_fund_research.md"
        output_file.write_text(report, encoding="utf-8")
        save_report_to_postgres(
            code,
            report,
            {
                "source": "tushare",
                "generation_mode": generation_mode,
                "fund": fund,
                "performance": performance,
                "risk": risk,
                "style": style,
                "holdings_count": len(holdings),
            },
            generator.provider,
            generator.model,
            generation_mode,
        )
        generated_files.append(output_file)
        log(f"generated report: {output_file} ({generation_mode})")

    return generated_files


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-funds", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=30)
    parser.add_argument("--reports", type=int, default=5)
    parser.add_argument("--codes", default="", help="逗号分隔的基金代码；传入后只为这些代码生成报告")
    parser.add_argument("--output-dir", default=str(BASE_DIR / "generated_reports"))
    parser.add_argument("--throttle-seconds", type=float, default=0.8, help="每只基金同步后的暂停秒数，避免触发 Tushare 限频")
    parser.add_argument("--sync-universe", action="store_true", help="先同步 Tushare 全市场基础基金库到本地 PostgreSQL")
    parser.add_argument("--universe-limit", type=int, default=0, help="全市场基础库同步上限；0 表示同步 Tushare 返回的全部基金")
    parser.add_argument("--universe-only", action="store_true", help="仅同步全市场基础基金库，不生成报告、不做深度同步")
    args = parser.parse_args()

    if not os.environ.get("TUSHARE_TOKEN"):
        raise RuntimeError("缺少 TUSHARE_TOKEN。请在环境变量或 backend/.env 中配置。")

    init_database()
    log(f"LLM provider: {os.environ.get('LLM_PROVIDER', 'anthropic')}")
    if args.sync_universe:
        synced = sync_universe(args.universe_limit)
        log(f"universe synced: {synced}")
        if args.universe_only:
            return 0
    if args.codes.strip():
        requested_codes = [code.strip() for code in args.codes.split(",") if code.strip()]
        synced_codes = sync_specific_funds(requested_codes, args.throttle_seconds)
    else:
        synced_codes = sync_funds(max_funds=args.max_funds, batch_size=args.batch_size, throttle_seconds=args.throttle_seconds)
    if not synced_codes:
        raise RuntimeError("没有同步到任何基金。")
    generated_files = generate_reports(synced_codes, args.reports, Path(args.output_dir))
    log(f"done: synced={len(synced_codes)} reports={len(generated_files)} output={args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
