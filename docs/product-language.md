# Newma-Desk 产品词汇与命名

更新日期：2026-08-18

## 产品定义

Newma-Desk 是一个面向人和 Agent 的可生长工作台。用户可以把临时需求固化成长期可使用、可更新、可继续迭代的 Mod。

推荐对外表述：

> 把一次需求，变成一个长期可用的 Mod。

## 统一词汇

| 产品词汇 | 定义 | 代码名称 |
| --- | --- | --- |
| Newma-Desk | 产品整体 | `newma-desk` |
| Desk | 默认前端、侧边栏和运行容器 | `@newma-desk/desk` |
| Mod | 可安装、发布和升级的功能单元 | `ModManifest` |
| View | Mod 中可独立访问的 HTML 页面 | `View` |
| Skill | Agent 可重复执行的工作流和技巧 | `Skill` |
| Desk UI | 统一视觉变量和基础组件 | `@newma-desk/desk-ui` |
| ViewSpec | 面向人和 Agent 的 HTML 语义规范 | `ViewSchema` |
| Mod SDK | 数据、AI、导航和跨 Mod 通信入口 | `@newma-desk/mod-sdk` |
| Mod Bridge | Desk、Mod 和其他页面之间的事件桥 | `ModBridge` |
| Mod Library | Mod 安装、启停和更新入口 | 后续 MVP |

## 边界

- Skill 回答“Agent 怎样完成工作”。
- Mod 回答“用户和 Agent 在哪里长期查看和操作”。
- View 是 Mod 中的具体页面，不承担安装和发布职责。
- 一个 Mod 未来可以有多个 View；当前 MVP 保持一个 Mod 对应一个主 View。
- Agent Gateway 管理 Agent 的长期 Session；Model Gateway 只进行传统模型调用。

## 默认导航

一级模块固定为：全球、宏观、政策、资金、市场、行业、公司、基金、配置、交易、策略、风险、量化、投决、创作、深瞳。显示名称使用两个汉字；稳定 ID 和完整能力边界见 [`investment-domain-mod-standard.md`](./investment-domain-mod-standard.md)。

二级面板直接显示 Mod 页面，不显示来源项目文件夹。自定义项目直接进入一级列表；Desk 的 Provider、权限和 Agent 接入统一放在面板底部“栏目数据与能力”。

当前示例的历史 ID 仍为 `market-daily`，但产品名称和 npm 包已经使用 Market Pulse。等数据迁移机制稳定后，再将持久化 ID 迁移为 `market-pulse`，避免现在破坏既有 Snapshot、Agent Session 和上游调用。

## 上游项目

Vibe Research 和 Vibe Trading 只表示代码来源，不再直接成为用户侧导航分组：

```text
integrations
├── vibe-research
└── vibe-trading
```

它们通过适配层向 Newma-Desk 提供数据或页面，业务后端继续独立部署和独立升级。

## 迁移规则

新代码统一使用 `Mod`；旧 `Module` 名称只作为兼容层保留。兼容层不能扩展新功能，新增能力应首先出现在 Mod API 中。

`vibedesk:*` Bridge 消息、`vibedesk.*` 本地存储键和 `VIBEDESK_*` 环境变量属于 1.x 兼容协议。新产品名称不直接改写这些持久化标识；后续采用双读双写迁移，避免既有 Mods、用户布局和会话失效。
