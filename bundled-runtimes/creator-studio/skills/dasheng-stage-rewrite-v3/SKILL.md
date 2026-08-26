---
name: dasheng-stage-rewrite-v3
description: Stage 5 Rewrite v3 - 渠道改写（集成增强质量评分和锚点映射）
version: 3.0.0
stage: rewrite
runner: node
---

# Newma Stage Rewrite v3 - 渠道改写

## 功能概述

Stage 5 Rewrite v3 是大声自媒体创作工作台的渠道改写阶段，负责将标准基线初稿改写为4个平台/语气组合版本。

**核心升级**（相比v2）：
- 集成 `EnhancedPromptBuilder` - 带字数预算的增强Prompt构建
- 集成 `QualityScorer` - 自动质量评分（≥8.0才通过）
- 集成 `AnchorMapper` - 锚点保留率校验（≥80%）
- 集成 `VersionGenerator` - 并行生成4个版本
- 字数校验从±30%收紧到±15%

## 输入要求

### 必需输入
- `draft_manifest.json` - 初稿清单（来自Draft阶段）
- `final_structure_snapshot.json` - **MANDATORY GATE** - 最终结构快照（必须status=approved）

### 可选输入
- `--run-id` - 自定义运行ID（默认从draft manifest读取）
- `--output-dir` - 自定义输出目录
- `--versions` - 自定义版本列表（默认：wechat_hot,wechat_normal,xiaohongshu_hot,xiaohongshu_normal）

## 输出产物

### 文档交付视图
- `<topic>__rewrite_bundle.md` - 所有版本打包文档
- `<topic>__wechat_luxun_hot.md` - 微信公众号热点版（鲁迅风格）
- `<topic>__wechat_lemon_normal.md` - 微信公众号常规版（柠檬风格）
- `<topic>__xhs_video_luxun_hot.md` - 小红书视频热点版（鲁迅风格）
- `<topic>__xhs_video_lemon_normal.md` - 小红书视频常规版（柠檬风格）

### 正式状态源（Canonical State）
- `rewrite_manifest.json` - 改写清单（包含所有版本元数据、质量评分、锚点保留率）
- `meta.json` - 元数据（结构继承追踪）

## 四个版本说明

| 版本ID | 平台 | 语气 | 目标字数 | 特点 |
|--------|------|------|----------|------|
| wechat_hot | 微信公众号 | 热点版 | 1300字 | 鲁迅风格，犀利深刻 |
| wechat_normal | 微信公众号 | 常规版 | 1000字 | 柠檬风格，温和理性 |
| xiaohongshu_hot | 小红书 | 热点版 | 900字 | 鲁迅风格，短平快 |
| xiaohongshu_normal | 小红书 | 常规版 | 650字 | 柠檬风格，轻松易读 |

## 执行方式

### Node.js API
```javascript
const { runRewrite } = require('./skills/dasheng-stage-rewrite-v3');

const result = runRewrite('/path/to/draft_manifest.json', {
  runId: '2026-04-14_120000',
  outputDir: '/custom/output/dir',
  versions: ['wechat_hot', 'wechat_normal', 'xiaohongshu_hot', 'xiaohongshu_normal']
});

console.log(result);
// {
//   success: true,
//   run_id: '2026-04-14_120000',
//   output_dir: '~/Desktop/自媒体创作/00_改写/2026-04-14_120000',
//   manifest_file: '.../rewrite_manifest.json',
//   completed_versions: 12,  // 3个主题 × 4个版本
//   failed_topics: 0,
//   total_topics: 3,
//   versions: ['wechat_hot', 'wechat_normal', 'xiaohongshu_hot', 'xiaohongshu_normal'],
//   next_step: 'dasheng-stage-publish'
// }
```

### Python 直接调用
```bash
python3 scripts/rewrite_execute_stage5.py \
  --draft-manifest /path/to/draft_manifest.json \
  --run-id 2026-04-14_120000 \
  --versions wechat_hot,wechat_normal,xiaohongshu_hot,xiaohongshu_normal \
  --json-output
```

## Gate 验证规则

### Upstream Gate: `final_structure_snapshot.json`
- 必须存在且状态为 `approved` / `locked` / `finalized`
- 必须包含每个主题的 `final_primary_sections`（最终一级结构）
- 如果gate状态为 `pending`，Rewrite阶段将拒绝执行

### Output Gate: `rewrite_manifest.json`
- 包含所有版本的质量评分、字数、锚点保留率
- 每个版本必须通过质量门槛：
  - `quality_score >= 8.0`
  - `word_count` 在目标±15%以内
  - `anchor_preserved_rate >= 80%`

## 质量标准

### 1. 质量评分（QualityScorer）
- **最低分数**：8.0/10（Rewrite阶段标准，高于Draft的7.0）
- **评分维度**：
  - 结构完整性
  - 论证逻辑
  - 证据充分性
  - 语言流畅度
  - 平台适配度

### 2. 字数控制
- **偏差范围**：目标字数±15%（从v2的±30%收紧）
- **示例**：
  - wechat_hot目标1300字 → 允许范围：1105-1495字
  - xiaohongshu_normal目标650字 → 允许范围：552-747字

### 3. 锚点保留率（AnchorMapper）
- **最低保留率**：80%
- **锚点类型**：
  - `{{image: ...}}` - 配图占位
  - `{{link: ...}}` - 链接占位
  - `{{ref: ...}}` - 参考文献标注
- **验证逻辑**：改写后的文档必须保留原稿中至少80%的锚点标注

### 4. 结构继承
- 必须继承 `final_structure_snapshot.json` 中的结构
- 追踪哪些顶层section被保留/删除/新增
- 追踪哪些subsection被保留/删除/新增
- 追踪哪些 Draft 资产锚点被保留/删除/新增

## 核心模块

### EnhancedPromptBuilder
构建带字数预算的改写Prompt：
```python
builder = EnhancedPromptBuilder()
prompt = builder.build_enhanced_prompt(
    platform="微信公众号",
    tone="热点版",
    original_text=original_draft,
    target_word_count=1300,
    min_word_count=1105,
    max_word_count=1495,
    primary_audience="关注科技和金融的中产阶级"
)
```

### QualityScorer
自动质量评分：
```python
scorer = QualityScorer(
    platform="wechat",
    tone="hot",
    original_doc=original_draft,
    final_snapshot={"sections": [...]}
)
quality_report = scorer.score(rewritten_text)
# quality_report.overall_score: 8.5
# quality_report.status: "excellent"
```

### AnchorMapper
锚点保留率校验：
```python
anchor_mapper = AnchorMapper(original_draft, rewritten_text)
anchor_report = anchor_mapper.generate_report()
# anchor_report.preserved_rate: 85.7
# anchor_report.preserved_anchors: [...]
# anchor_report.removed_anchors: [...]
```

### VersionGenerator
并行生成4个版本：
```python
generator = VersionGenerator()
schema = generator.get_version_schema("wechat_hot")
# schema["platform"]: "wechat"
# schema["tone"]: "hot"
# schema["word_count"]: {"target": 1300, "min": 1105, "max": 1495}
```

## 自动重试逻辑

如果某个版本未通过质量门槛，`should_regenerate()` 会返回True，触发重新生成：
- 质量评分 < 8.0
- 字数偏差 > 15%
- 锚点保留率 < 80%

## 下游阶段

- **Next Stage**: `dasheng-stage-publish` (Stage 6 Publish - 渠道分发)
- **Dependent Stages**: Publish (Stage 6)

## 技术实现

- **执行器**: `scripts/rewrite_execute_stage5.py`
- **包装器**: `skills/dasheng-stage-rewrite-v3/index.js`
- **超时限制**: 10分钟（改写需要更长时间）
- **输出格式**: JSON to stdout
- **AI模型**: claude-opus-4-6（通过Anthropic API调用）

## 与v2的区别

| 特性 | v2 | v3 |
|------|----|----|
| 质量评分 | 无 | 集成QualityScorer，≥8.0 |
| 字数控制 | ±30% | ±15%（更严格） |
| 锚点校验 | 无 | 集成AnchorMapper，≥80% |
| Prompt构建 | 基础 | EnhancedPromptBuilder |
| CLI参数 | 硬编码 | 完整argparse支持 |
| JSON输出 | 无 | --json-output标志 |
| 并行生成 | 串行 | VersionGenerator并行 |
