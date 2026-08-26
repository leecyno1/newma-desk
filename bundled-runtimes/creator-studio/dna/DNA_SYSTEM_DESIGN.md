# DNA系统设计文档 v1.0

**设计目标**: 构建可配置、可复用、可进化的文风和质量基因库

---

## 1. 文风DNA体系

### 1.1 基础风格定义（5种）

#### Style 1: 鲁迅风（Luxun）
**核心特征**:
- 犀利批判、一针见血
- 短句为主、节奏紧凑
- 反讽、对比、揭露

**语言特征**:
```yaml
sentence_length: 短句为主（8-15字）
tone_keywords: [揭露, 暴露, 撕开, 刺破, 戳穿]
rhetoric: [反讽, 对比, 排比]
opening_style: 直击痛点
closing_style: 留白反思
emoji_usage: 极少（≤1个/文）
```

**示例片段**:
```
这不是第一次，也不会是最后一次。
每当类似事件发生，总有人说"个案"。
但个案累积到一定数量，就不再是个案。
```

#### Style 2: 柠檬风（Lemon）
**核心特征**:
- 轻松幽默、亲和力强
- 口语化表达
- 类比、比喻、生活化

**语言特征**:
```yaml
sentence_length: 中等（12-20字）
tone_keywords: [其实, 说白了, 简单来说, 打个比方]
rhetoric: [类比, 比喻, 拟人]
opening_style: 轻松引入
closing_style: 友好互动
emoji_usage: 适中（3-5个/文）
```

**示例片段**:
```
说白了，这事儿就像你家WiFi密码被邻居知道了。
一开始你觉得没啥，反正网速还行。
但时间长了，你会发现不对劲。🤔
```

#### Style 3: 学术风（Academic）
**核心特征**:
- 严谨专业、逻辑清晰
- 数据支撑、引用权威
- 客观中立

**语言特征**:
```yaml
sentence_length: 长句（20-35字）
tone_keywords: [根据, 研究表明, 数据显示, 分析认为]
rhetoric: [因果论证, 对比分析, 归纳演绎]
opening_style: 问题陈述
closing_style: 结论总结
emoji_usage: 无
```

**示例片段**:
```
根据Coalition Greenwich 2026年Q1的调查数据，
全球前20大投行中，已有17家在核心业务流程中部署了生成式AI。
这一比例较2025年同期增长了42%，表明金融机构对AI技术的依赖度正在快速上升。
```

#### Style 4: 热点风（Hot）
**核心特征**:
- 激情澎湃、冲突强烈
- 数据冲击、反常现象
- 传播导向

**语言特征**:
```yaml
sentence_length: 短中结合（10-18字）
tone_keywords: [突然, 紧急, 首次, 罕见, 暴露, 颠覆]
rhetoric: [冲突对比, 数据冲击, 悬念设置]
opening_style: 冲突/数据/反常
closing_style: 转发激励
emoji_usage: 适中（2-4个/文）
punctuation: 感叹号、问号频繁
```

**示例片段**:
```
24小时内，3家中央银行同时表态！
这在过去10年从未发生过。
市场嗅到了什么？💥
```

#### Style 5: 常规风（Normal）
**核心特征**:
- 平衡理性、可读性强
- 专业但不生硬
- 信息密度适中

**语言特征**:
```yaml
sentence_length: 中等（15-25字）
tone_keywords: [值得注意, 需要关注, 可以看到, 实际上]
rhetoric: [SPA结构, 分点论述, 逻辑递进]
opening_style: 背景+问题
closing_style: 总结+展望
emoji_usage: 少量（1-2个/文）
```

---

## 2. 结构DNA模板（10种）

### 模板1: PAS（问题-分析-方案）
```yaml
template_id: PAS
sections:
  - name: 问题陈述
    word_ratio: 0.15
    purpose: 引出核心问题
  - name: 深度分析
    word_ratio: 0.60
    subsections: [原因分析, 影响评估, 案例佐证]
  - name: 解决方案
    word_ratio: 0.25
    subsections: [短期措施, 长期建议]
```

### 模板2: PCIS（现象-原因-影响-对策）
```yaml
template_id: PCIS
sections:
  - name: 现象描述
    word_ratio: 0.20
  - name: 原因剖析
    word_ratio: 0.30
  - name: 影响分析
    word_ratio: 0.30
  - name: 应对策略
    word_ratio: 0.20
```

### 模板3: CCS（对比-冲突-解决）
```yaml
template_id: CCS
sections:
  - name: 对比呈现
    word_ratio: 0.25
    purpose: A vs B的鲜明对比
  - name: 冲突揭示
    word_ratio: 0.50
    purpose: 矛盾点和张力
  - name: 解决路径
    word_ratio: 0.25
```

### 模板4: Timeline（时间线叙事）
```yaml
template_id: Timeline
sections:
  - name: 背景铺垫
    word_ratio: 0.15
  - name: 事件演进
    word_ratio: 0.60
    structure: 时间顺序
  - name: 当前状态与展望
    word_ratio: 0.25
```

### 模板5: Multi-Dimension（多维度分析）
```yaml
template_id: MultiDimension
sections:
  - name: 引言
    word_ratio: 0.10
  - name: 维度1（如政策层面）
    word_ratio: 0.25
  - name: 维度2（如市场层面）
    word_ratio: 0.25
  - name: 维度3（如技术层面）
    word_ratio: 0.25
  - name: 综合结论
    word_ratio: 0.15
```

### 模板6-10（简化定义）
```yaml
- Case-Driven: 案例驱动（3-5个案例串联）
- Data-Driven: 数据驱动（图表+数据为主）
- Opinion-Clash: 观点碰撞（多方观点对比）
- Deep-Dive: 深度解读（单一主题深挖）
- Quick-Scan: 快速扫描（要点罗列）
```

---

## 3. 视觉DNA规范

### 3.1 配图风格（4种）

#### 风格A: 写实摄影
```yaml
style_id: realistic
use_case: 新闻、事件、人物
image_source: [unsplash, pexels, 自有图库]
color_tone: 自然色调
resolution: 1920x1080 (16:9)
```

#### 风格B: 扁平插画
```yaml
style_id: flat_illustration
use_case: 概念、流程、对比
generation_tool: DALL-E 3 / Midjourney
color_palette: [#FF6B6B, #4ECDC4, #45B7D1, #FFA07A]
style_keywords: [flat design, minimalist, vector]
```

#### 风格C: 数据图表
```yaml
style_id: data_chart
use_case: 数据、趋势、对比
chart_types: [折线图, 柱状图, 饼图, 雷达图]
color_scheme: 商务蓝 + 强调橙
font: 思源黑体
```

#### 风格D: 漫画风格
```yaml
style_id: comic
use_case: 幽默、讽刺、轻松话题
generation_tool: Stable Diffusion / Midjourney
style_keywords: [comic style, cartoon, humorous]
```

### 3.2 色彩方案（5种预设）

```yaml
palette_1_professional:
  primary: "#2C3E50"    # 深蓝灰
  secondary: "#3498DB"  # 亮蓝
  accent: "#E74C3C"     # 强调红
  
palette_2_warm:
  primary: "#D35400"    # 暖橙
  secondary: "#F39C12"  # 金黄
  accent: "#C0392B"     # 深红

palette_3_cool:
  primary: "#16A085"    # 青绿
  secondary: "#1ABC9C"  # 薄荷绿
  accent: "#2980B9"     # 天蓝

palette_4_elegant:
  primary: "#34495E"    # 深灰蓝
  secondary: "#95A5A6"  # 银灰
  accent: "#9B59B6"     # 紫罗兰

palette_5_vibrant:
  primary: "#E91E63"    # 玫红
  secondary: "#FF5722"  # 橙红
  accent: "#FFC107"     # 琥珀黄
```

### 3.3 封面模板（10种）

```yaml
template_cover_1:
  name: 冲击型
  layout: 大标题 + 冲击图 + 数据标签
  font_size: 72pt (标题)
  image_ratio: 0.6
  
template_cover_2:
  name: 简约型
  layout: 居中标题 + 纯色背景 + 小图标
  font_size: 48pt
  image_ratio: 0.2

template_cover_3:
  name: 分屏型
  layout: 左文右图 / 上文下图
  font_size: 56pt
  image_ratio: 0.5

# ... 其他7种模板
```

---

## 4. 质量DNA标准

### 4.1 评分维度（6维）

#### 维度1: 结构完整性（Structure）
```yaml
weight: 0.25
criteria:
  - h2数量符合模板要求
  - 段落层级清晰
  - 逻辑递进合理
  - 开篇结尾完整
scoring:
  10分: 完全符合结构模板
  8分: 轻微偏差（±1个h2）
  6分: 明显偏差但可读
  4分: 结构混乱
```

#### 维度2: 内容质量（Content）
```yaml
weight: 0.25
criteria:
  - 事实准确性
  - 论据充分性
  - 数据可信度
  - 引用规范性
scoring:
  10分: 所有论点有据可查
  8分: 主要论点有据
  6分: 部分论点缺乏支撑
  4分: 大量无据断言
```

#### 维度3: 文风一致性（Tone）
```yaml
weight: 0.20
criteria:
  - 与目标风格DNA匹配度
  - 用词风格统一
  - 修辞手法恰当
  - 情感基调稳定
scoring:
  10分: 完全符合目标风格
  8分: 基本符合，偶有偏离
  6分: 风格混杂
  4分: 风格错位
```

#### 维度4: 可读性（Readability）
```yaml
weight: 0.15
criteria:
  - 句子长度适中
  - 段落长度合理
  - 专业术语解释
  - 排版清晰
scoring:
  10分: 流畅易读
  8分: 基本流畅
  6分: 部分晦涩
  4分: 难以理解
```

#### 维度5: 锚点完整性（Anchors）
```yaml
weight: 0.10
criteria:
  - 图片锚点保留率
  - 链接锚点保留率
  - 引用锚点保留率
  - 锚点位置合理性
scoring:
  10分: 100%保留且位置合理
  8分: ≥90%保留
  6分: ≥70%保留
  4分: <70%保留
```

#### 维度6: 字数合规性（Word Count）
```yaml
weight: 0.05
criteria:
  - 整体字数在目标范围
  - 各段落字数均衡
scoring:
  10分: 完全在范围内
  8分: 偏差≤10%
  6分: 偏差≤20%
  4分: 偏差>20%
```

### 4.2 综合评分公式

```python
overall_score = (
    structure_score * 0.25 +
    content_score * 0.25 +
    tone_score * 0.20 +
    readability_score * 0.15 +
    anchor_score * 0.10 +
    wordcount_score * 0.05
)

quality_level = {
    overall_score >= 9.0: "Excellent",
    overall_score >= 8.0: "Ready",
    overall_score >= 7.0: "Review",
    overall_score >= 6.0: "Needs Work",
    overall_score < 6.0: "Reject"
}
```

---

## 5. DNA配置系统

### 5.1 配置文件结构

```yaml
# dna_config.yaml

project:
  name: "大声自媒体创作工作台"
  version: "2.0.0"

default_style:
  primary: "normal"      # 默认风格
  fallback: "academic"   # 备用风格

default_structure:
  template: "PCIS"       # 默认结构模板
  h2_count: 3           # 默认h2数量
  word_count: 1200      # 默认字数

visual_defaults:
  image_style: "flat_illustration"
  color_palette: "professional"
  cover_template: "template_cover_1"

quality_thresholds:
  draft_min_score: 7.0
  rewrite_min_score: 8.0
  publish_min_score: 8.5

ai_capabilities:
  reasoning_model: "claude-opus-4-6"
  writing_model: "claude-sonnet-4-6"
  image_model: "dall-e-3"
  video_script_model: "claude-sonnet-4-6"
```

### 5.2 DNA选择器

```python
class DNASelector:
    """DNA智能选择器"""
    
    def select_style(self, topic_type, audience, platform):
        """根据主题、受众、平台选择最佳风格"""
        rules = {
            ("政治", "知识精英", "微信"): "luxun",
            ("科技", "年轻人", "小红书"): "lemon",
            ("金融", "投资者", "微信"): "academic",
            ("热点", "大众", "抖音"): "hot",
        }
        return rules.get((topic_type, audience, platform), "normal")
    
    def select_structure(self, content_type, word_count):
        """根据内容类型和字数选择结构模板"""
        if content_type == "分析":
            return "PCIS" if word_count > 1500 else "PAS"
        elif content_type == "对比":
            return "CCS"
        elif content_type == "叙事":
            return "Timeline"
        else:
            return "MultiDimension"
    
    def select_visual_style(self, topic_seriousness):
        """根据主题严肃程度选择视觉风格"""
        if topic_seriousness > 0.8:
            return "realistic"
        elif topic_seriousness > 0.5:
            return "data_chart"
        else:
            return "flat_illustration"
```

---

## 6. DNA进化机制

### 6.1 学习反馈循环

```
[内容发布] → [数据收集]
     ↓
[效果分析] → [模式识别]
     ↓
[DNA更新] → [知识沉淀]
     ↓
[下次应用] ← [持续优化]
```

### 6.2 进化规则

```yaml
evolution_rules:
  # 风格进化
  style_evolution:
    trigger: 连续5篇同风格文章平均阅读量 > 基线20%
    action: 提升该风格的推荐权重
    
  # 结构进化
  structure_evolution:
    trigger: 某结构模板的完成率 > 90%
    action: 标记为"高效模板"
    
  # 视觉进化
  visual_evolution:
    trigger: 某视觉风格的点击率 > 平均30%
    action: 增加该风格的使用频率
    
  # 质量标准进化
  quality_evolution:
    trigger: 用户反馈 + 数据表现
    action: 动态调整评分权重
```

---

## 7. DNA API接口

### 7.1 风格DNA调用

```python
from dna_engine import StyleDNA

# 获取风格DNA
style = StyleDNA.get("luxun")

# 应用风格
styled_text = style.apply(original_text, 
                          intensity=0.8,  # 风格强度
                          preserve_facts=True)

# 评估风格匹配度
score = style.evaluate(text)
```

### 7.2 结构DNA调用

```python
from dna_engine import StructureDNA

# 获取结构模板
template = StructureDNA.get("PCIS")

# 生成结构
structure = template.generate(
    topic="稳定币牌照",
    word_count=1500,
    h2_count=4
)

# 验证结构
is_valid = template.validate(article)
```

### 7.3 质量DNA调用

```python
from dna_engine import QualityDNA

# 评分
report = QualityDNA.score(
    text=article,
    target_style="normal",
    target_structure="PCIS"
)

print(report.overall_score)  # 8.5
print(report.dimensions)     # {structure: 9.0, content: 8.5, ...}
print(report.suggestions)    # ["增强论据", "调整段落长度"]
```

---

**DNA系统设计完成**
**下一步**: 实现DNA引擎核心代码
