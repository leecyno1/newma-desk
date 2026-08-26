# 🚀 大声自媒体创作工作台 v2.0 - 快速启动指南

**5分钟快速上手 | 零配置启动 | 开箱即用**

---

## ⚡ 极速启动（3步）

### Step 1: 设置API密钥

```bash
export ANTHROPIC_API_KEY="your-anthropic-key"
export OPENAI_API_KEY="your-openai-key"
```

### Step 2: 测试DNA引擎

```bash
cd ${DASHENG_PROJECT_ROOT}
python3 core/dna_engine.py
```

**预期输出**:
```
推荐风格: academic
风格名称: 学术风
特征: ['严谨专业', '逻辑清晰', '数据支撑']

推荐结构: PAS
结构名称: 问题-分析-方案
```

### Step 3: 运行完整流程

```python
from core.orchestrator import Orchestrator

orchestrator = Orchestrator()
ctx = orchestrator.create_run()
ctx = orchestrator.execute_pipeline(ctx)

print(f"✅ 完成！Run ID: {ctx.run_id}")
```

---

## 📦 核心文件清单

### 必需文件（已完成）

```
✅ core/
   ├── dna_engine.py          # DNA引擎
   ├── orchestrator.py        # 流程编排器
   └── ai_integrator.py       # AI集成器

✅ dna/
   ├── dna_config.yaml        # DNA配置
   └── DNA_SYSTEM_DESIGN.md   # DNA设计文档

✅ skill_package/
   ├── manifest.json          # Skill清单
   ├── config_schema.json     # 配置Schema
   └── installer.py           # 安装器

✅ 文档/
   ├── DEPLOYMENT_GUIDE.md    # 部署指南
   ├── USER_MANUAL.md         # 用户手册
   ├── PROJECT_SUMMARY_REPORT.md  # 总结报告
   └── SYSTEM_REDESIGN_MASTER_PLAN.md  # 总体规划
```

---

## 🎯 核心功能演示

### 1. DNA风格选择

```python
from core.dna_engine import DNAEngine

engine = DNAEngine()

# 自动选择最佳风格
style = engine.select_style(
    topic_type="金融",
    audience="投资者",
    platform="微信"
)
print(f"推荐风格: {style}")  # academic

# 获取风格详情
style_config = engine.get_style(style)
print(f"特征: {style_config.characteristics}")
```

### 2. 质量评估

```python
# 评估文章质量
report = engine.evaluate_quality(
    text=article,
    target_style="normal",
    target_structure="PCIS",
    target_word_count=1500,
    anchors_original=10,
    anchors_preserved=9
)

print(f"总分: {report.overall_score}/10")
print(f"等级: {report.quality_level}")
print(f"建议: {report.suggestions}")
```

### 3. AI能力调用

```python
from core.ai_integrator import AIIntegrator

integrator = AIIntegrator()

# 冲突分析
result = integrator.analyze_topic_conflict(
    topic="稳定币牌照落地",
    sources=["监管文件", "市场报道"]
)

# 图片生成
result = integrator.generate_image(
    prompt="稳定币牌照，传统银行入场",
    style="flat_illustration"
)
print(f"图片URL: {result['url']}")
```

---

## 🔧 安装到龙虾

### 一键安装

```bash
python3 skill_package/installer.py install \
  ${PROJECTS_ROOT}/lobster-world/skills/dasheng-media-platform
```

### 验证安装

```python
# 在龙虾中测试
from skills.dasheng_media_platform.core.orchestrator import Orchestrator

orchestrator = Orchestrator()
ctx = orchestrator.create_run()
print(f"✅ Skill已就绪: {ctx.run_id}")
```

---

## 📊 系统状态

### 完成度

| 模块 | 状态 | 完成度 |
|------|------|--------|
| DNA引擎 | ✅ | 100% |
| 流程编排器 | ✅ | 100% |
| AI集成器 | ✅ | 100% |
| Skill打包 | ✅ | 100% |
| 文档系统 | ✅ | 100% |
| 测试套件 | ⏳ | 60% |

### 性能指标

- **自动化率**: 85.7% (目标95%)
- **质量评分**: 7.2/10 (目标8.0+)
- **锚点保留**: 12.1% (目标95%)
- **h2保留**: 100% ✅

---

## 🎨 DNA系统概览

### 5种风格

```
鲁迅风 (luxun)     - 犀利批判、短句紧凑
柠檬风 (lemon)     - 轻松幽默、口语化
学术风 (academic)  - 严谨专业、数据支撑
热点风 (hot)       - 激情澎湃、冲突强烈
常规风 (normal)    - 平衡理性、可读性强
```

### 10种结构

```
PAS              - 问题-分析-方案
PCIS             - 现象-原因-影响-对策
CCS              - 对比-冲突-解决
Timeline         - 时间线叙事
MultiDimension   - 多维度分析
+ 5种扩展模板
```

---

## 🚨 已知限制

### 需要改进

1. **字数控制** - 偏差较大（±30%）
2. **锚点保留** - 保留率低（12.1%）
3. **质量评分** - 未达目标（7.2/10）

### 解决方案

- 增强Prompt约束
- 多轮生成优化
- 自动重试机制

---

## 📚 文档导航

| 文档 | 用途 | 路径 |
|------|------|------|
| **快速启动** | 5分钟上手 | 本文档 |
| **用户手册** | 详细使用说明 | USER_MANUAL.md |
| **部署指南** | 安装和配置 | DEPLOYMENT_GUIDE.md |
| **总结报告** | 项目成果 | PROJECT_SUMMARY_REPORT.md |
| **DNA设计** | DNA系统详解 | dna/DNA_SYSTEM_DESIGN.md |
| **总体规划** | 系统架构 | SYSTEM_REDESIGN_MASTER_PLAN.md |

---

## 🎯 下一步

### 立即可用

✅ DNA引擎 - 风格和结构选择  
✅ 质量评估 - 6维度评分  
✅ AI集成 - 推理/写作/图片/视频  
✅ Skill打包 - 可安装到龙虾

### 待完善

⏳ 端到端测试  
⏳ 性能优化  
⏳ 问题修复  
⏳ 生产部署

---

## 💡 快速示例

### 完整流程示例

```python
from core.orchestrator import Orchestrator
from core.dna_engine import DNAEngine

# 1. 初始化
orchestrator = Orchestrator()
dna_engine = DNAEngine()

# 2. 创建执行上下文
ctx = orchestrator.create_run()
print(f"Run ID: {ctx.run_id}")

# 3. 执行Intake（自动）
result = orchestrator.execute_stage(ctx, "intake")
print(f"✅ Intake完成")

# 4. 执行Brief（需要HITL）
result = orchestrator.execute_stage(ctx, "brief")
print(f"⏸️  等待人工选题...")

# 5. 人工确认后恢复
hitl_decision = {
    "approved": True,
    "outputs": {"selected_topics": ["topic1"]}
}
ctx = orchestrator.resume_pipeline(ctx, hitl_decision)

# 6. 后续环节自动执行
print(f"✅ 流程完成")
```

---

## 🆘 获取帮助

- **文档**: 查看 USER_MANUAL.md
- **问题**: 查看 PROJECT_SUMMARY_REPORT.md 的"已知问题"章节
- **配置**: 查看 DEPLOYMENT_GUIDE.md

---

**版本**: 2.0.0  
**状态**: ✅ 核心完成，可用  
**更新**: 2026-04-13

---

## 🎉 开始使用

```bash
# 克隆项目
cd ${DASHENG_PROJECT_ROOT}

# 设置API密钥
export ANTHROPIC_API_KEY="your-key"
export OPENAI_API_KEY="your-key"

# 测试DNA引擎
python3 core/dna_engine.py

# 运行完整流程
python3 -c "
from core.orchestrator import Orchestrator
orchestrator = Orchestrator()
ctx = orchestrator.create_run()
print(f'✅ 系统就绪: {ctx.run_id}')
"
```

**祝使用愉快！** 🚀
