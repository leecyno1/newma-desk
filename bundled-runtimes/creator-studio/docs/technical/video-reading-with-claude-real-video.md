# 视频读取：claude-real-video 本地链路

Date: 2026-07-10

## 定位

以后读取参考视频、审核成片、训练剪辑 DNA 时，默认先走本地 `claude-real-video`。

它不是剪辑器，而是读片预处理器：

- 场景变化抽帧，不按固定 1fps 盲抽。
- 去重近似帧，减少模型上下文浪费。
- 生成 3x3 contact sheet，方便模型按时间顺序看画面。
- 可选转写和保留完整音频。
- 生成 `MANIFEST.txt`，供 Agent/LLM 读取视频内容、节奏、构图、转场和证据画面。

## 本地仓库

```text
${PROJECTS_ROOT}/claude-real-video
```

上游：

```text
https://github.com/HUANGCHIHHUNGLeo/claude-real-video
```

同步：

```bash
git -C ${PROJECTS_ROOT}/claude-real-video pull --ff-only
```

## Newma 包装命令

默认不全局安装，直接通过本地源码运行：

```bash
python3 scripts/read_video_with_crv.py <video_or_url> \
  --why "提取剪辑节奏、镜头构图、证据画面、转场和风格 DNA" \
  --report
```

默认输出：

```text
~/Desktop/自媒体创作/00_范式学习/视频训练/_video_reading/<timestamp>_<video_slug>/
```

产物：

- `MANIFEST.txt`
- `frames/*.jpg`
- `grids/*.jpg`
- `dasheng_video_reading_manifest.json`
- 可选 `transcript.txt`
- 可选 `audio.m4a`
- 可选 `report.html`

## 使用原则

- 参考视频学习：默认使用 `learn_blogger_video_style_local.py`，内部调用 `read_video_with_crv.py`。
- 成片复盘：先抽关键帧和 manifest，再对照 `scene_plan_quality_gate.json` 判断“为什么业余”。
- 真人口播导演：用 crv 的关键帧/contact sheet 辅助识别真实镜头密度、PIP、转场和构图问题。
- 不把 `crv-out`、视频、音频、关键帧写入项目根目录或 skills 目录。
- 只有需要语音内容时才启用 `--transcribe`；当前 `.venv_media` 未安装 Whisper。
- 本阶段不上传视频到模型服务。
- 定时任务只生成 CRV 证据和 `codex_review_packet.json`；联系表、转录稿和
  `MANIFEST.txt` 由 Codex 直接读取，不经过 MiniMax 等外部分析模型。

## 已验证

2026-07-10 烟测通过：

```text
source: ${HOME}/Desktop/自媒体创作/20260709_金融投资口播_精简导演/render/final_hk_tech_talking_head_refined_v4_noscan_1200.mp4
output: ${HOME}/Desktop/自媒体创作/00_范式学习/视频训练/_video_reading/claude_real_video_smoke
frames: 5 kept from 24 extracted
manifest: dasheng_video_reading_manifest.json
```
