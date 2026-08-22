# Newma-Desk 十六大栏目与 Mod 接入标准

## 1. 目的

一级导航是投资体系的长期产品边界，不跟随来源仓库、技术栈、服务端口或项目更名变化。页面按唯一主职责进入一个栏目，跨栏目复用通过 Mod Wiki Graph 完成，不复制页面。

一个运行时可以提供多个 Mod Suite。每个 Suite 必须围绕一项完整业务能力，并整体归入一个栏目；同一页面不得重复出现在多个 Suite。运行时、数据、Agent Workspace 与导航归属彼此解耦。

## 2. 固定栏目

| 顺序 | 稳定 ID | 名称 | 能力边界 |
| --- | --- | --- | --- |
| 0 | `global-intelligence` | 全球 | 全球态势、新闻、地缘冲突、海外专题、事件与催化剂 |
| 10 | `fundamentals` | 宏观 | 周期叠加、经济基本面、增长通胀、金融条件与经济预测 |
| 20 | `policy-intelligence` | 政策 | 政策日历、政策流、量级、历史对比与影响解读 |
| 30 | `capital-flow` | 资金 | 跨境资金、流动性、ETF 与个股资金、筹码及风险偏好 |
| 40 | `market-surface` | 市场 | 行情、复盘、云图、技术结构、强弱、宽度与市场情绪 |
| 50 | `industry-research` | 行业 | 产业链、行业比较、景气选择、资金扩散与行业 ETF 轮动 |
| 60 | `equity-research` | 公司 | 公司基本面、财报、投资逻辑、同业、估值与研究档案 |
| 70 | `fund-research` | 基金 | 公募基金、ETF、基金经理、同类比较、评价与业绩归因 |
| 80 | `asset-allocation` | 配置 | 战略资产配置、目标权重、研究组合、再平衡与绩效归因 |
| 90 | `trading` | 交易 | 战术择时、交易计划、纸面执行、复盘回放与执行记录 |
| 100 | `strategy-research` | 策略 | 研究线索、条件筛选、策略验证、候选池与观察组合 |
| 110 | `risk-management` | 风险 | 集中度、暴露、相关性、回撤、压力测试与风险贡献 |
| 120 | `quant-research` | 量化 | 因子、策略实验、回测、相关性分析与可复现研究账本 |
| 130 | `investment-committee` | 投决 | 研究收敛、投委讨论、决策记录、反方意见与复核 |
| 140 | `creator-studio` | 创作 | 内容采集、研究转写、多媒体生产、发布与传播复盘 |
| 150 | `deepsee` | 深瞳 | 消息、邮件、会议、自媒体与外部信息触达分析 |

代码唯一来源是 `packages/contracts/src/investmentDomain.ts`。Shell 不得复制栏目列表。

## 3. Manifest 接口

独立 Mod 在 `manifest.navigation.project` 声明栏目：

```json
{
  "navigation": {
    "groupLabel": "公司",
    "groupOrder": 60,
    "itemOrder": 20,
    "label": "财报研究",
    "project": {
      "id": "equity-research",
      "name": "公司",
      "order": 60,
      "description": "公司基本面、财报、投资逻辑、同业、估值与研究档案。"
    },
    "icon": "research"
  }
}
```

Suite 的共享 `navigation.project` 声明唯一栏目，`navigation.directory.id` 必须等于 Suite ID。页面只覆盖标签、顺序和页面自身能力，不能覆盖项目或栏目。

```json
{
  "id": "source-company-suite",
  "manifest": {
    "navigation": {
      "groupLabel": "公司",
      "groupOrder": 60,
      "directory": {"id": "source-company-suite", "label": "公司研究", "order": 10},
      "project": {"id": "equity-research", "name": "公司", "order": 60}
    }
  },
  "pages": [
    {"id": "earnings-workbench", "navigation": {"itemOrder": 10}},
    {"id": "valuation-workbench", "navigation": {"itemOrder": 20}}
  ]
}
```

## 4. 归属规则

1. 页面按主要决策问题归属，不按技术来源归属。
2. 同一页面只有一个主栏目；相关栏目使用 Wiki Link 跳转。
3. 同一运行时跨多个职责时拆成多个 Suite，继续复用原运行时、数据与 Agent Workspace。
4. 公司回答“这家公司值不值得研究”，策略回答“哪些对象满足规则”，配置回答“组合怎么配”，风险回答“可能损失多少”，交易回答“何时及如何执行”。
5. 数据 Provider 与 Agent-only Skill 不创建导航页面。
6. 页面标题由 Desk 外框持有；内嵌页面不得重复主标题。

## 5. 自动行为

- 一级栏始终使用两字中文名称并支持纵向滚动。
- 二级栏直接显示页面，不显示来源文件夹。
- “栏目数据与能力”固定在面板底部。
- 页面只能在自己的栏目内排序，不能通过用户偏好改变主归属。
- 新旧栏目 ID 迁移时，Navigation Compiler 清理失效偏好。

## 6. 接入检查

1. Suite ID 与 `navigation.directory.id` 一致。
2. Suite 内所有页面继承同一栏目和项目身份。
3. 页面 ID、事件和数据能力不包含部署地址。
4. External Mod Runtime 不可用时独立降级，不影响 Desk 核心服务。
5. 通过合同、Mod Store、导航、主题、数据和兼容性检查。
6. 涉及真实下单、券商凭据或不可逆操作的能力不得默认接入。
