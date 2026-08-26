from services.fund_holder_structure_service import FundHolderStructureService


HTML = """
var apidata={ content:"<table class='w782 comm cyrjg'><thead><tr><th>公告日期</th><th>机构持有比例</th><th>个人持有比例</th><th>内部持有比例</th><th>总份额（亿份）</th></tr></thead><tbody>
<tr><td>2025-12-31</td><td>26.89%</td><td>73.11%</td><td>7.03%</td><td>448.35</td></tr>
<tr><td>2025-06-30</td><td>31.67%</td><td>68.33%</td><td>5.23%</td><td>559.46</td></tr>
</tbody></table>",summary:""};
"""


rows = FundHolderStructureService.parse_html(
    HTML,
    source_url="https://fundf10.eastmoney.com/cyrjg_512010.html",
)

assert len(rows) == 2
assert rows[0]["report_date"] == "2025-12-31"
assert rows[0]["institution_ratio"] == 0.2689
assert rows[0]["individual_ratio"] == 0.7311
assert rows[0]["internal_ratio"] == 0.0703
assert rows[0]["total_shares_yi"] == 448.35

comparison = FundHolderStructureService._comparison(rows[0], rows[1])
assert comparison["previous_report_date"] == "2025-06-30"
assert comparison["institution_ratio_change"] == -0.0478
assert comparison["total_shares_yi_change"] == -111.11

print("OK fund holder structure parses public disclosure and compares adjacent reports")
