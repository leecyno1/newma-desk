# 研究组合合同

## 定位

`instock-research-book` 负责校验和汇总研究状态，不负责保存、同步或交易。Desk 未来可直接持久化同一输入包，项目无需增加数据库。

## 接口

Action：`analysis.research-book`

HTTP：`POST /api/v1/research-books`

输入版本：`instock-research-book-packet-v1`。

每个观察项包含证券、行业、目标研究暴露、观察理由、至少一条证伪条件、风险标签和 0～10 个 Analysis Snapshot 引用。全部目标暴露之和不能超过 100%。

## 输出

- Snapshot 引用解析状态与缺口。
- 行业、风险标签和最大单项暴露。
- 单项超过 20%、行业超过 40% 的集中度警告。
- 现金余量、数据状态、限制和研究组合 Snapshot。

目标权重只用于研究暴露汇总，不是资产配置建议。Module 不持久化数据、不下单，也不恢复原 InStock `attention` 表。
