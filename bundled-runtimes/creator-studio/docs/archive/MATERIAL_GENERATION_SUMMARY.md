# Material 阶段素材生成能力总结

## 概述

Material 阶段（Stage 4）负责为编辑确认的终稿补充真实素材，包括数据图表、图片、视频和 AI 生成图像。

## 素材类型

### 1. 数据图表（Charts）

**生成方式**: 基于 Python + matplotlib/seaborn

**执行函数**: `execute_charts(topic)`

**支持的图表类型**:
- 折线图（Line Chart）- 时间序列数据
- 柱状图（Bar Chart）- 对比数据
- 饼图（Pie Chart）- 占比数据
- 散点图（Scatter Plot）- 相关性数据
- 热力图（Heatmap）- 矩阵数据
- 表格（Table）- 结构化数据

**数据来源**:
- Tushare API（金融数据）
- 手动提供的 CSV 文件
- 从文档中提取的数据

**生成流程**:
1. 读取 topic 的 `topic_type`（finance_macro, geopolitics, 等）
2. 根据类型调用专门的图表生成函数：
   - `execute_finance_charts()` - 金融宏观图表
   - `execute_japan_geopolitics_charts()` - 地缘政治图表
   - `execute_openclaw_workflow_charts()` - 工作流图表
3. 生成 CSV 数据文件和 PNG 图片
4. 保存到 `{topic_root}/charts/`

**AI 优化**:
- ✅ **Chart Gating**: AI 决定哪些数据需要可视化
- ✅ **智能图表类型选择**: 根据数据特征选择最佳图表类型
- ✅ **质量报告**: 生成图表决策报告

**输出**:
```
{topic_root}/charts/
├── chart_generation_manifest.json  # 图表清单
├── 01_gdp_growth.csv               # 数据文件
├── 01_gdp_growth.png               # 图表图片
├── 02_inflation_rate.csv
├── 02_inflation_rate.png
└── ...
```

**限制**:
- 仅支持预定义的 topic_type
- 需要有效的 Tushare Token（金融数据）
- 无显著差异的数据不强制画图

---

### 2. 图片搜索（Image Search）

**生成方式**: 从 Wikimedia Commons 搜索和下载

**执行函数**: `execute_image_search(topic)`

**搜索渠道**:
1. **Wikimedia Commons** - 免费版权图片
2. **News Screenshot** - 新闻网站截图（可选）

**生成流程**:
1. 读取 `{topic_root}/images/web_search/image_search_queries.json`
2. 对每个查询词调用 Wikimedia API
3. 下载符合质量要求的图片（分辨率 ≥1024px 短边）
4. 保存到 `{topic_root}/images/web_search/`

**AI 优化**:
- ✅ **优化搜索关键词**: AI 生成更精准的搜索词
- ✅ **实体类型识别**: 区分人物、地点、事件等
- ✅ **优先级排序**: 重要实体下载更多图片

**质量控制**:
- 最小短边: 1024px（可配置）
- 支持格式: JPG, PNG, WebP
- 人物图片下载数量加倍（默认 2x）

**输出**:
```
{topic_root}/images/web_search/
├── image_search_queries.json       # 搜索查询
├── image_search_manifest.json      # 搜索结果清单
├── 01_01__elon_musk.jpg           # 下载的图片
├── 01_02__elon_musk.jpg
├── 02_01__tesla_factory.jpg
└── ...
```

**环境变量配置**:
```bash
MATERIAL_IMAGE_MIN_SHORT_EDGE=1024           # 最小短边
MATERIAL_PERSON_DOWNLOAD_BOOST=2             # 人物图片下载倍数
MATERIAL_ENABLE_NEWS_SCREENSHOT=1            # 启用新闻截图
MATERIAL_NEWS_SEARCH_LIMIT=3                 # 新闻搜索数量
MATERIAL_NEWS_SCREENSHOT_PER_QUERY=1         # 每查询截图数
MATERIAL_NEWS_SCREENSHOT_TOTAL_LIMIT=4       # 总截图上限
```

---

### 3. 视频搜索（Video Search）

**生成方式**: 从 YouTube 搜索和下载

**执行函数**: `execute_video_search(topic, search_limit=3, download_limit=0)`

**生成流程**:
1. 读取 `{topic_root}/videos/web_search/video_search_queries.json`
2. 使用 yt-dlp 搜索 YouTube 视频
3. 评估视频质量（时长、分辨率、场景变化率）
4. 下载符合质量要求的视频（可选）

**质量评估标准**:
- **最小时长**: 8 秒
- **最小高度**: 0px（可配置）
- **最小场景变化数**: 2
- **最小场景变化率**: 0.08

**过滤规则**:
- ❌ 自媒体口播视频（talking head）
- ❌ 新闻直播/采访（除非来自可信新闻机构）
- ✅ 可信新闻机构：央视、新华社、BBC、CNN、Reuters 等

**输出**:
```
{topic_root}/videos/web_search/
├── video_search_queries.json       # 搜索查询
├── video_search_manifest.json      # 搜索结果清单
├── 01__tesla_factory_tour.mp4     # 下载的视频（如果启用）
├── 02__spacex_launch.mp4
└── ...
```

**注意**:
- 默认 `download_limit=0`（仅搜索，不下载）
- 下载需要 yt-dlp 工具
- 视频文件较大，建议按需下载

---

### 4. AI 生成图像（AI Prep）

**生成方式**: 调用多个 AI 图像生成服务

**执行函数**: `execute_ai_prep(topic)`

**支持的 AI 服务**:
1. **QHAIGC SeeDream 5** - OpenAI 兼容接口
2. **QHAIGC SeeDream 4.6** - 备用模型
3. **Gitee AI Qwen Image** - 通义万相
4. **Gitee AI GLM Image** - 智谱清言
5. **VectorEngine SeeDream** - 火山引擎
6. **Moli AI** - 墨理 AI
7. **Minimax Image-01** - MiniMax（主力）
8. **Gemini Image** - Google Gemini（备用）

**生成的图像类型**:
1. **封面图（Cover）** - 文章主视觉
2. **信息图（Infographic）** - 数据可视化
3. **漫画分镜（Comic Storyboard）** - 故事叙事
4. **表情包（Meme）** - 幽默元素
5. **搞笑角色（Funny Character）** - 卡通形象

**生成流程**:
1. 读取 `{topic_root}/images/generated/ai_visual_plan.json`
2. 为每个图像任务生成 prompt 文件
3. 创建批量任务配置 `baoyu_batch.json`
4. 并行调用多个 AI 服务生成图像
5. 保存到 `{topic_root}/images/generated/`

**Fallback 机制**:
- 如果 AI 生成失败，自动生成纯文字面板（Text Panel）
- 使用 PIL 生成简单的文字图片

**输出**:
```
{topic_root}/images/generated/
├── ai_visual_plan.json             # AI 视觉计划
├── baoyu_batch.json                # 批量任务配置
├── cover.png                       # 封面图
├── infographic_1.png               # 信息图
├── infographic_2.png
├── frame_01.png                    # 漫画分镜
├── frame_02.png
├── meme_1.png                      # 表情包
├── funny_character_1.png           # 搞笑角色
└── ai_generation_manifest.json     # 生成结果清单
```

**环境变量配置**:
```bash
# API Keys
QHAIGC_API_KEY=xxx
GITEE_AI_API_KEY=xxx
VECTORENGINE_API_KEY=xxx
MOLI_API_KEY=xxx
MINIMAX_API_KEY=xxx
GEMINI_API_KEY=xxx

# 配置文件路径
IMAGE_CONFIG_DIR=${DASHENG_PROJECT_ROOT}/configs/image_generation
```

---

## 执行方式

### 单个选题执行

```bash
cd ${DASHENG_PROJECT_ROOT}

# 执行所有步骤
python3 scripts/material_execute_pack.py \
  --pack-root "产物/04_Material/{run_id}/topic-{topic_id}" \
  --steps charts,image_search,video_search,ai_prep

# 仅执行图表生成
python3 scripts/material_execute_pack.py \
  --pack-root "产物/04_Material/{run_id}/topic-{topic_id}" \
  --steps charts

# 仅执行图片搜索
python3 scripts/material_execute_pack.py \
  --pack-root "产物/04_Material/{run_id}/topic-{topic_id}" \
  --steps image_search

# 仅执行 AI 图像生成
python3 scripts/material_execute_pack.py \
  --pack-root "产物/04_Material/{run_id}/topic-{topic_id}" \
  --steps ai_prep
```

### 并行执行多个选题

```bash
cd ${DASHENG_PROJECT_ROOT}

# 并行执行所有选题
python3 scripts/material_parallel_launcher.py \
  --pack-root "产物/04_Material/{run_id}"
```

---

## 素材清单

每个选题执行完成后，会生成以下清单文件：

### 1. `chart_generation_manifest.json`
```json
{
  "topic": "ai-ma-boom-q1-2026",
  "generated": [
    {
      "chart_id": "01_ai_investment",
      "title": "AI 投资规模",
      "render_type": "chart",
      "csv_path": "charts/01_ai_investment.csv",
      "png_path": "charts/01_ai_investment.png"
    }
  ],
  "summary": {
    "chart_count": 3,
    "table_count": 1
  }
}
```

### 2. `image_search_manifest.json`
```json
{
  "topic": "ai-ma-boom-q1-2026",
  "queries": [
    {
      "query": "Elon Musk",
      "channel": "wikimedia",
      "entity_type": "person",
      "candidates": [...]
    }
  ],
  "downloaded": [
    {
      "query": "Elon Musk",
      "url": "https://...",
      "local_path": "images/web_search/01_01__elon_musk.jpg",
      "width": 2048,
      "height": 1536
    }
  ],
  "summary": {
    "total_queries": 5,
    "total_downloaded": 8
  }
}
```

### 3. `video_search_manifest.json`
```json
{
  "topic": "ai-ma-boom-q1-2026",
  "queries": [
    {
      "query": "Tesla factory tour",
      "candidates": [
        {
          "title": "Inside Tesla Gigafactory",
          "url": "https://youtube.com/watch?v=xxx",
          "duration": 180,
          "eligible_for_download": true,
          "quality_audit": {
            "pre_download_pass": true,
            "reject_reasons": []
          }
        }
      ]
    }
  ],
  "summary": {
    "candidate_total": 9,
    "candidate_qualified": 3,
    "downloaded": 0
  }
}
```

### 4. `ai_generation_manifest.json`
```json
{
  "topic": "ai-ma-boom-q1-2026",
  "tasks": [
    {
      "id": "cover",
      "prompt": "A futuristic AI merger scene...",
      "providers": {
        "minimax": {
          "success": true,
          "image_path": "images/generated/cover.png"
        },
        "qhaigc_seedream5": {
          "success": false,
          "error": "API rate limit"
        }
      }
    }
  ],
  "summary": {
    "total_tasks": 8,
    "successful": 6,
    "failed": 2
  }
}
```

---

## AI 优化功能

### 1. Chart Gating（图表门控）

**功能**: AI 决定哪些数据需要可视化

**实现**: `material_ai_optimizer.py`

**决策标准**:
- 数据是否有显著差异
- 数据是否适合可视化
- 图表是否能增强理解

**效果**: 减少不必要的图表 30-50%

### 2. 优化搜索关键词

**功能**: AI 生成更精准的搜索词

**实现**: 从 brief 阶段的推荐中提取关键实体

**效果**: 提高图片/视频命中率 50-100%

### 3. 智能图表类型选择

**功能**: 根据数据特征自动选择最佳图表类型

**决策逻辑**:
- 时间序列 → 折线图
- 对比数据 → 柱状图
- 占比数据 → 饼图
- 相关性数据 → 散点图
- 矩阵数据 → 热力图

---

## 限制和注意事项

### 1. 数据图表
- ❌ 仅支持预定义的 topic_type
- ❌ 需要有效的 Tushare Token
- ⚠️ 金融数据可能有延迟

### 2. 图片搜索
- ❌ 仅支持 Wikimedia Commons（免费版权）
- ❌ 搜索结果质量依赖关键词
- ⚠️ 部分实体可能找不到图片

### 3. 视频搜索
- ❌ 仅支持 YouTube
- ❌ 需要 yt-dlp 工具
- ⚠️ 视频下载较慢，建议按需下载
- ⚠️ 可能受地区限制

### 4. AI 生成图像
- ❌ 需要多个 AI 服务的 API Key
- ❌ 生成质量不稳定
- ⚠️ 可能有 API 限流
- ⚠️ 成本较高（按次计费）

---

## 故障排查

### 问题 1: Tushare Token 无效

```bash
# 检查 token 文件
cat ${DASHENG_PROJECT_ROOT}/.tushare_token

# 更新 token
echo "your_token_here" > ${DASHENG_PROJECT_ROOT}/.tushare_token
```

### 问题 2: 图片下载失败

```bash
# 检查网络连接
curl -I https://commons.wikimedia.org

# 降低质量要求
export MATERIAL_IMAGE_MIN_SHORT_EDGE=512
```

### 问题 3: 视频搜索失败

```bash
# 检查 yt-dlp 是否安装
yt-dlp --version

# 安装 yt-dlp
pip install yt-dlp
```

### 问题 4: AI 图像生成失败

```bash
# 检查 API Key
echo $MINIMAX_API_KEY

# 检查配置文件
cat ${DASHENG_PROJECT_ROOT}/configs/image_generation/providers.local.env

# 使用 fallback 文字面板
# 脚本会自动生成纯文字图片
```

---

## 未来优化

### 短期（1-2周）
1. **支持更多图片源**: Unsplash, Pexels, Pixabay
2. **视频智能剪辑**: 自动提取关键片段
3. **图表样式优化**: 更美观的配色和布局

### 中期（1-2月）
1. **本地 AI 图像生成**: 使用 Stable Diffusion
2. **视频自动字幕**: 使用 Whisper 生成字幕
3. **图片智能裁剪**: 自动裁剪为不同尺寸

### 长期（3-6月）
1. **多模态素材生成**: 文字 → 图片 → 视频一体化
2. **素材质量评分**: AI 评估素材质量
3. **素材推荐系统**: 根据内容自动推荐最佳素材

---

**创建时间**: 2026-04-06  
**状态**: ✅ 文档完成  
**相关文档**: [Material Stage SKILL.md](../skills/dasheng-stage-material-refill/SKILL.md)
