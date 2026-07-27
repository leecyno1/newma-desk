# 市场终端架构与 Mod 边界

日期：2026-07-24

## 方案结论

市场行情统一采用三层结构：

```text
KLineChart 图表内核
        ↑
市场终端 Mod（OpenTerminalUI 风格的高密度交互）
        ↑
Newma-Dock Data Service + Bridge + Mod Context + Desk Copilot
```

- KLineChart 只负责 K 线、指标、画线与可视区间，不承载数据源或 Agent 逻辑。
- OpenTerminalUI 仅作为信息密度、快捷操作和终端布局参考，不复制它的业务代码。
- 行情、搜索、报价、K 线、指数和市场概览统一经过 `market-data` Data Service。
- 当前标的、周期、复权、指标、可视区间和报价摘要通过 Mod Context 交给 Desk。
- 提问和修改统一使用 Newma-Dock 右侧 Desk Copilot；市场终端内部不再保留重复的 Agent、模型选择和回答区。

## 当前能力

- A 股、港股、美股统一标的协议和跨市场搜索。
- 单股与批量报价、日周月及分钟 K 线、A 股复权。
- MA、EMA、BOLL 主图；VOL、MACD、RSI、KDJ 副图。
- 趋势线、水平线、斐波那契和清除画线。
- 盘口、估值、成交指标、市场宽度、指数、行业资金、成交额榜和全球指数。
- 用户自定义自选分组，默认提供 10 个跨市场示例标的。
- 白色默认主题，支持 Desk 明暗主题和系统深色模式。

## Chart Kit 与第一批图表 Mods

通用图表能力已经抽取到 `@newma-dock/chart-kit`。市场终端和新图表 Mods 共用同一套 KLineChart 生命周期、主题、指标、画线接口和相对强弱图表，不再各自维护图表初始化代码。

第一批图表工作区以五个独立 Level 3 Mods 发布，但共享 `market-daily` 运行时：

| Mod | 工作区入口 | 当前能力 |
| --- | --- | --- |
| 市场扫描器 | `?workspace=scanner` | 多市场过滤、AND/OR 条件表达式、保存/更新/删除组合、候选排序与标的联动。 |
| 多周期看盘 | `?workspace=multi-timeframe` | 日线、60 分钟、15 分钟、5 分钟四图联动、共享十字光标和聚焦布局。 |
| 相对强弱地图 | `?workspace=relative-strength` | 多标的归一化曲线、阶段排名与跨市场比较。 |
| 事件时间轴 | `?workspace=event-timeline` | 合并公告/财报/新闻/研报证据与 OHLCV 事件，保留来源、链接和证据 ID。 |
| 交易回放室 | `?workspace=trading-replay` | 隐藏未来数据、逐根播放、模拟买卖、交易点图层与 Replay Artifact。 |

每个工作区拥有独立 Mod ID、商店条目、侧边栏名称、本地状态和 Agent Context；部署时仍只需要一个 `5891` 前端进程。

## 与其他 Mods 的边界

| Mod | 处理结论 | 与市场终端的关系 |
| --- | --- | --- |
| 旧市场行情快照 | 完全替代 | 所有一级市场行情入口统一指向市场终端。 |
| 自选股 | 保留并升级 | 市场终端提供快速查看；自选股负责完整 CRUD、标签、排序、导入导出和批量维护。后续共享同一 Watchlist Service。 |
| 我的持仓 | 保留 | 成本、数量、仓位、盈亏和账户属于组合账本，不应进入纯行情终端。可复用行情报价和 K 线。 |
| 个股研究 | 保留 | 接收 `security.selected`，负责财务、估值、事件、研报、观点与研究沉淀。市场终端负责发现和切换标的。 |
| 资讯雷达 | 保留 | 独立承担新闻流、来源、主题追踪和舆情；可根据当前标的过滤，不嵌入行情终端形成重复信息流。 |
| 每日复盘 | 保留 | 使用市场终端的市场快照生成复盘，负责日级结论与归档，不重复实现实时行情面板。 |
| 产业链研究 | 保留 | 使用标的和行业事件联动，承担关系图谱和产业链沉淀，不能被价格图表替代。 |
| 量化总览 | 保留但瘦身 | 只展示策略、任务、信号和运行状态；通用行情、搜索和图表直接复用市场协议。 |
| 因子实验室 | 保留 | 因子定义、IC、分层和实验记录属于研究层；标的选择和行情数据复用终端协议。 |
| 回测实验室 | 保留 | 交易日历、撮合、费用、结果和报告属于策略验证层；图表可复用 KLineChart 展示净值和交易点。 |
| 相关性分析 | 保留 | 负责多标的、多因子矩阵；接收终端当前标的作为候选输入。 |
| 交易台 | 保留 | 订单、风控、确认、持仓和执行必须独立于行情浏览；可嵌入同一图表内核，但不能与市场终端合并权限。 |

## 已落地的共享能力

1. 事件时间轴通过 `market.announcements`、`market.reports`、`market.news` 接入真实证据；海外数据源未启用时显式显示 `unsupported`，不会生成虚构事件。
2. Chart Kit 已提供通用注释/信号图层、交易点图层与跨图表十字光标组；用户画线和系统注释使用独立 overlay group。
3. 市场扫描器已支持 AND/OR 条件表达式，覆盖涨跌幅、量比、成交额、PE、PB，并可在本机保存、恢复、更新和删除。
4. 交易回放可保存为 Newma-Dock Replay Artifact，API 提供创建、列表、最近、读取、发布和受 CSP 保护的 HTML 查看页。
5. Desk Agent 可通过标准 UI Action 协议执行 `market.refresh`、`market.set-timeframe`、`chart.set-indicator`、`market.set-alert`、`workspace.save-layout`；动作受当前 Mod Manifest 和页面上下文约束。

下一阶段可把扫描表达式作为量化实验室输入，并让 Replay Artifact 与每日复盘、研究笔记建立显式引用关系。

## 数据服务部署

`market-data` 的描述文件保留稳定能力 ID，实际服务地址由 `NEWMA_DOCK_RESEARCH_BASE_URL` 覆盖。这样本地进程内 Research Suite、测试假服务和未来独立数据服务可以复用同一前端协议，避免把端口写死在 Mod 中。

Research 与 Trading 当前作为 `mod-projects/` 下的内置领域源码，由 Newma-Dock API 进程内挂载。它们保留独立 Git 历史用于上游同步，但标准用户不需要单独启动两个服务。
