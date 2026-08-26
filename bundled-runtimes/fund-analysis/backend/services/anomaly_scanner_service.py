"""异常筛查器 (Anomaly Scanner) — 主动发现值得关注的基金变化。

扫描四类异常：
1. 规模异动：30 天内规模变化 > 30%
2. 回撤异常：近 3 月回撤接近或超过近 3 年回撤
3. 经理变更：fund_change_history 中 manager_change 类型
4. 集中度突变：前十大持仓占比一个季度变动 > 10pct

设计原则：
- 只扫描主动基金（排除 ETF/指数/货币），通过 wind_code 后缀和基金类型过滤
- 每条异常带证据引用
- 扫描结果不自动触发任何操作，仅供用户查看
"""
from datetime import date
from typing import Any, Dict, List

try:
    from backend.database import get_engine
except ModuleNotFoundError:
    from database import get_engine

# 排除被动基金的 wind_code 模式（ETF 通常以 1xxxxx.SH/SZ 或 5xxxxx.SH 开头）
_PASSIVE_CODE_PREFIXES = ('159', '510', '511', '512', '513', '515', '516', '518', '560', '561', '562', '563', '588', '159', '161')


def _is_passive_code(wind_code: str) -> bool:
    """判断是否为被动基金代码（ETF/LOF 指数类）。"""
    code = wind_code.split('.')[0] if '.' in wind_code else wind_code
    return any(code.startswith(p) for p in _PASSIVE_CODE_PREFIXES)


class AnomalyScannerService:
    def __init__(self, engine=None):
        self._engine = engine

    @property
    def engine(self):
        if self._engine is None:
            self._engine = get_engine()
        return self._engine

    def scan(self, limit: int = 50) -> Dict[str, Any]:
        """执行全量异常扫描，返回按类型分组的异常列表。"""
        results: Dict[str, List[Dict[str, Any]]] = {
            "scale_anomaly": self._scan_scale_anomaly(limit),
            "drawdown_anomaly": self._scan_drawdown_anomaly(limit),
            "manager_change": self._scan_manager_changes(limit),
            "concentration_change": self._scan_concentration_change(limit),
        }
        # 过滤被动基金
        for key in results:
            results[key] = [
                item for item in results[key]
                if not _is_passive_code(item.get("wind_code", ""))
            ]
        total = sum(len(v) for v in results.values())
        return {
            "scan_date": date.today().isoformat(),
            "total_anomalies": total,
            "by_type": {k: len(v) for k, v in results.items()},
            "anomalies": results,
        }

    def _scan_scale_anomaly(self, limit: int) -> List[Dict[str, Any]]:
        """规模异动：最新 AUM 与 30 天前差异 > 30%"""
        from sqlalchemy import text
        sql = text("""
            WITH ranked AS (
                SELECT target_id AS wind_code, metric_value, as_of_date,
                       ROW_NUMBER() OVER (PARTITION BY target_id ORDER BY as_of_date DESC) AS rn
                FROM metric_snapshots
                WHERE target_type = 'fund' AND metric_name = 'aum' AND metric_window = 'latest'
            ),
            latest AS (SELECT wind_code, metric_value AS aum_now, as_of_date FROM ranked WHERE rn = 1),
            prev AS (
                SELECT wind_code, metric_value AS aum_prev FROM (
                    SELECT target_id AS wind_code, metric_value,
                           ROW_NUMBER() OVER (PARTITION BY target_id ORDER BY as_of_date DESC) AS rn
                    FROM metric_snapshots
                    WHERE target_type = 'fund' AND metric_name = 'aum' AND metric_window = 'latest'
                      AND as_of_date BETWEEN CURRENT_DATE - INTERVAL '50 days' AND CURRENT_DATE - INTERVAL '20 days'
                ) t WHERE rn = 1
            )
            SELECT l.wind_code, l.aum_now, p.aum_prev,
                   ROUND(((l.aum_now - p.aum_prev) / NULLIF(p.aum_prev, 0)) * 100, 1) AS change_pct
            FROM latest l JOIN prev p ON l.wind_code = p.wind_code
            WHERE p.aum_prev > 0 AND ABS((l.aum_now - p.aum_prev) / p.aum_prev) > 0.30
            ORDER BY ABS((l.aum_now - p.aum_prev) / p.aum_prev) DESC
            LIMIT :limit
        """)
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(sql, {"limit": limit}).fetchall()
            return [
                {"type": "scale_anomaly", "wind_code": str(r[0]),
                 "aum_now": float(r[1]) if r[1] else None,
                 "aum_prev": float(r[2]) if r[2] else None,
                 "change_pct": float(r[3]) if r[3] else None,
                 "description": f"规模变动 {float(r[3]):+.1f}%"}
                for r in rows
            ]
        except Exception:
            return []

    def _scan_drawdown_anomaly(self, limit: int) -> List[Dict[str, Any]]:
        """回撤异常：近 3 月回撤 >= 近 3 年回撤的 80%"""
        from sqlalchemy import text
        sql = text("""
            WITH dd_3m AS (
                SELECT target_id AS wind_code, metric_value AS dd_3m FROM (
                    SELECT target_id, metric_value,
                           ROW_NUMBER() OVER (PARTITION BY target_id ORDER BY as_of_date DESC) AS rn
                    FROM metric_snapshots
                    WHERE target_type='fund' AND metric_name='max_drawdown' AND metric_window='3m' AND metric_value < 0
                ) t WHERE rn = 1
            ),
            dd_3y AS (
                SELECT target_id AS wind_code, metric_value AS dd_3y FROM (
                    SELECT target_id, metric_value,
                           ROW_NUMBER() OVER (PARTITION BY target_id ORDER BY as_of_date DESC) AS rn
                    FROM metric_snapshots
                    WHERE target_type='fund' AND metric_name='max_drawdown' AND metric_window='3y' AND metric_value < 0
                ) t WHERE rn = 1
            )
            SELECT d3.wind_code, d3.dd_3m, d3y.dd_3y,
                   ROUND((d3.dd_3m / NULLIF(d3y.dd_3y, 0)) * 100, 1) AS ratio_pct
            FROM dd_3m d3 JOIN dd_3y d3y ON d3.wind_code = d3y.wind_code
            WHERE d3y.dd_3y < 0 AND (d3.dd_3m / d3y.dd_3y) >= 0.80
              AND d3.dd_3m < -0.05
            ORDER BY (d3.dd_3m / d3y.dd_3y) DESC
            LIMIT :limit
        """)
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(sql, {"limit": limit}).fetchall()
            return [
                {"type": "drawdown_anomaly", "wind_code": str(r[0]),
                 "dd_3m": float(r[1]) if r[1] else None,
                 "dd_3y": float(r[2]) if r[2] else None,
                 "ratio_pct": float(r[3]) if r[3] else None,
                 "description": f"近3月回撤 {float(r[1])*100:.1f}% 已达近3年的 {float(r[3]):.0f}%"}
                for r in rows
            ]
        except Exception:
            return []

    def _scan_manager_changes(self, limit: int) -> List[Dict[str, Any]]:
        """经理变更：最近 30 天内的 manager_change 事件"""
        from sqlalchemy import text
        sql = text("""
            SELECT entity_id, changed_at, previous_value, new_value
            FROM fund_change_history
            WHERE change_type IN ('manager_change','manager_added','manager_removed')
              AND changed_at >= CURRENT_DATE - INTERVAL '30 days'
            ORDER BY changed_at DESC LIMIT :limit
        """)
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(sql, {"limit": limit}).fetchall()
            return [
                {"type": "manager_change", "wind_code": str(r[0]),
                 "changed_at": str(r[1]) if r[1] else None,
                 "previous_manager": str(r[2] or ""), "new_manager": str(r[3] or ""),
                 "description": f"经理变更：{r[2] or '—'} → {r[3] or '—'}"}
                for r in rows
            ]
        except Exception:
            return []

    def _scan_concentration_change(self, limit: int) -> List[Dict[str, Any]]:
        """集中度突变：前十大持仓占比季度间变动 > 10pct"""
        from sqlalchemy import text
        sql = text("""
            WITH quarterly_top10 AS (
                SELECT wind_code, quarter, SUM(weight) AS top10_weight
                FROM (
                    SELECT wind_code, quarter, weight,
                           ROW_NUMBER() OVER (PARTITION BY wind_code, quarter ORDER BY weight DESC) AS rn
                    FROM holdings WHERE weight IS NOT NULL AND weight > 0
                ) ranked WHERE rn <= 10
                GROUP BY wind_code, quarter
            ),
            q_list AS (SELECT DISTINCT quarter FROM quarterly_top10 ORDER BY quarter DESC LIMIT 2),
            q_latest AS (SELECT quarter FROM q_list ORDER BY quarter DESC LIMIT 1),
            q_prev AS (SELECT quarter FROM q_list ORDER BY quarter ASC LIMIT 1)
            SELECT l.wind_code, l.top10_weight AS latest_w, p.top10_weight AS prev_w,
                   ROUND((l.top10_weight - p.top10_weight) * 100, 1) AS change_pct
            FROM quarterly_top10 l
            JOIN quarterly_top10 p ON l.wind_code = p.wind_code
            JOIN q_latest ql ON l.quarter = ql.quarter
            JOIN q_prev qp ON p.quarter = qp.quarter
            WHERE ABS(l.top10_weight - p.top10_weight) > 0.10
            ORDER BY ABS(l.top10_weight - p.top10_weight) DESC
            LIMIT :limit
        """)
        try:
            with self.engine.connect() as conn:
                rows = conn.execute(sql, {"limit": limit}).fetchall()
            return [
                {"type": "concentration_change", "wind_code": str(r[0]),
                 "latest_weight": float(r[1]) if r[1] else None,
                 "prev_weight": float(r[2]) if r[2] else None,
                 "change_pct": float(r[3]) if r[3] else None,
                 "description": f"前十大集中度变动 {float(r[3]):+.1f}pct"}
                for r in rows
            ]
        except Exception:
            return []
