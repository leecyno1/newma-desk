# 仓库对比分析与优化方案

## 一、核心差异分析

### 1. wewrite (oaker-io/wewrite)

**定位**：单人公众号全流程自动化工具

**核心优势**：
- **完整的写作流程**：热点抓取 → 选题 → 框架 → 素材采集 → 内容增强 → 写作 → SEO → 视觉AI → 排版推送
- **风格学习系统**：范文风格库（exemplar-based few-shot）+ 学习飞轮（learn-edits）
- **7种写作框架**：痛点型、故事型、清单型、对比型、热点解读型、纯观点型、复盘型
- **内容增强策略**：角度发现、密度强化、细节锚定、真实体感（按框架类型自动匹配）
- **5种写作人格**：midnight-friend、warm-editor、industry-observer、sharp-journalist、cold-analyst
- **排版引擎**：16+主题 + 微信兼容修复 + 暗黑模式 + 容器语法
- **质量检测**：humanness_score.py（11项检测）
- **SEO优化**：百度+360搜索量化评分
- **工具链完整**：Python脚本 + CLI工具 + 微信API集成

**技术特点**：
- 单一SKILL.md管道（Step 1-8）
- 降级策略完善（每步都有fallback）
- 进度追踪（TaskCreate/TaskUpdate）
- 辅助功能按需加载

### 2. wechat-skills (gainubi/wechat-skills)

**定位**：模块化公众号写作技能套件

**核心优势**：
- **模块化设计**：5个独立技能，职责清晰
  - wechat-style-profiler：14维风格分析框架
  - wechat-topic-outline-planner：选题与大纲策划
  - wechat-draft-writer：基于风格DNA写初稿
  - wechat-title-generator：标题生成与打分
  - thesis-word-formatter：论文排版（额外能力）
- **14维风格分析框架**：
  - 表层特征（4维）：用词习惯、词汇句式、句式节奏、语气基调
  - 结构特征（3维）：段落结构、文章结构模式、论证逻辑
  - 深层特征（4维）：节奏感、修辞手法、情感表达、思维特征
  - 独特标记（3维）：专业度体现、签名式标记、起承转合微操
- **强制分析章节**：段落配方、叙述方法体系、内容推进方式、标点符号偏好、分块习惯
- **用户校准循环**：初版画像 → 用户确认 → 定点修正 → 固化
- **风格DNA资产化**：可长期迭代复用的风格画像文件

**技术特点**：
- 多技能协作模式
- 强调证据和边界
- 质量红线明确
- 适配微信阅读体验

### 3. newma-media-studio (本地仓库)

**定位**：多人协作的7阶段媒体生产流水线

**核心优势**：
- **固定7阶段流程**：intake → brief → draft → material → rewrite → publish → postmortem
- **多人协作设计**：每题独立目录、飞书集成、人工审核节点
- **4版本改写**：平台×DNA×情绪档位（微信/小红书 × luxun/lemon × hot/normal）
- **素材生成**：图表、图片、视频素材自动生成与回填
- **视频增强**：finance-motion-8787引擎生成动态图表视频和叙事动画
- **阶段路由**：orchestrator强制阶段顺序，防止跳阶段
- **manifest机制**：每阶段必须产出文档+manifest JSON

**技术特点**：
- 流水线式架构
- 强约束（不可跳阶段、每题隔离、继承规则）
- Python脚本驱动
- 环境变量配置

## 二、本地仓库的不足

### 1. 缺少风格学习系统
- 没有风格DNA提取机制
- 没有范文库系统
- 没有学习飞轮（learn-edits）
- 改写阶段只有luxun/lemon两种预设DNA，无法学习用户个人风格

### 2. 缺少写作框架库
- draft阶段只生成"标准事实稿"
- rewrite阶段只做平台适配，没有框架选择
- 缺少痛点型、故事型、清单型等结构化框架

### 3. 缺少内容增强策略
- 没有角度发现、密度强化、细节锚定、真实体感等策略
- 素材采集与内容生成脱节

### 4. 缺少质量检测
- 没有文章质量自检机制
- 没有humanness score类似的量化评估

### 5. 缺少SEO优化
- 没有热点抓取
- 没有关键词分析
- 没有搜索量化评分

### 6. 风格分析不够深入
- 没有14维风格分析框架
- 没有段落配方、叙述方法体系、内容推进方式等深度分析
- 没有标点符号偏好、分块习惯等细节分析

## 三、优化方案

### 方案A：渐进式融合（推荐）

**阶段1：增强rewrite阶段**
1. 新增 `dasheng-style-profiler` 技能
   - 移植14维风格分析框架
   - 支持从历史文章提取风格DNA
   - 生成可复用的风格画像文件
2. 改造rewrite阶段
   - 在luxun/lemon基础上增加用户个人DNA选项
   - 支持范文风格库注入
   - 增加学习飞轮机制

**阶段2：增强draft阶段**
1. 新增 `references/frameworks.md`
   - 移植7种写作框架
2. 新增 `references/content-enhance.md`
   - 移植4种内容增强策略
3. 改造draft阶段
   - 框架选择环节
   - 内容增强执行

**阶段3：增强brief阶段**
1. 新增热点抓取脚本
2. 新增SEO评分脚本
3. 改造brief阶段
   - 集成热点数据
   - SEO量化评分

**阶段4：增加质量检测**
1. 移植humanness_score.py
2. 在rewrite后增加质量自检环节
3. 输出质量报告

### 方案B：独立技能扩展

保持现有7阶段流程不变，新增独立技能：
1. `dasheng-style-profiler`：风格分析与DNA提取
2. `dasheng-quality-checker`：文章质量检测
3. `dasheng-seo-optimizer`：SEO优化与热点分析

用户可选择性使用，不强制集成到主流程。

### 方案C：混合架构

1. 保持orchestrator + 5个stage技能的主架构
2. 在rewrite阶段内部集成风格学习系统
3. 在draft阶段内部集成框架库和内容增强
4. 新增独立的质量检测和SEO优化技能

## 四、推荐实施路径

**优先级1（立即实施）**：
1. 创建 `dasheng-style-profiler` 技能
2. 在rewrite阶段增加个人风格DNA支持
3. 添加 `references/frameworks.md` 和 `references/content-enhance.md`

**优先级2（短期实施）**：
1. 移植humanness_score质量检测
2. 增加学习飞轮机制
3. 改造draft阶段支持框架选择

**优先级3（中期实施）**：
1. 集成热点抓取
2. 集成SEO评分
3. 完善质量自检报告

## 五、关键技术点

### 1. 风格DNA文件格式
```yaml
author: "作者名"
platform: "wechat"
created_at: "2026-04-04"
samples_count: 5

# 14维分析
style_14d:
  surface:
    vocabulary: "..."
    sentence_pattern: "..."
    rhythm: "..."
    tone: "..."
  structure:
    paragraph: "..."
    article: "..."
    logic: "..."
  deep:
    rhythm_sense: "..."
    rhetoric: "..."
    emotion: "..."
    thinking: "..."
  unique:
    professionalism: "..."
    signature: "..."
    structure_micro: "..."

# 强制章节
paragraph_recipe: "..."
narrative_system: "..."
content_progression: "..."
punctuation_preference: "..."
chunking_habit: "..."

# Few-shot示例
exemplars:
  - text: "..."
    context: "..."
```

### 2. 框架与增强策略映射
```python
FRAMEWORK_ENHANCE_MAP = {
    "热点解读型": "角度发现",
    "纯观点型": "角度发现",
    "痛点型": "密度强化",
    "清单型": "密度强化",
    "故事型": "细节锚定",
    "复盘型": "细节锚定",
    "对比型": "真实体感"
}
```

### 3. 质量检测集成点
- draft阶段后：快速自检（结构、逻辑）
- rewrite阶段后：完整检测（11项指标）
- publish阶段前：最终验证

## 六、风险与注意事项

1. **流程复杂度**：增加功能会增加流程复杂度，需要保持orchestrator的清晰路由
2. **性能影响**：风格分析和质量检测会增加执行时间
3. **兼容性**：需要确保新功能不破坏现有的飞书集成和manifest机制
4. **用户学习成本**：新增功能需要更新文档和烟雾测试
5. **维护成本**：更多的脚本和依赖需要更多的维护工作

## 七、下一步行动

1. 确认优化方案（A/B/C）
2. 创建新技能目录结构
3. 移植核心文件（frameworks.md、content-enhance.md、style-14d-framework.md）
4. 编写新技能的SKILL.md
5. 更新CLAUDE.md和SMOKE_PROMPTS.md
6. 测试集成
