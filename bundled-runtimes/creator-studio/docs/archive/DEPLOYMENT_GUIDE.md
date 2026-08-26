# 大声自媒体创作工作台 v2.0 - 部署指南

## 📦 快速安装

### 方法1: 使用安装器（推荐）

```bash
cd ${DASHENG_PROJECT_ROOT}
python3 skill_package/installer.py install
```

### 方法2: 手动安装

```bash
# 1. 克隆或复制项目
cp -r ${DASHENG_PROJECT_ROOT} /path/to/target

# 2. 安装依赖
pip install anthropic openai pyyaml pillow requests

# 3. 配置环境变量
export ANTHROPIC_API_KEY="your-key"
export OPENAI_API_KEY="your-key"

# 4. 测试安装
python3 core/dna_engine.py
```

---

## 🎯 安装到龙虾（Lobster）

### 步骤1: 准备龙虾环境

```bash
cd ${PROJECTS_ROOT}/lobster-world
```

### 步骤2: 安装Skill

```bash
python3 ${DASHENG_PROJECT_ROOT}/skill_package/installer.py install \
  ${PROJECTS_ROOT}/lobster-world/skills/dasheng-media-platform
```

### 步骤3: 注册Skill到龙虾

在龙虾的配置文件中添加：

```yaml
# lobster-world/config/skills.yaml
skills:
  - id: dasheng-media-platform
    name: 大声自媒体创作工作台
    version: 2.0.0
    path: skills/dasheng-media-platform
    enabled: true
```

### 步骤4: 验证安装

```python
from skills.dasheng_media_platform.core.orchestrator import Orchestrator

orchestrator = Orchestrator()
ctx = orchestrator.create_run()
print(f"✅ Skill已就绪，Run ID: {ctx.run_id}")
```

---

## ⚙️ 配置

### 核心配置文件

`dna/dna_config.yaml` - 主配置文件

```yaml
# 修改默认风格
default_style:
  primary: "normal"      # luxun/lemon/academic/hot/normal
  fallback: "academic"

# 修改AI模型
ai_capabilities:
  reasoning_model: "claude-opus-4-6"
  writing_model: "claude-sonnet-4-6"
  image_model: "dall-e-3"

# 修改自动化设置
automation:
  intake_auto: true
  brief_auto: false      # 需要人工确认
  draft_auto: true
  material_auto: false   # 需要人工审核
  rewrite_auto: false    # 需要人工选择
  publish_auto: true
  postmortem_auto: true
```

### 环境变量

```bash
# API密钥
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."

# 数据源配置（Intake环节）
export DASHENG_INTAKE_5173_BASE="http://127.0.0.1:18000"
export DASHENG_INTAKE_REPORTS_BASE="http://45.197.148.64:8080"

# 飞书配置
export FEISHU_APP_ID="..."
export FEISHU_APP_SECRET="..."
```

---

## 🚀 使用方法

### 基础用法

```python
from core.orchestrator import Orchestrator

# 创建编排器
orchestrator = Orchestrator()

# 创建执行上下文
ctx = orchestrator.create_run()

# 执行完整流程
ctx = orchestrator.execute_pipeline(ctx)

# 查看结果
print(f"Run ID: {ctx.run_id}")
print(f"完成环节: {len(ctx.stage_results)}")
```

### 高级用法：单独执行环节

```python
# 只执行Intake环节
result = orchestrator.execute_stage(ctx, "intake")

# 只执行Draft环节
result = orchestrator.execute_stage(ctx, "draft")
```

### HITL流程

```python
# 执行到Brief环节（会暂停等待人工确认）
ctx = orchestrator.execute_pipeline(ctx)

# 人工审核后，提供决策
hitl_decision = {
    "approved": True,
    "outputs": {
        "selected_topics": ["topic1", "topic2"]
    }
}

# 恢复流程
ctx = orchestrator.resume_pipeline(ctx, hitl_decision)
```

---

## 🎨 DNA系统使用

### 选择风格

```python
from core.dna_engine import DNAEngine

engine = DNAEngine()

# 自动选择风格
style_id = engine.select_style(
    topic_type="金融",
    audience="投资者",
    platform="微信"
)
# 返回: "academic"

# 获取风格配置
style = engine.get_style(style_id)
print(style.characteristics)  # ['严谨专业', '逻辑清晰', '数据支撑']
```

### 选择结构

```python
# 自动选择结构
structure_id = engine.select_structure(
    content_type="分析",
    word_count=1500
)
# 返回: "PCIS"

# 生成结构Prompt
prompt = engine.generate_structure_prompt(structure_id, 1500)
```

### 质量评估

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

---

## 🤖 AI能力集成

### 推理能力

```python
from core.ai_integrator import AIIntegrator

integrator = AIIntegrator()

# 分析主题冲突
result = integrator.analyze_topic_conflict(
    topic="稳定币牌照落地",
    sources=["监管加强", "市场需求", "传统金融入场"]
)
```

### 写作能力

```python
# 生成初稿
result = integrator.write(
    prompt="写一篇关于稳定币牌照的分析文章...",
    style="academic",
    max_tokens=4096
)
```

### 图片生成

```python
# 生成配图
result = integrator.generate_image(
    prompt="稳定币牌照落地，传统金融机构入场",
    style="flat_illustration"
)
print(f"图片URL: {result['url']}")
```

### 视频脚本

```python
# 生成视频脚本
result = integrator.generate_video_script(
    article=article_text,
    duration=60
)
```

---

## 📊 监控和日志

### 执行报告

每次运行会生成执行报告：

```
产物/runs/{run_id}/execution_report.json
```

报告内容：
- 各环节执行状态
- 执行时间
- 质量评分
- 错误信息
- HITL决策记录

### 日志查看

```bash
# 查看最近的执行日志
tail -f 产物/runs/latest/execution.log
```

---

## 🔧 故障排查

### 问题1: API密钥错误

```
错误: AuthenticationError: Invalid API key
解决: 检查环境变量 ANTHROPIC_API_KEY 和 OPENAI_API_KEY
```

### 问题2: 依赖缺失

```
错误: ModuleNotFoundError: No module named 'anthropic'
解决: pip install anthropic openai pyyaml
```

### 问题3: 配置文件错误

```
错误: yaml.parser.ParserError
解决: 检查 dna/dna_config.yaml 格式是否正确
```

### 问题4: HITL流程卡住

```
现象: 流程在Brief/Material/Rewrite环节暂停
解决: 这是正常的HITL检查点，需要人工审核后调用 resume_pipeline()
```

---

## 🧪 测试

### 运行单元测试

```bash
python3 -m pytest tests/unit/
```

### 运行集成测试

```bash
python3 -m pytest tests/integration/
```

### 端到端测试

```bash
python3 tests/e2e/test_full_pipeline.py
```

---

## 📚 更多资源

- **用户手册**: `USER_MANUAL.md`
- **API文档**: `API_REFERENCE.md`
- **DNA设计文档**: `dna/DNA_SYSTEM_DESIGN.md`
- **系统架构**: `SYSTEM_REDESIGN_MASTER_PLAN.md`

---

## 🆘 获取帮助

- GitHub Issues: https://github.com/dasheng/media-platform/issues
- 文档: https://docs.dasheng.ai
- 社区: https://community.dasheng.ai

---

**版本**: 2.0.0  
**更新时间**: 2026-04-13  
**维护者**: Dasheng Team
