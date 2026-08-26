# 外部 Skills 综合评测与注册（2026-08-21）

评测范围：用户指定 23 个候选（Qoder 宿主 skills）。
评测框架：对自媒体六环节（intake/brief/draft/transwrite/publish/postmortem）的增益，按治理规范（docs 的 skill-registry-governance：需有具体环节调用方才晋升）执行。

## 结论：注册 5 个，备案 3 个，不注册 15 个

### 注册（高价值，已挂载环节/节点）

| Skill | 环节/节点 | 价值与用法 |
| --- | --- | --- |
| **baoyu-diagram** | transwrite/article_build | 结构类说明图（SVG：产业链/架构/流程/时序图）——与账号角色插图互补：角色图讲概念，diagram 讲结构。T01 产业链账本类选题的刚需 |
| **drafter-diagram** | transwrite/article_build | 同上备选风格（Flat Engineering Blueprint 深色工程蓝图风）——科技类选题的结构图变体 |
| **content-research-writer** | draft/article_draft | 写作方法增强：research→引用→hook→outline 迭代循环。用于深度选题（LLM 直生骨架前的结构化写作流程） |
| **image-enhancer** | transwrite/visual_package | 图片后处理：ImageGen 出图→发布前分辨率/清晰度增强（封面与插图的缩略图质量保障） |
| **market-research-reports** | draft（深度模式） | McKinsey/BCG 风格市场研究报告生成（LaTeX+图表）——重武器，特定选题（如行业深度）时启用 |

### 备案（有场景但非现在）

| Skill | 场景 | 说明 |
| --- | --- | --- |
| theme-factory | transwrite 排版 | 10 预设主题可扩展公众号 HTML 排版多样性；当前品牌样式已定型，备选 |
| analytics-data-analysis | draft/evidence | Jupyter 数据分析最佳实践；已有 dasheng-finance-data 专门化，作参考 |
| cloudflare-deploy | publish 基建 | 发布面板/内容站上线部署时启用 |

### 不注册（15 个）

- **与创作无关**：baoyu-electron-extract（逆向）、internal-comms（内部沟通）、lead-research-assistant（销售）、slack-gif-creator（Slack GIF）、vm-error-recovery（工作区恢复）、plugin-creator（插件开发）、claude-api（LLM 工程基建——项目 LLM 层走 qoder-cli/K2.7）
- **非当前创作形态**：general-ppt、qoderwork-ppt（PPT 类）、quickbi-smartq-chat（企业 BI，无环境）
- **通用工程已被等价物覆盖**：create-plan（已有 docs/plans 模式）
- **未在当前会话暴露（无法评测）**：changelog-generator、grill-me、linear、setup-pre-commit、to-issues

## 注册方式

1. configs/skills/external_skill_candidates.json 追加上述 5+3 项（宿主 skill，非 vendored）
2. registry 节点描述挂载（article_build/article_draft/visual_package 的描述注明可用 skill）
3. 使用约定：说明图=角色插图（账号 DNA）+结构图（baoyu-diagram 家族）+数据图（matplotlib）三分法

## 使用三分法（固化为插图路由规则）

- **概念图**（角色讲概念）→ 账号 DNA 角色系统（dasheng-account-illustrations）
- **结构图**（产业链/流程/架构）→ baoyu-diagram / drafter-diagram（SVG，可缩放不失真）
- **数据图**（行情/统计）→ matplotlib + Tushare（永不角色化）
