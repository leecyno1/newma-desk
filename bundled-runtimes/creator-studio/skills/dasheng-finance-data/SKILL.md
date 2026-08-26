---
name: dasheng-finance-data
description: Draft 阶段按需金融数据增强工具。用于把 A 股/指数行情、估值与时间序列数据转成可直接嵌入 Draft HTML 的 Chart.js `chart_specs`。
version: 0.1.0
stage: on-demand
---

# Newma Finance Data

## 定位

本 skill 借鉴 `${BOUTIQUE_OPENCLAW_SKILLS_ROOT:-vendor/reserved/catalog/boutique-openclaw-skills}/skills/default/a-stock-data` 的数据源优先级：

- 行情/指数时间序列：优先使用东方财富 `push2his` 直连接口生成 K 线图表；接口断连时自动切换百度股市通 K 线。
- 实时估值/市值/PE/PB：使用腾讯财经 `qt.gtimg.cn`。
- 全球市场品种：优先使用 Yahoo Finance Chart HTTP 直连接口抓取美股指数、ETF、商品、汇率、Crypto 等时间序列；接口限流时退到本地缓存，再退到 `yfinance`。
- 经济日历：存在 `FMP_API_KEY` 时可抓取 FMP Economic Calendar，并生成事件影响等级统计图。
- 中国宏观/地产：使用东方财富数据中心宏观报表，轻量支持 CPI、PMI、GDP、货币供应、人民币贷款、70 城房价等常用图表。
- 暂不把完整 `a-stock-data` 巨型 skill 直接并入 Draft，避免引入 mootdx、研报、龙虎榜、两融等复杂依赖和风控负担。

## 何时使用

- Draft 文章需要 A 股、指数、ETF 的价格走势、对比走势、指数化表现图。
- 需要把“金融数据请求”转成 `chart_specs`，直接进入 `03_HTML草稿_<topic>.html`。
- 需要增强宏观/产业/市场文章的数据支撑，而不是手写静态数字。

## 输入格式

在 `topic_cards.json` 或 `--asset-specs-file` 中给对应 `topic_id` 添加 `data_requests` 或兼容字段 `finance_chart_requests`：

```json
{
  "data_requests": [
    {
      "id": "ai-chain-indexed-performance",
      "kind": "kline",
      "claim_id": "topic-ai-claim-01",
      "section_id": "section-01",
      "metric_id": "close_price",
      "title": "AI产业链核心标的走势对比",
      "symbols": [
        {"code": "300750", "label": "宁德时代"},
        {"code": "002594", "label": "比亚迪"}
      ],
      "start_date": "20250101",
      "end_date": "20260601",
      "field": "close",
      "unit": "起点=100",
      "normalize": true
    }
  ]
}
```

全球市场例子：

```json
{
  "finance_chart_requests": [
    {
      "id": "cross-asset-performance",
      "kind": "global_market",
      "title": "美股、黄金与长债走势对比",
      "symbols": [
        {"ticker": "^GSPC", "label": "S&P 500"},
        {"ticker": "GC=F", "label": "黄金期货"},
        {"ticker": "TLT", "label": "美国长债ETF"}
      ],
      "start_date": "20250101",
      "end_date": "20260601",
      "field": "close",
      "normalize": true
    }
  ]
}
```

经济日历例子：

```json
{
  "finance_chart_requests": [
    {
      "id": "macro-calendar-impact",
      "kind": "economic_calendar",
      "title": "未来两周高影响经济数据密度",
      "from_date": "2026-06-01",
      "to_date": "2026-06-14",
      "countries": ["US", "CN", "JP"]
    }
  ]
}
```

中国宏观例子：

```json
{
  "data_requests": [
    {
      "id": "china-cpi-yoy",
      "kind": "china_macro",
      "preset": "china_cpi",
      "claim_id": "topic-macro-claim-01",
      "title": "中国CPI同比走势",
      "start_date": "20240101",
      "end_date": "20260601"
    }
  ]
}
```

中国地产/房价例子：

```json
{
  "data_requests": [
    {
      "id": "tier1-house-price-yoy",
      "kind": "china_house_price",
      "preset": "china_house_price",
      "claim_id": "topic-property-claim-02",
      "title": "一线城市新建商品住宅价格同比",
      "cities": ["北京", "上海", "广州", "深圳"],
      "field": "FIRST_COMHOUSE_SAME",
      "transform": "delta_from_100",
      "unit": "%"
    }
  ]
}
```

当前内置 preset：

| preset | kind | 默认字段 | 说明 |
| --- | --- | --- | --- |
| `china_cpi` | `china_macro` | `NATIONAL_SAME` | CPI同比 |
| `china_pmi` | `china_macro` | `MAKE_INDEX` | 制造业PMI |
| `china_gdp` | `china_macro` | `SUM_SAME` | GDP同比 |
| `china_money_supply` | `china_macro` | `BASIC_CURRENCY_SAME` | 货币供应同比 |
| `china_rmb_loan` | `china_macro` | `RMB_LOAN_ACCUMULATE` | 人民币贷款累计新增 |
| `china_house_price` | `china_house_price` | `FIRST_COMHOUSE_SAME` | 新建商品住宅价格同比指数，默认 `delta_from_100` 转为涨跌幅 |

## 输出

Draft 会自动把 `finance_chart_requests` 展开为 `chart_specs`：

- `labels`：交易日期
- `datasets`：收盘价或指数化序列
- `claim_id / section_id / metric_id`：如请求中提供，会原样写入图表规格和 `meta`
- `source`：按实际数据源写入 `东方财富 push2his K线`、`百度股市通 K线`、`Yahoo Finance Chart API`、`Yahoo Finance 本地缓存` 等。
- `source_url`：按实际数据源写入东方财富、百度股市通或 Yahoo Finance。
- `meta.provenance`：来源、抓取时间、缓存状态、接口警告。
- `meta.data_quality`：数据点数量、缺失点数量、基础质量状态。
- `finance_chart_failures`：Draft 资产清单会记录请求级失败原因；只要有金融图表失败，`asset_status` 会标记为 `incomplete`。
- `data_validation`：Draft 资产清单会汇总请求数、生成数、失败数、警告数和整体状态。

如果金融接口失败或返回空，Draft 不会崩溃，但 `asset_status` 会保持 `incomplete`，避免伪装成完成稿。

## 直接生成 chart_specs

```bash
python3 scripts/finance_data_adapter.py chart-specs \
  --requests-file /path/to/finance_chart_requests.json \
  --output /path/to/chart_specs.json
```

如需同时查看失败明细：

```bash
python3 scripts/finance_data_adapter.py chart-specs \
  --requests-file /path/to/finance_chart_requests.json \
  --report
```

## 设计约束

- 不并发请求东方财富，遵守至少 1 秒间隔与随机抖动。
- 全球市场请求会写入 `.cache/finance_data/yahoo_chart`，用于降低限流影响；旧缓存只会在实时接口失败时标注为缓存来源，不伪装成实时数据。
- FMP 经济日历需要 `FMP_API_KEY`；没有 key 时不得编造宏观日历。
- 不在正文里写内部请求日志。
- 不构成投资建议；所有数据只作为文章事实支撑和图表素材。
