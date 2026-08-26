# Newma Media Studio - Skill 别名与版本映射

本文档定义技能的正式名称、别名与版本关系。

## 正式 Skill 列表

| Skill 名称 | 版本 | 状态 | 说明 |
|------------|------|------|------|
| `dasheng-media-sop` | 1.0.0 | ✅ 正式 | 总控入口，唯一正式编排 skill |
| `dasheng-paradigm-profiler` | 1.0.0 | ✅ 正式 | 可选前置资产，提炼文章结构范式 |
| `dasheng-daily-intake` | 1.0.0 | ✅ 正式 | 内容采集阶段 |
| `dasheng-daily-phase2` | 1.0.0 | ✅ 正式 | 选题分析阶段（替代 dasheng-daily-brief） |
| `dasheng-daily-draft` | 1.0.0 | ✅ 正式 | 写作与可发布底稿阶段 |
| `dasheng-stage-transwrite` | 1.0.0 | ✅ 正式 | 转写生产阶段，生成公众号/普通无头/VOX/真人/播客包 |
| `dasheng-stage-publish` | 1.0.0 | ✅ 正式 | 发布执行阶段 |
| `dasheng-daily-postmortem` | 1.0.0 | ✅ 正式 | 复盘与知识回写 |
| `dasheng-finance-data` | 0.1.0 | ✅ 正式 | Draft 金融数据增强工具，生成 Chart.js 图表规格 |
| `dasheng-style-profiler` | 1.0.0 | ✅ 正式 | 文风 Style DNA 提炼 |
| `feishu-doc-creator` | 1.0.0 | ✅ 正式 | 飞书文档创建辅助 |
| `dasheng-html-video-bridge` | 0.1.0 | ✅ 正式 | 转写阶段调用本地 html-video 的口播视频桥接 skill |
| `dasheng-html-anything-bridge` | 0.1.0 | ✅ 正式 | Draft/Transwrite 调用 HTML Anything 模板和视觉语言的桥接 skill |
| `dasheng-lemon-illustrations` | 0.1.0 | ✅ 正式 | 口播视频默认概念卡通插画系统，使用柠檬人替代上游角色 |
| `dasheng-video-talking-head` | 0.2.0 | ✅ 正式 | 真人与数字人有头口播的导演时间轴、证据层和包装工作流 |
| `dasheng-digital-human-talking-head` | 0.1.0 | ✅ 正式 | 一张授权照片加 MiniMax 音频，在本地生成数字人口播并接入真人导演链 |
| `dasheng-video-explainer-html` | 0.1.0 | ✅ 正式 | HTML 文章转无真人财经视频，默认横版 16:9，支持方形和竖版适配 |
| `dasheng-vox-skills` | 1.0.0 | ✅ 正式 | VOX 制作统一入口，编排导演分镜、Codex 参考图、Gemini API/浏览器、Remotion 二剪与质检 |
| `dasheng-video-vox` | 1.3.0 | 🧰 内部 | `dasheng-vox-skills` 的调查结构、导演分镜与视觉语法组件 |
| `dasheng-video-omni-browser` | 0.1.0 | 🧰 按需 | 通过 Chrome 已登录的 Gemini Omni 将参考图生成约 10 秒逐镜视频 |
| `dasheng-video-broll-generator` | 0.1.0 | 🧰 按需 | B-roll、Vox 拼贴、生成式插入片段和贴纸动画的证据安全路由 |
| `dasheng-caption-motion` | 0.1.0 | 🧰 按需 | 将 SRT/词级时间戳路由为 HyperFrames 或 Remotion 字幕动效 |
| `dasheng-video-editing-bridge` | 0.1.0 | 🧰 按需 | 内部管线、剪映、chengfeng-videocut 与 video-use 的全流程剪辑路由 |
| `dasheng-ffmpeg-toolkit` | 0.1.0 | 🧰 按需 | 受控媒体探测、转码、裁剪、音频提取和图片水印工具 |
| `social-auto-upload-bridge` | 0.2.0 | ✅ 正式 | Publish 阶段调用外部 social-auto-upload，支持四平台预演、登录检查、确认执行与结果回填 |
| `bilibili-upload-bridge` | 0.1.0 | ✅ 正式 | Publish 阶段调用外部 B站上传工具的投稿桥 |

## 按需工具（不属于正式主链）

| Skill 名称 | 状态 | 说明 |
|------------|------|------|
| `dasheng-stage-rewrite-v3` | 🧰 按需 | 多版本改写工具，能力并入 Draft/Publish 后按需调用 |
| `dasheng-video-roughcut` | 🧰 按需 | 基于 FunASR + FFmpeg 的真人口播粗剪、字幕和审核页；现在作为 `dasheng-video-talking-head` 的前置子能力 |

## 已废弃 Skill（请勿使用）

| Skill 名称 | 替代方案 | 废弃原因 |
|------------|----------|----------|
| `dasheng-stage-brief-ai` | `dasheng-daily-phase2` | 能力已被吸收合并 |
| `dasheng-daily-brief` | `dasheng-daily-phase2` | 与 phase2 重复 |
| `dasheng-daily-clustering` | `dasheng-daily-intake` | 与 intake 重复 |
| `dasheng-daily-outline` | `dasheng-daily-draft` | 与 draft 重复 |
| `dasheng-daily-final` | `dasheng-daily-draft` | 与 draft 重复 |
| `dasheng-stage-draft` | `dasheng-daily-draft` | 旧版本，已合并 |
| `dasheng-stage-rewrite` | `dasheng-stage-rewrite-v3` | 已退为按需工具 |
| `dasheng-stage-intake-brief-draft` | `dasheng-daily-intake` + `dasheng-daily-phase2` | 多阶段合并 |
| `dasheng-stage-publish-video` | `dasheng-stage-transwrite` | 已并入口播视频转写生产 |
| `dasheng-stage-distribute` | `dasheng-stage-publish` | 已并入 publish 阶段 |
| `dasheng-collection-workflow` | `dasheng-daily-intake` | 能力已并入 intake |
| `dasheng-sop-orchestrator` | `dasheng-media-sop` | 旧版本总控 |

## 别名映射

以下别名用于兼容旧调用：

```json
{
  "aliases": {
    "dasheng-stage-brief-ai": "dasheng-daily-phase2",
    "dasheng-daily-brief": "dasheng-daily-phase2",
    "dasheng-daily-clustering": "dasheng-daily-intake",
    "dasheng-daily-outline": "dasheng-daily-draft",
    "dasheng-daily-final": "dasheng-daily-draft",
    "dasheng-stage-draft": "dasheng-daily-draft",
    "dasheng-stage-rewrite": "dasheng-stage-rewrite-v3",
    "dasheng-stage-intake-brief-draft": "dasheng-daily-intake",
    "dasheng-stage-publish-video": "dasheng-stage-transwrite",
    "dasheng-stage-distribute": "dasheng-stage-publish",
    "dasheng-collection-workflow": "dasheng-daily-intake",
    "dasheng-sop-orchestrator": "dasheng-media-sop"
  }
}
```

## 路径约定

所有正式 skill 位于 `skills/` 目录，使用 `dasheng-daily-*` 或 `dasheng-stage-*` 命名：
- `dasheng-daily-*`：日常生产流程 skill
- `dasheng-stage-*`：单阶段执行 skill
- `dasheng-media-*`：核心引擎 skill

## 安装说明

当通过 `scripts/install.sh` 安装时，系统会自动：
1. 验证所有正式 skill 的完整性
2. 创建必要的符号链接（如果有别名配置）
3. 更新 OpenClaw 的 skill 注册表
