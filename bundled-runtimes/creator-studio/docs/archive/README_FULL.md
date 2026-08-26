# 大圣自媒体工作流系统 (Newma Media Studio)

[![Production Ready](https://img.shields.io/badge/production-ready-brightgreen.svg)](docs/PRODUCTION_READINESS_STATUS.md)
[![Tests](https://img.shields.io/badge/tests-87%20passed-success.svg)](tests/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Node.js](https://img.shields.io/badge/node-18.0%2B-green.svg)](https://nodejs.org/)

端到端的中文社交媒体内容创作自动化系统，支持微信公众号、小红书、微博、抖音、知乎等平台的内容生产与分发。

## 📋 目录

- [系统概述](#系统概述)
- [核心特性](#核心特性)
- [架构设计](#架构设计)
- [7阶段工作流](#7阶段工作流)
- [快速开始](#快速开始)
- [技能体系](#技能体系)
- [使用指南](#使用指南)
- [配置说明](#配置说明)
- [开发文档](#开发文档)

## 系统概述

大圣自媒体工作流系统是一个**生产级的AI驱动内容创作平台**，实现了从内容采集、选题分析、初稿生成、素材收集、渠道改写、分发发布到数据复盘的全流程自动化。

### 设计理念

- **Manifest驱动架构**：每个阶段产出规范的JSON manifest作为状态源（source of truth）
- **人机协同（HITL）**：关键决策点设置人工审核门控（gate），确保内容质量
- **渠道适配**：同一内容自动生成适配不同平台的多个版本（微信热点版/常规版、小红书热点版/常规版）
- **质量保障**：内置质量评分系统，自动重试机制，确保输出达标（≥8.0/10分）

### 适用场景

- 自媒体团队的日常内容生产
- 财经/科技/时事评论类公众号运营
- 多平台内容矩阵管理
- 内容创作流程标准化

## 核心特性

### ✅ 全流程自动化
- 自动采集多源数据（微信公众号、新闻网站、Reddit、Hacker News等）
- AI驱动的选题分析与推荐
- 结构化初稿生成（含论证链和证据映射）
- 自动素材收集（图表、图片、视频、引用）
- 多版本渠道改写（4个版本/主题）
- 一键分发到多个平台

### ✅ 质量控制体系
- 5维度选题评分（热度/锐度/证据/持久性/读者价值）
- 自动质量评分（≥8.0/10）
- 字数偏差控制（±15%）
- 锚点保留率验证（≥80%）
- 最多3次自动重试

### ✅ 人机协同设计
- 6个HITL门控点（Intake审核、选题确认、结构锁定、素材验收、发布决策）
- 飞书文档实时同步
- 编辑可随时介入修改

### ✅ 多平台适配
- 微信公众号（热点版1300字、常规版1000字）
- 小红书（热点版900字、常规版650字）
- 微博、抖音、知乎（可选）
- 自动生成封面图、标题候选、摘要

## 架构设计

### 三层架构

```
┌─────────────────────────────────────────────────────────────┐
│                      素材层 (Materials)                       │
│  原始输入：抓取文章、研究数据、图表、图片                      │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                      项目层 (Projects)                        │
│  按主题组织的工作目录，每个阶段独立产出                        │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                      引擎层 (Engines)                         │
│  方法库：提示词、模板、风格知识库、DNA配置                     │
└─────────────────────────────────────────────────────────────┘
```

### 执行层组件

```
skills/              # 可执行技能（OpenClaw/Hermes兼容）
scripts/             # Python/Node.js自动化脚本
产物/                # 官方输出产物（按阶段和run_id组织）
core/                # Python编排库
dna/                 # DNA配置（风格/结构/质量默认值）
tests/               # 单元测试套件（87个测试）
```

### DNA系统

DNA系统（`dna/dna_config.yaml`）定义全局默认值：

**风格（Styles）**：
- `luxun` - 锐利/文学化热点风格
- `lemon` - 常规/对话式风格
- `academic` - 分析型
- `hot` / `normal` - 热度级别变体

**结构（Structures）**：`PCIS`（默认）、`PAS`、`CCS`、`Timeline`、`MultiDimension`

**平台字数目标**：
| 平台 | 热点版 | 常规版 |
|------|--------|--------|
| 微信 | 1300字 | 1000字 |
| 小红书 | 900字 | 650字 |
| 抖音 | 500字 | - |

**质量阈值**：初稿≥7.0、改写≥8.0、发布≥8.5（自动重试最多3次）

**AI模型配置**：推理→`claude-opus-4-6`；写作→`claude-sonnet-4-6`；图像→`dall-e-3`

## 7阶段工作流

系统实现标准的7阶段SOP流水线：

```
Intake → Brief → Draft → Material → Rewrite → Publish → Postmortem
  ↓       ↓       ↓        ↓          ↓         ↓          ↓
采集    选题    初稿     素材       改写      发布       复盘
```

### Stage 1: Intake (内容采集)

**目标**：从多个数据源采集当日内容并标准化

**数据源**：
- Port 5173: 推荐笔记/内容研究组
- Port 18080: 新闻报道/Newsrear
- Port 8001/8090: 微信公众号文章（慢源，需重试）
- External: 3个补充热点话题

**关键输出**：
- `01_内容采集_报告.md` - 每个频道Top 10（真实标题+链接）
- `intake_records.json` - 标准化采集记录
- `entity_rankings.json` - 实体频率分析
- `event_clusters.json` - 事件聚类
- `brief_input.json` - Brief阶段输入

**执行**：
```bash
python3 scripts/run_stage1_intake.py
```

**规则**：
- 使用真实抓取标题，禁止生成假标题
- 每条必须有原始链接
- 微信是慢源：重试3次，间隔8秒，最少8条有效
- 热度评级使用频道相对分级：S/A/B/C/D

### Stage 2: Brief (选题分析)

**目标**：AI驱动的选题生成 + 研究简报 + 来源确认

**核心原则**：Brief环节允许**人工介入生成**，AI生成作为辅助选项

**关键输入**（优先级顺序）：
1. `brief_input.json`
2. `channel_top10.json`
3. `event_clusters.json`

**关键输出**：
- `02_编辑Brief库.md` - 编辑向选题卡（5-10个候选）
- `02_研究Brief库.md` - 研究向证据需求
- `topic_cards.json` - 结构化选题卡
- `selected_topics.json` - **必需门控**：编辑选定的选题

**选题卡要求**：
- `topic_kind`、`mother_topic_id`、`angle_variant_of`
- `core_proposition`和`conflict_axis`
- 5维度评分：热度/锐度/证据/持久性/读者价值
- 3-5个证明要求（含当前证据和缺口）

**规则**：
- 母选题不得重叠；每个母选题最多1个变体
- 变体必须指定`changed_dimension`
- 禁止同义词替换制造假选题
- Draft阶段**不能**在没有`selected_topics`门控文件的情况下进行

### Stage 3: Draft (初稿生成)

**目标**：生成带人机协同迭代工作流的初稿

**核心原则**：Draft环节是**人工 + AI迭代循环**，直到编辑approve或确认"中版"

**触发AI生成的条件**：
1. 编辑通过飞书/微信给出明确Brief（含题目、大纲、写作要求）
2. 编辑投喂范文（1篇或多篇），要求AI结合范文生成

**编辑可做的操作**：
- **人工直接写初稿**：编辑可自己写初稿
- **人工修改AI初稿**：直接修改文件内容，给出具体修改意见
- **投喂范文**：提供1篇或多篇参考文章，要求AI结合范文风格/逻辑生成

**迭代循环流程**：
```
编辑修改内容 → 给出具体修改意见 → AI修改相应部分 → 编辑再审
    ↑                                              ↓
    ←←←←←←←←← 直到用户发送"approve"或确认"中版"←←←←←←←
```

**关键输出**：
- `03_ReasoningSheet_<topic>.md` - 论证结构（含论点和证据）
- `03_标准初稿_<topic>.md` - 标准初稿（每个主题一份）
- `final_structure_snapshot.json` - **必需门控**：锁定的结构快照

**结构规则**：
- 顶层章节最多3-4个（绝不超过4个）
- 结构必须继承选题意图，不能机械复制Brief列表
- ReasoningSheet中的每个`Claim`必须映射到`EvidenceItem / MissingProof / ChartNeed`
- 这是**标准基线稿** - 无风格DNA注入，无渠道定制

### Stage 4: Material (素材收集)

**目标**：用图表、图片、视频和数据填补证据缺口

**执行**：
```bash
python3 scripts/material_execute_pack.py --draft-manifest <path/to/draft_manifest.json>
```

**关键输入**：
- `draft_manifest.json`
- `03_ReasoningSheet_<topic>.json`

**关键输出**：
- `05_MaterialPack.md` - 素材包文档
- `material_manifest.json` - 素材元数据
- `material_acceptance.json` - **必需门控**：编辑验收素材
- `pack_assets/<topic>/` - 实际资产文件

**素材绑定**：
每个资产必须绑定到：`claim_id`、`section_id`、`usage_type`、`relevance_score`、`editor_status`

**子能力**：
- 证据图表（TuShare/AkShare数据可视化）
- 视觉参考（抓取图片）
- 生成视觉（AI生成图片）
- 视频资产（动态图形）
- Layer 5增强（FinanceMotionDeck格式）

### Stage 5: Rewrite (改写)

**目标**：渠道特定适配，同时保留结构

**执行**：通过`skills/dasheng-media-sop`

**关键输出**（每个主题4个版本）：
- `<topic>__rewrite_bundle.md` - 所有版本打包
- `<topic>__wechat_luxun_hot.md` - 微信热点版
- `<topic>__wechat_lemon_normal.md` - 微信常规版
- `<topic>__xhs_video_luxun_hot.md` - 小红书视频热点版
- `<topic>__xhs_video_lemon_normal.md` - 小红书视频常规版
- `meta.json` - 带结构继承跟踪的元数据
- `rewrite_manifest.json` - 改写清单

**规则**：
- 必须从`final_structure_snapshot.json`继承
- 跟踪保留了哪些顶层章节
- 跟踪保留/删除/添加了哪些子章节
- 跟踪保留/删除/添加了哪些素材锚点
- 所有版本必须通过字数验证

### Stage 6: Publish (渠道分发)

**目标**：生成可发布的渠道包

**关键输出**：
- `07_发布包.md` - 发布包
- `07_发布计划.md` - 发布计划
- `publish_decision.json` - **必需门控**：最终发布决策
- `publish_manifest.json` - 发布清单

**必须包含**：
- 标题候选
- 封面图候选
- 渠道版本矩阵
- 发布时机建议
- 风险检查清单
- 动态图形视频

### Stage 7: Postmortem (分析复盘)

**目标**：提取经验教训并更新知识库

**执行**：通过`skills/dasheng-daily-postmortem`

**关键输出**：
- `08_复盘报告.md` - 复盘报告
- `08_L1回写建议.md` - L1风格知识库更新建议
- `postmortem_manifest.json` - 复盘清单

**必须更新4个模式库**：
- 选题模式库
- 证据模式库
- 视觉模式库
- 渠道模式库

**最终操作**：用验证过的模式更新`引擎/01_调性分析引擎/STYLE_KNOWLEDGE_BASE.md`

## 快速开始

### 系统要求

- Python 3.10+
- Node.js 18.0+
- Git
- macOS / Linux / Windows with WSL2

### 安装

```bash
# 1. 克隆仓库
git clone <repository-url> /path/to/dasheng-media-workflow
cd /path/to/dasheng-media-workflow

# 2. 安装Python依赖
pip install anthropic requests pytest matplotlib pandas tushare akshare

# 3. 设置环境变量
export DASHENG_PROJECT_ROOT="/path/to/dasheng-media-workflow"
export DASHENG_DESKTOP_ROOT="$HOME/Desktop/自媒体创作"

# 4. 验证安装
python3 -m pytest tests/ -v
python3 scripts/workflow_doctor.py
```

详细安装说明请参阅 [INSTALLATION.md](docs/INSTALLATION.md)

### 运行第一个工作流

```bash
# Stage 1: 采集内容
python3 scripts/run_stage1_intake.py

# Stage 2: 生成选题（AI辅助）
# 使用 dasheng-stage-brief-ai skill 或手动编辑

# Stage 3: 生成初稿（AI + 人工迭代）
# AI接收编辑的Brief/大纲/范文后生成初稿
# 编辑修改后给出意见，AI修改，循环直到approve

# Stage 4: 收集素材
python3 scripts/material_execute_pack.py --draft-manifest <path>

# Stage 5-7: 改写/发布/复盘
# 使用相应的skills
```

## 技能体系

系统包含10个标准化技能，全部采用统一的config.json格式：

### 核心工作流技能

| 技能名称 | 阶段 | 描述 | 版本 |
|---------|------|------|------|
| `dasheng-daily-intake` | Stage 1 | 内容采集 | 4.1.0 |
| `dasheng-daily-phase2` | Stage 2 | 选题分析 | 3.0.0 |
| `dasheng-stage-draft` | Stage 3 | 初稿生成 | 1.0.0 |
| `dasheng-daily-material` | Stage 4 | 素材收集 | 3.1.0 |
| `dasheng-stage-rewrite-v3` | Stage 5 | 渠道改写 | 3.0.0 |
| `dasheng-stage-publish` | Stage 6 | 渠道分发 | 1.0.0 |
| `dasheng-daily-postmortem` | Stage 7 | 分析复盘 | 1.0.0 |

### 编排与工具技能

| 技能名称 | 类型 | 描述 | 版本 |
|---------|------|------|------|
| `dasheng-media-sop` | 编排器 | 主工作流编排器 | 4.0.0 |
| `dasheng-style-profiler` | 工具 | 风格分析与画像 | 1.0.0 |
| `feishu-doc-creator` | 工具 | 飞书文档创建 | 1.0.0 |

### 技能配置标准

所有技能遵循统一的config.json模式（v2.0.0）：

```json
{
  "name": "string",
  "version": "semver",
  "description": "string",
  "stage": "intake|brief|draft|material|rewrite|publish|postmortem",
  "stage_number": 1-7,
  "runner": "node|python",
  "upstream_gate": "previous_gate.json",
  "output_gate": "current_gate.json",
  "hitl": true|false,
  "dependencies": {...},
  "inputs": {...},
  "outputs": {...},
  "quality_requirements": {...}
}
```

详细模式说明请参阅 [SKILL_CONFIG_SCHEMA.md](docs/SKILL_CONFIG_SCHEMA.md)

## 使用指南

### 日常工作流

```bash
# 每日早上10点自动触发Intake
# 或手动运行：
python3 scripts/run_stage1_intake.py

# 查看采集报告
cat 产物/01_内容采集/<run_id>/notes/01_内容采集_报告.md

# 生成选题（AI辅助）
# 编辑可人工添加/修改选题

# 编辑确认选题后，生成初稿
# AI接收Brief后生成，编辑可修改并给意见，AI再改，循环

# 收集素材
python3 scripts/material_execute_pack.py --draft-manifest <path>

# 改写为多个渠道版本
# 通过 dasheng-media-sop 调度

# 发布到各平台
# 通过 dasheng-stage-publish

# 复盘分析
# 通过 dasheng-daily-postmortem
```

### 飞书协作同步

```bash
# 正常同步（首次）
python3 scripts/feishu_stage_sync.py --latest

# 中断后恢复（推荐）
python3 scripts/feishu_stage_sync.py --resume-only <run_id>

# 强制重新开始（仅当旧进度损坏时使用）
python3 scripts/feishu_stage_sync.py --fresh <run_id>
```

### 诊断与测试

```bash
# 运行诊断
python3 scripts/workflow_doctor.py --latest

# 运行测试套件
python3 -m pytest tests/ -v

# 运行特定测试
python3 -m pytest tests/test_material_stage.py -v
```

## 配置说明

### 环境变量

```bash
# 核心路径
export DASHENG_PROJECT_ROOT="/path/to/dasheng-media-workflow"
export DASHENG_DESKTOP_ROOT="$HOME/Desktop/自媒体创作"

# 飞书配置
export DASHENG_FEISHU_CONFIG="$HOME/clawd/configs/feishu_api.conf"

# 数据源
export DASHENG_INTAKE_5173_BASE="http://127.0.0.1:18000"
export DASHENG_INTAKE_REPORTS_BASE="http://45.197.148.64:8080"
export DASHENG_INTAKE_8000_BASE="http://45.197.148.64:8001"

# 微信重试配置
export DASHENG_WECHAT_FETCH_ROUNDS=3
export DASHENG_WECHAT_WAIT_SECONDS=8
export DASHENG_WECHAT_MIN_VALID_ITEMS=8

# 素材阶段控制标志
export MATERIAL_ENABLE_NEWS_SCREENSHOT=1
export MATERIAL_SKIP_VIDEO_PROBE=1
export MATERIAL_AI_STOP_AFTER_FIRST_SUCCESS=1
```

### 外部服务配置

详细配置说明请参阅 [CONFIGURATION.md](docs/CONFIGURATION.md)

## 开发文档

### 文档索引

- [INSTALLATION.md](docs/INSTALLATION.md) - 安装指南
- [API_REFERENCE.md](docs/API_REFERENCE.md) - API参考文档
- [SKILL_CONFIG_SCHEMA.md](docs/SKILL_CONFIG_SCHEMA.md) - 技能配置模式
- [CONFIGURATION.md](docs/CONFIGURATION.md) - 配置说明
- [PRODUCTION_READINESS_STATUS.md](docs/PRODUCTION_READINESS_STATUS.md) - 生产就绪状态
- [CLAUDE.md](CLAUDE.md) - Claude Code开发指南

### API参考

完整的API文档请参阅 [API_REFERENCE.md](docs/API_REFERENCE.md)，包括：
- 每个阶段的输入/输出模式
- Manifest格式
- Gate模式
- CLI命令
- 验证规则

### 测试

```bash
# 运行所有测试
python3 -m pytest tests/ -v

# 运行特定阶段测试
python3 -m pytest tests/test_material_stage.py -v
python3 -m pytest tests/test_postmortem_stage.py -v

# 查看测试覆盖率
python3 -m pytest tests/ --cov=scripts --cov=core
```

### 贡献指南

1. Fork仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 开启Pull Request

## 许可证

[待定]

## 支持

- 文档：查看 `docs/` 目录
- 配置帮助：`docs/CONFIGURATION.md`
- API参考：`docs/API_REFERENCE.md`
- GitHub Issues：报告bug和功能请求

---

**版本**: 2.0.0  
**最后更新**: 2026-04-17  
**生产就绪状态**: ✅ 100/100
