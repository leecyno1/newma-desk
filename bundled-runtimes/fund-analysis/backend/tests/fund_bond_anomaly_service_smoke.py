import numpy as np
import pandas as pd

from services.fund_bond_anomaly_service import FundBondAnomalyService


dates = pd.bdate_range("2025-01-02", periods=100)
peer_data = {}
for index in range(8):
    returns = np.full(len(dates), 0.0002 + index * 0.000001)
    returns[68:74] = -0.008 - index * 0.00001
    peer_data[f"peer-{index}"] = returns
peer_returns = pd.DataFrame(peer_data, index=dates)

target_returns = np.full(len(dates), 0.0002)
target_returns[71] = -0.035
target_levels = pd.Series(np.cumprod(1 + target_returns), index=dates)

service = FundBondAnomalyService.__new__(FundBondAnomalyService)
result = service._analyze_series(
    target_levels,
    peer_returns,
    minimum_peer_count=5,
    window_days=100,
)

assert result["events"]
assert result["anomaly_counts"]["year"] > 0
assert any("净值跌破26日下轨" in event["reason"] for event in result["events"])
assert any("债市调整期显著弱于同类" in event["reason"] for event in result["events"])
assert all(event["peer_count"] >= 5 for event in result["events"])
assert len(result["chart"]) == 100

print("OK bond anomaly monitor applies 26-day lower band and peer 3-sigma adjustment gate")
