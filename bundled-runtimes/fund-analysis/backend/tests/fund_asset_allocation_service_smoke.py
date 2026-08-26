from services.fund_asset_allocation_service import FundAssetAllocationService


HTML = """
<table class="w782 comm tzxq">
  <thead><tr><th>报告期</th><th>股票占净比</th><th>债券占净比</th><th>现金占净比</th><th>净资产（亿元）</th></tr></thead>
  <tbody>
    <tr><td>2026-06-30</td><td>99.82%</td><td>---</td><td>0.23%</td><td>171.45</td></tr>
    <tr><td>2026-03-31</td><td>99.85%</td><td>---</td><td>0.20%</td><td>172.15</td></tr>
  </tbody>
</table>
"""


rows = FundAssetAllocationService.parse_html(
    HTML,
    source_url="https://fundf10.eastmoney.com/zcpz_512010.html",
)

assert len(rows) == 2
assert rows[0]["report_date"] == "2026-06-30"
assert rows[0]["stock_ratio"] == 0.9982
assert rows[0]["bond_ratio"] is None
assert rows[0]["cash_ratio"] == 0.0023
assert rows[0]["net_asset_yi"] == 171.45
assert rows[0]["source"] == FundAssetAllocationService.SOURCE
assert rows[0]["source_url"].endswith("zcpz_512010.html")

print("OK fund asset allocation parses public periodic-report data")
