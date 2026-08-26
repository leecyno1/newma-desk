# Brief 环节选题生成问题分析

## 问题描述

用户反馈：brief 环节生成的选题题目"特别硬，逻辑关系像生搬硬套，没有特别强的逻辑关系和背后的逻辑意义"。

例如生成的选题：
- "外交部、伊朗：事件升级之外，长期秩序成本在怎样上升"
- "美联储、中东这条线，市场是否低估了再通胀与利率预期回摆"
- "川普、美国这条线，风险溢价究竟在围绕什么变量重估"

## 根本原因：硬编码模板拼接

### 1. 选题生成完全依赖硬编码模板

**代码位置**: `scripts/phase2_rebuilder.py` 第 893-948 行

```python
def extract_conflict_axis(cluster: dict[str, Any]) -> str:
    variable_key = cluster["primary_variable"]
    if variable_key == "policy_inflation":
        return "市场是否低估了再通胀与利率预期回摆"
    if variable_key == "supply_order":
        return "供给秩序重估会不会比价格波动更重要"
    if variable_key == "technology_adoption":
        return "真正拉开差距的是功能演示还是工作流落地"
    if variable_key == "semiconductor_cycle":
        return "局部修复会不会被误读成全面复苏"
    if variable_key == "diplomacy_conflict":
        return "事件升级之外，长期秩序成本在怎样上升"
    if variable_key == "risk_pricing":
        return "风险溢价究竟在围绕什么变量重估"
    return "情绪波动背后真正变化的结构变量是什么"

def render_topic_card(proposition: dict[str, Any], topic_kind: str, ...) -> str:
    object_phrase = proposition["object_phrase"]
    conflict_axis = proposition["conflict_axis"]
    if topic_kind == "mother":
        if proposition["article_use"] == "结构稿":
            return f"{object_phrase}：{conflict_axis}"
        if proposition["article_use"] == "判断稿":
            return f"{object_phrase}这条线，{conflict_axis}"
        return f"{object_phrase}：真正值得写的是{conflict_axis}"
```

**问题**：
- 只有 7 个固定的 `conflict_axis` 模板
- 选题标题 = `对象` + `固定连接词` + `固定冲突轴`
- 完全是字符串拼接，没有任何 AI 推理

### 2. 变量分类也是硬编码关键词匹配

**代码位置**: `scripts/phase2_rebuilder.py` 第 15-33 行

```python
VARIABLE_KEYWORDS = {
    "risk_pricing": ["风险", "risk", "reprice", "定价", "估值", "溢价", "避险", "黄金", "白银", "油价"],
    "supply_order": ["供给", "库存", "航运", "运费", "通道", "油轮", "出口", "订单", "产能", "航道", "制裁"],
    "policy_inflation": ["通胀", "再通胀", "降息", "加息", "利率", "政策", "财政", "预算", "赤字", "就业", "美联储"],
    "technology_adoption": ["openclaw", "agent", "workflow", "skill", "skills", "接入", "部署", "安装", "自动化", "工作流", "一键安装"],
    "semiconductor_cycle": ["半导体", "芯片", "晶圆", "封测", "存储", "设备", "算力", "gpu", "光刻", "代工"],
    "diplomacy_conflict": ["停火", "冲突", "制裁", "谈判", "中东", "伊朗", "日本", "外交", "高市早苗", "以色列"],
    "market_sentiment": ["行情", "股债", "基金", "市场情绪", "波动", "反弹", "下跌", "上涨", "资产", "风险偏好"],
}

TENSION_LABELS = {
    "risk_pricing": "表面事件和真实定价链条是否正在背离",
    "supply_order": "真正被重估的是短期价格还是供给秩序",
    "policy_inflation": "主线会不会其实是再通胀",
    "technology_adoption": "真正的壁垒是功能数量还是工作流落地",
    "semiconductor_cycle": "热闹信号会不会被误读成全面复苏",
    "diplomacy_conflict": "事件叙事与长期秩序成本是否正在分化",
    "market_sentiment": "情绪波动背后到底是哪条结构变量在动",
}
```

**问题**：
- 通过关键词匹配将事件分类到 7 个固定桶
- 每个桶对应一个固定的"张力标签"
- 无法处理新的话题类型或复杂的跨领域话题

### 3. 生成流程完全是规则驱动

**流程**：
1. 从 intake 数据中提取关键词
2. 用关键词匹配到 7 个变量桶之一
3. 提取 `core_objects`（通常是实体名）
4. 套用固定模板：`{对象}：{固定冲突轴}`
5. 完成

**没有 AI 参与的环节**：
- ❌ 没有理解事件之间的因果关系
- ❌ 没有分析为什么这个话题值得写
- ❌ 没有推理读者真正关心什么
- ❌ 没有生成有洞察力的角度

## 具体问题示例

### 示例 1: "外交部、伊朗：事件升级之外，长期秩序成本在怎样上升"

**生成过程**：
1. 检测到关键词 "伊朗"、"外交部" → 匹配到 `diplomacy_conflict`
2. 提取对象：`["外交部", "伊朗"]`
3. 套用模板：`{外交部、伊朗}：{事件升级之外，长期秩序成本在怎样上升}`

**问题**：
- "外交部" 和 "伊朗" 之间没有明确的逻辑关系
- "长期秩序成本" 是一个抽象概念，与具体事件脱节
- 读者看到这个标题不知道在说什么

### 示例 2: "美联储、中东这条线，市场是否低估了再通胀与利率预期回摆"

**生成过程**：
1. 检测到 "美联储"、"中东"、"通胀" → 匹配到 `policy_inflation`
2. 提取对象：`["美联储", "中东"]`
3. 套用模板：`{美联储、中东}这条线，{市场是否低估了再通胀与利率预期回摆}`

**问题**：
- "美联储" 和 "中东" 的关系是什么？为什么放在一起？
- "这条线" 是什么线？没有说清楚
- "利率预期回摆" 是专业术语，但与前面的对象关系不清

## 为什么会这样设计？

从代码注释和结构看，这个系统的设计思路是：

1. **快速原型**：通过规则快速生成大量候选选题
2. **人工筛选**：依赖编辑在 Brief Gate 环节人工筛选和修改
3. **可控性**：避免 AI 生成不可控的内容

但这导致了：
- ✅ 速度快、可预测
- ❌ 质量低、缺乏洞察
- ❌ 需要大量人工修改

## 对比：wewrite 和 wechat-skills 的做法

### wewrite 的选题生成

**使用 AI 推理**：
- Step 2: 热点抓取 → **AI 分析** → 选题评分
- 使用 `references/topic-selection.md` 指导 AI 评估选题价值
- AI 生成选题时考虑：
  - 为什么现在值得写
  - 读者会关心什么
  - 有什么独特角度

### wechat-skills 的选题生成

**wechat-topic-outline-planner**：
- 输入：粗点子、资料包、语音底稿
- AI 处理：
  1. 整理输入，区分事实、观点、情绪
  2. 使用 `references/topic-evaluation-rubric.md` 评估
  3. 产出 2-3 个选题角度
  4. 推荐 1 个主角度并说明理由
  5. 生成主大纲和备选大纲

**关键差异**：
- ✅ AI 理解内容
- ✅ AI 推理角度
- ✅ AI 解释为什么

## 解决方案

### 方案 A：完全重写 brief 环节（推荐）

**创建新的 skill**: `dasheng-stage-brief-ai`

**流程**：
1. **输入**：intake 的 `brief_input.json` + `event_clusters.json`
2. **AI 分析**：
   - 理解每个事件簇的核心内容
   - 识别事件之间的因果关系
   - 分析为什么现在值得写
   - 推理读者真正关心什么
3. **AI 生成**：
   - 生成 8-10 个候选选题
   - 每个选题包含：
     - 标题（自然语言，不是模板）
     - 核心论点
     - 为什么值得写
     - 目标读者
     - 证据需求
4. **AI 评分**：
   - 使用 7 种写作框架评估适配度
   - 使用 4 种内容增强策略评估可行性
   - 综合评分排序

**参考文档**：
- `skills/dasheng-stage-rewrite/references/frameworks.md`
- `skills/dasheng-stage-rewrite/references/content-enhance.md`
- wewrite 的 `references/topic-selection.md`
- wechat-skills 的 `references/topic-evaluation-rubric.md`

### 方案 B：混合模式（渐进式）

**保留现有规则系统**，但增加 AI 优化层：

1. **Phase 1**: 规则系统生成初始候选（当前逻辑）
2. **Phase 2**: AI 优化层
   - 输入：规则生成的候选 + 原始事件数据
   - AI 任务：
     - 重写标题，使其更自然、更有洞察力
     - 补充核心论点
     - 解释为什么值得写
   - 输出：优化后的候选选题
3. **Phase 3**: Brief Gate（人工审核）

**优点**：
- 保留现有系统的稳定性
- 渐进式改进，风险低
- 可以 A/B 测试

**缺点**：
- 仍然受限于规则系统的 7 个桶
- AI 只是"美化"，不是真正的推理

### 方案 C：人工 + AI 协作（最灵活）

**不自动生成选题**，而是：

1. **编辑提供种子**：
   - 手动指定 2-3 个感兴趣的方向
   - 或者从 intake 数据中手动标记感兴趣的事件

2. **AI 扩展**：
   - 基于种子生成 5-8 个变体角度
   - 每个角度都有完整的论证
   - AI 解释为什么这个角度有价值

3. **编辑选择**：
   - 从 AI 生成的角度中选择
   - 或者继续让 AI 生成更多角度

**优点**：
- 质量最高
- 最灵活
- 编辑保持控制权

**缺点**：
- 需要更多人工参与
- 不适合完全自动化流程

## 推荐实施路径

### 短期（1-2 周）

1. **创建 `dasheng-stage-brief-ai` skill**
2. **移植选题评估框架**：
   - 从 wewrite 移植 `topic-selection.md`
   - 从 wechat-skills 移植 `topic-evaluation-rubric.md`
3. **实现 AI 选题生成**：
   - 输入：intake 数据
   - 输出：8-10 个候选选题（自然语言）
4. **A/B 测试**：
   - 同时运行规则系统和 AI 系统
   - 对比质量

### 中期（1 个月）

1. **优化 AI 提示词**：
   - 根据测试结果调整
   - 增加更多约束和指导
2. **集成写作框架**：
   - 让 AI 在生成选题时考虑 7 种框架
   - 为每个选题推荐最适合的框架
3. **集成内容增强策略**：
   - 让 AI 评估每个选题适合哪种增强策略
   - 提前规划素材需求

### 长期（3 个月）

1. **建立选题质量评估体系**：
   - 跟踪哪些选题最终被采用
   - 跟踪文章发布后的数据
   - 持续优化 AI 生成逻辑
2. **支持多种生成模式**：
   - 全自动模式（当前）
   - 半自动模式（编辑提供种子）
   - 交互模式（编辑与 AI 对话）

## 关键技术点

### 1. AI 提示词设计

**核心原则**：
- 不要让 AI 套模板
- 让 AI 理解事件的因果关系
- 让 AI 推理读者的需求
- 让 AI 生成有洞察力的角度

**提示词结构**：
```
你是一个资深的财经媒体选题编辑。

【输入数据】
- 事件簇：{event_clusters}
- 热点排名：{channel_top10}
- 时间范围：{date_range}

【你的任务】
1. 理解每个事件簇的核心内容和相互关系
2. 识别哪些话题值得深入写作
3. 为每个值得写的话题生成一个选题

【选题要求】
- 标题要自然、有洞察力，不要套模板
- 要有明确的核心论点
- 要解释为什么现在值得写
- 要说明目标读者是谁
- 要列出需要什么证据

【输出格式】
为每个选题输出：
1. 标题
2. 核心论点（一句话）
3. 为什么值得写（2-3 句）
4. 目标读者
5. 需要的证据类型
6. 推荐的写作框架（痛点型/故事型/清单型/对比型/热点解读型/纯观点型/复盘型）
```

### 2. 与现有系统集成

**保持兼容性**：
- 输入：仍然使用 intake 的输出
- 输出：仍然生成 `brief_manifest.json` 和 `selected_topics.json`
- Brief Gate：仍然需要人工审核

**新增字段**：
```json
{
  "topic_id": "...",
  "title": "AI 生成的自然语言标题",
  "core_argument": "核心论点",
  "why_now": "为什么现在值得写",
  "target_audience": "目标读者",
  "evidence_needs": ["需要的证据1", "需要的证据2"],
  "recommended_framework": "痛点型",
  "recommended_strategy": "密度强化",
  "generation_method": "ai" // 或 "rule"
}
```

## 总结

**当前问题的本质**：
- brief 环节完全依赖硬编码规则
- 选题标题是字符串模板拼接
- 没有利用 AI 的推理能力

**解决方向**：
- 创建新的 AI 驱动的 brief skill
- 让 AI 理解事件、推理角度、生成选题
- 集成写作框架和内容增强策略
- 保持与现有系统的兼容性

**预期效果**：
- 选题标题更自然、更有洞察力
- 核心论点更清晰、更有说服力
- 减少人工修改的工作量
- 提高最终文章的质量
