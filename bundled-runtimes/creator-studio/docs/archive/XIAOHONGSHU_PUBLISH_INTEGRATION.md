# 小红书自动发布集成文档

## 概述

本文档说明如何将小红书自动发布功能集成到 Dasheng 工作流的 distribute 阶段。

## 现有资源

### 已安装的小红书 Skills

1. **xiaohongshu-auto** - 自动发布笔记和管理内容
   - 路径: `~/.openclaw/skills/xiaohongshu-auto`
   - 功能: 自动登录、发布笔记、管理内容
   - 认证: 需要手动登录一次（保存 Cookie）

2. **xiaohongshutools** - 数据采集和交互工具包
   - 路径: `~/.openclaw/skills/xiaohongshutools`
   - 功能: 搜索、抓取、分析小红书内容
   - 基于: RedCrack 纯 Python 逆向工程

3. **xiaohongshu-ops** - 端到端运营流程
   - 路径: `~/.openclaw/skills/xiaohongshu-ops`
   - 功能: 账号定位、选题研究、内容生产、发布执行

## 集成方案

### 方案：使用 xiaohongshu-auto + 自动化脚本

**优势**:
- 利用现有已安装的 skill
- 无需安装额外的 MCP Server
- 与 Dasheng 工作流无缝集成
- 自动读取 rewrite 阶段的平台元数据

**架构**:
```
Rewrite 阶段
  ↓ 生成 xhs_video_luxun_hot.md + platform_metadata
Publish 阶段
  ↓ 生成视频文件
Distribute 阶段
  ↓ distribute_xiaohongshu.py 脚本
  ↓ 读取内容 + 元数据 + 视频
  ↓ 调用 xiaohongshu-auto skill
  ↓ 自动发布到小红书
```

## 使用方法

### 1. 准备工作

#### 1.1 配置 xiaohongshu-auto

首次使用需要手动登录小红书：

```bash
# 方式 A: 使用 Chrome 扩展 Relay（推荐）
# 1. 安装 OpenClaw Browser Relay 扩展
# 2. 访问 https://www.xiaohongshu.com 并登录
# 3. 保持登录状态

# 方式 B: 使用 OpenClaw 管理的浏览器
openclaw browser start --profile openclaw
# 在浏览器中访问 https://www.xiaohongshu.com 并登录
```

#### 1.2 验证 xiaohongshu-auto 可用

```bash
# 测试发布功能（可选）
openclaw skill xiaohongshu-auto list
```

### 2. 执行小红书分发

#### 2.1 Dry Run（预览模式）

```bash
cd ${PROJECTS_ROOT}/newma-media-studio

# 预览发布计划，不实际发布
python3 scripts/distribute_xiaohongshu.py 2026-04-05_075240_ai --dry-run
```

输出示例：
```
🚀 开始小红书分发流程
   Run ID: 2026-04-05_075240_ai
   Workspace: ${DASHENG_PROJECT_ROOT}
   Dry Run: True

📖 加载 manifests...

============================================================
              小红书发布计划
============================================================
1. 1.2万亿美元AI并购狂潮
   标题: AI并购狂潮来袭
   话题: #AI并购, #科技投资, #人工智能...
   视频: ✓

2. 全球媒体都误读了中国的4.5%
   标题: 误读中国4.5%
   话题: #中国经济, #十五五规划, #GDP...
   视频: ✓

============================================================

🔍 Dry run 模式，不执行实际发布
```

#### 2.2 正式发布

```bash
# 执行实际发布
python3 scripts/distribute_xiaohongshu.py 2026-04-05_075240_ai
```

发布流程：
1. 加载 rewrite_manifest.json 和 video manifest
2. 提取小红书变体（xhs_video_luxun_hot）
3. 读取平台元数据（标题、话题标签、封面文案）
4. 展示发布计划，等待用户确认
5. 依次发布每个选题
6. 每篇之间随机等待 5-30 分钟（避免被限流）
7. 保存发布结果到 `产物/08_Distribute/{run_id}/xiaohongshu_distribute_result.json`

### 3. 查看发布结果

```bash
# 查看发布结果
cat ${DASHENG_PROJECT_ROOT}/产物/08_Distribute/2026-04-05_075240_ai/xiaohongshu_distribute_result.json
```

结果格式：
```json
{
  "run_id": "2026-04-05_075240_ai",
  "platform": "xiaohongshu",
  "generated_at": "2026-04-06T11:00:00",
  "total": 2,
  "success": 2,
  "failed": 0,
  "results": [
    {
      "topic_id": "ai-ma-boom-q1-2026",
      "topic_title": "1.2万亿美元AI并购狂潮",
      "success": true,
      "timestamp": "2026-04-06T11:00:00",
      "stdout": "发布成功..."
    },
    {
      "topic_id": "china-15th-five-year-plan-2026",
      "topic_title": "全球媒体都误读了中国的4.5%",
      "success": true,
      "timestamp": "2026-04-06T11:15:00",
      "stdout": "发布成功..."
    }
  ]
}
```

## 技术细节

### 脚本功能

`distribute_xiaohongshu.py` 脚本提供以下功能：

1. **自动读取内容**
   - 从 `rewrite_manifest.json` 读取小红书变体路径
   - 从 `publish_video_supplement_manifest.json` 读取视频路径
   - 自动匹配选题和视频

2. **元数据提取**
   - 标题（≤20字）
   - 话题标签（5-8个，#格式）
   - 封面文案（前300字）

3. **智能发布**
   - 支持视频 + 文字发布
   - 支持纯文字发布（如果视频未就绪）
   - 自动间隔发布（5-30分钟随机）

4. **错误处理**
   - 发布超时检测（5分钟）
   - 失败重试机制（可选）
   - 详细错误日志

### 调用 xiaohongshu-auto 的方式

脚本通过以下命令调用 xiaohongshu-auto skill：

```bash
openclaw skill xiaohongshu-auto publish \
  --title "标题" \
  --content "正文内容" \
  --cover-text "封面文案" \
  --hashtag "#话题1" \
  --hashtag "#话题2" \
  --video "/path/to/video.mp4"
```

**注意**: 实际命令格式需要根据 xiaohongshu-auto 的 API 文档调整。

## 限制和注意事项

### 小红书平台限制

1. **发布频率**
   - 每日上限: 5篇
   - 建议间隔: 5-30分钟
   - 避免被限流或封号

2. **内容规范**
   - 标题: ≤20字
   - 话题标签: 5-8个
   - 视频规格: 竖版 9:16，1080x1440px，≤15分钟

3. **认证要求**
   - 需要手动登录一次
   - Cookie 有效期约 30 天
   - 过期后需要重新登录

### 脚本限制

1. **依赖 xiaohongshu-auto skill**
   - 必须先安装和配置 xiaohongshu-auto
   - 需要有效的登录 session

2. **单线程发布**
   - 不支持并行发布多个账号
   - 每次只能发布一个 run_id

3. **视频依赖**
   - 如果视频未生成，会跳过视频发布
   - 需要先完成 publish 阶段

## 故障排查

### 问题 1: xiaohongshu-auto skill 未找到

```bash
# 检查 skill 是否安装
ls ~/.openclaw/skills/ | grep xiaohongshu

# 如果未安装，联系管理员安装
```

### 问题 2: 登录 session 过期

```bash
# 重新登录
openclaw browser start --profile openclaw
# 访问 https://www.xiaohongshu.com 并登录
```

### 问题 3: 发布失败

```bash
# 查看详细错误日志
cat ${DASHENG_PROJECT_ROOT}/产物/08_Distribute/{run_id}/xiaohongshu_distribute_result.json

# 检查 xiaohongshu-auto 日志
tail -f ~/.openclaw/logs/xiaohongshu-auto.log
```

### 问题 4: 视频未找到

```bash
# 检查 publish 阶段是否完成
ls ${DASHENG_PROJECT_ROOT}/产物/07_Publish/{run_id}/videos/motion_narrative/

# 如果视频未生成，先运行 publish 阶段
```

## 后续优化

### 短期优化（1-2周）

1. **批量发布支持**
   - 支持一次发布多个 run_id
   - 支持定时发布

2. **失败重试**
   - 自动重试失败的发布
   - 可配置重试次数和间隔

3. **发布预览**
   - 在浏览器中预览发布效果
   - 用户确认后再正式发布

### 中期优化（1-2月）

1. **多账号支持**
   - 支持发布到多个小红书账号
   - 账号轮换发布

2. **数据回流**
   - 发布后自动抓取阅读量、点赞数
   - 用于 postmortem 阶段分析

3. **A/B 测试**
   - 同一内容生成多个标题/封面
   - 测试哪个效果更好

### 长期优化（3-6月）

1. **智能推荐**
   - 根据历史数据推荐最佳发布时间
   - 推荐最佳话题标签组合

2. **自动回复**
   - 自动回复评论
   - 智能识别和过滤垃圾评论

3. **完整闭环**
   - 发布 → 监控 → 分析 → 优化
   - 形成完整的运营闭环

## 相关文档

- [Dasheng Stage Distribute](../skills/dasheng-stage-distribute/SKILL.md)
- [Dasheng Stage Rewrite](../skills/dasheng-stage-rewrite/SKILL.md)
- [Platform Metadata Rules](../skills/dasheng-stage-rewrite/references/platform-metadata.md)
- [Video Generation Complete](../VIDEO_GENERATION_COMPLETE.md)

---

**创建时间**: 2026-04-06  
**状态**: ✅ 脚本已创建，待测试  
**下一步**: 使用实际数据测试发布流程
