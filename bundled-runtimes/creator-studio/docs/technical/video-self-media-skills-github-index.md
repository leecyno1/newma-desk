# Newma 视频与自媒体生成 Skills / GitHub 项目总索引

更新时间：2026-08-22  
适用项目：Newma Media Studio、Newma Desk（历史仓库名包含 newma-dock）  
用途：把历史会话中提到的、已检索的、已注册的以及暂存备用的视频和自媒体创作能力集中列出，供 Newma、Qoder 和后续导演/渲染节点查阅。

## 0. 阅读说明

### 检索口径

本索引综合了以下材料：

- 本项目的技能依赖图、视频生产线、技术栈候选和外部项目注册表；
- Newma Media Studio、Newma Desk、boutique-skills、video-shotcraft、html-video 的 Git remote；
- 已克隆或登记在 vendor/reserved/ 中的上游项目；
- 历史会话中提到的公众号、视频、剪辑、数字人、发布和视觉设计能力。

GitHub 的 star、更新时间和仓库状态均是核验时的快照，不代表当前实时数据。没有找到稳定仓库或没有完成适配的能力，不应直接作为生产路由。

### 状态标记

| 标记 | 含义 |
| --- | --- |
| 主链 | 已有 Newma 调用方，可进入正式工作流 |
| 已接入 | 已有本地项目、桥接器或运行入口 |
| 参考 | 已核验，可借鉴方法或模板，但不作为默认路由 |
| 储备 | 已保留或已克隆，等待适配、冒烟测试和人工验收 |
| 候选 | 已发现，尚未完成注册或稳定性评估 |
| 暂缓 | 外部 API、许可证、依赖或质量风险尚未满足生产条件 |
| 历史名 | 旧的 dasheng 命名或旧技能名，保留用于兼容检索 |

### Newma 命名约定

历史资料中大量使用 dasheng-*。当前产品标准名称是 Newma，后续新代码、注册表和文档应优先使用 newma-*。旧名暂时保留为兼容别名，避免已有项目和历史产物无法检索。

## 1. Newma 内部 Skills

### 1.1 自媒体主链

| Skill | 主要职责 | 阶段 | 状态 |
| --- | --- | --- | --- |
| dasheng-media-sop | 统一编排 intake → brief → draft → transwrite → publish → postmortem | 总控 | 主链 / 历史名 |
| dasheng-paradigm-profiler | 学习账号和样本文风、结构、节奏与视觉范式 | intake / brief | 主链 / 历史名 |
| dasheng-daily-intake | 热点、来源、实体、事件和素材入库 | intake | 主链 / 历史名 |
| dasheng-hotspot-radar | 热点扫描、候选题目发现和优先级判断 | intake | 主链 / 历史名 |
| dasheng-daily-phase2 | 生成 TopicCard、研究 Brief 和编辑确认项 | brief | 主链 / 历史名 |
| dasheng-stage-brief-ai | 研究方向、论证问题和 Brief 辅助生成 | brief | 已并入 dasheng-daily-phase2 |
| dasheng-stage-draft | 生成正文、推理表、证据表和 Draft HTML | draft | 已并入 dasheng-daily-draft |
| dasheng-daily-draft | 日常长文草稿生产 | draft | 主链 / 历史名 |
| dasheng-finance-data | 金融数据取数、时间序列、估值比较和图表规格 | draft / evidence | 主链 / 历史名 |
| dasheng-style-profiler | 账号 DNA、语言风格和写作规范校准 | draft / transwrite | 主链 / 历史名 |
| wechat-style-profiler | 公众号文章的局部风格分析 | draft | 历史兼容 |
| dasheng-stage-rewrite-v3 | 文章重写、口语化、降低 AI 味和节奏调整 | draft / transwrite | 主链 / 历史名 |
| content-research-writer | research → 引用 → hook → outline 的深度写作循环 | draft | 已注册的外部增强 |
| dasheng-stage-transwrite | 把确认后的 Draft 转成公众号、视频、播客生产包 | transwrite | 主链 / 历史名 |
| dasheng-stage-publish | 生成发布包、草稿、渠道元数据和发布回执 | publish | 主链 / 历史名 |
| dasheng-daily-postmortem | 发布后数据回写、归因和下一轮选题反馈 | postmortem | 主链 / 历史名 |

### 1.2 文章、配图和公众号

| Skill | 主要职责 | 状态 |
| --- | --- | --- |
| baoyu-markdown-to-html | Markdown 转公众号 HTML | 主链 |
| md2wechat | 微信排版和发布前转换 | 主链 / 外部工具 |
| baoyu-cover-image | 封面图设计 | 主链 |
| baoyu-imagine | 文章和视频概念图生成 | 主链 |
| baoyu-infographic | 信息图和结构化视觉 | 主链 |
| baoyu-article-illustrator | 文章插图 | 主链 |
| dasheng-lemon-illustrations | DNA 柠檬博士及账号角色插图系统 | 主链 / 历史名 |
| dasheng-account-illustrations | 账号角色、贴纸、概念视觉和透明素材 | 主链 / 历史名 |
| baoyu-diagram | 产业链、架构、流程和时序说明图 | 已注册增强 |
| drafter-diagram | Flat Engineering Blueprint 风格结构图 | 已注册增强 |
| image-enhancer | 封面和插图的清晰度、分辨率和缩略图质量增强 | 已注册增强 |
| theme-factory | 公众号 HTML 主题备选 | 备案，暂不替换当前品牌样式 |

概念图、结构图和数据图必须分开：角色插图解释概念，baoyu-diagram / drafter-diagram 解释结构，matplotlib / Tushare / AkShare 负责真实数据。不能用装饰性插图冒充数据证据。

### 1.3 视频导演与执行

| Skill | 主要职责 | 对应流水线 |
| --- | --- | --- |
| dasheng-video-director | 统一导演入口、分镜状态机、Claim/Evidence Ledger 和镜头规划 | 全部 |
| dasheng-video-talking-head | 真人口播导演时间线、PIP、证据镜头、花字、贴纸和抽帧 QC | 真人出镜 |
| dasheng-video-roughcut | FunASR + FFmpeg 粗剪、删口水词、停顿、重说和候选删除 | 真人出镜 |
| dasheng-video-explainer-html | 文章到 HTML 分镜、TTS、动画和无真人视频 | 无头口播 |
| dasheng-video-vox | 中心问题、证据地图、真实资料、反证和有限结论 | VOX |
| dasheng-vox-skills | VOX 适配器、Shotcraft 镜头配方、Gemini Omni 与 Remotion 合成 | VOX |
| dasheng-video-omni-browser | 通过已登录 Gemini Omni 逐镜生成约 10 秒底片并下载回项目 | VOX / 数字人备用 |
| dasheng-video-broll-generator | 解释性 B-roll 和抽象镜头生成 | VOX / 无头 |
| dasheng-caption-motion | 字幕样式、逐字高亮、重点花字、字幕时间轴 | 全部 |
| dasheng-video-editing-bridge | 调用剪映、FFmpeg 或其他剪辑执行器 | 真人 / 全部 |
| dasheng-ffmpeg-toolkit | 转码、裁剪、拼接、音频增强、字幕烧录和封装检查 | 全部 |
| dasheng-digital-human-talking-head | 授权肖像、单人和双人数字人口播、口型和身份 QC | AI 数字人 |
| dasheng-commercial-promo-video | 品牌 Brief、广告脚本、Proof、CTA、声明和多比例安全区 | 广告宣传片 |
| dasheng-video-style-trainer | 从样板视频学习镜头、节奏、转场、色彩和模板偏好 | 风格训练 |
| dasheng-video-self-learning | 成片复盘和视觉模板回写 | postmortem / transwrite |
| dasheng-html-video-bridge | 调用 html-video 的创建、预览和渲染能力 | 无头 / 真人 / 广告 |
| dasheng-html-anything-bridge | 借用 HTML Anything 的文章、卡片和视频模板语言 | 无头 / 文章 |
| dasheng-omni-video-bridge | Omni 类视频生成与项目素材回接 | VOX / 数字人 |
| dasheng-video-short-clips | 长视频切片、爆点评分、竖屏字幕和二次分发 | 候选，建议放在 publish 后 |

### 1.4 发布与平台桥

| Skill / 工具 | 用途 | 状态 |
| --- | --- | --- |
| dasheng-publish-operations-bridge | 发布包、账号、渠道和回执统一接口 | 主链 / 历史名 |
| dasheng-xhs-publish-bridge | 小红书发布或人工交接 | 主链 / 历史名 |
| social-auto-upload-bridge | 多平台上传桥 | 主链 / 历史名 |
| bilibili-upload-bridge | B 站上传和回执 | 主链 / 历史名 |
| wechat-draft-writer | 微信草稿箱回填 | 历史兼容 |
| wechat-publisher | 微信发布流程参考 | 历史兼容 |
| douyin-upload-skill | 抖音上传备选 | 历史兼容 |

### 1.5 历史兼容入口与旧架构

这些名称在旧安装说明、归档设计或早期任务中出现过。它们保留用于查找旧产物，不应新建调用：

| 旧名 | 当前替代 | 说明 |
| --- | --- | --- |
| dasheng-daily-clustering | dasheng-daily-intake | 旧聚类/入库入口 |
| dasheng-daily-outline | dasheng-daily-draft | 旧大纲入口 |
| dasheng-daily-final | dasheng-daily-draft | 旧最终稿入口 |
| dasheng-stage-brief-ai | dasheng-daily-phase2 | Brief 能力已合并 |
| dasheng-stage-draft | dasheng-daily-draft | Draft 能力已合并 |
| dasheng-stage-rewrite | dasheng-stage-rewrite-v3 | 旧重写入口 |
| dasheng-stage-intake-brief-draft | dasheng-daily-intake + dasheng-daily-phase2 | 多阶段旧入口 |
| dasheng-stage-publish-video | dasheng-stage-transwrite | 视频转写已并入 transwrite |
| dasheng-stage-distribute | dasheng-stage-publish | 分发已并入 publish |
| dasheng-collection-workflow | dasheng-daily-intake | 采集流程旧名 |
| dasheng-sop-orchestrator | dasheng-media-sop | 总控旧名 |
| dasheng-media-rewrite-v2 | dasheng-stage-rewrite-v3 | 旧 EnhancedPromptBuilder / QualityScorer 重写引擎，仍可作为实现参考 |
| dasheng-media-workflow | dasheng-media-sop | 早期模块/安装名 |
| dasheng-media-platform | Newma Media Studio | 早期工作台项目名 |
| dasheng-media-platform-v2 | Newma Creator Studio / Newma Desk | 归档架构重设计名称 |
| dasheng-daily-shared | 主链共享模块 | 旧共享依赖，不单独路由 |

## 2. 外部或全局 Skills

### 2.1 视频、剪辑、字幕和媒体

| Skill | 作用 | 在 Newma 中的角色 |
| --- | --- | --- |
| video-use | 对话式从素材文件夹到 final.mp4 的粗剪 | Path C 实验 |
| freecut | video-use 的本地 Whisper / VibeVoice-ASR 分支 | 测试 video-use 时优先 |
| video-wrapper | 访谈/播客包装、名牌、小语卡、金句、关注条 | 真人口播包装参考 |
| cut-talking-head | 口播停顿、重复和口水词清理 | 真人粗剪 |
| finish-talking-head | 口播后期收尾、声音和画面整理 | 真人后期 |
| claude-shorts | 长视频切短、爆点评分和竖屏字幕 | publish 后二创候选 |
| media-downloader | 新闻、网页、图片和视频素材下载 | intake / asset |
| video-frames | 抽帧、关键帧和画面审查 | intake / QC |
| reusable-footage-material | 可复用素材库和素材元数据 | asset |
| remotion-video-skill | Remotion 程序化视频、TTS、字幕和转场 | 参考，主链已有同类能力 |
| remotion-video-toolkit | Remotion、动态图表、3D 和字幕渲染 | 参考 / 可调用组件 |
| remotion-best-practices | Remotion 工程规范和性能实践 | 参考 |
| gif-sticker-maker | GIF、贴纸和透明动效 | 贴纸素材 |
| animated-financial-display | 金融数据动态显示 | 数据 reveal |
| seedance2-skill | 参考图到视频、生成式 B-roll 和 prompt 设计 | 官方模型备用 |
| auto-editor | 静音、节奏和粗剪计划 | CLI 备用 |
| chengfeng-videocut-skills | 视频编辑、粗剪计划和多执行器路由 | 实验参考 |

### 2.2 动画、HTML 和视觉

| Skill | 作用 | 当前角色 |
| --- | --- | --- |
| hyperframes | HTML 视频、GSAP 动效、动态图表和最终渲染 | 重要方法参考 |
| hyperframes:gsap | GSAP 时间轴、路径、SVG 和性能 | 动画执行 |
| hyperframes-cli | HyperFrames CLI 工作流 | 工具参考 |
| hyperframes-registry | HyperFrames 模板和注册机制 | 模板参考 |
| website-to-hyperframes | 网站转可渲染场景 | 场景采集参考 |
| animation-vocabulary | 动画语言、节奏和动作命名 | 导演/审查 |
| find-animation-opportunities | 从内容识别动画机会 | 分镜前审查 |
| improve-animations | 动效改进 | 视觉 QC |
| review-animations | 动画验收 | 视觉 QC |
| apple-design | Apple 风格界面和动效参考 | 视觉参考 |
| emil-design-eng | 细节、动效和界面工程 | 视觉参考 |
| canvas-design | Canvas 图形和构图 | 设计参考 |
| algorithmic-art | 程序化视觉和抽象动效 | 抽象 B-roll |
| image-to-code | 图片/界面转 HTML 或代码 | HTML 场景参考 |
| minimalist-ui | 简洁界面和信息层级 | 视觉参考 |
| pick-ui-library | UI 组件库选择 | Desk/HTML |
| design-taste-frontend | 反模板感、版式和视觉品味审查 | Newma 视觉总审 |
| frontend-design | 前端界面设计 | Creator Studio |
| frontend-patterns | 前端工程模式 | Creator Studio |
| high-end-visual-design | 高端视觉设计 | 封面/广告 |
| brand-guidelines | 品牌规范 | 广告/账号 DNA |
| brandkit | 品牌资产和组件 | 广告/发布 |
| gpt-image-2-style-library | 图像风格库 | ImageGen 辅助 |
| guizang-social-card-skill | 社交卡片、数据卡、海报和封面 | 文章/发布 |
| ian-xiaohei-illustrations | 小黑手绘概念插图 | 文章/视频概念图 |
| baoyu-* | 封面、插图、信息图、Markdown 和微信 HTML | 文章主链 |

### 2.3 文章、研究和内容生产

| Skill | 作用 | 当前角色 |
| --- | --- | --- |
| lemon | 柠檬博士账号风格和文章结构参考 | DNA 参考 |
| ima-skill | 内容知识和素材组织 | 参考 |
| humanizer-zh | 中文自然化、节奏编辑和降低 AI 味 | 候选，需做 Style DNA 回归 |
| khazix-skills | 长文、行业报告和深度结构 | 候选，需做证据回归 |
| finance-skills | Twitter、LinkedIn、Discord、Telegram 等多源读取 | 只读 intake 候选 |
| market-research-reports | McKinsey/BCG 风格市场研究、LaTeX 和图表 | 深度选题重武器 |
| analytics-data-analysis | Jupyter 数据分析和证据分析 | 备案参考 |
| baoyu-format-markdown | Markdown 格式整理 | 文章主链 |
| baoyu-post-to-wechat | 微信草稿或发布 | 发布主链 |

### 2.4 数字人和生成模型相关能力

| Skill / 能力 | 作用 | 状态 |
| --- | --- | --- |
| codex-imagegen-omni-presenter | 保留身体、替换头部，再用 omni（Gemini 图生视频）做中文口型和微动作 | 数字人主路线（2026-08-22 起，Luma 已废弃） |
| joyvasa-liveportrait | 单头像音频驱动、中文口型、Apple Silicon MPS | 本地 fallback |
| echomimic-v3 | 半身动作和长视频配置 | 仅 CUDA 实验 |
| sadtalker | 单头像音频驱动 | 兼容性 fallback |
| Gemini API / Gemini Omni | 逐镜视频底片、参考图动画和浏览器调用 | 官方能力，需保持登录与额度 |
| Luma Dream Machine | 肖像动画、嘴部和眼部动作 | ❌ 已废弃（2026-08-22 用户裁决），禁止再用 |
| MiniMax CLI mmx | 配音、配乐、图片、口播音频 | 默认生产入口之一 |
| Seedance / 即梦 / Seedream | 视频、图像和参考图生成 | 官方模型备用 |
| WhisperX / stable-ts / FunASR | 字幕、语音识别和时间轴 | FunASR 为中文主路径，其余为兜底 |

## 3. 已确认的 GitHub 项目

### 3.1 Newma、目录和核心渲染仓库

| 项目 | 仓库 | 用途 | 状态 |
| --- | --- | --- | --- |
| Newma Media Studio | https://github.com/leecyno1/newma-media-studio | 当前自媒体文章、视频和生产脚本主项目 | 当前项目 |
| Newma Desk | https://github.com/leecyno1/newma-dock | Desk/Creator Studio 前端和工作流看板方向 | 外部同级项目 |
| boutique-skills | https://github.com/leecyno1/boutique-skills | Skills 目录、标准 Skill 和 video-shotcraft 来源 | 目录源 |
| boutique-openclaw-skills | https://github.com/leecyno1/boutique-openclaw-skills | OpenClaw/Skills 目录和候选能力 | 目录源 |
| video-shotcraft | https://github.com/Vincentwei1021/video-shotcraft | 镜头配方、电影运镜、节拍、声音设计和 Remotion 冒烟渲染 | 高优先级储备，已有 Newma 适配器 |
| html-video | https://github.com/nexu-io/html-video | HTML/React/Remotion/GSAP/Lottie 主渲染项目 | 已接入外部项目 |
| html-anything | https://github.com/nexu-io/html-anything | HTML 文章、卡片、图表和视觉模板参考 | 已接入/模板参考 |

### 3.2 视频、剪辑、字幕和渲染

| 项目 | 仓库 | 主要能力 | Newma 处理方式 |
| --- | --- | --- | --- |
| video-use | https://github.com/browser-use/video-use | 对话式粗剪、文件夹输入、EDL 和 final.mp4 | A 级 Path C 实验，不替代 FunASR/剪映 |
| freecut | https://github.com/Moh4696/freecut | video-use 的本地 ASR 分支 | 测试 video-use 时优先 |
| talking-head-editor | https://github.com/chrislema/videoeditor | 口播 8 步精剪、缩放、调色、声音和字幕 | 仅流程参考，无顶层 SKILL.md |
| caption-clip | https://github.com/kwindla/skill-caption-clip | Deepgram、SRT 清洗和 FFmpeg 字幕烧录 | 字幕 lane 参考，Deepgram 可选 |
| claude-shorts | https://github.com/AgriciDaniel/claude-shorts | 长视频切片、爆点评分、竖屏字幕 | 计划做 publish 后二创 Skill |
| Video Wrapper Skills | https://github.com/op7418/Video-Wrapper-Skills | 访谈/播客 lower-third、金句、章节卡、社交条 | 高优先级包装模板参考 |
| remotion-video-skill | https://github.com/wshuyi/remotion-video-skill | Remotion、TTS、字幕和模板 | 参考，不重复安装主依赖 |
| remotion-video-toolkit | https://github.com/shreefentsar/remotion-video-toolkit | Remotion、动态图表、3D 和字幕 | 外部参考 |
| claude-real-video | https://github.com/HUANGCHIHHUNGLeo/claude-real-video | 场景识别、关键帧、contact sheet、转录和 MANIFEST | 已保留，作为视频读取/风格训练入口 |
| claude-code-video-toolkit | https://github.com/digitalsamba/claude-code-video-toolkit | 从想法到脚本、旁白、音乐、视觉和 MP4 的工作台 | 重点工作台参考，不整包接入云服务 |
| product-launch-video-skill | https://github.com/memex-lab/product-launch-video-skill | 产品发布片、卖点、CTA、MP4/GIF | 小众广告参考 |
| chengfeng-videocut-skills | https://github.com/Agentchengfeng/chengfeng-videocut-skills | 视频编辑、粗剪计划和执行器路由 | 实验参考 |
| auto-editor | https://github.com/WyattBlue/auto-editor | 静音清理和节奏粗剪 | CLI 备用 |
| video-autopilot-kit | https://github.com/Hao0321/video-autopilot-kit | 短视频脚本、CapCut JSON、FFmpeg 批处理 | 高优先级储备，需 Newma 适配器 |
| Lottie | https://github.com/diffusionstudio/lottie | Agent 生成和验证 Lottie/Bodymovin JSON | 透明贴纸、lower-third、数据流等辅助动效 |
| HyperFrames | https://github.com/heygen-com/hyperframes | HTML 视频、场景组织和时间轴方法 | 方法参考，和本地 html-video 结合 |
| GSAP Skills | https://github.com/greensock/gsap-skills | GSAP 时间轴、SVG、React、性能和响应式动效 | 以一个 Suite 入口注册 |
| Seedance Skill | https://github.com/dexhunter/seedance2-skill | 参考图转视频、生成式 B-roll、提示词设计 | 官方模型备用 |
| media-downloader | https://github.com/yizhiyanhua-ai/media-downloader | 图片、网页和视频下载 | 素材采集桥 |

### 3.3 AI 数字人

| 项目 | 仓库 | 能力 | 状态 |
| --- | --- | --- | --- |
| JoyVASA | https://github.com/jdh-algo/JoyVASA | 单肖像音频驱动、中文动作、长视频滑窗、MPS | 本地 fallback |
| EchoMimic v3 | https://github.com/antgroup/echomimic_v3 | 半身动作和长视频配置 | CUDA 实验，当前 Mac 不作主路由 |
| SadTalker | https://github.com/OpenTalker/SadTalker | 单肖像音频驱动 | 老技术栈兼容 fallback |

### 3.4 视觉、写作和文章生产

| 项目 | 仓库 | 主要用途 | Newma 角色 |
| --- | --- | --- | --- |
| baoyu-skills | https://github.com/JimLiu/baoyu-skills | 封面、插图、信息图、社交卡片、Markdown 和微信 HTML | 文章视觉主链 |
| guizang-social-card-skill | https://github.com/op7418/guizang-social-card-skill | 社交卡片、海报、数据卡、封面 | 发布视觉辅助 |
| taste-skill | https://github.com/Leonxlnx/taste-skill | 视觉方向、反模板感、版式和品牌系统 | 视觉顾问 |
| impeccable | https://github.com/pbakaus/impeccable | HTML 场景审计、响应式、动效和浏览器视觉 QA | 视觉 QC 储备 |
| emilkowalski skills | https://github.com/emilkowalski/skills | 动画语言、动效机会、动画审查和交互润色 | 动效审查 Suite |
| inference skills | https://github.com/inference-sh/skills | 视觉、动效、渲染器选择和 Web Animation | 视觉技术参考 |
| anthropics skills | https://github.com/anthropics/skills | 视觉设计、海报、程序化艺术和品牌系统 | 参考能力 |
| MiniMax skills | https://github.com/MiniMax-AI/skills | 视觉、动效、品牌、图片和 image-to-HTML | 官方模型配套参考 |
| humanizer-zh | https://github.com/idao-cube/humanizer-zh | 中文自然化和反 AI 表达 | 候选，需风格回归 |
| khazix-skills | https://github.com/KKKKhazix/khazix-skills | 长文、行业报告、深度结构和内容审查 | 候选，需证据回归 |
| finance-skills | https://github.com/himself65/finance-skills | 多社交平台只读信息采集 | intake 候选 |
| UZI-Skill | https://github.com/wbh604/UZI-Skill | 自媒体内容和视觉能力候选 | 参考 |
| ian-xiaohei-illustrations | https://github.com/helloianneo/ian-xiaohei-illustrations | 手绘概念图、镜头表和透明覆盖层 | 文章/视频概念视觉 |

### 3.5 发布、账号和平台

| 项目 | 仓库 | 用途 | 状态 |
| --- | --- | --- | --- |
| social-auto-upload | https://github.com/dreammis/social-auto-upload | 多平台上传 | 项目内 vendor 隔离 |
| social-auto-upload-web-ui | https://github.com/DevilJie/social-auto-upload-web-ui | 上传 Web UI | 备用 |
| postbot | https://github.com/gitcoffee-os/postbot | 社交内容发布 | 备用 |
| OpenCLI | https://github.com/jackwener/OpenCLI | CLI 能力发现和平台操作 | 只读采集/平台桥参考 |
| biliup-rs | https://github.com/biliup/biliup-rs | B 站上传 | 备用执行器 |
| Postiz | https://github.com/gitroomhq/postiz-app | 多平台社交发布和排程 | 发布平台参考 |
| agent-skills-launch-pack | https://github.com/chenjin-cmd/agent-skills-launch-pack_ | 发布 Skills 备份 | reserve |
| All-IN-ONE | https://github.com/cv-cat/All-IN-ONE | 发布和平台工具集合 | reserve |
| xiaohongshu-skills | https://github.com/autoclaw-cc/xiaohongshu-skills | 小红书能力集合 | reserve |
| XhsSkills | https://github.com/cv-cat/XhsSkills | 小红书操作技能 | reserve |
| Spider_XHS | https://github.com/cv-cat/Spider_XHS | 小红书采集 | reserve |
| xiaohongshu-mcp | https://github.com/xpzouying/xiaohongshu-mcp | 小红书 MCP | 已克隆，需登录态 |
| XHS-Downloader | https://github.com/JoeanAmier/XHS-Downloader | 小红书下载 | 已克隆，需登录态 |
| rednote-mcp | https://github.com/TimeCyber/mcp-xiaohongshu | Node/Playwright 小红书 MCP，支持搜索、评论和图文发布 | 浏览器/MCP fallback，不是默认主路由 |
| xurl | https://github.com/xdevplatform/xurl | X/Twitter CLI 发布或读取 | 平台备用 |
| x-cli | https://github.com/Infatoshi/x-cli | X/Twitter API v2 CLI | X API fallback |
| OpenClaw social-copy-generator | https://github.com/openclaw/skills/social-copy-generator | 多平台社交文案生成 | 历史外部 Skill，参考 |
| OpenClaw wechat-video-publish | https://github.com/openclaw/skills/wechat-video-publish | 视频号浏览器发布 | 历史外部 Skill，需登录态 |
| OpenClaw auto-publisher | https://github.com/openclaw/skills/auto-publisher | 抖音、视频号、小红书、B站、YouTube 多平台发布 | 历史外部 Skill，参考 |

## 4. 没有确认稳定仓库的能力

以下名称在历史截图、会话或候选清单中出现过，但没有确认到稳定、可直接注册的独立 GitHub 上游，或不应当被当作 Skill 仓库：

| 名称 | 当前判断 |
| --- | --- |
| video-editing-pipeline | 仅确认概念，未定位可信 owner/repo；内部粗剪链已覆盖 |
| ffmpeg-usage | 不是必须独立注册的 Skill；FFmpeg 已作为底层工具写入 Newma 工具注册表 |
| FableCut | 未确认稳定公开仓库 |
| video-rough-cut | 项目内/全局技能名，不能等同于某个已确认 GitHub 仓库 |
| pyJianYingDraft | 剪映草稿自动化候选，仍需 schema、版本和实际导入验证 |
| capcut-cli | 候选 CLI，未满足默认生产路由条件 |
| Palmier MCP | 候选 MCP，未完成稳定性和权限审查 |
| TweetCLI | 历史名称，未作为 Newma 默认 X 发布器 |
| Gemini API / Gemini Omni | 官方模型能力，不是本项目内的可克隆仓库 |
| Luma Dream Machine | 官方服务，不是可直接克隆的 GitHub 项目；2026-08-22 起路线废弃 |
| MiniMax CLI mmx | 官方 CLI / provider 能力，不应把密钥写进仓库 |
| Seedance、即梦、Seedream | 官方模型或产品能力，需经过 provider 路由 |
| Codex ImageGen | 平台内置能力，不是 GitHub 仓库 |
| WhisperX、stable-ts、FunASR | ASR 技术栈和模型工具，不是 Newma Skill 仓库 |
| FFmpeg、Remotion、GSAP、Lottie | 底层运行时或 npm/系统依赖；由工具注册表管理 |

暂不确认不代表不能使用。正确做法是把它们注册为工具或 provider，并写清依赖、权限、输出目录、回滚方式和人工审核门，而不是伪装成已注册 Skill。

## 5. 六条视频生产流水线

六条线统一遵循：

素材接收 → 剧本重写/口播化 → 导演分镜 → 素材生成 → 剪辑合成 → 渲染 → QC/交付

### 5.1 真人出镜口播

主链：

dasheng-video-roughcut → dasheng-video-talking-head → Remotion / FFmpeg

核心能力：

- 以真人音频/视频作为主时间轴；
- FunASR 或剪映清理口水词、停顿、重说和重复；
- Agent 语义校对字幕，再进入终版渲染；
- Remotion 负责主时间轴和合成，HTML Video、GSAP、Lottie 负责标题卡、图表、贴纸、花字和证据层；
- 视频中的“人物名、央行、公司、机构”等实体出现时，必须配对应说明标签；
- 数据图表必须来自文章或已验证取数链路，不能让装饰性动画代替证据；
- 目标人声音量约 -16 LUFS，字幕 1–2 行，语义断句，不能和画面重叠。

### 5.2 VOX 调查解释

主链：

dasheng-vox-skills → Shotcraft / Gemini Omni → Remotion 二剪 → FFmpeg / QC

叙事状态机：

cold_open → central_question → evidence_map → historical_context → mechanism_explainer → field_or_human_evidence → counterargument → data_resolution → qualified_conclusion

关键原则：

- 先锁中心问题，再检索证据，不能把文章章节标题直接当分镜；
- 真实新闻、人物、文档、图表和现场素材要记录来源、时间段、本地路径以及 direct/context 关系；
- 新闻主播一般用 PIP 或分屏，只有原话或原始字幕需要时才全屏；
- 必须保留反证、边界条件和“已知/推演/条件/未知”的区别；
- Gemini Omni 只生成运动底片，真实资料、准确文字、图表、字幕和最终音频由 Remotion 叠加；
- Shotcraft 负责镜头语言和节奏卡，不能绕过 Newma 的证据和口播约束。

### 5.3 无头口播 / HTML 科普

主链：

dasheng-video-explainer-html → HTML Anything → html-video → Remotion

默认状态机：

hook_card → question_setup → chapter_card → evidence_scene → logic_animation → cinematic_bridge → recap_card

关键原则：

- HTML 文章是事实源，不能在视频里另起一套事实链；
- 文章中的表格、图表、图片、claim 和引用直接进入分镜证据；
- HTML Anything 提供模板和视觉语言，html-video 负责场景，Remotion 负责主时间轴；
- GSAP 控制入场、出场、路径、数字和图表 reveal，Lottie 只做辅助动效；
- TTS、配乐和生图默认使用 MiniMax CLI；macOS say 只用于烟测 fallback；
- 不做单纯 PPT 翻页，要有问题设置、证据、逻辑动画、复盘和留存节奏。

### 5.4 AI 数字人

主链：

授权肖像 → ImageGen 角色参考图 → omni / JoyVASA（离线备用）生成口型和微动作 → Remotion 合成 → QC

单人和双人都要遵守：

- 每个人物单独建立 speaker_id、肖像、音轨、生成任务和 QC 记录；
- 两人访谈不能由一个图生视频任务同时控制两个嘴部；
- 每个对话 turn 只能有一个 active_speaker，非发言者保留自然待机；
- 两个人物源都静音，最终音频按 turn 挂载；
- 交付时必须有 AI 生成披露、肖像授权和短样审核。

### 5.5 广告宣传片

主链：

品牌/产品素材 → 广告脚本 → 导演分镜 → 产品与品牌素材 → Remotion → 多比例渲染 → 品牌/声明/QC

关键原则：

- 一条广告只保留一个主要目标和一个主 CTA；
- 脚本必须有钩子、承诺、卖点收益、Proof、品牌记忆和 CTA；
- 产品能力、比较、价格、客户结果和优惠绑定来源；
- 官方 Logo、产品录屏和实拍优先，生成式画面不能伪装真实产品 UI、客户证言或效果证明；
- 9:16、16:9、1:1、4:5 都要检查字幕、Logo、Offer、法律说明和 CTA 安全区。

### 5.6 电影短剧

当前状态：execution_enabled=false。

允许：

- 剧本；
- 角色圣经；
- 场景圣经；
- 连续性表；
- 逐镜分镜；
- 声音和后期规划。

暂不默认调用外部视频 API。只有用户明确批准供应商、预算、角色授权、内容安全边界和 provider 路由后，才能启用 Seedance、Gemini/Veo 或 MiniMax 官方路线。第三方聚合商不进入默认路由。

## 6. 核心技术栈与职责边界

| 能力层 | 主技术 | 说明 |
| --- | --- | --- |
| 编排与 Agent | Codex、Qoder CLI、Newma Agent、Stage Router | 对话和可视化双端编排，所有决定写入 Event |
| 本地 CLI 发现 | html-anything / html-video 的 Agent 调用机制、OpenCLI 思路 | 识别本机已安装 CLI，调用前做能力和输出路径检查 |
| 研究和网页 | 浏览器、requests、BeautifulSoup、media-downloader | 搜索新闻、官网、研报、图表和原始资料 |
| 金融数据 | AkShare、Tushare、pandas、numpy、matplotlib、seaborn | 文章和视频的真实数据、图表和证据 |
| 语音识别 | FunASR、modelscope、torch、torchaudio | 中文口播粗剪主路径 |
| 字幕兜底 | WhisperX、stable-ts、SRT 回填脚本 | 时间轴和多语种兜底 |
| 剪辑底层 | FFmpeg | 裁剪、拼接、转码、压缩、音频增强、字幕烧录和封装检查 |
| 主时间轴 | Remotion | 多路素材、字幕、音频、场景和最终合成 |
| HTML 场景 | html-video、html-anything | HTML 文章、卡片、动态图表和场景模板 |
| 动画 | GSAP、Lottie、HyperFrames | 时间轴、SVG、路径、数字 reveal、贴纸和场景组织 |
| 配音和配乐 | MiniMax CLI mmx | 生产级 TTS、BGM、图片和口播音频 |
| 生成式视频 | Gemini Omni、Seedance、即梦 | 只生成需要的逐镜底片或概念 B-roll |
| 数字人 | omni（主）、JoyVASA（离线备用）、EchoMimic/SadTalker（淘汰参考） | 授权肖像动画、口型、眨眼和微动作 |
| 发布 | md2wechat、baoyu-post-to-wechat、social-auto-upload、biliup、XHS MCP | 文章、视频和渠道回执 |
| 人工介入 | 剪映专业版、Creator Studio / Newma Desk | 粗剪、时间轴微调、审核、素材替换和反馈 |

### 输出和依赖边界

- 发布项目代码与虚拟环境放在 vendor/publish/；
- 登录态放在系统应用支持目录或独立 profile 目录；
- 每次任务的素材、产物、截图、回执和失败记录放在桌面任务目录；
- 不把运行产物写入 skills/、.codex/skills/、vendor/reserved/ 或仓库根目录；
- 外部项目默认不锁死版本，但升级前必须通过依赖预检、冒烟渲染、证据门和人工复核。

## 7. 注册、适配和晋级规则

### 7.1 当前注册入口

视频工作流的主要配置和契约文件：

- configs/video/director_registry.json
- configs/video/tool_registry.json
- configs/video/pipelines/talking_head.yaml
- configs/video/pipelines/vox_explainer.yaml
- configs/video/pipelines/explainer_html.yaml
- configs/video/pipelines/digital_human.yaml
- configs/video/pipelines/cinematic_short_drama.yaml
- configs/video/pipelines/commercial_promo.yaml
- configs/video/pipelines/style_training.yaml
- configs/video/artifact_schemas/
- configs/workflow/project_run_manifest.schema.json

### 7.2 外部能力晋级条件

外部 Skill 或仓库必须满足以下条件，才可以从参考或储备晋级为生产路由：

1. 已阅读 SKILL.md 或 README；
2. 许可证和依赖已确认；
3. 有具体 Newma 调用方；
4. 有输入和输出契约；
5. 输出路径受到保护；
6. 完成依赖预检；
7. 完成可重复的 smoke test 或渲染样片；
8. 通过证据、画面、字幕、声音和人工审核门。

### 7.3 当前高优先级推进

| 优先级 | 项目/能力 | 建议 |
| --- | --- | --- |
| S | video-shotcraft | 继续通过 Newma VOX Adapter 使用镜头配方、真实页面采集、节拍和声音设计 |
| S | Video-Wrapper-Skills | 迁移 lower-third、term-card、quote-callout、social-bar 到真人口播包装库 |
| A | claude-shorts | 新建 publish 后短视频切片子链，不放入主视频生成 |
| A | video-use / freecut | 实验素材文件夹到 final.mp4 的 Path C，不替代 FunASR/剪映 |
| A | claude-code-video-toolkit | 借鉴模板、转场、浏览器录制和工作台结构，不引入第三方云凭据 |
| B | text-to-lottie | ✅ 已晋级生产路由（2026-08-22）：tool_registry ready，人物名牌冒烟通过（newma-lower-thirds/scene-1，帧 0/12/45/89 官方播放器验证） |
| B | impeccable | ✅ 已晋级视觉 QC 顾问（2026-08-22）：适配器 scripts/run_impeccable_visual_qc.py，draft/transwrite/publish 三阶段 advisor，T06 冒烟（4 warning/0 error）通过 |
| A | video-autopilot-kit | 先做 CapCut JSON、FFmpeg 批处理和输出契约适配器，再考虑注册 |

## 8. 当前主链关系

公众号和视频的主链关系如下：

intake  
→ 来源、热点、账号 DNA 和原始素材

brief  
→ TopicCard、中心问题、研究 Brief、事实清单和证据需求

draft  
→ 长文、推理表、引用、数据图、Draft HTML

transwrite  
→ 公众号文章、真人口播稿、VOX 叙事、无头视频包、数字人包、广告包

director  
→ 剧本重写、留存结构、导演分镜、Claim/Evidence Ledger、素材清单

render  
→ HTML/Remotion/FFmpeg/外部生成器合成、字幕、花字、贴纸、声音和多比例输出

QC / delivery  
→ 事实、来源、字幕、音画同步、品牌安全、AI 披露、文件封装和发布包

publish / postmortem  
→ 账号发布、平台回执、数据归因和下一轮风格/选题回写

## 9. 维护建议

1. 新增能力优先使用 newma-* 命名，旧 dasheng-* 只做兼容别名。
2. 把本索引与 configs/video/upstream_video_skills.json、configs/external/reserved_projects.json、configs/workflow/creator_technology_candidates.json 一起维护。
3. 每个外部仓库都记录：URL、许可证、核验时间、版本快照、用途、调用方、状态和阻塞项。
4. Skills、仓库、CLI、Provider 分开登记，不能因为同名就混为一类。
5. 视觉包装、动画和生成式 B-roll 都不能替代真实数据、来源截图、人物原话和证据素材。
6. 文章和视频必须共用同一份 Draft、Claim、Evidence 和数据资产，避免文章与视频各自生成一套事实。
7. 任何自动发布、登录态和外部 API 都要保留人工确认点；发布草稿和正式发布必须分开。

## 10. 相关本地文档

- [公众号文章与视频生成 Skill 依赖地图](./wechat-video-skill-dependency-map.md)
- [Video Production Lines](./video-production-lines.md)
- [视频流水线治理](./video-pipeline-governance.md)
- [视频剪辑驱动机制](./video-editing-driving-mechanism.md)
- [外部 Skills 综合评测与注册](./external-skills-review-20260821.md)
- [Boutique Skills 视频与自媒体储备复核](./boutique-skills-video-media-reserve-review-20260802.md)
- [HTML Anything 模板矩阵](./html-anything-template-matrix.md)
- [HTML Anything 视频模板路由](./html-anything-video-template-routing.md)
- [视频读取与风格训练](./video-reading-with-claude-real-video.md)
