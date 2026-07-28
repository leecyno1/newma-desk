# vibe-visualization 简化版基座设计

> 历史文档：产品已于 2026-07-21 更名为 Newma-Desk。当前词汇和命名以 [产品词汇与模块命名](../../product-language.md) 为准。

日期：2026-07-20

## 1. 产品定义

`vibe-visualization` 是一个带默认界面、默认数据接入方式和统一网页生成规范的可视化基座。

它不以空白插件框架为目标，而是直接继承 Vibe-Research 与 Vibe-Trading 已经验证过的研究、量化和交易界面结构，形成一个默认可用的 Web Base。新的页面作为独立 Module 接入，既可以显示在统一侧边栏中，也可以通过独立 URL 打开。

产品由五个简单部分组成：

1. 默认 Web Base：统一侧边栏、模块容器、Research/Trading 视觉风格。
2. Module：独立 HTML 页面及其模块配置。
3. Vibe HTML：统一的颜色、排版、组件、页面模板和机器可读 HTML 规范。
4. Data：Vibe-Research、Vibe-Trading 和其他服务继续作为独立数据后端。
5. AI：Model Gateway 与 Agent Gateway 两条可切换、互不串联的入口。

## 2. 当前阶段原则

- 保留单前端、双上游后端和一个基座 API。
- 不合并 Vibe-Research 与 Vibe-Trading 的业务后端。
- 不建设公共市场、多人协作和复杂租户体系。
- 不让 Agent 通过截图或鼠标自动化理解页面。
- 不让普通模型调用强制经过 Agent。
- 不让 Agent 调用强制经过 Model Gateway。
- 不重新设计一套与现有 Research/Trading 完全不同的视觉风格。
- 新模块应通过配置加入基座，不应要求修改基座核心业务判断。

## 3. 默认基座

默认侧边栏以两类工作为主：

```text
研究
├── 每日复盘
├── 资讯自选
├── 持仓研报
├── 股票行情
├── 个股分析
└── 产业链研究

量化
├── Alpha Zoo
├── 因子挖掘
├── 回测报告
└── 交易控制台
```

基座只负责统一导航、视觉、数据入口、AI 入口和模块状态。模块内部业务保持隔离，便于继续同步两个上游仓库。

模块配置需要同时描述页面与导航信息：

```json
{
  "id": "market-daily",
  "name": "每日股票行情",
  "category": "market",
  "navigation": {
    "groupLabel": "市场",
    "groupOrder": 20,
    "itemOrder": 10,
    "icon": "market"
  },
  "entry": {
    "type": "structured",
    "url": "/modules/market-daily/"
  }
}
```

Shell 不再保存固定的分类中文名称和顺序。新增模块只需提供配置并发布，侧边栏自动出现。

## 4. Vibe HTML

Vibe HTML 是供人和 Agent 共同使用的网页规范。人看到美观的交互页面，Agent 直接读取页面 HTML、语义标签和嵌入数据，不依赖截图识别。

### 4.1 统一视觉基础

第一版从当前 Web Research、Web Trading 和 market-daily 的深色界面中提取公共变量：

- 背景、表面、边框和文字颜色。
- 上涨、下跌、警告、成功和错误颜色。
- 字体、字号、行高和等宽字体。
- 间距、圆角、控件高度和动画时间。

第一阶段只提取现有风格，不进行大规模视觉重做。

### 4.2 第一版标准内容元素

- 页面标题与说明。
- 指标卡。
- 数据表格。
- ECharts 图表。
- Markdown。
- 筛选器。
- 操作按钮。
- 数据时间、来源、加载、空数据和错误状态。

后续扩展元素使用相同风格：

- K 线、收益曲线、回撤、相关性矩阵。
- 产业链图、关系网络、时间线和地图。
- 图片、视频、文件和代码。
- Three.js / React Three Fiber 3D 场景。

### 4.3 机器可读 HTML

所有标准页面和区块必须输出明确的语义属性：

```html
<main data-vibe-page="1.0" data-vibe-title="每日股票行情">
  <section data-vibe-block="chart" data-vibe-block-id="index-trend">
    <h2>主要指数涨跌</h2>
    <div data-vibe-visual></div>
    <script type="application/json" data-vibe-chart-option>
      {"xAxis":{"data":["上证指数"]},"series":[{"data":[0.8]}]}
    </script>
  </section>
</main>
```

规则：

- 指标和表格使用真实语义 HTML，不只画在 Canvas 中。
- 图表必须保留 ECharts 配置的安全 JSON 表达。
- Markdown 转换为语义 HTML，禁止任意原始 HTML。
- 页面根节点声明 Vibe HTML 版本和页面标题。
- 区块声明类型和稳定 ID。
- 交互页面与未来的静态 Agent HTML 必须来自同一份 View Schema 和数据，避免内容分叉。

第一阶段先保证浏览器渲染后的 HTML 语义统一；后续增加同源的静态 Agent HTML 输出，使 Agent 可以只通过 HTTP 获取完整页面内容。

## 5. Model Gateway 与 Agent Gateway

两条链路并列存在：

```text
Module -> Model Gateway -> 选定模型
Module -> Agent Gateway -> 选定 Agent -> Skills / 工具 / 数据 / 长期记忆
```

Model Gateway：

- 传统模型调用。
- 接收用户问题和当前页面内容。
- 默认不保存 Module 长期记忆。
- 可以切换 GPT、Claude、本地模型或其他兼容提供商。

Agent Gateway：

- 接入 Hermes、Codex 或其他 Agent Runtime。
- Agent 记忆按 `用户 + Agent + Module` 隔离保存。
- 保存历史摘要、研究假设、页面版本、运行结果和待办任务。
- Agent 自己决定使用哪个模型；基座不强制将其转发给 Model Gateway。

前端需要提供清晰的模式选择，但该工作作为独立阶段实现，不与 Vibe HTML 第一阶段混在一个提交中。

## 6. 暂缓范围

当前暂缓：

- 公共模块市场。
- 多租户和团队权限。
- 跨设备实时事件网络。
- 完整在线 IDE。
- 复杂 Artifact 平台；现阶段继续使用 Snapshot 保存结果和历史。
- 完整图形化 Module Studio；现阶段继续由 Agent 或配置文件创建模块。

## 7. 第一阶段验收

- Shell 品牌改为 Vibe Visualization，不再显示 Research Shell。
- 侧边栏分组名称、顺序和图标来自 Module Manifest。
- 现有 market-daily 模块继续正常工作。
- Shell 和模块共享同一套基础视觉变量。
- Structured Renderer 输出统一的 `data-vibe-*` 语义 HTML。
- ECharts 区块在 HTML 中包含安全、机器可读的图表配置。
- 现有构建、单元测试和 E2E 不回归。
