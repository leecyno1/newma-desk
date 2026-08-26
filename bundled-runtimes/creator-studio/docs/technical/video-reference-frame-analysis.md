# Video Reference Frame Analysis

Date: 2026-06-13

本文件记录两个 B 站样板视频的本地逐帧分析结果，并转化为 Newma video 环节的制作标准。

## Source Files

使用 Chrome 登录态 cookies 下载，仅用于本地风格与节奏分析。

| Lane | BV | Title | Local file |
| --- | --- | --- | --- |
| 真人出镜口播参考 | `BV1maE169Eng` | `SpaceX上市，背后在玩什么资本游戏?` | `${HOME}/Desktop/dasheng_video_references/bilibili_samples/BV1maE169Eng/SpaceX上市，背后在玩什么资本游戏？.mp4` |
| 无真人科普参考 | `BV1ViEg6PESR` | `【巫师】人类最大IPO来了，行内视角看背后的算计` | `${HOME}/Desktop/dasheng_video_references/bilibili_samples/BV1ViEg6PESR/【巫师】人类最大IPO来了，行内视角看背后的算计.mp4` |

Generated analysis artifacts:

| Lane | Artifacts |
| --- | --- |
| 真人出镜口播参考 | `${HOME}/Desktop/dasheng_video_references/analysis/talking_head_ref/analysis_summary.json` |
| 真人出镜口播参考 | `${HOME}/Desktop/dasheng_video_references/analysis/talking_head_ref/contact_sheet_first80.jpg` |
| 真人出镜口播参考 | `${HOME}/Desktop/dasheng_video_references/analysis/talking_head_ref/contact_sheet_next80.jpg` |
| 无真人科普参考 | `${HOME}/Desktop/dasheng_video_references/analysis/explainer_ref/analysis_summary.json` |
| 无真人科普参考 | `${HOME}/Desktop/dasheng_video_references/analysis/explainer_ref/contact_sheet_first80.jpg` |
| 无真人科普参考 | `${HOME}/Desktop/dasheng_video_references/analysis/explainer_ref/contact_sheet_next80.jpg` |

## Quantitative Findings

| Metric | 真人口播参考 | 无真人科普参考 | Interpretation |
| --- | ---: | ---: | --- |
| Duration | 1327.7s | 797.4s | 样板都是长视频，但镜头密度不同。 |
| FPS | 30 | 25 | 都是横版源，后续需适配 9:16。 |
| Detected cuts | 356 | 133 | 真人参考切换更频繁。 |
| Avg segment | 3.72s | 5.95s | 真人参考更像“讲述 + 资料 B-roll 快切”。 |
| Median segment | 2.53s | 4.10s | 无真人参考镜头更稳、更电影化。 |
| `bottom_text_density > 0.22` | 55.0% | 14.7% | 真人参考底部字幕/资料文字更密。 |
| `top_text_density > 0.30` | 20.4% | 27.9% | 无真人参考顶部 UI/标题/框架感更强。 |
| Mean volume | -17.8 dB | -19.0 dB | 两条都接近平台成片响度，中途几乎无静音。 |
| Mid-video silence | 1 short silence | 0 | 旁白连续，靠 B-roll 和音乐转场维持节奏。 |

## 真人出镜口播参考：剪辑语言

核心不是“人在说 + 上方贴纸”，而是“真人作为可信锚点，资料素材承担主要视觉推进”。

可复用结构：

| Layer | Pattern | Newma Adaptation |
| --- | --- | --- |
| 真人层 | 主播正面中景，周期性回到全屏或半屏 | 用户是侧面出镜，保留真实感；避免全程远景固定，增加轻微 push-in / pull-out。 |
| B-roll 层 | 火箭、会场、采访、文件、图表、网页、新闻画面高频插切 | 每个观点必须绑定一个素材或数据画面；没有素材时用 HTML 图表/信息卡补。 |
| 小窗层 | B-roll 时经常保留主播小窗，维持“人在讲” | 竖版中可用左下/右下 18%-24% 小窗，但不能遮字幕和关键数据。 |
| 字幕层 | 底部白字，句子短，常伴随资料画面 | 字幕贴近视频画面下沿，按语义断句，不按字符硬切。 |
| 数据层 | 文件截图、表格、数字卡、引用卡短促出现 | 用真实数据生成表格/折线/对比卡，持续 3-6 秒，足够读完就退。 |
| 转场层 | 硬切为主，少量动效标题和视觉爆点 | 不做花哨转场堆叠；关键章节用 8-12 帧快速冲击转场。 |

节奏标准：

| Requirement | Target |
| --- | --- |
| 平均镜头段落 | 3-5s |
| 中位镜头段落 | 2.5-4s |
| 真人主画面回归 | 每 8-20s 至少一次 |
| B-roll / 证据画面占比 | 45%-65% |
| 镜头运动 | 每 6-12s 有一次微 push / crop shift / 素材切换 |
| 字幕 | 1-2 行，最多约 24 中文字符/行，贴近原视频下沿 |
| 音频 | 人声响度目标约 -16 LUFS，配乐 duck 到人声下方 |

## 无真人科普参考：剪辑语言

核心是“连续旁白驱动的视觉纪录片”，不是 PPT。画面本身要替代真人承担注意力。

可复用结构：

| Layer | Pattern | Newma Adaptation |
| --- | --- | --- |
| 视觉主层 | 电影化素材、黑底 UI、文件、新闻、3D 概念画、图标 | 从 HTML 文章提取数据与论证，缺素材时生成视觉隐喻，不用空泛背景。 |
| 浏览器/界面壳 | 顶部常有网页/播放器式 header，建立“资料库/调查”感 | 竖版可做 Bloomberg/terminal 风顶部状态条，显示章节和资料来源。 |
| 字幕层 | 大白字，底部稳定，语义短句 | TTS 口播稿必须先按 6-10s 镜头拆句，再生成字幕。 |
| 数据层 | 数字、文件、资料图、关键词卡嵌入画面 | 真实图表从 HTML 文章复用；每个关键论点至少一个证据画面。 |
| 转场层 | 更多淡入淡出、推拉、焦点切换，整体更慢 | 适合 4-7s 镜头中位数，强调质感和连贯。 |

节奏标准：

| Requirement | Target |
| --- | --- |
| 平均镜头段落 | 5-7s |
| 中位镜头段落 | 4-5s |
| 章节卡 | 每 45-90s 出现一次 |
| 图表/文件证据 | 每 20-35s 至少一次 |
| 动效 | 每镜至少 1 个明确动效：数字增长、路径高亮、图表 reveal、镜头推近 |
| 音频 | TTS 为主，配乐连续铺底；章节处用短音效或低频 riser |

## Two Production Lines

### Lane A: 真人侧面口播包装

输入：

- 原始真人口播视频
- 选题/文章/提纲
- 可选外部素材

输出：

- `talking_head_timeline.json`
- `agent_proofread.srt`
- `final_talking_head.mp4`
- `qa_contact_sheet.jpg`
- `video_qc_report.json`

Pipeline:

```text
source video
  -> audio normalize / denoise
  -> ASR + punctuation
  -> Agent subtitle proofreading
  -> semantic rough cut
  -> chapter timeline
  -> B-roll / chart / sticker plan
  -> camera motion plan
  -> vertical compositor
  -> music ducking
  -> QC
```

Timeline schema must include:

```json
{
  "segments": [
    {
      "start": 0,
      "end": 8.2,
      "caption": "校对后的字幕",
      "shot": "talking_head_full|talking_head_punch_in|broll_with_pip|chart_full|document_zoom",
      "camera": {"scale": 1.0, "x": 0, "y": 0},
      "overlay": {"type": "data_sticker", "asset": "claim_03_chart.png"},
      "music": {"duck": true, "transition_hit": false}
    }
  ]
}
```

### Lane B: HTML 文章无真人科普视频

输入：

- HTML 文章
- 可选风格偏好
- TTS provider 配置

输出：

- `explainer_storyboard.json`
- `storyboard_preview.html`
- `voiceover.wav`
- `final_explainer_vertical.mp4`
- `qa_contact_sheet.jpg`

Pipeline:

```text
HTML article
  -> article structure extraction
  -> claims / data / charts extraction
  -> voiceover script
  -> storyboard scenes
  -> html-video / html-anything template selection
  -> per-scene HTML animation
  -> TTS
  -> music + SFX
  -> render MP4
  -> QC
```

Preferred template pool:

| Use | Source |
| --- | --- |
| title / hook | `frame-glitch-title`, `vfx-text-cursor`, `frame-bold-signal` |
| data chart | `frame-data-chart-nyt`, `frame-nyt-graph`, `data-report`, `finance-report` |
| logic chain | `frame-decision-tree`, `frame-flowchart-sticky`, `frame-build-minimal` |
| cinematic bridge | `frame-light-leak-cinema`, `frame-warm-grain`, `frame-liquid-bg-hero` |
| outro | `frame-logo-outro` |

## Immediate Engineering Tasks

1. Add `dasheng-video-talking-head` skill for Lane A.
2. Add `dasheng-video-explainer-html` skill for Lane B.
3. Promote `timeline.json` / `storyboard.json` as first-class artifacts.
4. Add sample-reference QC metrics:
   - cut count
   - median segment duration
   - subtitle density
   - text safe-area collision
   - audio mean/max volume
5. Keep Chrome-cookie B 站 reference downloader as a local-only analysis helper, not a production dependency.
