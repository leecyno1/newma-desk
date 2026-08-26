# Vibe-Research Backend

A股数据层 + 可插拔 AI 层。全部只读、无状态；不预置任何标的、不推荐、不预测。

## 安装

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

> 行情 + 研报只需 `fastapi / uvicorn / requests`（秒装、必可用）。
> 一致预期 / 新闻 / 公告需 `akshare`，K线 / 财务需 `mootdx`；未装时对应端点返回 501 + 安装提示，不影响其余功能。

## 1. HTTP API（给网页前端 + 系统 AI）

```bash
.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8900
```

| 端点 | 说明 | 依赖 |
|---|---|---|
| `GET /api/health` | 健康检查 | — |
| `GET /api/indices` | 大盘指数实时行情 | stdlib |
| `GET /api/quote?codes=600519,000858` | 实时行情（PE/PB/市值/涨跌停…） | stdlib |
| `GET /api/valuation?code=600519` | 完整估值（前向PE/PEG/消化年数） | requests+akshare |
| `GET /api/valuation/percentile?code=600519` | 估值历史分位（近5年·百度股市通） | akshare |
| `GET /api/financials?code=600519` | 财务关键指标（同花顺摘要，最新报告期，前端个股页用） | akshare |
| `GET /api/reports?code=600519` | 个股研报列表（含 PDF 链接） | requests |
| `GET /api/announcements?code=600519` | 近期公告（东财） | requests |
| `GET /api/news?code=600519` | 个股新闻 | akshare |
| `GET /api/kline?code=600519` | K线 | mootdx |
| `GET /api/market-terminal/security-master` | A 股证券主数据覆盖状态 | 本地 SQLite |
| `POST /api/market-terminal/security-master/refresh` | 刷新沪深北全部 A 股目录 | mootdx + 东财 |
| `GET /api/finance?code=600519` | 季报财务快照（mootdx，前端未用 / 备用） | mootdx |
| **资金面·筹码·信号（v3.3）** | `/api/margin` · `/block-trade` · `/holders` · `/dividend` · `/fund-flow` · `/dragon-tiger` · `/lockup` · `/blocks` · `/hot-concepts` · `/investor-qa` · `/industry` | requests |
| `GET /api/market/overview` · `/api/radar` | 市场情绪+板块资金 · 资讯雷达 | akshare / stdlib |
| `POST /api/chat` | 系统 AI 对话（function calling，AI 自己调数据工具） | requests |

> 上表为主要端点；完整路由清单见 `app.py`。要更全量的 A 股数据（打板 / ETF期权 / 全市场行业排名等），用根目录 [`a-stock-data/`](../a-stock-data/SKILL.md) 工具箱。

证券主数据与重行情分层：主表保存全部沪深北 A 股的代码、名称、交易所、行业和上市状态，搜索和各 Mod 共用；K 线、资金、公告、财务等重数据按标的按需抓取并缓存。主表刷新不会批量请求五千多只股票的重数据。

`/api/chat` 请求体：
```json
{
  "messages": [{"role": "user", "content": "茅台估值贵不贵？"}],
  "context": "本页上下文（可空）",
  "llm": {"baseURL": "https://api.deepseek.com", "apiKey": "sk-…", "model": "deepseek-chat"}
}
```
`llm` 由前端从本地配置随请求带上，后端不持久化 key。

## 2. MCP Server（给 Claude Code / 高手 agent）

零第三方依赖，复用同一套数据工具。挂进 Claude Code：

```bash
claude mcp add vibe-research -- \
  "$(pwd)/.venv/bin/python" "$(pwd)/mcp_server.py"
```

挂上后，你的 agent 直接拥有 `query_quote / query_valuation / query_reports / query_news` 四个工具，
用你自己的订阅额度调数据、多步分析——无需 API key、不占本产品成本。

### 完整 A 股数据工具箱（随仓库自带）

MCP 的 4 个工具是「零配置、开箱即用」的常用项。若 agent 需要更全的 A 股数据（龙虎榜 / 融资融券 / 大宗交易 / 股东户数 / 分红 / 资金流 / 解禁 / 概念板块 / 打板情绪 / ETF 期权 / 互动易 / 全市场行业排名 …共 **40 个端点**），本仓库根目录**自带完整数据源** [`a-stock-data/`](../a-stock-data/SKILL.md)（a-stock-data v3.3）：

- 要调哪个接口，直接看 [`a-stock-data/SKILL.md`](../a-stock-data/SKILL.md)——每个端点都有 copy-paste 即用的代码（内嵌全部调用逻辑，零第三方数据封装依赖，东财接口已内置限流防封）。
- 运行依赖：`pip install mootdx requests pandas stockstats`（自包含，v3.0 起已移除 akshare）。
- 上游与更新：[github.com/simonlin1212/a-stock-data](https://github.com/simonlin1212/a-stock-data)（不更新也能一直用，自带的是固定可用快照）。
- 分工：**MCP 4 工具** = 网页 / 轻量常用；**自带数据源 40+ 端点** = agent 深度自助调研的全量工具箱。二者同源，按需取用。

## 合规

- 数据端点只返回客观行情/研报/财报/新闻，不含任何建议、排名、预测。
- `/api/chat` 的 system prompt 内置中立红线：不荐股、不预测涨跌、不给买卖时机、不构成投资建议。
- 分析结论一律由用户配置的模型 / agent 给出，本产品只提供数据与工具。
