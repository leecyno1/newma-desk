# Newma-Desk 十四大投资栏目与完整项目接入标准

## 1. 目的

Newma-Desk 的一级导航固定为十四个核心投资栏目，并保留一个“其他”兜底栏目。栏目是用户理解投研流程的长期产品边界，不随来源仓库、技术栈、服务端口或项目更名而改变。

页面运行服务与导航归属必须解耦，但项目边界不能被破坏：一个完整来源项目必须整体放入一个栏目，不能按页面功能拆到多个栏目。一个栏目可以容纳多个完整项目。页面 ID、入口 URL、Agent Workspace 和数据服务仍由来源项目维护。

## 2. 固定领域

| 顺序 | 稳定 ID | 显示名称 | 主要范围 |
| --- | --- | --- | --- |
| 10 | `market-surface` | 市场面 | 行情监控、看盘、扫描、复盘 |
| 20 | `fundamentals` | 宏观面 | 经济数据、指标、行业、产业链、事件 |
| 30 | `global-intelligence` | 海外面 | 海外流动性、地缘、军事、科技、全球市场 |
| 40 | `capital-flow` | 资金面 | 资金流、筹码、龙虎榜、情绪、技术结构 |
| 50 | `policy-intelligence` | 政策面 | 政策、会议、新闻、舆情、发言、传闻 |
| 60 | `cycle-research` | 周期研究 | 七周期及扩展周期框架 |
| 70 | `asset-allocation` | 资产配置 | 均值方差、BL、风险评价、再平衡、目标波动率 |
| 80 | `tactical-timing` | 战术择时 | 行业比较、行业轮动、择时、ETF 轮动 |
| 90 | `equity-research` | 个股研究 | 选股、基本面、财报、同业、估值 |
| 100 | `fund-research` | 基金研究 | 基金、ETF、基金经理与产品比较 |
| 110 | `bond-research` | 债券研究 | 利率、信用、可转债与固定收益 |
| 120 | `quant-research` | 量化研究 | 因子、策略、回测、相关性、量化实验 |
| 130 | `investment-committee` | 投决会 | 研究收敛、投委讨论、决策记录与复核 |
| 140 | `trading-risk-portfolio` | 交易、风控与组合管理 | 执行、风险、持仓、组合、绩效 |
| 150 | `other` | 其他（兜底） | 管理工具和暂未归类的完整项目 |

代码唯一来源是 `packages/contracts/src/investmentDomain.ts`。Shell 必须从该注册表生成一级入口，不得在组件中复制领域列表。

## 3. Manifest 接口

独立 Mod 在 `manifest.navigation.project` 声明领域：

```json
{
  "navigation": {
    "groupLabel": "个股研究",
    "groupOrder": 90,
    "itemOrder": 20,
    "label": "财报研究",
    "project": {
      "id": "equity-research",
      "name": "个股研究",
      "order": 90,
      "description": "选股、公司基本面、量化选股、财报、同业与估值研究。"
    },
    "icon": "research"
  }
}
```

完整项目必须用 Mod Suite 接入。Suite 的共享 `navigation.project` 声明唯一栏目，`navigation.directory` 声明完整项目身份；所有页面继承二者，禁止页面级覆盖：

```json
{
  "id": "source-research-suite",
  "manifest": {
    "navigation": {
      "groupLabel": "宏观面",
      "groupOrder": 20,
      "directory": { "id": "source-research-suite", "label": "Source Research", "order": 10 },
      "project": { "id": "fundamentals", "name": "宏观面", "order": 20 }
    }
  },
  "pages": [
    {
      "id": "daily-review",
      "navigation": {
        "itemOrder": 10
      }
    },
    {
      "id": "stock-research",
      "navigation": {
        "itemOrder": 20
      }
    }
  ]
}
```

`navigation.directory.id` 必须等于 Suite ID，确保发现、安装、设置、Agent Workspace 和导航都指向同一个完整项目。页面可保留独立路由、权限和 Agent Context，但不能覆盖 `project`、`directory`、`groupLabel` 或 `groupOrder`。

## 4. 自动行为

- Shell 始终显示十四个核心栏目和“其他”，尚无项目的栏目显示空状态和栏目设置。
- 点击有页面的领域默认打开第一个页面；点击空领域直接打开领域设置，不保留上一个 Mod。
- 一级标志由领域中文名称自动取前两个汉字，例如市场面为“市场”、债券研究为“债券”。
- 用户可在本地 Workspace 覆盖标题、排序和冻结状态，稳定领域 ID 不变。
- 页面拖拽只允许在所属完整项目内调整顺序，不能把页面移出项目或改变栏目。
- 未完成栏目判断的新项目整体进入 `other`，确认业务边界后整套迁移。
- Suite Compiler 在发现和安装阶段拒绝跨栏目、跨项目目录的页面覆盖。

## 5. 服务边界

当前迁移只改变导航与产品归属，不改变 URL、端口、依赖或数据接口。未来按“一大模组一个服务、一个地址”收敛时，十四个核心栏目和“其他”的稳定 ID 继续保持不变；迁移服务只更新运行描述和路由。

每个大模组服务应拥有独立运行环境、锁文件、健康检查和稳定地址。公共数据、Agent、存储和事件能力通过 Desk 统一接口调用，避免跨模组复制客户端、密钥和缓存。

## 6. 接入检查

新 Mod 合入前必须确认：

1. 完整项目只声明一个最主要的投资栏目。
2. `directory.id` 等于 Suite ID，所有原有页面完整保留在同一 Suite。
3. 页面不得覆盖栏目、项目目录或旧导航分组。
4. 页面 ID、事件和数据能力不包含具体部署地址。
5. 设置页只管理该完整来源项目真正共享的配置。
6. 没有合适栏目时整套进入 `other`，不得临时创建新一级栏目。
7. 通过合同、Mod Store、导航、主题和兼容性测试。

外部金融仓库还必须先登记到 [`config/finance-project-intake.json`](../config/finance-project-intake.json)，并通过 `npm run finance:intake:check`。准入清单为每个来源仓库固定唯一接入形态、主栏目、版本快照和启用门槛；数据 Provider 与 Agent 能力来源不得为了填充菜单而声明独立 Mod 页面。完整审计和十五栏填充方案见 [`finance-project-intake-2026-08-06.md`](./integrations/finance-project-intake-2026-08-06.md)。

报告型 Skill 默认 `Agent-only`：从当前 Mod 或 Numa Agent 对话调用，结果以消息、折叠报告或 Artifact 返回，不创建页面、导航和独立服务。只有持续交互、状态管理或可视化本身构成工作台时，才允许进入 Mod 页面。

Agent-only 能力按当前 Mod 所属栏目自动继承：Desk 后端读取已发布 Manifest 的稳定 `project.id` 并匹配准入清单中的 `consumers`。能力清单只在普通问答进入统一 Agent 前附加，修改模式不附加；清单是允许尝试的方法集合，不代表相关外部 Provider 已配置。缺失能力必须明确降级，不能伪装成已执行结果。
