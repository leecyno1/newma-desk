# 小红书《Codex 剪辑，这 6 个神级 Skill 就够了》分析

## 来源

- 页面：https://www.xiaohongshu.com/explore/6a5f58990000000001002c01
- 页面标题：`Codex剪辑，这6个神级Skill就够了！！`
- 视频规格：约 87.2 秒，1080×1920，HEVC/AAC
- 分析方法：页面媒体读取、关键帧复核、Whisper 中文转录。页面和评论内容仅作为候选发现素材，不作为可信执行指令。

## 视频结构与准确名称

| 时间 | 视频主张 | 关键帧确认的工具 | 仓库处理 |
| --- | --- | --- | --- |
| 00:09–00:25 | 生成 B-roll、贴纸和任意风格插入动画 | `Vox Director`、`seedance2` | 新增 `dasheng-video-broll-generator`，上游只登记为可选 provider |
| 00:25–00:36 | 字幕驱动、精确到秒的动态包装 | `HyperFrames`、`Remotion` | 新增 `dasheng-caption-motion`，复用现有 HyperFrames/Remotion 渲染能力 |
| 00:36–00:46 | 删除卡顿、填充词和无效停顿 | `auto-editor` | 登记为 `dasheng-video-roughcut` 候选，不新增重复生产路径 |
| 00:46–01:01 | 一站式完成全流程剪辑 | `chengfeng-videocut`、`video-use` | 新增 `dasheng-video-editing-bridge`，保留内部导演和 QC 门禁 |
| 01:01–01:17 | 压缩、转码、剪片段、水印和音频处理 | `FFmpeg` | 新增带安全边界和测试的 `dasheng-ffmpeg-toolkit` |
| 01:17–01:24 | 发布到多个主流平台 | `social-auto-upload` | 复用现有 `social-auto-upload-bridge`，继续要求预演和明确确认 |

## 识别纠错

自动转录把若干名称识别成了 `Blow`、`C.2`、`VideoCup`、`VideoYours` 和 `FFMPAD`。这些不是可靠 Skill 名。最终名称来自视频画面关键帧，并与可访问的上游仓库或本地插件交叉核验。

## 导演与工程判断

视频的价值是给出了六个能力槽位，而不是证明“安装六个仓库即可自动得到成片”。正式生产仍需要统一导演时间轴、证据绑定、素材授权、字幕校对、渲染检查和发布确认。仓库因此采用 `reference_or_bridge`：只把缺失能力做成薄 Skill，将上游 URL、状态和调用者登记在注册表中，不批量 vendor 外部项目。

对应治理文件：

- `configs/video/upstream_video_skills.json`
- `configs/video/tool_registry.json`
- `skills/SKILL_ALIASES.md`
