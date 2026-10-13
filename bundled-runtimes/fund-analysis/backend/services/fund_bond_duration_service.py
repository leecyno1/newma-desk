"""基于真实中债分期限财富指数估算债基久期。"""

import math
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.cluster import KMeans

from services.chinabond_index_service import ChinaBondIndexService
from services.bond_nav_series import positive_levels, weekly_endpoints, returns_at_endpoints


class FundBondDurationService:
    METHODOLOGY_VERSION = "jigouyun_public_rbsa_adj_endpoints_v3"
    MINIMUM_WEEKS = 52
    SOURCE = "local.postgres.fund_nav+chinabond.index"
    GROUP_ORDER = ["policy_bank", "credit", "short_financing", "interbank_cd"]
    LIMITATIONS = [
        "这是基于净值收益的估算久期，不是基金披露的组合久期。",
        "可转债、股票、杠杆和信用利差变化会进入回归残差；拟合度低时不可作强结论。",
        "久期结果只用于解释基金风险来源，不参与基金评分。",
    ]

    def __init__(
        self,
        repo: Optional[Any] = None,
        nav_repo: Optional[Any] = None,
        fund_repo: Optional[Any] = None,
        index_service: Optional[ChinaBondIndexService] = None,
    ):
        if repo is None or nav_repo is None or fund_repo is None:
            from repositories import get_bond_duration_repo, get_fund_repo, get_nav_repo

            repo = repo or get_bond_duration_repo()
            nav_repo = nav_repo or get_nav_repo()
            fund_repo = fund_repo or get_fund_repo()
        self.repo = repo
        self.nav_repo = nav_repo
        self.fund_repo = fund_repo
        self.index_service = index_service or ChinaBondIndexService(repo=repo)

    def get(self, wind_code: str, window_weeks: int = 104) -> Dict[str, Any]:
        window_weeks = self._window(window_weeks)
        fund = self.fund_repo.get_fund_by_identifier(wind_code)
        if not fund:
            raise ValueError(f"Fund not found: {wind_code}")
        if not self._is_bond_fund(fund):
            return self._base_response(
                wind_code,
                window_weeks,
                status="not_applicable",
                missing_items=["当前只对债券型基金估算久期"],
            )
        latest = self.repo.latest_estimate(str(fund.get("wind_code") or wind_code), window_weeks)
        if latest:
            if latest.get("methodology_version") != self.METHODOLOGY_VERSION:
                return self._base_response(
                    str(fund.get("wind_code") or wind_code), window_weeks, "not_run",
                    ["已有久期缓存使用旧净值口径，请重新现场测算；旧结果不作为当前风险证据"],
                )
            return self._decorate({**latest, "index_inventory": self.repo.index_inventory()})
        inventory = self.repo.index_inventory()
        return self._base_response(
            str(fund.get("wind_code") or wind_code),
            window_weeks,
            status="not_run",
            missing_items=[] if inventory.get("status") == "ready" else ["中债分期限指数尚未同步；首次现场测算会自动同步"],
            index_inventory=inventory,
        )

    def calculate(self, wind_code: str, window_weeks: int = 104, refresh_indices: bool = False) -> Dict[str, Any]:
        window_weeks = self._window(window_weeks)
        fund = self.fund_repo.get_fund_by_identifier(wind_code)
        if not fund:
            raise ValueError(f"Fund not found: {wind_code}")
        code = str(fund.get("wind_code") or wind_code)
        if not self._is_bond_fund(fund):
            return self._base_response(code, window_weeks, "not_applicable", ["当前只对债券型基金估算久期"])

        fund_levels = positive_levels(self.nav_repo.get_nav_series(code))
        fund_weekly = self._weekly_returns(fund_levels)
        nav_basis = "adj_nav"
        if len(fund_weekly) < self.MINIMUM_WEEKS:
            return self._base_response(
                code,
                window_weeks,
                "insufficient_evidence",
                [f"有效复权净值周收益只有 {len(fund_weekly)} 个观测，至少需要 {self.MINIMUM_WEEKS} 个；不以累计或单位净值补齐"],
            )

        if refresh_indices:
            self.index_service.sync()
            inventory = self.repo.index_inventory()
        else:
            inventory = self.index_service.ensure_local_data()
        if inventory.get("status") != "ready":
            return self._base_response(code, window_weeks, "insufficient_evidence",
                inventory.get("missing_items") or ["中债分期限指数或久期数据仍不完整，请核对数据源后重试"], index_inventory=inventory)

        end_date = fund_weekly.index.max().date().isoformat()
        start_date = (fund_weekly.index.max().date() - timedelta(days=window_weeks * 10)).isoformat()
        definitions = ChinaBondIndexService.definitions()
        definition_map = {item["series_key"]: item for item in definitions}
        wealth_rows = self.repo.list_index_series(list(definition_map), "wealth", start_date, end_date)
        endpoints = weekly_endpoints(fund_levels)
        weekly_by_key = {
            key: returns_at_endpoints(self._series(rows), endpoints)
            for key, rows in wealth_rows.items()
            if rows
        }

        selected = []
        group_diagnostics = []
        for group in self.GROUP_ORDER:
            candidates = [item for item in definitions if item["index_group"] == group]
            selection, diagnostics = self._select_group(fund_weekly, candidates, weekly_by_key, window_weeks)
            if not selection:
                return self._base_response(
                    code,
                    window_weeks,
                    "insufficient_evidence",
                    [f"{ChinaBondIndexService.GROUP_LABELS[group]}指数与基金的重叠周收益不足"],
                )
            selected.append(selection)
            group_diagnostics.append(diagnostics)

        selected_keys = [item["series_key"] for item in selected]
        final_frame = pd.concat(
            [fund_weekly.rename("fund"), *[weekly_by_key[key].rename(key) for key in selected_keys]],
            axis=1,
        ).dropna().tail(window_weeks)
        if len(final_frame) < self.MINIMUM_WEEKS:
            return self._base_response(
                code,
                window_weeks,
                "insufficient_evidence",
                [f"基金与四组指数共同周收益只有 {len(final_frame)} 个观测"],
            )

        weights, r_squared, tracking_error = self._style_regression(
            final_frame["fund"].to_numpy(),
            final_frame[selected_keys].to_numpy(),
        )
        actual_end = endpoints.loc[final_frame.index[-1]].date().isoformat()
        duration_values = self.repo.latest_indicator_values(selected_keys, "duration", actual_end)
        if len(duration_values) != len(selected_keys):
            return self._base_response(code, window_weeks, "insufficient_evidence", ["所选期限指数缺少同期平均市值法久期"])

        weight_rows = []
        estimated_duration = 0.0
        selected_rows = []
        for index, key in enumerate(selected_keys):
            definition = definition_map[key]
            duration_row = duration_values[key]
            duration_date = date.fromisoformat(str(duration_row["trade_date"])[:10])
            if (date.fromisoformat(actual_end) - duration_date).days > 7:
                return self._base_response(code, window_weeks, "insufficient_evidence", [f"{definition['group_label']}·{definition['period_label']} 久期截至 {duration_date}，与净值观测日相差超过7日"])
            try:
                duration = float(duration_row["value"])
            except (TypeError, ValueError):
                duration = np.nan
            if not np.isfinite(duration) or duration < 0:
                return self._base_response(code, window_weeks, "insufficient_evidence", ["所选指数久期无效，不能形成估算"])
            weight = float(weights[index])
            contribution = weight * duration
            estimated_duration += contribution
            selected_rows.append({
                "series_key": key,
                "index_group": definition["index_group"],
                "group_label": definition["group_label"],
                "index_name": definition["index_name"],
                "period_code": definition["period_code"],
                "period_label": definition["period_label"],
                "selection_r_squared": selected[index]["selection_r_squared"],
                "duration_as_of": duration_row["trade_date"],
            })
            weight_rows.append({
                "series_key": key,
                "group_label": definition["group_label"],
                "period_label": definition["period_label"],
                "weight": round(weight, 8),
                "index_duration": round(duration, 6),
                "duration_contribution": round(contribution, 6),
            })

        as_of_date = actual_end
        low_fit = r_squared < 0.45
        row = {
            "wind_code": code,
            "as_of_date": as_of_date,
            "window_weeks": window_weeks,
            "data_start": endpoints.shift(1).loc[final_frame.index[0]].date().isoformat(),
            "data_end": as_of_date,
            "observations": len(final_frame),
            "estimated_duration": round(estimated_duration, 6),
            "duration_bucket": self._duration_bucket(estimated_duration),
            "r_squared": round(r_squared, 8),
            "tracking_error": round(tracking_error, 8),
            "selected_series": selected_rows,
            "weights": weight_rows,
            "group_diagnostics": group_diagnostics,
            "methodology_version": self.METHODOLOGY_VERSION,
            "status": "low_fit" if low_fit else "ok",
            "source": self.SOURCE,
            "missing_items": ["回归拟合度低于 45%，久期结果只作弱证据"] if low_fit else [],
            "nav_basis": nav_basis,
        }
        self.repo.upsert_estimate(row)
        return self._decorate({**row, "calculated_at": None, "index_inventory": inventory})

    def _select_group(
        self,
        fund_weekly: pd.Series,
        candidates: List[Dict[str, Any]],
        weekly_by_key: Dict[str, pd.Series],
        window_weeks: int,
    ) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        latest_allowed = fund_weekly.index.max() - pd.Timedelta(days=14)
        available = [
            item for item in candidates
            if item["series_key"] in weekly_by_key and weekly_by_key[item["series_key"]].index.max() >= latest_allowed
        ]
        if len(available) < 2:
            return None, {}
        frame = pd.concat(
            [fund_weekly.rename("fund"), *[weekly_by_key[item["series_key"]].rename(item["series_key"]) for item in available]],
            axis=1,
        ).dropna().tail(window_weeks)
        if len(frame) < self.MINIMUM_WEEKS:
            return None, {}

        matrix = frame.to_numpy().T
        standard_deviation = matrix.std(axis=1, keepdims=True)
        standardized = (matrix - matrix.mean(axis=1, keepdims=True)) / np.where(standard_deviation > 0, standard_deviation, 1)
        candidate_keys = [item["series_key"] for item in available]
        try:
            labels = KMeans(n_clusters=2, random_state=42, n_init=10).fit_predict(standardized)
            same_cluster = [key for index, key in enumerate(candidate_keys, start=1) if labels[index] == labels[0]]
        except Exception:
            same_cluster = []
        pool = same_cluster or candidate_keys
        scores = {
            key: self._univariate_r_squared(frame["fund"].to_numpy(), frame[key].to_numpy())
            for key in candidate_keys
        }
        selected_key = max(pool, key=lambda key: scores[key])
        definition = next(item for item in available if item["series_key"] == selected_key)
        selection = {**definition, "selection_r_squared": round(scores[selected_key], 8)}
        diagnostics = {
            "index_group": definition["index_group"],
            "group_label": definition["group_label"],
            "observations": len(frame),
            "selected_series_key": selected_key,
            "same_cluster_candidates": same_cluster,
            "candidate_scores": [
                {
                    "series_key": item["series_key"],
                    "period_label": item["period_label"],
                    "r_squared": round(scores[item["series_key"]], 8),
                }
                for item in available
            ],
        }
        return selection, diagnostics

    @staticmethod
    def _style_regression(y: np.ndarray, x: np.ndarray) -> Tuple[np.ndarray, float, float]:
        result = minimize(
            lambda weights: float(np.sum((y - x @ weights) ** 2)),
            np.repeat(1 / x.shape[1], x.shape[1]),
            method="SLSQP",
            bounds=[(0.0, 1.0)] * x.shape[1],
            constraints=[{"type": "eq", "fun": lambda weights: float(np.sum(weights) - 1)}],
            options={"maxiter": 500, "ftol": 1e-12},
        )
        if not result.success:
            raise ValueError(f"久期风格回归未收敛：{result.message}")
        prediction = x @ result.x
        residual = y - prediction
        total_variation = float(np.sum((y - np.mean(y)) ** 2))
        r_squared = 1 - float(np.sum(residual ** 2)) / total_variation if total_variation > 0 else 0.0
        tracking_error = float(np.std(residual, ddof=1) * math.sqrt(52)) if len(residual) > 1 else 0.0
        return result.x, r_squared, tracking_error

    def _fund_weekly_returns(self, wind_code: str) -> Tuple[pd.Series, str]:
        return self._weekly_returns(positive_levels(self.nav_repo.get_nav_series(wind_code))), "adj_nav"

    @staticmethod
    def _series(rows: List[Dict[str, Any]]) -> pd.Series:
        return positive_levels(rows, "value")

    @staticmethod
    def _weekly_returns(levels: pd.Series) -> pd.Series:
        if levels.empty:
            return levels
        return returns_at_endpoints(levels, weekly_endpoints(levels))

    @staticmethod
    def _univariate_r_squared(y: np.ndarray, x: np.ndarray) -> float:
        design = np.column_stack([np.ones(len(x)), x])
        coefficients = np.linalg.lstsq(design, y, rcond=None)[0]
        residual = y - design @ coefficients
        total_variation = float(np.sum((y - np.mean(y)) ** 2))
        return 1 - float(np.sum(residual ** 2)) / total_variation if total_variation > 0 else 0.0

    @staticmethod
    def _duration_bucket(value: float) -> str:
        if value < 1:
            return "短久期"
        if value < 3:
            return "中短久期"
        if value < 5:
            return "中久期"
        if value < 7:
            return "中长久期"
        return "长久期"

    @staticmethod
    def _window(value: int) -> int:
        return max(52, min(int(value or 104), 156))

    @staticmethod
    def _is_bond_fund(fund: Dict[str, Any]) -> bool:
        value = f"{fund.get('type') or ''} {fund.get('name') or ''}".lower()
        return "债" in value or "bond" in value

    def _decorate(self, row: Dict[str, Any]) -> Dict[str, Any]:
        payload = dict(row)
        if payload.get("as_of_date") and (date.today() - date.fromisoformat(str(payload["as_of_date"])[:10])).days > 7:
            payload["status"] = "stale"
            payload["missing_items"] = [*(payload.get("missing_items") or []), "此结果观测日距今超过7日，仅作历史参考，请重新测算"]
        current_method = payload.get("methodology_version") == self.METHODOLOGY_VERSION
        payload["formal_duration_ready"] = current_method and payload.get("status") == "ok" and float(payload.get("r_squared") or 0) >= 0.45
        if current_method:
            payload["nav_basis"] = "adj_nav"
        payload["fit_label"] = self._fit_label(payload.get("r_squared"))
        payload["methodology"] = {
            "reference": "基构云公开债基久期方法",
            "candidate_series": 20,
            "groups": 4,
            "selection": "每组将基金与 5 条分期限指数周收益聚成 2 类，再在基金所在簇选择单变量拟合度最高的指数",
            "regression": "对 4 条入选指数执行非负、权重和为 1 的 Sharpe 收益率风格回归",
            "duration": "使用各入选指数同期平均市值法久期按回归权重加权",
            "version": payload.get("methodology_version"),
            "nav_basis": "仅使用复权净值；基金与指数按相同实际起止日期计算周收益，不填补缺失值",
        }
        payload["limitations"] = self.LIMITATIONS
        payload["source_url"] = ChinaBondIndexService.PAGE_URL
        return payload

    def _base_response(
        self,
        wind_code: str,
        window_weeks: int,
        status: str,
        missing_items: List[str],
        index_inventory: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self._decorate({
            "wind_code": wind_code,
            "methodology_version": self.METHODOLOGY_VERSION,
            "nav_basis": "adj_nav",
            "status": status,
            "window_weeks": window_weeks,
            "estimated_duration": None,
            "duration_bucket": None,
            "r_squared": None,
            "tracking_error": None,
            "observations": 0,
            "selected_series": [],
            "weights": [],
            "group_diagnostics": [],
            "source": self.SOURCE,
            "missing_items": missing_items,
            "index_inventory": index_inventory or self.repo.index_inventory(),
        })

    @staticmethod
    def _fit_label(value: Any) -> str:
        try:
            score = float(value)
        except (TypeError, ValueError):
            return "尚未测算"
        if score >= 0.7:
            return "拟合较高"
        if score >= 0.45:
            return "拟合一般"
        return "拟合较低"
