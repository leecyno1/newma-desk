# 独立基金应用与 Desk Adapter

状态：Canonical
Desk：Manifest `1.1` / Bridge `1.0` / ViewSpec `1.0`

## 产品范围

正式产品是独立基金应用。Desk Adapter 复用正式页面，只提供五个入口：

| 页面 | 路由 | 用途 |
| --- | --- | --- |
| 找基金 | `/mod/fund-research/discover` | 基金搜索、详情、净值和比较 |
| 调研库 | `/mod/fund-research/research` | 本地纪要、经理归类和标签确认 |
| AI 分析 | `/mod/fund-research/analysis` | 按需评价和分析历史 |
| 标签推荐 | `/mod/fund-research/recommendations` | 同类候选基金组 |
| 业绩归因 | `/mod/fund-research/advanced` | Barra、Brinson 和证据覆盖 |

不包含准入工作流、尽调、持续监控、投资决策、购买金额、个人适当性和交易执行。

## 运行结构

```text
独立浏览器
  └─ 基金选择应用（3000）
      └─ FastAPI 基金后端（8005）

牛马 Desk（可选宿主）
  └─ 基金选择 Suite
      ├─ security.selected
      ├─ Level 3 Context
      └─ Manifest Actions
          └─ FastAPI Desk Adapter
              └─ 正式基金 Module
                  └─ PostgreSQL 与真实数据源
```

独立前端默认地址为 `http://127.0.0.1:3000`。发现入口：

```text
GET /.well-known/newma-desk-suite.json
GET /api/newma-desk/health
```

`3001` 由 Orchestra 使用，基金项目不得占用。项目只提供标准 Suite 与发现入口，不直接调用 Newma 控制面；人工验收通过后再将描述文件加入 `desk-mods`。

## Desk Actions

- `fund.search`
- `fund.research.snapshot`
- `fund.compare`
- `fund.attribution.run`
- `fund.analysis.run`
- `fund.recommendations.list`

所有 Action 都对应真实入口。数据不足时返回缺口或不可用状态，不生成模拟基金、持仓、标签和归因。

## 稳定协议

`lib/newma-desk/bridge.ts` 保留：

- `vibedesk:hello → vibedesk:init → vibedesk:ack`
- Context 请求与发布
- Action 请求代理
- `security.selected` 的基金选择同步
- Desk 主题、语言和时区

业务基金数据存储在 dedicated PostgreSQL。Desk 不保存数据库凭据和上游数据源密钥。

## 验收

- 五个模组页面可独立访问。
- Suite 默认端口为 `3000`。
- 页面不出现准入、尽调、监控和投资决策语义。
- Context 只暴露当前功能、基金选择、真实 Action 和证据说明。
- AI 分析由用户现场发起并保存历史。
- Barra、Brinson 数据不足时明确显示证据状态。
