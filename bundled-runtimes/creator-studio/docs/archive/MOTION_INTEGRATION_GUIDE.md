# Motion 系统整合指南

本文档说明 Finance Motion 8787 和 Remotion 两个系统的分工、整合方式和使用场景。

---

## 系统概述

### Finance Motion 8787

**定位**：互动网页预览系统 + JSON 配置驱动的模板工厂

**核心能力**：
- 23 个模板家族（17 个公开 + 6 个创作者）
- 8 种风格预设（default, glass, broadcast, poster, editorial, newsTicker, neon, zen）
- 4 种调色板（financeBlue, emerald, sunset, mono）
- 实时数据集成（AKShare/Tushare）
- 浏览器实时渲染和交互预览
- WebM 格式视频导出

**运行环境**：
- URL: http://127.0.0.1:8787
- 启动命令：`cd ${PROJECTS_ROOT}/finance-motion-8787 && npm run dev`

### Remotion Video Starter

**定位**：视频渲染引擎 + React 组件驱动的高质量输出

**核心能力**：
- React 组件完全自定义
- 服务器端高质量渲染
- MP4/WebM 格式输出
- 复杂动画和特效支持
- 批量渲染和自动化

**运行环境**：
- URL: http://localhost:3000
- 启动命令：`cd ${LEGACY_OPENCLAW_ROOT}/remotion-video-starter && npm start`

---

## 功能对比

| 维度 | Finance Motion 8787 | Remotion Video Starter |
|------|---------------------|------------------------|
| **核心定位** | 互动网页预览 + JSON 配置 | 视频渲染引擎 + React 组件 |
| **运行环境** | 浏览器实时渲染 | Node.js 离线渲染 |
| **数据驱动** | JSON 配置文件 | React props |
| **模板数量** | 23 个模板家族 | 需手写 React 组件 |
| **风格系统** | 8 种预设风格 | 需手写样式 |
| **实时数据** | AKShare/Tushare 集成 | 需手动集成 |
| **输出格式** | WebM（浏览器录制） | MP4/WebM（高质量渲染） |
| **交互性** | ✅ 支持（网页交互） | ❌ 不支持（静态视频） |
| **渲染质量** | 中等（浏览器限制） | 高（服务器渲染） |
| **开发效率** | 高（JSON 配置） | 低（手写代码） |
| **批量生产** | ❌ 受限 | ✅ 服务器渲染 |
| **自定义能力** | 中等（预设模板） | 高（完全自定义） |

---

## 分工建议

### Finance Motion 8787 适用场景

✅ **开发和验证阶段**
- 快速配置模板和风格
- 实时预览数据效果
- 验证动画时序和节奏
- 调整调色板和视觉风格

✅ **数据探索阶段**
- 测试不同数据源
- 验证图表类型选择
- 调整数据展示密度

✅ **客户演示阶段**
- 交互式演示效果
- 实时调整参数
- 快速响应反馈

### Remotion 适用场景

✅ **生产渲染阶段**
- 最终视频输出
- 高质量渲染要求
- 批量视频生成

✅ **复杂动画需求**
- 自定义特效
- 复杂转场
- 3D 元素

✅ **自动化流程**
- CI/CD 集成
- 定时批量渲染
- 服务器端渲染

---

## 整合工作流

### 推荐流程

```
Step 1: Finance Motion 8787 - 快速迭代
  ↓ 配置 JSON，预览效果
  ↓ 调整风格和数据
  ↓ 验证动画时序
  
Step 2: 导出配置
  ↓ 导出 scenes.json
  ↓ 包含所有场景配置
  
Step 3: 转换为 Remotion 配置
  ↓ 运行转换脚本
  ↓ 生成 Remotion props
  
Step 4: Remotion - 高质量渲染
  ↓ 服务器端渲染
  ↓ 输出最终视频
```

### 详细步骤

#### Step 1: 在 Finance Motion 8787 中设计

1. **启动 Finance Motion 8787**
```bash
cd ${PROJECTS_ROOT}/finance-motion-8787
npm run dev
# 访问 http://127.0.0.1:8787
```

2. **配置场景**
- 编辑 `dashboard/factory.config.json`
- 选择模板家族（timeSeriesStory, barStory 等）
- 配置风格预设（glass, broadcast 等）
- 设置调色板（financeBlue, emerald 等）
- 配置动画参数（enter, emphasis 等）

3. **预览和调整**
- 在浏览器中实时预览
- 切换不同场景标签
- 调整参数直到满意

4. **导出配置**
```bash
# 生成最终的 scenes.json
npm run scenes:build

# 验证配置正确性
npm run scenes:check
```

#### Step 2: 转换为 Remotion 配置

1. **运行转换脚本**
```bash
cd ${PROJECTS_ROOT}/newma-media-studio

python3 scripts/convert_finance_motion_to_remotion.py \
  --input ${PROJECTS_ROOT}/finance-motion-8787/dashboard/scenes.json \
  --output ${LEGACY_OPENCLAW_ROOT}/remotion-video-starter/src/compositions/generated-config.json \
  --style claude-purple
```

2. **转换器功能**
- 读取 Finance Motion 的 `scenes.json`
- 映射模板家族到 Remotion 组件
- 转换调色板和风格参数
- 生成 Remotion 可用的 props

#### Step 3: 在 Remotion 中渲染

1. **启动 Remotion Studio（可选，用于预览）**
```bash
cd ${LEGACY_OPENCLAW_ROOT}/remotion-video-starter
npm start
# 访问 http://localhost:3000
```

2. **渲染最终视频**
```bash
# 渲染单个组合
npx remotion render FinanceNewsXhs out/finance-news.mp4

# 批量渲染（使用生成的配置）
npx remotion render --props=src/compositions/generated-config.json
```

3. **高级渲染选项**
```bash
# 指定分辨率
npx remotion render FinanceNewsXhs out/video.mp4 --width=1920 --height=1080

# 指定帧率
npx remotion render FinanceNewsXhs out/video.mp4 --fps=60

# 指定编码质量
npx remotion render FinanceNewsXhs out/video.mp4 --quality=100

# 并行渲染
npx remotion render FinanceNewsXhs out/video.mp4 --concurrency=4
```

---

## 在 Dasheng 工作流中的应用

### Publish 阶段集成

在 `dasheng-stage-publish-video` 阶段，系统会：

1. **读取 rewrite_manifest.json**
   - 获取推荐的视频风格
   - 获取选题关键数据

2. **选择模板风格**
   - 根据内容类型自动选择风格
   - 或由用户手动指定风格

3. **生成 Finance Motion 配置**
   - 从选题数据生成 `scenes.json`
   - 应用选定的风格预设

4. **预览（可选）**
   - 在 Finance Motion 8787 中预览
   - 用户确认效果

5. **转换并渲染**
   - 转换为 Remotion 配置
   - Remotion 渲染最终视频

### 自动化脚本

```bash
cd ${PROJECTS_ROOT}/newma-media-studio

# 完整的 publish 流程
python3 scripts/publish_video_supplement.py \
  --run-id 2026-04-05_075240_ai \
  --style claude-purple \
  --preview  # 可选：在 Finance Motion 中预览
```

---

## 风格模板映射

### Finance Motion 8787 风格预设

当前支持的 8 种风格：

1. **default** - 默认风格
2. **glass** - 玻璃风格（毛玻璃效果）
3. **broadcast** - 广播风格（新闻播报）
4. **poster** - 海报风格（大字标题）
5. **editorial** - 编辑风格（杂志排版）
6. **newsTicker** - 新闻滚动风格
7. **neon** - 霓虹风格（赛博朋克）
8. **zen** - 禅意极简风格

### Remotion 模板组件

对应的 5 套 Remotion 模板：

1. **ClaudePurple** - Claude 紫色风格
   - Finance Motion 映射：`neon` + 紫粉调色板
   - 特点：科技感、渐变文字、粒子动画

2. **Cyberpunk** - 赛博朋克风格
   - Finance Motion 映射：`neon` + 青品黄调色板
   - 特点：故障效果、扫描线、霓虹边框

3. **FinanceBusiness** - 金融商务风格
   - Finance Motion 映射：`broadcast` + financeBlue 调色板
   - 特点：专业、稳重、数据可视化强调

4. **MedicalLancet** - 医学柳叶刀风格
   - Finance Motion 映射：`editorial` + 红蓝调色板
   - 特点：学术、简洁、高对比度

5. **AnimeLight** - 浅色动漫风格
   - Finance Motion 映射：`zen` + 柔和调色板
   - 特点：可爱、圆角、柔和阴影

### 映射配置文件

`${LEGACY_OPENCLAW_ROOT}/remotion-video-starter/src/templates/template-mapping.json`

```json
{
  "claude-purple": {
    "component": "ClaudePurple",
    "financeMotionStyle": "neon",
    "palette": {
      "primary": "#a855f7",
      "secondary": "#ec4899",
      "background": "#1a0b2e"
    }
  },
  "cyberpunk": {
    "component": "Cyberpunk",
    "financeMotionStyle": "neon",
    "palette": {
      "primary": "#00ffff",
      "secondary": "#ff00ff",
      "accent": "#ffff00",
      "background": "#0a0a1a"
    }
  },
  "finance-business": {
    "component": "FinanceBusiness",
    "financeMotionStyle": "broadcast",
    "palette": {
      "primary": "#ffd700",
      "secondary": "#ffffff",
      "background": "#0a1929"
    }
  },
  "medical-lancet": {
    "component": "MedicalLancet",
    "financeMotionStyle": "editorial",
    "palette": {
      "primary": "#8b0000",
      "secondary": "#003366",
      "background": "#f5f5f5"
    }
  },
  "anime-light": {
    "component": "AnimeLight",
    "financeMotionStyle": "zen",
    "palette": {
      "primary": "#ffb3d9",
      "secondary": "#b3d9ff",
      "accent": "#ffffb3",
      "background": "#fff9f0"
    }
  }
}
```

---

## 转换器使用说明

### 基本用法

```bash
python3 scripts/convert_finance_motion_to_remotion.py \
  --input <finance-motion-scenes.json> \
  --output <remotion-config.json> \
  --style <style-name>
```

### 参数说明

| 参数 | 必需 | 说明 |
|------|------|------|
| `--input` | 是 | Finance Motion 的 scenes.json 路径 |
| `--output` | 是 | 输出的 Remotion 配置文件路径 |
| `--style` | 否 | 风格名称（默认：claude-purple） |
| `--template` | 否 | 指定模板组件（默认：根据风格自动选择） |
| `--fps` | 否 | 帧率（默认：30） |
| `--width` | 否 | 视频宽度（默认：1080） |
| `--height` | 否 | 视频高度（默认：1920） |

### 示例

```bash
# 使用 Claude 紫色风格
python3 scripts/convert_finance_motion_to_remotion.py \
  --input ${PROJECTS_ROOT}/finance-motion-8787/dashboard/scenes.json \
  --output ${LEGACY_OPENCLAW_ROOT}/remotion-video-starter/src/compositions/config.json \
  --style claude-purple

# 使用赛博朋克风格，横版视频
python3 scripts/convert_finance_motion_to_remotion.py \
  --input ${PROJECTS_ROOT}/finance-motion-8787/dashboard/scenes.json \
  --output ${LEGACY_OPENCLAW_ROOT}/remotion-video-starter/src/compositions/config.json \
  --style cyberpunk \
  --width 1920 \
  --height 1080

# 指定特定模板组件
python3 scripts/convert_finance_motion_to_remotion.py \
  --input ${PROJECTS_ROOT}/finance-motion-8787/dashboard/scenes.json \
  --output ${LEGACY_OPENCLAW_ROOT}/remotion-video-starter/src/compositions/config.json \
  --template FinanceBusiness
```

---

## 常见问题

### Q1: 何时使用 Finance Motion 8787，何时使用 Remotion？

**A**: 
- **开发阶段**：使用 Finance Motion 8787 快速迭代和预览
- **生产阶段**：使用 Remotion 渲染最终高质量视频
- **演示阶段**：使用 Finance Motion 8787 交互式演示
- **批量生产**：使用 Remotion 自动化渲染

### Q2: Finance Motion 8787 导出的 WebM 视频质量如何？

**A**: Finance Motion 8787 使用浏览器录制，质量受限于浏览器性能和录制 API。适合快速预览和验证，但不适合最终发布。最终发布应使用 Remotion 渲染。

### Q3: 转换器是否支持所有 Finance Motion 模板？

**A**: 当前转换器支持常用的模板家族（timeSeriesStory, barStory, heroStatement 等）。复杂模板可能需要手动调整 Remotion 组件。

### Q4: 如何在 Remotion 中使用实时数据？

**A**: 
1. 在 Finance Motion 8787 中使用 AKShare/Tushare 获取实时数据
2. 数据会保存到 `scenes.json` 中
3. 转换器会将数据传递给 Remotion props
4. Remotion 组件直接使用 props 中的数据

### Q5: 两个系统可以同时运行吗？

**A**: 可以。Finance Motion 8787 运行在 8787 端口，Remotion 运行在 3000 端口，互不冲突。

---

## 最佳实践

### 1. 开发流程

```
1. 在 Finance Motion 8787 中快速配置和预览
2. 调整到满意后导出 scenes.json
3. 使用转换器生成 Remotion 配置
4. 在 Remotion Studio 中预览（可选）
5. 使用 Remotion CLI 渲染最终视频
```

### 2. 风格选择

- **财经内容**：使用 finance-business 或 claude-purple
- **科技内容**：使用 cyberpunk 或 claude-purple
- **医学内容**：使用 medical-lancet
- **生活内容**：使用 anime-light

### 3. 性能优化

- Finance Motion 8787：使用 Chrome 浏览器，关闭不必要的扩展
- Remotion：使用 `--concurrency` 参数并行渲染，提高速度

### 4. 质量控制

- 在 Finance Motion 8787 中验证数据正确性
- 在 Remotion 中渲染前检查配置文件
- 使用高质量参数渲染最终视频（`--quality=100`）

---

## 相关文档

- [Finance Motion 8787 README](${PROJECTS_ROOT}/finance-motion-8787/README.md)
- [Remotion 官方文档](https://www.remotion.dev/docs)
- [模板风格文档](${PROJECTS_ROOT}/newma-media-studio/skills/dasheng-stage-publish-video/references/template-styles.md)
- [平台元数据规则](${PROJECTS_ROOT}/newma-media-studio/skills/dasheng-stage-rewrite/references/platform-metadata.md)

---

**最后更新**：2026-04-06  
**维护者**：Dasheng Media Team
