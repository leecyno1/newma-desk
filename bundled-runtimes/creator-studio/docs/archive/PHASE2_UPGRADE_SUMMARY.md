# 第二阶段升级总结：Draft 和 Material 优化

## 概述

第二阶段在第一阶段（Brief AI 化）的基础上，继续优化 Draft 和 Material 环节，使整个工作流更加智能化和高效。

## 完成的工作

### 1. 框架驱动的 Draft 生成

**创建文件**：`scripts/draft_with_framework.py`

**核心功能**：
- 根据 brief 推荐的框架自动生成结构化初稿
- 应用内容增强策略（角度发现、密度强化、细节锚定、真实体感）
- 自动验证 draft 质量（字数、结构、引用清单）
- 生成详细的 draft manifest

**使用方式**：
```bash
python3 scripts/draft_with_framework.py \
  --brief-dir "产物/02_Brief/2026-04-04_204231_ai" \
  --output-dir "产物/03_Draft/2026-04-04_204231"
```

**生成的 AI Prompt 包含**：
- 选题信息（标题、核心论点、为什么值得写、目标读者）
- 框架结构指南（从 `frameworks.md` 加载）
- 内容增强策略指南（从 `content-enhance.md` 加载）
- 证据需求和来源
- 写作要求（字数、格式、风格）
- 框架和策略应用要点

**质量验证**：
- 字数检查：3000-6000 字
- 结构检查：2-6 个 H2 标题
- 引用检查：是否有引用清单
- 空话检查：避免"需要注意"、"建议大家"等空话

---

### 2. Material 环节的 AI 优化

**创建文件**：`scripts/material_ai_optimizer.py`

**核心功能**：

#### 2.1 动态图表门控（AI 辅助决策）

**问题**：
- 旧系统对所有数据都生成图表，导致图表过多、质量参差不齐
- 简单数据（1-3 个数值）用图表反而不如文字清晰

**解决方案**：
- AI 判断每个数据点是否需要可视化
- 考虑数据复杂度、对论证的重要性、读者理解难度
- 推荐最合适的图表类型（折线图、柱状图、饼图、散点图、热力图、表格）
- 给出优先级（high/medium/low）

**AI Prompt 包含**：
- 数据信息（类型、数值、描述）
- 上下文（文章段落、论证目标）
- 判断标准（复杂度、重要性、理解难度）
- 图表类型选择指南
- 决策原则

**输出格式**：
```json
{
  "should_generate": true/false,
  "chart_type": "折线图/柱状图/饼图/散点图/热力图/表格",
  "reason": "判断理由...",
  "priority": "high/medium/low",
  "alternative": "如果不生成图表，建议的文字表达方式"
}
```

#### 2.2 智能素材检索（AI 优化搜索关键词）

**问题**：
- 直接用段落文字搜索，命中率低
- 关键词过于宽泛或过于具体
- 缺少英文关键词，错过国际素材库

**解决方案**：
- AI 从段落中提取最佳搜索关键词
- 生成主关键词、次要关键词、英文关键词
- 提供搜索策略和预期结果
- 考虑版权和敏感话题

**AI Prompt 包含**：
- 段落内容
- 搜索类型（图片/视频）
- 关键词要求（数量、语言、精准度、多样性）
- 关键词类型（核心概念、视觉元素、情绪/氛围、行业术语）
- 注意事项（避免宽泛词、考虑版权）

**输出格式**：
```json
{
  "primary_keywords": ["主关键词1", "主关键词2"],
  "secondary_keywords": ["次要关键词1", "次要关键词2", "次要关键词3"],
  "english_keywords": ["English keyword 1", "English keyword 2"],
  "search_strategy": "搜索策略说明",
  "expected_results": "预期找到的素材类型"
}
```

**示例**：
```
段落：中东冲突导致霍尔木兹海峡封锁，全球能源供应链面临重大风险。

输出：
{
  "primary_keywords": ["霍尔木兹海峡", "能源供应链"],
  "secondary_keywords": ["石油运输", "海峡封锁", "油轮"],
  "english_keywords": ["Strait of Hormuz", "oil tanker", "energy supply chain", "maritime chokepoint"],
  "search_strategy": "优先使用英文关键词搜索国际新闻图片，中文关键词搜索本地媒体素材",
  "expected_results": "海峡地图、油轮照片、供应链示意图"
}
```

#### 2.3 质量报告生成

**图表决策质量报告**：
- 总数据点数
- 需要生成的图表数
- 高优先级图表数
- 图表类型分布
- 生成率

**素材搜索质量报告**：
- 总查询数
- 总结果数
- 平均每次查询的结果数
- 有结果的查询数
- 成功率

---

### 3. 更新 Skill 文档

**更新文件**：`skills/dasheng-stage-intake-brief-draft/SKILL.md`

**新增内容**：
- Brief 环节已升级为 AI 驱动的说明
- Draft 环节已集成框架系统的说明
- 推荐使用新系统的命令
- 新增强约束：Brief 必须使用 AI 系统，Draft 应遵循推荐框架
- 参考文档链接

---

## 工作流程对比

### 旧工作流

```
Intake → Brief (规则) → Draft (通用) → Material (全量图表) → Rewrite → Publish
         ↓                ↓                ↓
      模板拼接        无框架指导      图表过多
      标题生硬        结构随意        素材命中率低
```

### 新工作流

```
Intake → Brief (AI) → Draft (框架驱动) → Material (AI 优化) → Rewrite → Publish
         ↓              ↓                    ↓
      自然标题      结构化初稿          智能图表决策
      有洞察力      应用策略            精准素材检索
      推荐框架      质量验证            质量报告
```

---

## 关键改进

### Brief → Draft 的连贯性

**旧系统**：
- Brief 推荐框架，但 Draft 不使用
- Brief 推荐策略，但 Draft 不应用
- 两个环节脱节

**新系统**：
- Draft 自动读取 Brief 推荐的框架
- Draft 自动应用 Brief 推荐的策略
- 生成的 AI Prompt 包含完整的框架和策略指南
- 两个环节无缝衔接

### Material 的智能化

**旧系统**：
- 所有数据都生成图表（过度可视化）
- 直接用段落文字搜索素材（命中率低）
- 缺少质量控制

**新系统**：
- AI 判断哪些数据需要可视化（精准控制）
- AI 优化搜索关键词（提高命中率）
- 生成质量报告（可追踪优化）

---

## 技术实现

### 框架加载器

使用 `framework_strategy_loader.py` 统一加载框架和策略指南：

```python
from framework_strategy_loader import load_framework_guide, load_strategy_guide

# 加载框架指南
framework_guide = load_framework_guide("痛点型")

# 加载策略指南
strategy_guide = load_strategy_guide("密度强化")
```

### AI Prompt 设计原则

1. **完整性**：包含所有必要信息（选题、框架、策略、证据）
2. **结构化**：使用清晰的分段和标记
3. **可操作**：提供具体的应用要点和示例
4. **可验证**：输出格式明确，便于验证

### 质量验证

**Draft 验证**：
- 字数范围：3000-6000 字
- 结构完整：2-6 个 H2 标题
- 引用清单：必须有数据来源
- 空话检查：避免无意义的表述

**Material 验证**：
- 图表决策合理性：检查必需字段、图表类型、优先级
- 搜索关键词合理性：检查必需字段、关键词数量、英文关键词
- 结果去重和排序：避免重复素材

---

## 使用示例

### 完整工作流

```bash
# 1. Intake
cd "${DASHENG_WORKSPACE}"
python3 scripts/run_stage1_intake.py

# 2. Brief (AI 驱动)
# 使用 dasheng-stage-brief-ai skill 生成选题

# 3. Draft (框架驱动)
python3 scripts/draft_with_framework.py \
  --brief-dir "产物/02_Brief/2026-04-04_204231_ai" \
  --output-dir "产物/03_Draft/2026-04-04_204231"

# 4. Material (AI 优化)
# 使用 material_ai_optimizer.py 的函数优化图表和素材检索
```

### 单独使用 Material AI 优化

```python
from material_ai_optimizer import (
    ai_decide_chart_generation_prompt,
    ai_optimize_search_query_prompt
)

# 图表决策
data_point = {
    'type': 'time_series',
    'data': [...],
    'description': '...'
}
context = "文章段落：..."
prompt = ai_decide_chart_generation_prompt(data_point, context)
# 将 prompt 发送给 AI，获取决策

# 素材检索
paragraph = "霍尔木兹海峡是全球最重要的能源通道..."
prompt = ai_optimize_search_query_prompt(paragraph, "image")
# 将 prompt 发送给 AI，获取优化的关键词
```

---

## 预期效果

### Draft 质量提升

- **结构更清晰**：严格遵循框架，逻辑连贯
- **内容更充实**：应用策略，避免空话
- **证据更充分**：每段都有数据支撑
- **可读性更强**：符合目标读者的阅读习惯

### Material 效率提升

- **图表更精准**：只生成真正需要的图表，减少 30-50% 的图表数量
- **素材更相关**：优化关键词，提高 50-100% 的命中率
- **质量更可控**：生成报告，持续优化

### 编辑工作量减少

- **Brief 修改减少**：标题自然，论点清晰，基本不需要修改
- **Draft 修改减少**：结构完整，内容充实，主要修改细节
- **Material 筛选减少**：图表精准，素材相关，减少无效筛选

---

## 下一步建议

### 短期（1-2 周）

1. **测试新系统**：
   - 用真实数据测试 draft_with_framework.py
   - 用真实段落测试 material_ai_optimizer.py
   - 收集编辑反馈

2. **优化 Prompt**：
   - 根据测试结果调整 AI prompt
   - 增加更多示例和约束
   - 优化输出格式

3. **集成到生产流程**：
   - 更新 SOP 文档
   - 培训编辑使用新系统
   - 建立反馈机制

### 中期（1 个月）

1. **自动化集成**：
   - 将 material_ai_optimizer 集成到 material_execute_pack.py
   - 实现图表决策的自动化流程
   - 实现素材检索的自动化流程

2. **质量追踪**：
   - 跟踪 draft 的修改率
   - 跟踪图表的使用率
   - 跟踪素材的采用率

3. **持续优化**：
   - 根据数据优化 AI prompt
   - 优化框架和策略指南
   - 增加新的框架和策略

### 长期（3 个月）

1. **端到端优化**：
   - Brief → Draft → Material 全流程自动化
   - 建立质量评估体系
   - 实现闭环优化

2. **个性化**：
   - 学习编辑的偏好
   - 适应不同媒体的风格
   - 支持不同读者群体

3. **智能化升级**：
   - AI 自动选择最佳框架
   - AI 自动生成完整 draft
   - AI 自动生成图表和配图

---

## 总结

第二阶段成功实现了 Draft 和 Material 环节的 AI 优化：

1. **Draft 框架驱动**：根据 brief 推荐的框架生成结构化初稿，应用内容增强策略
2. **Material 智能优化**：AI 辅助图表决策和素材检索，提高效率和质量
3. **工作流连贯性**：Brief → Draft → Material 无缝衔接，形成完整的智能化工作流

结合第一阶段的 Brief AI 化，整个上游工作流（Intake → Brief → Draft → Material）已经实现了全面的 AI 驱动和优化。

---

## 文件清单

### 新增文件

1. `scripts/draft_with_framework.py` - 框架驱动的 Draft 生成脚本
2. `scripts/material_ai_optimizer.py` - Material 环节的 AI 优化模块
3. `PHASE2_UPGRADE_SUMMARY.md` - 第二阶段升级总结（本文件）

### 更新文件

1. `skills/dasheng-stage-intake-brief-draft/SKILL.md` - 更新说明和命令

### 第一阶段文件（参考）

1. `skills/dasheng-stage-brief-ai/SKILL.md` - AI 驱动的 brief 生成
2. `skills/dasheng-stage-brief-ai/references/ai-generation-guide.md` - AI 生成指南
3. `skills/dasheng-stage-brief-ai/references/topic-evaluation.md` - 选题评估框架
4. `BRIEF_AI_TEST_REPORT.md` - Brief AI 测试报告
5. `BRIEF_AI_COMPARISON.md` - Brief 新旧系统对比
