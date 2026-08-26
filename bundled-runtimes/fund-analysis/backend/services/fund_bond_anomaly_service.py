"""基于真实净值和标准化同类组监控债基异常波动。"""

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


class FundBondAnomalyService:
    ROLLING_DAYS = 26
    NAV_BAND_SIGMA = 2.0
    MARKET_BAND_SIGMA = 1.0
    PEER_OUTLIER_SIGMA = 3.0
    MINIMUM_OBSERVATIONS = 52
    SOURCE = "local.postgres.fund_nav+standardized_peer_group"
    REFERENCE_URL = "https://www.jigouyun.com.cn/#/toolcabinet/lof-abnormal-monitoring"
    LIMITATIONS = [
        "本地同类指数由标准化同类组基金日收益等权合成，不是基构云或第三方发布的官方指数。",
        "净值异常只表示相对自身历史或同类的异常下跌，不判断原因，也不构成投资建议。",
        "异常监控只用于解释和复核，不参与基金评分。",
    ]

    def __init__(
        self,
        fund_repo: Optional[Any] = None,
        nav_repo: Optional[Any] = None,
        classification_repo: Optional[Any] = None,
    ):
        if fund_repo is None or nav_repo is None or classification_repo is None:
            from repositories import get_fund_classification_repo, get_fund_repo, get_nav_repo

            fund_repo = fund_repo or get_fund_repo()
            nav_repo = nav_repo or get_nav_repo()
            classification_repo = classification_repo or get_fund_classification_repo()
        self.fund_repo = fund_repo
        self.nav_repo = nav_repo
        self.classification_repo = classification_repo

    def analyze(self, wind_code: str, window_days: int = 252) -> Dict[str, Any]:
        window_days = max(126, min(int(window_days or 252), 756))
        fund = self.fund_repo.get_fund_by_identifier(wind_code)
        if not fund:
            raise ValueError(f"Fund not found: {wind_code}")
        code = str(fund.get("wind_code") or wind_code)
        if not self._is_bond_fund(fund):
            return self._base(code, window_days, "not_applicable", ["当前只监控债券型基金"])

        target_levels, nav_basis = self._levels(self.nav_repo.get_nav_series(code))
        if len(target_levels) < self.MINIMUM_OBSERVATIONS:
            return self._base(
                code,
                window_days,
                "insufficient_evidence",
                [f"基金净值只有 {len(target_levels)} 个观测，至少需要 {self.MINIMUM_OBSERVATIONS} 个"],
                nav_basis=nav_basis,
            )

        target_levels = target_levels.tail(window_days + self.ROLLING_DAYS + 10)
        classification = self.classification_repo.get_classification_context(code)
        peer_group_id = str(classification.get("peer_group_id") or "")
        minimum_peer_count = max(5, int(classification.get("minimum_peer_count") or 5))
        peer_rows = self.classification_repo.list_peer_nav_series(
            peer_group_id,
            target_levels.index.min().date().isoformat(),
            target_levels.index.max().date().isoformat(),
        ) if peer_group_id else []
        peer_returns, peer_nav_basis = self._peer_returns(peer_rows, exclude_code=code)

        result = self._analyze_series(
            target_levels,
            peer_returns,
            minimum_peer_count=minimum_peer_count,
            window_days=window_days,
        )
        peer_fund_count = int(peer_returns.shape[1]) if not peer_returns.empty else 0
        missing_items = list(result.pop("missing_items"))
        if not peer_group_id:
            missing_items.append("基金尚未进入标准化同类组，无法运行债市调整期同类异常门槛")
        elif peer_fund_count < minimum_peer_count:
            missing_items.append(f"同类净值有效基金只有 {peer_fund_count} 只，至少需要 {minimum_peer_count} 只")

        return {
            "wind_code": code,
            "status": "available",
            "window_days": window_days,
            "nav_basis": nav_basis,
            "as_of_date": target_levels.index.max().date().isoformat(),
            "data_start": result["data_start"],
            "data_end": result["data_end"],
            "observations": result["observations"],
            "current_signal": result["current_signal"],
            "current_label": self._signal_label(result["current_signal"]),
            "daily_return": result["daily_return"],
            "weekly_return": result["weekly_return"],
            "market_regime": result["market_regime"],
            "market_regime_label": "同类债市调整" if result["market_regime"] == "adjustment" else "同类债市正常",
            "anomaly_counts": result["anomaly_counts"],
            "events": result["events"],
            "chart": result["chart"],
            "peer_group_id": peer_group_id,
            "peer_group_name": classification.get("peer_group_name") or classification.get("peer_group_key"),
            "peer_fund_count": peer_fund_count,
            "minimum_peer_count": minimum_peer_count,
            "peer_model_ready": peer_fund_count >= minimum_peer_count,
            "peer_nav_basis": peer_nav_basis,
            "methodology": {
                "reference": "基构云公开债基异常监控模型",
                "routine_monitor": "基金净值低于过去 26 个净值日均值减 2 倍标准差",
                "market_adjustment": "本地标准化同类基金等权指数低于过去 26 个交易日均值减 1 倍标准差",
                "adjustment_monitor": "调整期内基金日收益低于同类日收益均值减 3 倍标准差",
            },
            "source": self.SOURCE,
            "source_url": self.REFERENCE_URL,
            "missing_items": missing_items,
            "limitations": self.LIMITATIONS,
            "formal_monitor_ready": len(target_levels) >= self.MINIMUM_OBSERVATIONS and peer_fund_count >= minimum_peer_count,
        }

    def _analyze_series(
        self,
        target_levels: pd.Series,
        peer_returns: pd.DataFrame,
        minimum_peer_count: int,
        window_days: int,
    ) -> Dict[str, Any]:
        target = target_levels.sort_index().astype(float)
        target_return = target.pct_change(fill_method=None)
        prior_mean = target.shift(1).rolling(self.ROLLING_DAYS, min_periods=self.ROLLING_DAYS).mean()
        prior_std = target.shift(1).rolling(self.ROLLING_DAYS, min_periods=self.ROLLING_DAYS).std(ddof=0)
        lower_band = prior_mean - self.NAV_BAND_SIGMA * prior_std
        routine_anomaly = target < lower_band

        peer_mean = pd.Series(index=target.index, dtype=float)
        peer_std = pd.Series(index=target.index, dtype=float)
        peer_count = pd.Series(0, index=target.index, dtype=int)
        peer_index = pd.Series(index=target.index, dtype=float)
        market_lower = pd.Series(index=target.index, dtype=float)
        market_adjustment = pd.Series(False, index=target.index, dtype=bool)
        peer_threshold = pd.Series(index=target.index, dtype=float)

        if not peer_returns.empty:
            aligned = peer_returns.reindex(target.index)
            peer_count = aligned.count(axis=1)
            peer_mean = aligned.mean(axis=1, skipna=True)
            peer_std = aligned.std(axis=1, ddof=0, skipna=True)
            eligible_return = peer_mean.where(peer_count >= minimum_peer_count).dropna()
            eligible_index = (1 + eligible_return).cumprod()
            eligible_mean = eligible_index.shift(1).rolling(self.ROLLING_DAYS, min_periods=self.ROLLING_DAYS).mean()
            eligible_std = eligible_index.shift(1).rolling(self.ROLLING_DAYS, min_periods=self.ROLLING_DAYS).std(ddof=0)
            eligible_lower = eligible_mean - self.MARKET_BAND_SIGMA * eligible_std
            peer_index = eligible_index.reindex(target.index)
            market_lower = eligible_lower.reindex(target.index)
            market_adjustment = (eligible_index < eligible_lower).reindex(target.index, fill_value=False)
            peer_threshold = peer_mean - self.PEER_OUTLIER_SIGMA * peer_std

        peer_outlier = (
            market_adjustment
            & (peer_count >= minimum_peer_count)
            & (target_return < peer_threshold)
        ).fillna(False)
        anomaly = routine_anomaly.fillna(False) | peer_outlier
        frame = pd.DataFrame({
            "nav": target,
            "daily_return": target_return,
            "center": prior_mean,
            "lower_band": lower_band,
            "routine_anomaly": routine_anomaly.fillna(False),
            "peer_mean": peer_mean,
            "peer_std": peer_std,
            "peer_count": peer_count,
            "peer_threshold": peer_threshold,
            "peer_index": peer_index,
            "market_lower": market_lower,
            "market_adjustment": market_adjustment.fillna(False),
            "peer_outlier": peer_outlier,
            "anomaly": anomaly,
        }).tail(window_days)

        events = []
        for event_date, row in frame[frame["anomaly"]].tail(30).sort_index(ascending=False).iterrows():
            reasons = []
            if bool(row["routine_anomaly"]):
                reasons.append("净值跌破26日下轨")
            if bool(row["peer_outlier"]):
                reasons.append("债市调整期显著弱于同类")
            events.append({
                "date": event_date.date().isoformat(),
                "reason": "；".join(reasons),
                "nav": self._round(row["nav"], 6),
                "daily_return": self._round(row["daily_return"], 8),
                "lower_band": self._round(row["lower_band"], 6),
                "peer_mean_return": self._round(row["peer_mean"], 8),
                "peer_threshold_return": self._round(row["peer_threshold"], 8),
                "peer_count": int(row["peer_count"] or 0),
                "market_adjustment": bool(row["market_adjustment"]),
            })

        latest_index = frame.index[-1]
        latest_is_anomaly = bool(frame.iloc[-1]["anomaly"])
        recent_is_anomaly = bool(frame["anomaly"].tail(5).any())
        current_signal = "abnormal" if latest_is_anomaly else "recent_abnormal" if recent_is_anomaly else "normal"
        valid_market = frame["market_adjustment"].dropna()
        market_regime = "adjustment" if len(valid_market) and bool(valid_market.iloc[-1]) else "normal"

        first_nav = float(frame["nav"].dropna().iloc[0])
        valid_peer_index = frame["peer_index"].dropna()
        first_peer_index = float(valid_peer_index.iloc[0]) if len(valid_peer_index) else None
        chart = []
        for chart_date, row in frame.tail(160).iterrows():
            chart.append({
                "date": chart_date.date().isoformat(),
                "nav_index": self._round(float(row["nav"]) / first_nav * 100, 4),
                "lower_band_index": self._round(float(row["lower_band"]) / first_nav * 100, 4),
                "peer_index": self._round(float(row["peer_index"]) / first_peer_index * 100, 4) if first_peer_index and pd.notna(row["peer_index"]) else None,
                "anomaly": bool(row["anomaly"]),
                "market_adjustment": bool(row["market_adjustment"]),
            })

        counts = {}
        for key, days in (("today", 1), ("week", 5), ("month", 22), ("quarter", 66), ("half_year", 132), ("year", 252)):
            counts[key] = int(frame["anomaly"].tail(days).sum())

        return {
            "data_start": frame.index.min().date().isoformat(),
            "data_end": latest_index.date().isoformat(),
            "observations": len(frame),
            "current_signal": current_signal,
            "daily_return": self._round(frame.iloc[-1]["daily_return"], 8),
            "weekly_return": self._round(target.tail(6).iloc[-1] / target.tail(6).iloc[0] - 1, 8) if len(target) >= 6 else None,
            "market_regime": market_regime,
            "anomaly_counts": counts,
            "events": events,
            "chart": chart,
            "missing_items": [] if len(peer_returns.columns) >= minimum_peer_count else ["同类调整期模型证据不足，当前仍可使用基金自身26日下轨监控"],
        }

    @staticmethod
    def _levels(rows: List[Dict[str, Any]]) -> Tuple[pd.Series, str]:
        accum_count = sum(row.get("accum_nav") is not None for row in rows)
        nav_basis = "accum_nav" if accum_count >= 2 else "unit_nav"
        values = {}
        for row in rows:
            raw = row.get("accum_nav") if nav_basis == "accum_nav" else (row.get("nav") or row.get("unit_nav"))
            try:
                value = float(raw)
                item_date = pd.Timestamp(str(row.get("date") or row.get("trade_date"))[:10])
            except (TypeError, ValueError):
                continue
            if value > 0:
                values[item_date] = value
        return pd.Series(values, dtype=float).sort_index(), nav_basis

    def _peer_returns(self, rows: List[Dict[str, Any]], exclude_code: str) -> Tuple[pd.DataFrame, Dict[str, str]]:
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            code = str(row.get("wind_code") or "")
            if code and code != exclude_code:
                grouped.setdefault(code, []).append(row)
        series = {}
        basis = {}
        for code, items in grouped.items():
            levels, nav_basis = self._levels(items)
            if len(levels) >= self.ROLLING_DAYS:
                series[code] = levels.pct_change(fill_method=None)
                basis[code] = nav_basis
        return (pd.concat(series, axis=1) if series else pd.DataFrame()), basis

    def _base(
        self,
        wind_code: str,
        window_days: int,
        status: str,
        missing_items: List[str],
        nav_basis: str = "",
    ) -> Dict[str, Any]:
        return {
            "wind_code": wind_code,
            "status": status,
            "window_days": window_days,
            "nav_basis": nav_basis,
            "current_signal": "unavailable",
            "current_label": "暂不可用",
            "daily_return": None,
            "weekly_return": None,
            "market_regime": "unknown",
            "market_regime_label": "同类债市状态未知",
            "anomaly_counts": {},
            "events": [],
            "chart": [],
            "peer_model_ready": False,
            "formal_monitor_ready": False,
            "source": self.SOURCE,
            "source_url": self.REFERENCE_URL,
            "missing_items": missing_items,
            "limitations": self.LIMITATIONS,
        }

    @staticmethod
    def _is_bond_fund(fund: Dict[str, Any]) -> bool:
        value = f"{fund.get('type') or ''} {fund.get('name') or ''}".lower()
        return "债" in value or "bond" in value

    @staticmethod
    def _signal_label(value: str) -> str:
        return {"abnormal": "今日触发异常", "recent_abnormal": "近1周曾触发", "normal": "当前正常"}.get(value, "暂不可用")

    @staticmethod
    def _round(value: Any, digits: int) -> Optional[float]:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return round(parsed, digits) if np.isfinite(parsed) else None
