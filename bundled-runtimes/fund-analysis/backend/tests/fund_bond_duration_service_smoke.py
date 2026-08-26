import numpy as np
import pandas as pd

from services.chinabond_index_service import ChinaBondIndexService
from services.fund_bond_duration_service import FundBondDurationService


definitions = ChinaBondIndexService.definitions()
assert len(definitions) == 20
assert {item["index_group"] for item in definitions} == set(FundBondDurationService.GROUP_ORDER)
assert all(sum(item["index_group"] == group for item in definitions) == 5 for group in FundBondDurationService.GROUP_ORDER)

weights, r_squared, tracking_error = FundBondDurationService._style_regression(
    np.array([0.01, 0.02, -0.01, 0.03]),
    np.array([
        [0.01, 0.00],
        [0.02, 0.01],
        [-0.01, 0.00],
        [0.03, 0.01],
    ]),
)
assert np.all(weights >= 0)
assert abs(float(weights.sum()) - 1) < 1e-8
assert np.isfinite(r_squared)
assert np.isfinite(tracking_error)

fund = pd.Series([0.001, 0.002, -0.001, 0.003] * 20, index=pd.date_range("2025-01-03", periods=80, freq="W-FRI"))
candidate_a = fund * 0.95
candidate_b = pd.Series([0.003, -0.002, 0.001, -0.001] * 20, index=fund.index)
service = FundBondDurationService.__new__(FundBondDurationService)
selection, diagnostics = service._select_group(
    fund,
    [
        {"series_key": "credit:01", "index_group": "credit", "group_label": "信用债", "period_label": "1年以下"},
        {"series_key": "credit:02", "index_group": "credit", "group_label": "信用债", "period_label": "1-3年"},
    ],
    {"credit:01": candidate_a, "credit:02": candidate_b},
    52,
)
assert selection and selection["series_key"] == "credit:01"
assert diagnostics["observations"] == 52

low_fit = service._decorate({"status": "low_fit", "r_squared": 0.2})
assert low_fit["formal_duration_ready"] is False
assert low_fit["fit_label"] == "拟合较低"
assert "不参与基金评分" in "".join(low_fit["limitations"])

print("OK bond duration model uses 20 real-index definitions, constrained weights and weak-evidence gate")
