from services.fund_product_profile_service import FundProductProfileService
from services.fund_research_snapshot_service import FundResearchSnapshotService


BASIC_HTML = """
<table class="info">
  <tr><th>基金全称</th><td>测试指数基金</td><th>基金简称</th><td>测试ETF</td></tr>
  <tr><th>基金管理人</th><td>测试基金</td><th>基金托管人</th><td>测试银行</td></tr>
</table>
<div class="boxitem"><h4 class="t"><label class="left">投资目标</label></h4><p>紧密跟踪标的指数。</p></div>
<div class="boxitem"><h4 class="t"><label class="left">投资理念</label></h4><p>被动指数化投资。</p></div>
<div class="boxitem"><h4 class="t"><label class="left">投资范围</label></h4><p>标的指数成份股及备选成份股。</p></div>
<div class="boxitem"><h4 class="t"><label class="left">投资策略</label></h4><p>主要采取完全复制法。</p></div>
<div class="boxitem"><h4 class="t"><label class="left">风险收益特征</label></h4><p>风险和收益高于混合型基金。</p></div>
"""

FEE_HTML = """
<div class="boxitem"><h4 class="t"><label class="left">运作费用</label></h4><table><tr><td class="th">管理费率</td><td>0.50%（每年）</td><td class="th">托管费率</td><td>0.10%（每年）</td><td class="th">销售服务费率</td><td>---</td></tr></table></div>
<div class="boxitem"><h4 class="t"><label class="left">认购费率</label></h4><table><thead><tr><th>适用金额</th><th>费率</th></tr></thead><tbody><tr><td>小于50万元</td><td>0.08%</td></tr><tr><td>100万元以上</td><td>每笔500元</td></tr></tbody></table></div>
<div class="boxitem"><h4 class="t"><label class="left">申购费率</label></h4><table><thead><tr><th>适用金额</th><th>费率</th></tr></thead><tbody><tr><td>---</td><td>0.05%</td></tr></tbody></table></div>
<div class="boxitem"><h4 class="t"><label class="left">赎回费率</label></h4><table><thead><tr><th>适用期限</th><th>赎回费率</th></tr></thead><tbody><tr><td>---</td><td>0.15%</td></tr></tbody></table></div>
"""


basic = FundProductProfileService.parse_basic_page(BASIC_HTML)
fees = FundProductProfileService.parse_fee_page(FEE_HTML)

assert basic["product"]["management_company"] == "测试基金"
assert basic["product"]["investment_objective"] == "紧密跟踪标的指数。"
assert basic["product"]["investment_strategy"] == "主要采取完全复制法。"
assert basic["product"]["risk_return_characteristics"] == "风险和收益高于混合型基金。"
assert fees["management_fee_rate"] == "0.50%（每年）"
assert fees["custodian_fee_rate"] == "0.10%（每年）"
assert fees["sales_service_fee_rate"] is None
assert fees["subscription_fee_rules"][1] == {
    "condition": "100万元以上",
    "rate": "每笔500元",
    "condition_label": "适用金额",
}
assert fees["purchase_fee_rules"][0]["rate"] == "0.05%"
assert fees["redemption_fee_rules"][0]["rate"] == "0.15%"

projected = FundResearchSnapshotService.project_fund({
    "wind_code": "512010.SH",
    "name": "测试ETF",
    "type": "指数型",
    "raw_data": {"product_profile": {"status": "available", "product": basic["product"], "fees": fees}},
})
assert projected["product_profile"]["status"] == "available"
assert projected["product_profile"]["fees"]["subscription_fee_rules"][0]["rate"] == "0.08%"

print("OK fund product profile parses product introduction and tiered fees")
