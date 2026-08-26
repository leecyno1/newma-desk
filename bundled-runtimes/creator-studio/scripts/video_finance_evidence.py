#!/usr/bin/env python3
"""Build machine-readable finance evidence assets for video claims."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


SOURCE_NAME = "Yahoo Finance via yfinance"
EASTMONEY_SOURCE_NAME = "Eastmoney delayed quote API"


def configure_matplotlib_font(candidates: list[str] | None = None) -> str:
    import matplotlib
    from matplotlib import font_manager

    candidates = candidates or ["Hiragino Sans GB", "Heiti SC", "Songti SC", "Arial Unicode MS"]
    for family in candidates:
        try:
            font_manager.findfont(family, fallback_to_default=False)
        except ValueError:
            continue
        matplotlib.rcParams["font.family"] = ["sans-serif"]
        matplotlib.rcParams["font.sans-serif"] = [family]
        matplotlib.rcParams["axes.unicode_minus"] = False
        return family
    raise RuntimeError("No CJK-capable Matplotlib font is installed.")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_relative_series(
    prices: pd.DataFrame,
    labels: dict[str, str],
    *,
    window_sessions: list[int] | None = None,
) -> dict[str, Any]:
    columns = [ticker for ticker in labels if ticker in prices.columns]
    if not columns:
        raise ValueError("No requested ticker columns were returned.")
    common = prices[columns].apply(pd.to_numeric, errors="coerce").dropna(how="any")
    if common.empty:
        raise ValueError("Requested tickers have no common non-null dates.")
    normalized = common.divide(common.iloc[0]).multiply(100.0)
    windows: list[dict[str, Any]] = []
    for sessions in window_sessions or []:
        if sessions <= 0 or len(common) <= sessions:
            continue
        start = common.iloc[-1 - sessions]
        end = common.iloc[-1]
        windows.append(
            {
                "sessions": sessions,
                "start_date": common.index[-1 - sessions].strftime("%Y-%m-%d"),
                "end_date": common.index[-1].strftime("%Y-%m-%d"),
                "returns": [
                    {
                        "ticker": ticker,
                        "name": labels[ticker],
                        "return_pct": round(float(end[ticker] / start[ticker] - 1.0) * 100.0, 3),
                    }
                    for ticker in columns
                ],
            }
        )
    return {
        "dates": [timestamp.strftime("%Y-%m-%d") for timestamp in normalized.index],
        "series": [
            {
                "ticker": ticker,
                "name": labels[ticker],
                "values": [round(float(value), 3) for value in normalized[ticker].tolist()],
                "return_pct": round(float(normalized[ticker].iloc[-1] - 100.0), 3),
            }
            for ticker in columns
        ],
        "start_date": normalized.index[0].strftime("%Y-%m-%d"),
        "end_date": normalized.index[-1].strftime("%Y-%m-%d"),
        "normalization": "first common close = 100",
        "window_returns": windows,
    }


def parse_tencent_kline(payload: dict[str, Any], symbol: str) -> pd.Series:
    bucket = (payload.get("data") or {}).get(symbol) or {}
    rows = bucket.get("qfqday") or bucket.get("day") or bucket.get("hfqday") or []
    if not rows:
        raise ValueError(f"Tencent Finance returned no daily rows for {symbol}.")
    dates = pd.to_datetime([row[0] for row in rows], errors="coerce")
    closes = pd.to_numeric([row[2] for row in rows], errors="coerce")
    series = pd.Series(closes, index=dates, name=symbol).dropna().sort_index()
    if series.empty:
        raise ValueError(f"Tencent Finance daily rows are invalid for {symbol}.")
    return series


def build_southbound_flow(frame: pd.DataFrame) -> dict[str, Any]:
    required = {"trade_date", "buy_amount", "sell_amount"}
    if not required <= set(frame.columns):
        raise ValueError(f"Southbound data missing fields: {sorted(required - set(frame.columns))}")
    data = frame[list(required)].copy()
    data["date"] = pd.to_datetime(data["trade_date"], format="%Y%m%d", errors="coerce")
    data["buy_amount"] = pd.to_numeric(data["buy_amount"], errors="coerce")
    data["sell_amount"] = pd.to_numeric(data["sell_amount"], errors="coerce")
    data = data.dropna().sort_values("date")
    data["net_amount"] = data["buy_amount"] - data["sell_amount"]
    data["cumulative_net_amount"] = data["net_amount"].cumsum()
    return {
        "dates": data["date"].dt.strftime("%Y-%m-%d").tolist(),
        "buy_amount": [round(float(value), 2) for value in data["buy_amount"]],
        "sell_amount": [round(float(value), 2) for value in data["sell_amount"]],
        "net_amount": [round(float(value), 2) for value in data["net_amount"]],
        "cumulative_net_amount": [round(float(value), 2) for value in data["cumulative_net_amount"]],
        "unit": "Tushare ggt_daily provider unit",
        "formula": "net_amount = buy_amount - sell_amount",
    }


def build_valuation_rows(
    info_by_ticker: dict[str, dict[str, Any]],
    pairs: list[dict[str, Any]],
    *,
    fetched_at: str,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    missing: list[dict[str, str]] = []
    for pair in pairs:
        company_ticker = str(pair["company"])
        peer_ticker = str(pair["peer"])
        company = info_by_ticker.get(company_ticker) or {}
        peer = info_by_ticker.get(peer_ticker) or {}
        company_forward = company.get("forwardPE")
        peer_forward = peer.get("forwardPE")
        for ticker, value in [(company_ticker, company_forward), (peer_ticker, peer_forward)]:
            if value is None:
                missing.append({"ticker": ticker, "field": "forwardPE"})
        ratio = None
        if company_forward is not None and peer_forward not in {None, 0}:
            ratio = round(float(company_forward) / float(peer_forward), 3)
        rows.append(
            {
                "label": str(pair.get("label") or f"{company_ticker} vs {peer_ticker}"),
                "company_ticker": company_ticker,
                "company_name": company.get("shortName") or company.get("longName") or company_ticker,
                "company_forward_pe": company_forward,
                "company_trailing_pe": company.get("trailingPE"),
                "company_currency": company.get("currency"),
                "peer_ticker": peer_ticker,
                "peer_name": peer.get("shortName") or peer.get("longName") or peer_ticker,
                "peer_forward_pe": peer_forward,
                "peer_trailing_pe": peer.get("trailingPE"),
                "peer_currency": peer.get("currency"),
                "forward_pe_ratio": ratio,
            }
        )
    return {
        "status": "ok" if not missing else "partial",
        "fetched_at": fetched_at,
        "provider": SOURCE_NAME,
        "metric_note": "forwardPE and trailingPE are provider fields captured in one collection run; definitions may differ from company filings.",
        "rows": rows,
        "missing": missing,
    }


def parse_eastmoney_quote(payload: dict[str, Any], secid: str) -> dict[str, Any]:
    data = payload.get("data") or {}
    if not data:
        raise ValueError(f"Eastmoney returned no quote data for {secid}.")
    scale = 10 ** int(data.get("f152") or 0)

    def scaled(field: str) -> float | None:
        value = data.get(field)
        if value in {None, "-", ""}:
            return None
        number = float(value) / scale
        return round(number, 4) if number > 0 else None

    price_raw = data.get("f43")
    price = None
    if price_raw not in {None, "-", ""}:
        market = secid.split(".", 1)[0]
        price_divisor = 1000 if market in {"105", "106", "116"} else scale
        price = round(float(price_raw) / price_divisor, 4)

    return {
        "secid": secid,
        "ticker": str(data.get("f57") or secid),
        "name": str(data.get("f58") or secid),
        "price": price,
        "pe_dynamic": scaled("f162"),
        "pe_static": scaled("f163"),
        "pe_ttm": scaled("f164"),
        "pb": scaled("f167"),
        "market_cap": data.get("f116"),
        "float_market_cap": data.get("f117"),
    }


def build_eastmoney_valuation_rows(
    quote_by_secid: dict[str, dict[str, Any]],
    pairs: list[dict[str, Any]],
    *,
    fetched_at: str,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    missing: list[dict[str, str]] = []
    for pair in pairs:
        company_secid = str(pair["company_secid"])
        peer_secid = str(pair["peer_secid"])
        company = quote_by_secid.get(company_secid) or {}
        peer = quote_by_secid.get(peer_secid) or {}
        company_pe = company.get("pe_ttm")
        peer_pe = peer.get("pe_ttm")
        for secid, value in [(company_secid, company_pe), (peer_secid, peer_pe)]:
            if value is None:
                missing.append({"secid": secid, "field": "pe_ttm"})
        ratio = None
        if company_pe is not None and peer_pe not in {None, 0}:
            ratio = round(float(company_pe) / float(peer_pe), 3)
        rows.append(
            {
                "label": str(pair.get("label") or f"{company_secid} vs {peer_secid}"),
                "company_secid": company_secid,
                "company_ticker": company.get("ticker") or company_secid,
                "company_name": company.get("name") or company_secid,
                "company_pe_ttm": company_pe,
                "peer_secid": peer_secid,
                "peer_ticker": peer.get("ticker") or peer_secid,
                "peer_name": peer.get("name") or peer_secid,
                "peer_pe_ttm": peer_pe,
                "pe_ttm_ratio": ratio,
            }
        )
    return {
        "status": "ok" if not missing else "partial",
        "fetched_at": fetched_at,
        "provider": EASTMONEY_SOURCE_NAME,
        "metric": "PE (TTM)",
        "metric_note": "f164 PE (TTM), captured from the same provider in one collection run; PE is unitless.",
        "rows": rows,
        "missing": missing,
        "quotes": quote_by_secid,
    }


def claim_evidence_item(
    asset: dict[str, Any],
    *,
    rows: list[str] | None = None,
    verdict: str = "neutral",
) -> dict[str, Any]:
    return {
        "asset_id": asset["id"],
        "relation": "direct" if asset.get("status") == "ok" else "context",
        "verdict": verdict,
        "authenticity": "real_data" if asset.get("status") == "ok" else "user_claim_card",
        "source_locator": {
            "kind": "machine_readable_finance_dataset",
            "json_path": asset.get("json_path"),
            "csv_path": asset.get("csv_path"),
            "rows": rows or [],
            "provider": asset.get("source") or SOURCE_NAME,
            "fetched_at": asset.get("fetched_at"),
        },
        "confidence": "medium" if asset.get("status") == "ok" else "low",
        "claim_text": asset.get("title") or asset["id"],
    }


def _download_close(tickers: list[str], *, period: str, interval: str) -> pd.DataFrame:
    import yfinance as yf

    raw = yf.download(
        tickers=tickers,
        period=period,
        interval=interval,
        auto_adjust=True,
        progress=False,
        threads=False,
        group_by="column",
    )
    if raw.empty:
        raise RuntimeError("yfinance returned no price history.")
    if isinstance(raw.columns, pd.MultiIndex):
        if "Close" not in raw.columns.get_level_values(0):
            raise RuntimeError("yfinance response has no Close field.")
        close = raw["Close"]
    else:
        if "Close" not in raw.columns:
            raise RuntimeError("yfinance response has no Close field.")
        close = raw[["Close"]]
        close.columns = tickers[:1]
    if isinstance(close, pd.Series):
        close = close.to_frame(name=tickers[0])
    close.index = pd.to_datetime(close.index).tz_localize(None)
    return close


def _download_info(tickers: list[str]) -> dict[str, dict[str, Any]]:
    import yfinance as yf

    output: dict[str, dict[str, Any]] = {}
    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).info or {}
        except Exception as exc:  # pragma: no cover - network failure path
            info = {"fetch_error": str(exc)}
        output[ticker] = {
            key: info.get(key)
            for key in ["shortName", "longName", "forwardPE", "trailingPE", "currency", "marketCap", "quoteType"]
        }
        if info.get("fetch_error"):
            output[ticker]["fetch_error"] = info["fetch_error"]
    return output


def _download_eastmoney_info(secids: list[str]) -> dict[str, dict[str, Any]]:
    import requests

    session = requests.Session()
    output: dict[str, dict[str, Any]] = {}
    fields = "f43,f57,f58,f116,f117,f152,f162,f163,f164,f167"
    for secid in secids:
        response = session.get(
            "https://push2delay.eastmoney.com/api/qt/stock/get",
            params={"secid": secid, "fields": fields},
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://quote.eastmoney.com/"},
            timeout=20,
        )
        response.raise_for_status()
        output[secid] = parse_eastmoney_quote(response.json(), secid)
    return output


def _download_tencent_series(symbol: str, *, count: int) -> pd.Series:
    import requests

    url = "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"
    response = requests.get(
        url,
        params={"param": f"{symbol},day,,,{count},qfq"},
        headers={"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"},
        timeout=20,
    )
    response.raise_for_status()
    return parse_tencent_kline(response.json(), symbol)


def _download_tushare_global(symbol: str, *, start_date: str, end_date: str) -> pd.Series:
    import tushare as ts

    token = os.environ.get("TUSHARE_TOKEN")
    if not token:
        raise RuntimeError("TUSHARE_TOKEN is not configured.")
    frame = ts.pro_api(token).index_global(ts_code=symbol, start_date=start_date, end_date=end_date)
    if frame.empty:
        raise RuntimeError(f"Tushare returned no global index data for {symbol}.")
    dates = pd.to_datetime(frame["trade_date"], format="%Y%m%d", errors="coerce")
    closes = pd.to_numeric(frame["close"], errors="coerce")
    return pd.Series(closes.values, index=dates, name=symbol).dropna().sort_index()


def _download_southbound(*, start_date: str, end_date: str) -> pd.DataFrame:
    import tushare as ts

    token = os.environ.get("TUSHARE_TOKEN")
    if not token:
        raise RuntimeError("TUSHARE_TOKEN is not configured.")
    frame = ts.pro_api(token).ggt_daily(start_date=start_date, end_date=end_date)
    if frame.empty:
        raise RuntimeError("Tushare returned no southbound trading data.")
    return frame


def _render_relative_chart(payload: dict[str, Any], output: Path, title: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.style.use("seaborn-v0_8-whitegrid")
    configure_matplotlib_font()
    fig, ax = plt.subplots(figsize=(14, 7.5), dpi=160)
    dates = pd.to_datetime(payload["dates"])
    colors = ["#0d766e", "#d65c45", "#396b88", "#c6933a"]
    for index, series in enumerate(payload["series"]):
        ax.plot(dates, series["values"], linewidth=2.8, label=series["name"], color=colors[index % len(colors)])
        ax.annotate(
            f"{series['return_pct']:+.1f}%",
            (dates[-1], series["values"][-1]),
            xytext=(8, 0),
            textcoords="offset points",
            color=colors[index % len(colors)],
            fontsize=10,
            fontweight="bold",
        )
    ax.axhline(100, color="#67716d", linewidth=1, alpha=0.55)
    ax.set_title(title, loc="left", fontsize=18, fontweight="bold", pad=16)
    ax.set_ylabel("Normalized close (first common date = 100)")
    ax.legend(frameon=False, ncol=min(4, len(payload["series"])), loc="upper left")
    ax.spines[["top", "right"]].set_visible(False)
    fig.autofmt_xdate()
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, bbox_inches="tight", facecolor="#f5f2e9")
    plt.close(fig)


def _render_valuation_chart(payload: dict[str, Any], output: Path, title: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    configure_matplotlib_font()
    import matplotlib.pyplot as plt
    import numpy as np

    use_ttm = payload.get("metric") == "PE (TTM)"
    company_key = "company_pe_ttm" if use_ttm else "company_forward_pe"
    peer_key = "peer_pe_ttm" if use_ttm else "peer_forward_pe"
    rows = [row for row in payload["rows"] if row.get(company_key) is not None and row.get(peer_key) is not None]
    fig, ax = plt.subplots(figsize=(13, 7.5), dpi=160)
    if rows:
        positions = np.arange(len(rows))
        width = 0.34
        company_values = [row[company_key] for row in rows]
        peer_values = [row[peer_key] for row in rows]
        company_bars = ax.barh(positions - width / 2, company_values, height=width, color="#0d766e", label="港股公司")
        peer_bars = ax.barh(positions + width / 2, peer_values, height=width, color="#d65c45", label="美股可比")
        ax.set_yticks(positions, [row["label"] for row in rows])
        ax.invert_yaxis()
        ax.legend(frameon=False)
        for bar, value in [*(zip(company_bars, company_values)), *(zip(peer_bars, peer_values))]:
            ax.text(
                bar.get_width() + max(peer_values) * 0.012,
                bar.get_y() + bar.get_height() / 2,
                f"{value:.1f}x",
                va="center",
                fontsize=10,
                fontweight="bold",
                color="#303834",
            )
    else:
        ax.text(0.5, 0.5, "No complete forward PE pairs", ha="center", va="center", transform=ax.transAxes)
    ax.set_title(title, loc="left", fontsize=18, fontweight="bold", pad=16)
    ax.set_xlabel("市盈率（TTM，倍）" if use_ttm else "Forward PE (provider field)")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, bbox_inches="tight", facecolor="#f5f2e9")
    plt.close(fig)


def _render_southbound_chart(payload: dict[str, Any], output: Path, title: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    configure_matplotlib_font()
    import matplotlib.pyplot as plt

    dates = pd.to_datetime(payload["dates"])
    fig, (ax_top, ax_bottom) = plt.subplots(2, 1, figsize=(14, 8), dpi=160, sharex=True, gridspec_kw={"height_ratios": [1.1, 1]})
    colors = ["#0d766e" if value >= 0 else "#d65c45" for value in payload["net_amount"]]
    ax_top.bar(dates, payload["net_amount"], color=colors, width=0.75)
    ax_top.axhline(0, color="#67716d", linewidth=1)
    ax_top.set_ylabel("Daily net")
    ax_top.set_title(title, loc="left", fontsize=18, fontweight="bold", pad=16)
    ax_bottom.plot(dates, payload["cumulative_net_amount"], color="#396b88", linewidth=2.8)
    ax_bottom.fill_between(dates, payload["cumulative_net_amount"], 0, color="#396b88", alpha=0.14)
    ax_bottom.axhline(0, color="#67716d", linewidth=1)
    ax_bottom.set_ylabel("Cumulative net")
    for axis in [ax_top, ax_bottom]:
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="y", alpha=0.2)
    fig.autofmt_xdate()
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, bbox_inches="tight", facecolor="#f5f2e9")
    plt.close(fig)


def build_asset(request: dict[str, Any], output_dir: Path, fetched_at: str) -> dict[str, Any]:
    asset_id = str(request["id"])
    kind = str(request["kind"])
    asset_dir = output_dir / asset_id
    asset_dir.mkdir(parents=True, exist_ok=True)
    json_path = asset_dir / f"{asset_id}.json"
    csv_path = asset_dir / f"{asset_id}.csv"
    png_path = asset_dir / f"{asset_id}.png"

    if kind == "relative_performance":
        labels = {str(key): str(value) for key, value in (request.get("tickers") or {}).items()}
        prices = _download_close(list(labels), period=str(request.get("period") or "3mo"), interval=str(request.get("interval") or "1d"))
        payload = build_relative_series(
            prices,
            labels,
            window_sessions=[int(value) for value in request.get("window_sessions") or []],
        )
        payload.update({"asset_id": asset_id, "fetched_at": fetched_at, "provider": SOURCE_NAME})
        normalized = pd.DataFrame(
            {series["name"]: series["values"] for series in payload["series"]},
            index=payload["dates"],
        )
        normalized.to_csv(csv_path, encoding="utf-8-sig", index_label="date")
        _render_relative_chart(payload, png_path, str(request.get("title") or asset_id))
        status = "ok"
        source = SOURCE_NAME
    elif kind == "relative_performance_mixed":
        request_series = list(request.get("series") or [])
        collected: list[pd.Series] = []
        labels: dict[str, str] = {}
        start_date = str(request.get("start_date") or "")
        end_date = str(request.get("end_date") or "")
        for item in request_series:
            symbol = str(item["symbol"])
            provider = str(item["provider"])
            labels[symbol] = str(item.get("label") or symbol)
            if provider == "tencent":
                collected.append(_download_tencent_series(symbol, count=int(request.get("count") or 100)))
            elif provider == "tushare_global":
                collected.append(_download_tushare_global(symbol, start_date=start_date, end_date=end_date))
            else:
                raise ValueError(f"Unsupported mixed-series provider: {provider}")
        prices = pd.concat(collected, axis=1)
        payload = build_relative_series(
            prices,
            labels,
            window_sessions=[int(value) for value in request.get("window_sessions") or []],
        )
        payload.update(
            {
                "asset_id": asset_id,
                "fetched_at": fetched_at,
                "provider": "Tencent Finance K-line + Tushare Pro index_global",
                "series_sources": request_series,
            }
        )
        pd.DataFrame(
            {series["name"]: series["values"] for series in payload["series"]},
            index=payload["dates"],
        ).to_csv(csv_path, encoding="utf-8-sig", index_label="date")
        _render_relative_chart(payload, png_path, str(request.get("title") or asset_id))
        status = "ok"
        source = payload["provider"]
    elif kind == "southbound_flow":
        payload = build_southbound_flow(
            _download_southbound(
                start_date=str(request.get("start_date") or ""),
                end_date=str(request.get("end_date") or ""),
            )
        )
        payload.update(
            {
                "asset_id": asset_id,
                "fetched_at": fetched_at,
                "provider": "Tushare Pro ggt_daily",
            }
        )
        pd.DataFrame(
            {
                "date": payload["dates"],
                "buy_amount": payload["buy_amount"],
                "sell_amount": payload["sell_amount"],
                "net_amount": payload["net_amount"],
                "cumulative_net_amount": payload["cumulative_net_amount"],
            }
        ).to_csv(csv_path, encoding="utf-8-sig", index=False)
        _render_southbound_chart(payload, png_path, str(request.get("title") or asset_id))
        status = "ok"
        source = payload["provider"]
    elif kind == "valuation_comparison":
        pairs = list(request.get("pairs") or [])
        tickers = sorted({str(item[key]) for item in pairs for key in ["company", "peer"]})
        payload = build_valuation_rows(_download_info(tickers), pairs, fetched_at=fetched_at)
        pd.DataFrame(payload["rows"]).to_csv(csv_path, encoding="utf-8-sig", index=False)
        _render_valuation_chart(payload, png_path, str(request.get("title") or asset_id))
        status = payload["status"]
        source = SOURCE_NAME
    elif kind == "valuation_comparison_eastmoney":
        pairs = list(request.get("pairs") or [])
        secids = sorted({str(item[key]) for item in pairs for key in ["company_secid", "peer_secid"]})
        payload = build_eastmoney_valuation_rows(_download_eastmoney_info(secids), pairs, fetched_at=fetched_at)
        pd.DataFrame(payload["rows"]).to_csv(csv_path, encoding="utf-8-sig", index=False)
        _render_valuation_chart(payload, png_path, str(request.get("title") or asset_id))
        status = payload["status"]
        source = EASTMONEY_SOURCE_NAME
    else:
        raise ValueError(f"Unsupported finance evidence kind: {kind}")

    write_json(json_path, payload)
    return {
        "id": asset_id,
        "title": str(request.get("title") or asset_id),
        "kind": kind,
        "status": status,
        "source": source,
        "fetched_at": fetched_at,
        "json_path": str(json_path),
        "csv_path": str(csv_path),
        "png_path": str(png_path),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build market and valuation evidence for video claims.")
    parser.add_argument("--request", required=True)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    request_path = Path(args.request).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    request = read_json(request_path)
    fetched_at = datetime.now().astimezone().isoformat(timespec="seconds")
    assets: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for item in request.get("assets") or []:
        try:
            assets.append(build_asset(item, output_dir, fetched_at))
        except Exception as exc:  # pragma: no cover - network failure path
            failures.append({"id": str(item.get("id") or "unknown"), "error": str(exc)})
    manifest = {
        "schema_version": "dasheng.video.finance_evidence_manifest.v1",
        "created_at": fetched_at,
        "provider": "multiple" if len({asset["source"] for asset in assets}) > 1 else (assets[0]["source"] if assets else SOURCE_NAME),
        "providers": sorted({asset["source"] for asset in assets}),
        "request": str(request_path),
        "status": "pass" if not failures else "partial" if assets else "fail",
        "assets": assets,
        "claim_evidence_items": [claim_evidence_item(asset) for asset in assets],
        "failures": failures,
    }
    write_json(output_dir / "finance_evidence_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if assets else 1


if __name__ == "__main__":
    raise SystemExit(main())
