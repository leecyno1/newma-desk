# Vibe HTML 页面规范

Vibe HTML 是 `vibe-visualization` 默认的页面生成规范。它的目标是让不同 Agent 生成的研究、量化和数据页面保持相同的结构与视觉，同时让人和 Agent 都能高效读取页面。

## 默认选择顺序

创建模块时按以下顺序选择：

1. `structured`：指标、表格、图表、Markdown、筛选器和操作按钮能够表达需求时，优先使用。
2. `static`：复杂关系图、3D、地图或高度定制交互超出 Structured Renderer 时使用。
3. `external`：已有独立项目或上游页面需要低耦合接入时使用。

不要因为 Agent 能生成 React 代码，就默认创建一套新的前端工程。结构化模块更容易保持一致、升级和检查。

## 默认技术

- 页面：React + Vite。
- 普通图表、K 线和金融图表：ECharts。
- Markdown：react-markdown，并保持原始 HTML 禁用。
- 复杂关系网络：Cytoscape.js；简单关系图继续使用 ECharts Graph。
- 3D：Three.js / React Three Fiber。
- 地图：MapLibre。
- 视觉变量：`@vibe-visualization/ui-foundation/tokens.css`。

后四项属于扩展能力。没有明确需要时，不应提前加入模块依赖。

## 页面必须具备的信息

每个页面需要明确显示或在数据中提供：

- 页面标题和用途说明。
- 当前数据时间。
- 数据来源。
- 加载状态。
- 空数据状态。
- 错误或离线状态。
- 最后成功结果。

页面不得在 HTML、JavaScript、Manifest 或 View Schema 中保存 API Key、Token 和其他 Secret。

## HTML 语义

Structured Renderer 会输出：

```html
<main data-vibe-page="1.0" data-vibe-title="页面标题">
  <section
    data-vibe-block="table"
    data-vibe-block-id="companies"
    data-vibe-rows-path="companies"
  >
    ...
  </section>
</main>
```

Agent 可以通过以下属性理解页面：

- `data-vibe-page`：Vibe HTML 版本。
- `data-vibe-title`：页面标题。
- `data-vibe-block`：区块类型。
- `data-vibe-block-id`：跨版本保持稳定的区块 ID。
- `data-vibe-value-path`：指标对应的数据路径。
- `data-vibe-rows-path`：表格对应的数据路径。
- `data-vibe-option-path`：图表配置路径。
- `data-vibe-content-path`：Markdown 内容路径。

图表同时输出：

```html
<script type="application/json" data-vibe-chart-option>
  {"xAxis":{"data":["上证指数"]},"series":[{"data":[0.8]}]}
</script>
```

该节点不是可执行脚本，只保存经过安全转义的 JSON。Agent 不需要读取 Canvas 像素就能获得图表内容。

## 稳定性规则

- 发布后不要随意更换区块 ID。
- 数据结构改变时生成新的模块修订版本。
- 单纯数据刷新不改变 Module Manifest。
- 图表必须同时保留机器可读配置。
- 重要数据不能只用颜色表达。
- 表格必须使用真实 `<table>`，不要用纯 Canvas 模拟。
- 复杂 3D 或关系图必须额外提供节点、边、对象或场景数据。
- 交互页面和未来的静态 Agent HTML 必须来自同一份 Schema 和数据。

## 产业链研究页面范式

机器人产业链和光模块产业链应使用同一套页面骨架：

```json
{
  "version": "1.0",
  "title": "机器人产业链研究",
  "blocks": [
    {
      "id": "summary",
      "type": "metrics",
      "items": [
        {"label": "覆盖公司", "valuePath": "summary.companyCount", "format": "number"},
        {"label": "近期催化", "valuePath": "summary.catalystCount", "format": "number"}
      ]
    },
    {
      "id": "chain-graph",
      "type": "chart",
      "title": "产业链关系",
      "optionPath": "charts.chainGraph",
      "height": 520
    },
    {
      "id": "companies",
      "type": "table",
      "title": "相关公司",
      "rowsPath": "companies",
      "columns": [
        {"key": "symbol", "label": "代码"},
        {"key": "name", "label": "公司"},
        {"key": "segment", "label": "产业环节"},
        {"key": "relevance", "label": "相关度", "format": "percent"}
      ]
    },
    {
      "id": "research-note",
      "type": "markdown",
      "title": "研究结论",
      "contentPath": "analysis"
    }
  ]
}
```

生成光模块产业链时保留相同区块 ID、顺序、排版和交互，只替换标题、数据和研究内容。

## 量化回测页面范式

```json
{
  "version": "1.0",
  "title": "策略回测报告",
  "blocks": [
    {
      "id": "performance",
      "type": "metrics",
      "items": [
        {"label": "年化收益", "valuePath": "metrics.annualReturn", "format": "percent"},
        {"label": "最大回撤", "valuePath": "metrics.maxDrawdown", "format": "percent"},
        {"label": "夏普比率", "valuePath": "metrics.sharpe", "format": "number"}
      ]
    },
    {
      "id": "equity-curve",
      "type": "chart",
      "title": "收益曲线",
      "optionPath": "charts.equityCurve",
      "height": 360
    },
    {
      "id": "drawdown",
      "type": "chart",
      "title": "回撤",
      "optionPath": "charts.drawdown",
      "height": 280
    },
    {
      "id": "trades",
      "type": "table",
      "title": "交易记录",
      "rowsPath": "trades",
      "columns": [
        {"key": "date", "label": "日期"},
        {"key": "symbol", "label": "代码"},
        {"key": "side", "label": "方向"},
        {"key": "return", "label": "收益", "format": "percent"}
      ]
    }
  ]
}
```

Alpha Zoo、因子详情和策略比较页面应复用相同指标、图表和表格组件，不自行定义另一套颜色和间距。
