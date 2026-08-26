# 公众号文章与视频生成 Skill 依赖地图

更新时间：2026-07-04

## 1. 小红书 Video Skill 清单与补充判断

来源：小红书笔记《自媒体人最该安装的10个Video Skill》及 GitHub 核验。

| 编号 | 截图 Skill / 项目 | 已确认仓库 | GitHub 状态 | 与当前 Newma 链路关系 | 建议 |
| --- | --- | --- | --- | --- | --- |
| 01 | `video-use` | `browser-use/video-use` | MIT；约 14.4k stars；2026-07-01 仍更新；有 `SKILL.md` | 对话式粗剪、素材到 final.mp4。覆盖“自动粗剪/转码/字幕/调色”的大工作流。 | 作为粗剪备选 Path C 研究，不直接替代 FunASR 主链和剪映实验链。优先参考 EDL/文件夹输入/最终文件组织方式。 |
| 01b | `freecut` | `Moh4696/freecut` | MIT；`video-use` fork；本地 Whisper/VibeVoice-ASR 替代付费 ElevenLabs | 更贴近本地低成本 ASR 实验。 | 如要试 `video-use`，优先试 `freecut`，避免新增付费转写依赖。 |
| 02 | `talking-head-editor` | `chrislema/videoeditor` | 约 14 stars；无顶层 `SKILL.md`；license 未标明 | 8 步口播自动精剪：删停顿、动态缩放、调色、音频、字幕。 | 只作为流程参考，不纳入正式依赖。可对照完善 `video-rough-cut` 和 `dasheng-video-talking-head` 的检查项。 |
| 03 | `video-editing-pipeline` | 未稳定定位，仅截图确认 `pipeline + ffmpeg` 集合 | 未找到可信 owner/repo | 素材盘点、镜头整理、生成粗剪 EDL、FFmpeg 切片 + Remotion 合成。 | 暂不采纳。当前内部已有 `dasheng-video-roughcut`、`video-rough-cut`、FFmpeg 合成。后续若定位到仓库，再补入参考库。 |
| 04 | `ffmpeg-usage` | 未稳定定位，仅截图确认 `pipeline + ffmpeg` 集合 | 未找到可信 owner/repo | 转码、压缩、合并、裁剪、抽音频、改尺寸、换码率、烧字幕。 | 不单独引入。内部把 FFmpeg 作为底层工具，最佳实践写入各视频 skill 即可。 |
| 05 | `caption-clip` | `kwindla/skill-caption-clip` | 有 `SKILL.md`；Deepgram + FFmpeg；2026-01 后较少更新 | 短视频字幕、SRT 清洗、样式字幕烧录。 | 可作为字幕 lane 参考。默认仍用 FunASR / 剪映 / Agent 校对；Deepgram 只做可选外部 ASR。 |
| 06 | `claude-shorts` | `AgriciDaniel/claude-shorts` | MIT；约 140 stars；有 `SKILL.md`、8 个脚本；2026-06 更新 | 长视频切短视频、爆点评分、竖屏字幕、Remotion 渲染。 | 值得补一个未来子 skill：`dasheng-video-short-clips`。定位在 Publish 后二创切片，不进入主视频生成链路。 |
| 07 | `video-wrapper` | `op7418/Video-Wrapper-Skills` | 约 319 stars；有 `SKILL.md`；含 9 个视觉模板 | 访谈/播客包装：关键词高亮、名牌、小语卡、金句、关注条等。 | 推荐吸收模板思想，补强 `dasheng-video-talking-head` 的视觉包装库；不建议直接全量安装到主链。 |
| 08 | `remotion-video` | `wshuyi/remotion-video-skill` | 约 305 stars；有超长 `SKILL.md`；含 MiniMax/Edge TTS 脚本 | Remotion 程序化视频、动画、字幕、转场、旁白。 | 作为 Remotion 实践参考。当前已有 OpenAI Remotion skill、html-video、GSAP/Lottie，不再重复引入主依赖。 |
| 08b | `text-to-lottie` | `diffusionstudio/lottie` | MIT；含 `skills/text-to-lottie/SKILL.md`；提供 Skia Skottie 本地播放器 | 用 Agent 生成、编辑、验证 Lottie/Bodymovin JSON 动画。 | 推荐作为可选外部依赖接入 `dasheng-html-video-bridge`，用于透明贴纸、lower-third、警报、数据流、文档扫描、章节符号；不得替代真实图表/证据。 |
| 09 | `product-launch-video` | `memex-lab/product-launch-video-skill` | MIT；低 stars；多 skill 目录 | 15-30 秒产品发布视频、卖点、场景、CTA、MP4/GIF/social copy。 | 仅作为产品发布片模板参考。当前财经/公众号主线不需要作为必装依赖。 |
| 10 | `claude-code-video-toolkit` | `digitalsamba/claude-code-video-toolkit` | MIT；约 1.6k stars；含 `openclaw-video-toolkit`、5 类模板、示例 | 从想法到脚本、旁白、音乐、视觉、MP4 的完整视频工作台。 | 作为重点参考仓库。适合借鉴模板包、迁移脚本、工作台结构；不建议整包并入，避免与 `dasheng-stage-transwrite`、`html-video` 重叠。 |

采纳优先级：

| 优先级 | 项目 | 采纳方式 |
| --- | --- | --- |
| S | `op7418/Video-Wrapper-Skills` | 借鉴/迁移视觉包装模板，补 `dasheng-video-talking-head` 的真人口播包装能力。 |
| S | `AgriciDaniel/claude-shorts` | 新增未来短视频切片子能力，服务 Publish 后二次分发。 |
| A | `browser-use/video-use` / `Moh4696/freecut` | 作为粗剪 Path C 实验，不替代 FunASR 和剪映。 |
| A | `digitalsamba/claude-code-video-toolkit` | 作为视频工作台和模板结构参考。 |
| B | `kwindla/skill-caption-clip` | 参考字幕样式和 SRT 清洗；Deepgram 仅作为可选。 |
| B | `wshuyi/remotion-video-skill` | 参考 Remotion 和 TTS 组织方式，不重复安装。 |
| B | `diffusionstudio/lottie` | 可选外部依赖，用于生成并验证 Lottie JSON 动效素材，输出放到桌面创作任务目录。 |
| C | `chrislema/videoeditor`、`product-launch-video` | 流程/模板参考，暂不进入正式依赖。 |
| 暂缓 | `video-editing-pipeline`、`ffmpeg-usage` | 未定位到稳定仓库；内部已有能力覆盖。 |

## 2. 当前公众号文章生成依赖

### 主链 Skill

| 环节 | 主 Skill / 脚本 | 职责 |
| --- | --- | --- |
| 总控 | `dasheng-media-sop` | 唯一主链入口，约束 intake -> brief -> draft -> transwrite -> publish -> postmortem。 |
| 内容采集 | `dasheng-daily-intake`、`dasheng-hotspot-radar` | 热点、来源、实体、事件聚合。 |
| 选题 Brief | `dasheng-daily-phase2`、`dasheng-stage-brief-ai` | 生成候选 TopicCard、研究 Brief、编辑确认。 |
| 初稿 | `dasheng-stage-draft`、`dasheng-daily-draft` | 生成正文、Reasoning Sheet、自包含 Draft HTML。 |
| 金融数据 | `dasheng-finance-data` | A 股、指数、估值、时间序列数据转 Chart.js / 图表规格。 |
| 风格 | `dasheng-style-profiler`、`wechat-style-profiler` | 作者风格 DNA、公众号表达校准。 |
| 转写 | `dasheng-stage-transwrite` | 把已确认 Draft 转成公众号文章、视频、播客生产包。 |
| 公众号排版 | `baoyu-markdown-to-html`、`md2wechat`、`scripts/wechat_layout_variants.py` | Markdown/HTML 转微信可发布版，控制 H2、表格、正文样式。 |
| 封面/插图 | `baoyu-cover-image`、`baoyu-imagine`、`baoyu-infographic`、`baoyu-article-illustrator` | 封面、信息图、文章插图。 |
| 发布 | `dasheng-stage-publish`、`baoyu-post-to-wechat`、`wechat-draft-writer` | 生成发布包、推草稿、回填草稿 ID/链接。 |

### 外部依赖

| 类型 | 依赖 | 当前定位 |
| --- | --- | --- |
| Python 数据/写作 | `anthropic`、`requests`、`beautifulsoup4`、`PyYAML`、`pandas`、`numpy`、`matplotlib`、`seaborn` | `requirements.txt` |
| 金融数据 | `akshare`、`tushare` | `requirements.txt`，用于 Draft 数据补强。 |
| HTML 模板参考 | `nexu-io/html-anything` | 当前 config 默认路径：`${HTML_ANYTHING_ROOT:-${HOME}/Documents/html一切}`；本机需确认实际目录。 |
| 微信发布 | 微信公众号 AppID/AppSecret、`md2wechat` CLI 或 `baoyu-post-to-wechat` | Publish 阶段使用，必须区分草稿和正式发布。 |
| 协作 | 飞书 API 配置 | 用于阶段审核与团队协作展示，不是文章生产事实源。 |

## 3. 当前视频生成依赖

### 主链 Skill

| 场景 | 主 Skill / 脚本 | 职责 |
| --- | --- | --- |
| 视频转写总入口 | `dasheng-stage-transwrite` | 生成无头、VOX、真人出镜、AI 数字人、广告宣传片、电影短剧规划和可选 `podcast` lane manifest。 |
| 真人口播粗剪 | `dasheng-video-roughcut` | FunASR + FFmpeg 粗剪、候选删除、审核页、字幕校对输入。 |
| 剪映粗剪 | 全局 `video-rough-cut` | Computer Use 操作剪映：导入 -> 粗剪 -> 剪口播 -> 导出桌面 -> 进入导演剪辑。 |
| 真人导演剪辑 | `dasheng-video-talking-head` | 按转录和剧本对齐，生成导演时间线、PIP、证据镜头、HTML 贴片、抽帧 QC。 |
| 无头口播 | `dasheng-video-explainer-html` | 文章转 storyboard，HTML Anything 模板路由，html-video/Remotion/GSAP 动画，MiniMax 配音配乐。 |
| VOX 调查解释 | `dasheng-video-vox`、`dasheng-vox-skills` | 中心问题、证据地图、真实资料、反证、Shotcraft/Remotion 与生成镜头路由。 |
| AI 数字人 | `dasheng-digital-human-talking-head` | 授权肖像、逐人无声人物源、单人/双人对话合成、身份口型和 AI 披露 QC。 |
| 电影短剧规划 | `cinematic_planning_router` | 只生成剧本、角色/场景/连续性圣经与分镜规划；外部模型 API 默认禁用。 |
| 广告宣传片 | `dasheng-commercial-promo-video` | 品牌 Brief、广告脚本、产品展示、Proof、品牌记忆、CTA、多比例安全区和声明合规。 |
| 模板桥 | `dasheng-html-video-bridge`、`dasheng-html-anything-bridge` | 调用外部 `html-video` 渲染器和 `html-anything` 模板参考。 |
| 风格训练 | `dasheng-video-style-trainer` | 从样板视频学习节奏、镜头、转场、色彩、模板偏好。 |
| 发布桥 | `social-auto-upload-bridge`、`bilibili-upload-bridge`、`dasheng-xhs-publish-bridge` | 把视频包交给各平台发布工具或人工包。 |

### 外部依赖

| 类型 | 依赖 | 当前定位 |
| --- | --- | --- |
| 视频渲染 | `nexu-io/html-video` | 本机实际存在：`${PROJECTS_ROOT}/html-video`；`package.json` 显示 Node >=20、pnpm >=9、Remotion 4、GSAP、Lottie、React 18。 |
| 模板参考 | `nexu-io/html-anything` | 用于模板视觉、文章卡片、视频 frame 参考；当前实际路径需再确认。 |
| 动画/合成 | Remotion、GSAP、Lottie、HyperFrames 思路 | `html-video` 内置依赖 Remotion/GSAP/Lottie；HyperFrames 作为场景组织方法。 |
| Lottie 生成/验证 | `diffusionstudio/lottie` / `text-to-lottie` | 可选外部依赖；默认路径 `${TEXT_TO_LOTTIE_ROOT:-${PROJECTS_ROOT}/text-to-lottie}`；用于生成 Skia Skottie 可验收的 Lottie JSON。 |
| 媒体底层 | FFmpeg | 裁剪、转码、音频增强、字幕烧录、最终合成。 |
| ASR | FunASR、modelscope、torch、torchaudio | `requirements-media.txt`；中文粗剪主路径。 |
| 字幕/对齐备选 | WhisperX、stable-ts、ASR 回填脚本 | 转写 lane 中作为字幕时间轴兜底。 |
| 配音/配乐/生图 | MiniMax CLI `mmx` | 默认女声 `tianxin_xiaoling`，语速 `1.2x`，BGM “light technology explainer / data reveal”。 |
| 剪映 GUI | 剪映专业版 `/Applications/VideoFusion-macOS.app` + Computer Use | 用于剪映智能粗剪、剪口播、云草稿实验。 |
| 发布 | `social-auto-upload` | config 指向 `https://github.com/dreammis/social-auto-upload.git`，默认根 `${SOCIAL_AUTO_UPLOAD_ROOT:-${DASHENG_PROJECT_ROOT}/vendor/publish/social-auto-upload}`。它是第 7 环节的项目内上游依赖，但通过 `.gitignore` 与主仓库隔离并独立更新。 |

发布依赖源码和虚拟环境放在 `vendor/publish/`；登录态放在 `~/Library/Application Support/NewmaPublishSessions/` 或 `NewmaPublishProfiles/`；第 7 环节生成的发布包、回执、截图和失败记录放在 `~/Desktop/自媒体创作/<run_id>/05_发布/`。三者不得混放。

### 需要修正或确认

| 项 | 问题 | 建议 |
| --- | --- | --- |
| `dasheng-html-video-bridge/config.json` | 默认路径写的是 `${HTML_VIDEO_ROOT:-${EXTERNAL_VOLUME}/html-video}`，但本机实际存在 `${PROJECTS_ROOT}/html-video`。 | 后续修 config 或在环境变量中显式设置 `HTML_VIDEO_ROOT=${PROJECTS_ROOT}/html-video`。 |
| `dasheng-html-anything-bridge/config.json` | 默认路径是 `${HOME}/Documents/html一切`，本轮未在该路径读到 package 信息。 | 重新定位实际 `html-anything` 仓库路径后再修 config。 |
| `video-editing-pipeline` / `ffmpeg-usage` | 小红书截图有概念，但 GitHub 未稳定定位。 | 暂不引入，内部 FFmpeg SOP 覆盖即可。 |

## 4. 历史参考 Skill 与依赖

| 类别 | 项目 / Skill | 当前角色 |
| --- | --- | --- |
| 公众号写作 | `wechat-style-profiler`、`wechat-topic-outline-planner`、`wechat-draft-writer`、`wechat-title-generator` | 历史公众号专用 rewrite 能力，适合嵌入 `wechat_article` lane。 |
| 公众号排版发布 | `md2wechat`、`baoyu-post-to-wechat`、`wechat-publisher` | 参考/备选发布链；当前发布必须 API-first 或明确草稿回填，不能手动粘贴冒充自动化。 |
| 小红书/抖音发布 | `dasheng-xhs-publish-bridge`、`social-auto-upload-bridge`、`douyin-upload-skill`、XHS MCP/CLI | Publish 阶段备选执行器。需要持久化 Profile 或 API-first，不使用临时 Chrome 登录态。 |
| 视频模板 | `html-video`、`html-anything`、OpenAI Remotion skill、HyperFrames / GSAP / Lottie | 当前视频主链模板与动画基础设施。 |
| Lottie 动效 | `diffusionstudio/lottie` | 新增可选参考/执行器，适合透明贴纸、lower-third、图标、数据流、文档扫描，不替代数据图表。 |
| 剪映 | `video-rough-cut`、`pyJianYingDraft`、`capcut-cli`、剪映专业版 | 剪映智能粗剪与草稿接力；程序化草稿读写仍属实验。 |
| 视频包装参考 | `Video-Wrapper-Skills`、`claude-code-video-toolkit`、`claude-shorts`、`video-use/freecut` | 推荐纳入“上游参考清单”，按需抽取模板/流程，不全量并入。 |

## 5. 后续补包建议

1. 新增 `configs/video/upstream_video_skills.json`，记录上述 GitHub 上游仓库、用途、采纳状态、最后核验时间、是否进入正式依赖。
2. 给 `dasheng-video-talking-head` 增加“包装模板库”章节，优先借鉴 `Video-Wrapper-Skills` 的 lower-third、term-card、quote-callout、social-bar。
3. 新建候选 skill：`dasheng-video-short-clips`，只处理长视频切片、爆点评分、竖屏字幕，参考 `claude-shorts`。
4. 把 `video-use/freecut` 定义为粗剪 Path C：仅实验“素材文件夹 -> 对话式粗剪 -> final.mp4”，不替代 FunASR 主链和剪映路径。
5. 暂不全量安装 `claude-code-video-toolkit`，只参考其模板工作台结构，避免和 `dasheng-stage-transwrite` 重复。
