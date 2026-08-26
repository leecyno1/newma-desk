# 自媒体创作工作台 - 系统级重构总体规划

**项目代号**: Dasheng Media Creation Platform v2.0
**目标**: 打造可安装到多AI助手的高度自动化自媒体创作Skill包
**时间框架**: 24小时
**执行模式**: 并行Sub Agent + 细粒度任务 + 持续测试

---

## 🎯 核心目标

### 1. 高度自动化（Automation First）
- 7个环节自动化率：当前60% → 目标95%
- 人工介入点：仅在关键质量检查节点（HITL Gates）
- 端到端执行时间：当前8-12小时 → 目标2-3小时

### 2. AI能力深度集成（AI-Powered）
- **推理能力**：选题分析、论证结构、逻辑检查
- **写作能力**：初稿生成、改写、标题优化
- **视频生成**：自动生成短视频脚本和素材
- **图片生成**：配图、图表、封面自动生成

### 3. DNA化（DNA System）
- **文风DNA**：可配置的写作风格基因库
- **结构DNA**：标准化的文章结构模板
- **视觉DNA**：统一的视觉风格体系
- **质量DNA**：可量化的质量标准

### 4. 可移植性（Portable Skill）
- 标准化Skill包格式
- 跨平台部署（龙虾、Claude、其他AI助手）
- 配置驱动、插件化架构

---

## 📋 5个Phase执行计划

### Phase 1: 系统深度分析（2小时）
**负责人**: Explore Agent
**产出**: 系统分析报告

**子任务**:
1.1 分析7个环节的当前实现
1.2 识别自动化瓶颈
1.3 评估AI能力利用率
1.4 分析数据流和依赖关系
1.5 识别质量问题和改进空间

### Phase 2: DNA系统设计（4小时）
**负责人**: Plan Agent + 写作专家Agent
**产出**: DNA基因库设计文档

**子任务**:
2.1 设计文风DNA体系（5种基础风格）
2.2 设计结构DNA模板（10种文章结构）
2.3 设计视觉DNA规范（配图、图表、封面）
2.4 设计质量DNA标准（评分体系）
2.5 构建DNA配置系统

### Phase 3: 自动化流程重构（8小时）
**负责人**: 多个专项Agent并行
**产出**: 7个环节的重构代码

**子任务**:
3.1 Intake环节：智能去重 + 热度预测
3.2 Brief环节：AI选题生成 + 冲突分析
3.3 Draft环节：结构化生成 + 论证链
3.4 Material环节：AI配图 + 图表生成 + 视频脚本
3.5 Rewrite环节：多版本并行 + 质量自检
3.6 Publish环节：渠道适配 + 发布自动化
3.7 Postmortem环节：数据分析 + DNA更新

### Phase 4: Skill打包和部署（4小时）
**负责人**: 架构Agent
**产出**: 可部署的Skill包

**子任务**:
4.1 设计Skill包格式（manifest + 配置 + 代码）
4.2 实现安装/卸载机制
4.3 设计配置系统（用户可定制）
4.4 实现跨平台适配层
4.5 编写部署文档

### Phase 5: 测试和上线（6小时）
**负责人**: 测试Agent + 集成Agent
**产出**: 生产就绪的系统

**子任务**:
5.1 单元测试（每个环节）
5.2 集成测试（端到端流程）
5.3 性能测试（并发、速度）
5.4 质量验证（输出质量）
5.5 用户手册和API文档

---

## 🔧 技术架构设计

### 核心组件

```
dasheng-media-platform-v2/
├── core/                    # 核心引擎
│   ├── orchestrator.py      # 流程编排器
│   ├── dna_engine.py        # DNA引擎
│   ├── ai_integrator.py     # AI能力集成
│   └── quality_gate.py      # 质量检查门
├── stages/                  # 7个环节
│   ├── stage1_intake/
│   ├── stage2_brief/
│   ├── stage3_draft/
│   ├── stage4_material/
│   ├── stage5_rewrite/
│   ├── stage6_publish/
│   └── stage7_postmortem/
├── dna/                     # DNA基因库
│   ├── style_dna/           # 文风DNA
│   ├── structure_dna/       # 结构DNA
│   ├── visual_dna/          # 视觉DNA
│   └── quality_dna/         # 质量DNA
├── ai_modules/              # AI能力模块
│   ├── reasoning/           # 推理模块
│   ├── writing/             # 写作模块
│   ├── image_gen/           # 图片生成
│   └── video_gen/           # 视频生成
├── skill_package/           # Skill打包
│   ├── manifest.json        # Skill清单
│   ├── installer.py         # 安装器
│   └── config_schema.json   # 配置模式
└── tests/                   # 测试套件
    ├── unit/
    ├── integration/
    └── e2e/
```

---

## 🚀 并行执行策略

### 时间线（24小时）

**Hour 0-2**: Phase 1 系统分析
- Sub Agent 1: 分析Intake/Brief/Draft
- Sub Agent 2: 分析Material/Rewrite
- Sub Agent 3: 分析Publish/Postmortem

**Hour 2-6**: Phase 2 DNA设计
- Sub Agent 1: 文风DNA + 结构DNA
- Sub Agent 2: 视觉DNA + 质量DNA
- Sub Agent 3: DNA配置系统

**Hour 6-14**: Phase 3 流程重构（并行）
- Sub Agent 1: Intake + Brief
- Sub Agent 2: Draft + Material
- Sub Agent 3: Rewrite + Publish
- Sub Agent 4: Postmortem + 集成

**Hour 14-18**: Phase 4 Skill打包
- Sub Agent 1: 打包格式 + 安装器
- Sub Agent 2: 配置系统 + 适配层

**Hour 18-24**: Phase 5 测试上线
- Sub Agent 1: 单元测试 + 集成测试
- Sub Agent 2: 性能测试 + 质量验证
- Sub Agent 3: 文档编写

---

## 📊 关键指标（KPI）

### 自动化指标
- 端到端自动化率：≥95%
- 人工介入次数：≤3次/run
- 执行时间：≤3小时

### 质量指标
- Draft质量评分：≥8.0/10
- Rewrite质量评分：≥8.5/10
- 锚点保留率：≥95%
- h2结构保留率：100%

### AI能力利用
- 推理模块调用：≥10次/run
- 图片生成：≥15张/run
- 视频脚本生成：≥3个/run

### 可移植性
- 安装时间：≤5分钟
- 配置复杂度：≤10个参数
- 跨平台兼容：100%

---

## 🎨 DNA系统概览

### 文风DNA（5种基础风格）

1. **鲁迅风（Luxun）** - 犀利、批判、深刻
2. **柠檬风（Lemon）** - 轻松、幽默、亲和
3. **学术风（Academic）** - 严谨、专业、权威
4. **热点风（Hot）** - 激情、冲突、传播
5. **常规风（Normal）** - 平衡、理性、可读

### 结构DNA（10种模板）

1. 问题-分析-方案（PAS）
2. 现象-原因-影响-对策（PCIS）
3. 对比-冲突-解决（CCS）
4. 时间线叙事（Timeline）
5. 多维度分析（Multi-Dimension）
6. 案例驱动（Case-Driven）
7. 数据驱动（Data-Driven）
8. 观点碰撞（Opinion-Clash）
9. 深度解读（Deep-Dive）
10. 快速扫描（Quick-Scan）

### 视觉DNA

- 配图风格：写实/插画/图表/漫画
- 色彩方案：5种预设色板
- 排版规范：标题/正文/引用/数据
- 封面模板：10种预设模板

---

## ⚙️ 自动化流程设计

### 完整流程（端到端）

```
[用户输入] → [Orchestrator启动]
    ↓
[Stage 1: Intake] 自动采集 + 去重 + 热度预测
    ↓ (自动)
[Stage 2: Brief] AI选题生成 + 冲突分析 + 大纲
    ↓ (HITL Gate 1: 选题确认)
[Stage 3: Draft] 结构化生成 + 论证链 + 初稿
    ↓ (自动)
[Stage 4: Material] AI配图 + 图表 + 视频脚本
    ↓ (HITL Gate 2: 素材审核)
[Stage 5: Rewrite] 多版本生成 + 质量自检
    ↓ (HITL Gate 3: 版本选择)
[Stage 6: Publish] 渠道适配 + 自动发布
    ↓ (自动)
[Stage 7: Postmortem] 数据分析 + DNA更新
    ↓
[完成] → [输出报告]
```

### HITL检查点（3个）

1. **Brief Gate**: 编辑确认选题和大纲
2. **Material Gate**: 编辑审核素材质量
3. **Rewrite Gate**: 编辑选择最终版本

---

## 📦 Skill包格式

### manifest.json

```json
{
  "skill_id": "dasheng-media-platform",
  "version": "2.0.0",
  "name": "大声自媒体创作工作台",
  "description": "高度自动化的7环节自媒体创作系统",
  "author": "Dasheng Team",
  "compatible_platforms": ["lobster", "claude", "openai"],
  "dependencies": {
    "anthropic": ">=0.18.0",
    "openai": ">=1.0.0",
    "pillow": ">=10.0.0"
  },
  "entry_point": "core/orchestrator.py",
  "config_schema": "skill_package/config_schema.json",
  "stages": [
    {"id": "intake", "auto": true},
    {"id": "brief", "auto": false, "hitl": true},
    {"id": "draft", "auto": true},
    {"id": "material", "auto": false, "hitl": true},
    {"id": "rewrite", "auto": false, "hitl": true},
    {"id": "publish", "auto": true},
    {"id": "postmortem", "auto": true}
  ]
}
```

---

## 🧪 测试策略

### 测试金字塔

```
        /\
       /E2E\        端到端测试（3个完整流程）
      /------\
     /集成测试\      集成测试（7个环节串联）
    /----------\
   /  单元测试  \    单元测试（每个函数/类）
  /--------------\
```

### 测试覆盖率目标
- 单元测试：≥80%
- 集成测试：100%（7个环节）
- E2E测试：3个典型场景

---

## 📝 交付清单

### 代码交付
- [ ] 7个环节重构代码
- [ ] DNA引擎实现
- [ ] AI集成模块
- [ ] Skill打包系统
- [ ] 测试套件

### 文档交付
- [ ] 系统架构文档
- [ ] DNA设计文档
- [ ] API参考文档
- [ ] 用户手册
- [ ] 部署指南

### 配置交付
- [ ] DNA配置文件
- [ ] Skill manifest
- [ ] 环境配置模板
- [ ] 示例配置

---

**开始执行时间**: 2026-04-12 23:45
**预计完成时间**: 2026-04-13 23:45
**当前状态**: Phase 1 准备启动
