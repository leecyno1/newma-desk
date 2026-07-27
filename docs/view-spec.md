# ViewSpec 页面规范

ViewSpec 是 Newma-Dock 默认的页面生成规范。它让不同 Agent 生成的研究、量化和数据页面保持一致，也让 Agent 无需截图或鼠标自动化即可理解页面。

## 页面类型

创建 Mod 时按以下顺序选择：

1. `structured`：指标、表格、图表、Markdown、筛选器和操作按钮能够表达需求时优先使用。
2. `static`：复杂关系图、3D、地图或高度定制交互超出 View Renderer 时使用。
3. `external`：已有独立项目或上游页面需要低耦合接入时使用。

不要因为 Agent 能生成 React 代码，就默认创建一套新的前端工程。结构化 View 更容易保持一致、升级和检查。

## 默认技术

- 页面：React + Vite。
- 普通图表、K 线和金融图表：ECharts。
- Markdown：react-markdown，并保持原始 HTML 禁用。
- Agent 生成、需要固化和版本化的关系网络：Newma-Dock Graph Artifact + Archify。
- 高频实时变化的关系网络：Cytoscape.js；简单关系图继续使用 ECharts Graph。
- 3D：Three.js / React Three Fiber。
- 地图：MapLibre。
- 视觉变量：`@newma-dock/desk-ui/tokens.css`。

后四项属于扩展能力，没有明确需要时不提前加入 Mod 依赖。

## 页面必须提供的信息

- 页面标题和用途说明。
- 当前数据时间。
- 数据来源。
- 加载状态。
- 空数据状态。
- 错误或离线状态。
- 最后成功结果。

页面不得在 HTML、JavaScript、Manifest 或 View Schema 中保存 API Key、Token 和其他 Secret。

## HTML 语义

View Renderer 输出机器可读的 HTML：

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

`data-vibe-*` 是稳定的协议前缀，产品更名不会迫使已经发布的 View 修改 HTML：

- `data-vibe-page`：ViewSpec 版本。
- `data-vibe-title`：页面标题。
- `data-vibe-block`：区块类型。
- `data-vibe-block-id`：跨版本保持稳定的区块 ID。
- `data-vibe-value-path`：指标对应的数据路径。
- `data-vibe-rows-path`：表格对应的数据路径。
- `data-vibe-option-path`：图表配置路径。
- `data-vibe-content-path`：Markdown 内容路径。
- `data-vibe-artifact-renderer`：Artifact 使用的确定性渲染器。
- `data-vibe-artifact-url-path`：Artifact View URL 在数据中的路径。

图表同时输出安全 JSON：

```html
<script type="application/json" data-vibe-chart-option>
  {"xAxis":{"data":["上证指数"]},"series":[{"data":[0.8]}]}
</script>
```

该节点不是可执行脚本。Agent 可以直接读取图表数据，无需分析 Canvas 像素。

## 稳定性规则

- 发布后不要随意更换区块 ID。
- 数据结构改变时生成新的 Mod 修订版本。
- 单纯数据刷新不改变 Mod Manifest。
- 图表必须保留机器可读配置。
- 重要数据不能只用颜色表达。
- 表格使用真实 `<table>`，不使用纯 Canvas 模拟。
- 复杂 3D 或关系图额外提供节点、边、对象或场景数据。
- Agent 生成的关系图必须保存结构化节点和边；图片或文本树只能作为降级视图。
- 交互 View 和未来的静态 Agent HTML 来自同一份 Schema 和数据。

## Artifact 区块

`artifact` 用于把 Agent 生成的复杂成果作为可版本化对象嵌入 View。当前标准
渲染器为 `archify`。Mod 提交的是 Newma-Dock Graph Artifact，API 负责转换、校验、
渲染和持久化；Mod 不依赖 Archify 的内部 JSON 格式。

```json
{
  "id": "industry-graph",
  "type": "artifact",
  "title": "产业链关系",
  "renderer": "archify",
  "urlPath": "artifacts.industry.viewUrl",
  "specPath": "artifacts.industry.spec",
  "height": 620
}
```

Artifact View 使用受限 iframe。`specPath` 对应的结构化数据会同时写入不可执行的
`application/json` 节点，供 Agent、无障碍降级视图和后续迁移直接读取。

Graph Artifact 的标准生命周期：

1. Agent 或 Mod 生成 `nodes`、`edges`、来源与原始研究文本。
2. `POST /api/artifacts` 创建草稿并用 Archify 生成可交互 View。
3. 用户检查图谱、节点表和原文后，调用 `POST /api/artifacts/{id}/publish` 固化版本。
4. Mod 通过 `GET /api/artifacts?module_id={modId}` 恢复历史版本。

## 标准页面骨架

产业链研究、Alpha Lab 和 Backtest Lab 应复用同一套指标、图表、表格、Markdown 和操作组件。不同研究主题只替换标题、数据和内容，不重新定义颜色、间距与交互结构。

示例：

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
