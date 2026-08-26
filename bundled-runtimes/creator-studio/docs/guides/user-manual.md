# 大声自媒体创作工作台 v2.0 - 用户手册

## 📖 目录

1. [快速开始](#快速开始)
2. [7个环节详解](#7个环节详解)
3. [DNA系统](#dna系统)
4. [AI能力](#ai能力)
5. [最佳实践](#最佳实践)
6. [常见问题](#常见问题)

---

## 快速开始

### 5分钟上手

```python
from core.orchestrator import Orchestrator

# 1. 创建编排器
orchestrator = Orchestrator()

# 2. 创建执行上下文
ctx = orchestrator.create_run()

# 3. 执行流程
ctx = orchestrator.execute_pipeline(ctx)

# 4. 查看结果
print(f"✅ 完成！Run ID: {ctx.run_id}")
```

### 完整示例

```python
# 示例：生成一篇关于"稳定币牌照"的文章

from core.orchestrator import Orchestrator
from core.dna_engine import DNAEngine

# 初始化
orchestrator = Orchestrator()
dna_engine = DNAEngine()

# 创建执行上下文
ctx = orchestrator.create_run()

# 执行Intake环节（自动采集内容）
result = orchestrator.execute_stage(ctx, "intake")
print(f"✅ Intake完成，采集了{len(result.outputs['intake_records'])}条内容")

# 执行Brief环节（生成选题）
result = orchestrator.execute_stage(ctx, "brief")
# ⏸️ 暂停，等待人工选择选题

# 人工选择选题
hitl_decision = {
    "approved": True,
    "outputs": {
        "selected_topics": ["稳定币牌照落地"]
    }
}
ctx = orchestrator.resume_pipeline(ctx, hitl_decision)

# 后续环节自动执行...
```

---

## 7个环节详解

### Stage 1: Intake（内容采集）

**目的**: 从多个数据源采集内容，去重，评估热度

**自动化**: ✅ 完全自动

**输入**: 无（自动从配置的数据源采集）

**输出**:
- `intake_records.json` - 采集记录
- `entity_rankings.json` - 实体排名
- `event_clusters.json` - 事件聚类
- `channel_top10.json` - 各渠道Top10

**使用方法**:
```python
result = orchestrator.execute_stage(ctx, "intake")
records = result.outputs['intake_records']
```

**配置**:
```yaml
# dna_config.yaml
automation:
  intake_auto: true
```

---

### Stage 2: Brief（选题分析）

**目的**: AI生成选题建议，编辑确认

**自动化**: ⚠️ 需要人工确认（HITL）

**输入**: `intake_records.json`

**输出**:
- `topic_cards.json` - 选题卡片（5-10个候选）
- `selected_topics.json` - 编辑确认的选题

**使用方法**:
```python
# 执行Brief
result = orchestrator.execute_stage(ctx, "brief")

# 查看AI生成的选题
topic_cards = result.outputs['topic_cards']
for card in topic_cards:
    print(f"- {card['title']}")
    print(f"  热度: {card['heat_score']}")
    print(f"  冲突轴: {card['conflict_axis']}")

# 人工选择后恢复
hitl_decision = {
    "approved": True,
    "outputs": {
        "selected_topics": ["topic1", "topic2"]
    }
}
ctx = orchestrator.resume_pipeline(ctx, hitl_decision)
```

**选题卡片结构**:
```json
{
  "topic_id": "topic_001",
  "title": "稳定币牌照落地",
  "core_proposition": "传统金融与加密市场的融合",
  "conflict_axis": "监管 vs 创新",
  "heat_score": 8.5,
  "evidence_requirements": [
    "牌照具体要求",
    "传统金融机构布局",
    "市场反应数据"
  ]
}
```

---

### Stage 3: Draft（初稿生成）

**目的**: 生成结构化初稿

**自动化**: ✅ 完全自动

**输入**: `selected_topics.json`

**输出**:
- `03_标准初稿_{topic}.md` - 初稿文件
- `03_ReasoningSheet_{topic}.json` - 论证结构
- `draft_manifest.json` - 初稿清单

**使用方法**:
```python
result = orchestrator.execute_stage(ctx, "draft")
drafts = result.outputs['drafts']
```

**DNA应用**:
```python
# 指定风格和结构
dna_engine = DNAEngine()

# 选择风格
style_id = dna_engine.select_style(
    topic_type="金融",
    audience="投资者",
    platform="微信"
)

# 选择结构
structure_id = dna_engine.select_structure(
    content_type="分析",
    word_count=1500
)
```

---

### Stage 4: Material（素材收集）

**目的**: 收集图片、图表、视频等素材

**自动化**: ⚠️ 需要人工审核（HITL）

**输入**: `draft_manifest.json`

**输出**:
- `material_pack/` - 素材文件夹
- `material_manifest.json` - 素材清单
- `material_acceptance.json` - 审核结果

**使用方法**:
```python
result = orchestrator.execute_stage(ctx, "material")

# 查看生成的素材
materials = result.outputs['material_pack']
for material in materials:
    print(f"- {material['type']}: {material['path']}")

# 人工审核后恢复
hitl_decision = {
    "approved": True,
    "outputs": {
        "accepted_materials": ["img1.jpg", "chart1.png"]
    }
}
ctx = orchestrator.resume_pipeline(ctx, hitl_decision)
```

**AI图片生成**:
```python
from core.ai_integrator import AIIntegrator

integrator = AIIntegrator()

# 生成配图
result = integrator.generate_image(
    prompt="稳定币牌照落地，传统银行入场",
    style="flat_illustration"
)
```

---

### Stage 5: Rewrite（改写）

**目的**: 生成多平台多版本

**自动化**: ⚠️ 需要人工选择（HITL）

**输入**: `draft_manifest.json`, `material_manifest.json`

**输出**:
- `{topic}__wechat_hot.md` - 微信热点版
- `{topic}__wechat_normal.md` - 微信常规版
- `{topic}__xhs_hot.md` - 小红书热点版
- `{topic}__xhs_normal.md` - 小红书常规版
- `rewrite_manifest.json` - 改写清单

**使用方法**:
```python
result = orchestrator.execute_stage(ctx, "rewrite")

# 查看各版本质量评分
versions = result.outputs['rewrite_versions']
for version in versions:
    print(f"{version['platform']}_{version['tone']}: {version['quality_score']}/10")

# 人工选择最终版本
hitl_decision = {
    "approved": True,
    "outputs": {
        "selected_versions": {
            "wechat": "wechat_hot",
            "xiaohongshu": "xhs_normal"
        }
    }
}
ctx = orchestrator.resume_pipeline(ctx, hitl_decision)
```

**质量评分**:
```python
from core.dna_engine import DNAEngine

engine = DNAEngine()

# 评估质量
report = engine.evaluate_quality(
    text=rewritten_text,
    target_style="hot",
    target_structure="PCIS",
    target_word_count=1300,
    anchors_original=10,
    anchors_preserved=9
)

print(f"总分: {report.overall_score}/10")
print(f"等级: {report.quality_level}")
# 输出: 总分: 8.5/10, 等级: Ready
```

---

### Stage 6: Publish（渠道分发）

**目的**: 生成发布包，适配各渠道

**自动化**: ✅ 完全自动

**输入**: `rewrite_manifest.json`

**输出**:
- `publish_packages/` - 发布包
- `publish_manifest.json` - 发布清单

**使用方法**:
```python
result = orchestrator.execute_stage(ctx, "publish")
packages = result.outputs['publish_packages']
```

---

### Stage 7: Postmortem（分析复盘）

**目的**: 数据分析，DNA更新

**自动化**: ✅ 完全自动

**输入**: `publish_manifest.json`

**输出**:
- `postmortem_report.md` - 复盘报告
- `dna_updates.json` - DNA更新建议

**使用方法**:
```python
result = orchestrator.execute_stage(ctx, "postmortem")
report = result.outputs['postmortem_report']
```

---

## DNA系统

### 5种风格DNA

| 风格 | 特征 | 适用场景 |
|------|------|---------|
| **鲁迅风** | 犀利批判、短句紧凑 | 政治、社会议题 |
| **柠檬风** | 轻松幽默、口语化 | 科技、生活话题 |
| **学术风** | 严谨专业、数据支撑 | 金融、研究报告 |
| **热点风** | 激情澎湃、冲突强烈 | 热点事件、传播导向 |
| **常规风** | 平衡理性、可读性强 | 通用场景 |

### 10种结构DNA

| 结构 | 说明 | 适用字数 |
|------|------|---------|
| **PAS** | 问题-分析-方案 | 1000-1500 |
| **PCIS** | 现象-原因-影响-对策 | 1500-2000 |
| **CCS** | 对比-冲突-解决 | 1000-1500 |
| **Timeline** | 时间线叙事 | 1500-2500 |
| **MultiDimension** | 多维度分析 | 2000-3000 |

### DNA智能选择

```python
from core.dna_engine import DNAEngine

engine = DNAEngine()

# 自动选择最佳风格
style = engine.select_style(
    topic_type="金融",    # 主题类型
    audience="投资者",     # 目标受众
    platform="微信"        # 发布平台
)
# 返回: "academic"

# 自动选择最佳结构
structure = engine.select_structure(
    content_type="分析",   # 内容类型
    word_count=1500       # 目标字数
)
# 返回: "PCIS"
```

---

## AI能力

### 推理能力

```python
from core.ai_integrator import AIIntegrator

integrator = AIIntegrator()

# 冲突分析
result = integrator.analyze_topic_conflict(
    topic="稳定币牌照落地",
    sources=["监管文件", "市场报道", "专家观点"]
)

# 论证链生成
result = integrator.generate_reasoning_chain(
    claim="稳定币牌照将重塑市场格局",
    evidence=["牌照门槛高", "传统金融入场", "小机构退出"]
)
```

### 写作能力

```python
# 初稿生成
result = integrator.write(
    prompt="写一篇关于稳定币牌照的分析...",
    style="academic",
    max_tokens=4096
)

# 标题优化
titles = integrator.optimize_title(
    article=article_text,
    platform="wechat",
    tone="hot"
)
# 返回: ["稳定币牌照落地！传统金融巨头抢滩", ...]
```

### 图片生成

```python
# 配图生成
result = integrator.generate_image(
    prompt="稳定币牌照，传统银行与加密市场融合",
    style="flat_illustration"
)
print(f"图片URL: {result['url']}")

# 封面生成
result = integrator.generate_image(
    prompt="稳定币牌照落地，标题：银行牌照时刻",
    style="realistic"
)
```

### 视频脚本

```python
# 生成60秒短视频脚本
result = integrator.generate_video_script(
    article=article_text,
    duration=60
)

# 脚本包含：
# - 分镜头描述
# - 旁白文案
# - 视觉元素建议
# - 文字叠加
```

---

## 最佳实践

### 1. 选题策略

✅ **好的选题**:
- 有明确的冲突轴
- 证据充分
- 时效性强
- 读者价值高

❌ **避免的选题**:
- 纯事实罗列
- 缺乏冲突点
- 证据不足
- 过于宽泛

### 2. 风格选择

| 场景 | 推荐风格 | 原因 |
|------|---------|------|
| 政策分析 | 学术风 | 需要严谨性 |
| 热点事件 | 热点风 | 传播导向 |
| 科技产品 | 柠檬风 | 轻松易懂 |
| 社会议题 | 鲁迅风 | 批判深刻 |

### 3. 质量控制

```python
# 设置质量阈值
config = {
    "quality_thresholds": {
        "draft_min_score": 7.0,
        "rewrite_min_score": 8.0,
        "publish_min_score": 8.5
    }
}

# 自动重试
if report.overall_score < 8.0:
    # 重新生成
    pass
```

### 4. HITL检查点

**Brief Gate**: 确认选题方向
- 检查冲突轴是否清晰
- 评估证据是否充分
- 确认读者价值

**Material Gate**: 审核素材质量
- 图片是否相关
- 图表是否准确
- 视频是否合适

**Rewrite Gate**: 选择最终版本
- 对比各版本质量
- 选择最适合平台的版本
- 确认字数和锚点

---

## 常见问题

### Q1: 如何修改默认风格？

```yaml
# dna_config.yaml
default_style:
  primary: "hot"         # 改为热点风
  fallback: "normal"
```

### Q2: 如何跳过HITL检查点？

```yaml
# dna_config.yaml
automation:
  brief_auto: true       # 自动通过Brief
  material_auto: true    # 自动通过Material
  rewrite_auto: true     # 自动通过Rewrite
```

⚠️ **警告**: 跳过HITL会降低质量控制

### Q3: 如何添加新的风格DNA？

```python
# 在 dna_engine.py 中添加
new_style = StyleDNAConfig(
    style_id="custom",
    name="自定义风格",
    sentence_length="中等",
    tone_keywords=["关键词1", "关键词2"],
    rhetoric=["修辞1", "修辞2"],
    opening_style="开篇风格",
    closing_style="结尾风格",
    emoji_usage="适中"
)
```

### Q4: 如何查看执行日志？

```bash
# 查看最新执行报告
cat ~/Desktop/自媒体创作/runs/latest/execution_report.json

# 查看特定Run的报告
cat ~/Desktop/自媒体创作/runs/2026-04-13_123456/execution_report.json
```

### Q5: 如何导出到飞书？

```bash
# 同步到飞书
python3 scripts/feishu_stage_sync.py --latest

# 恢复中断的同步
python3 scripts/feishu_stage_sync.py --resume-only <run_id>
```

---

## 📞 获取支持

- **文档**: https://docs.dasheng.ai
- **社区**: https://community.dasheng.ai
- **Issues**: https://github.com/dasheng/media-platform/issues
- **Email**: support@dasheng.ai

---

**版本**: 2.0.0  
**更新时间**: 2026-04-13  
**作者**: Newma Team
