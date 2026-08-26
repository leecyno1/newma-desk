# Newma 视频与自媒体技术栈储备审核（实验研究版）

更新时间：2026-08-23  
范围：粗剪、精剪、视频生成、动画生成、漫画/漫剧、插图、文案与相关 Agent Skills  
用途：供 Newma 技术栈扩充、超市注册、实验 PoC 和后续适配立项审核

> 本版采用“先判断能否提升 Newma，再单独处理生产准入”的口径。许可证只保留为项目元数据，不参与实验优先级；是否进入正式产品、如何部署和分发，留到生产准入阶段处理。

## 1. 结论：从“工具储备”升级成“可恢复的制片系统”

上一版重点是补工具。本轮重新审视后，真正值得吸收的是下面十二个系统机制：

1. **Agent 与人工共用一条真实时间线**：Agent 不能只输出建议文本，人工拖动后的结果也必须回写同一个工程。
2. **Proposal → Validate → Commit → Undo**：任何自动剪辑先形成可预览提案，通过检查后提交，并能逐项撤销。
3. **Style Skill**：把一次完整剪辑中的节奏、转场、字幕、花字、B-roll 和音效选择归档成可复用风格技能。
4. **Script → Asset → Keyframe → Video**：脚本不能直接跳到视频生成，先完成资产登记和低成本关键帧预审。
5. **Asset Passport**：角色、服装、场景、道具、品牌元素都有身份、参考图、反参考、状态变体和使用记录。
6. **生成前压力测试**：角色在多角度、不同光线、双人同框和动作状态下通过一致性检查后才锁定。
7. **Take 与版本永久保留**：每次生成保存模型、参数、输入、修改点、成本和人工裁决，不覆盖旧结果。
8. **镜头级恢复**：支持按 shot/beat 局部重试、断点续跑和替换，不因单镜失败重跑整片。
9. **Dry-run 与成本闸门**：生成前给出依赖、预计耗时、硬成本上限和更便宜的替代路线。
10. **多 Agent 制片分工**：编剧、导演、制片、摄影、资产管理员、审片员分别产出结构化交付物。
11. **事件驱动看板**：状态看板由真实 Artifact、Timeline、Proposal、QC 和 Event 自动生成，不维护第二套假状态。
12. **机器质量门**：主体/背景一致性、闪烁、运动平滑、镜头语义、角色动作和风格连续性进入自动 QC。

### 实验优先级

| 标记 | 含义 | 本轮判断标准 |
| --- | --- | --- |
| E0 | 立即拆解并做最小 PoC | 能补 Newma 核心协议、导演流程、可恢复生产或自动质检 |
| E1 | 吸收方法、Schema 或局部能力 | 价值明确，但不需要先运行整套系统 |
| E2 | 研究观察 | 偏论文验证、硬件较重、功能重叠或暂时缺少直接调用方 |

许可证、部署方式和商业边界改为独立的 `production_admission` 审核，不再把高价值项目降成“只读参考”。

### 本轮 E0：立即进入拆解/PoC

| 项目 | 重点吸收 | 对应 Newma 模块 |
| --- | --- | --- |
| [OpenTimelineIO](https://github.com/AcademySoftwareFoundation/OpenTimelineIO) | 统一时间线和编辑器交换 | `timeline_contract` |
| [OpenCut](https://github.com/OpenCut-app/OpenCut) + [OpenChatCut](https://github.com/0xsline/OpenChatCut) | 人工/Agent 共用时间线、可撤销编辑 | `editor_workspace`、`edit_proposal` |
| [FireRed-OpenStoryline](https://github.com/FireRedTeam/FireRed-OpenStoryline) | 意图驱动剪辑、自然语言精修、AI 转场、Style Skill、Agent Memory | `roughcut_agent`、`style_skill_registry` |
| [BigBanana-AI-Director](https://github.com/shuyu-labs/BigBanana-AI-Director) | Script → Asset → Keyframe、世界观/角色/场景资产库 | `director_preproduction` |
| [shuohao-skills](https://github.com/eternityspring/shuohao-skills) | 确定性时长、镜头长度门、提示词对账、多级质量门 | `storyboard_gate` |
| [film-studio-skills](https://github.com/machina-exm/film-studio-skills) | Asset Passport、反参考、状态变体、连续性压力测试 | `asset_registry` |
| [ViMax](https://github.com/HKUDS/ViMax) | Director/Screenwriter/Producer/Generator 多 Agent、项目恢复与检查点 | `production_orchestrator` |
| [vibeframe](https://github.com/vericontext/vibeframe) | dry-run、成本上限、逐 beat 重建、机器可读修复报告 | `run_planner`、`recovery` |
| [VBench](https://github.com/Vchitect/VBench) + [ViStoryBench](https://github.com/ViStoryBench/vistorybench) | 视频质量、剧情对应、人物/风格/镜头连续性指标 | `generation_qc` |
| [ComfyUI-Copilot](https://github.com/ATH-MaaS/ComfyUI-Copilot) | 工作流生成、调试、重写、参数优化和本地节点感知 | `generation_workflow_agent` |

### 本轮 E1：吸收方法和 Schema

| 项目 | 重点吸收 |
| --- | --- |
| [Pixelle-Video](https://github.com/ATH-MaaS/Pixelle-Video) | 文案→配图规划→逐帧处理→合成的任务分解及 ComfyUI 工作流挂载 |
| [Inline-Studio](https://github.com/inlineresearch/Inline-Studio) | 节点画布、版本化 take、不覆盖历史、连续性评分、项目整体导入导出 |
| [VideoClaw](https://github.com/HITsz-TMG/VideoClaw) | 对话驱动、多 Agent 从创意到成片的协作边界 |
| [30x-video](https://github.com/norahe0304-art/30x-video) | 品牌官网采集、五幕广告结构、Taste Codex、证据门和 proof frame |
| [ShotPlan](https://github.com/Pensioner-11/ShotPlan) | 精确硬切帧、global/shot 分层提示和多镜头规划 token |
| [DramaDirector](https://github.com/iLearn-Lab/DramaDirector) | 结构化 shot schema、深度/姿态检索、文本视觉奖励和首帧规划 |
| [Evaluation-Agent](https://github.com/Vchitect/Evaluation-Agent) | 按用户问题动态设计、少样本、多轮、可解释的评测流程 |
| [OpenMontage](https://github.com/calesthio/OpenMontage) | 多流水线、工具注册、Backlot 过程看板和成本记录 |
| [DramaClaw](https://github.com/dramaclaw/dramaclaw)、[WaooWaoo](https://github.com/waooAI/waoowaoo)、[Huobao Drama](https://github.com/chatfire-AI/huobao-drama) | 供应商路由、工业化虚拟制片、剧本到成片的完整功能面 |

### 本轮 E2：研究观察

- [MovieAgent](https://github.com/showlab/MovieAgent)：多 Agent 电影规划的角色协作方式。
- [MM_StoryAgent](https://github.com/X-PLUG/MM_StoryAgent)：图像、语音、音乐、故事 Agent 的可插拔组合。
- [Anim-Director](https://github.com/HITsz-TMG/Anim-Director)：用搜索/MCTS 选择并改进长篇动画片段。
- Wan、LTX、Hunyuan、MiniMax 等生成模型：继续作为 Provider/Worker 候选，不直接决定 Newma 的上层流程。

## 2. 搜索口径与限制

### 已完成

- 本地审计 `boutique-skills`：396 个 Skills，仓库快照 `e16c7a0`，2026-08-16。
- GitHub：逐仓核验仓库、Star、最近提交、许可证、README 和主要技术栈。
- B 站：直接搜索项目名、开源剪辑、AI 视频、漫剧、插图和 Skills。
- 小红书：直接搜索同类关键词，并将产品名反查到 GitHub 主仓。
- 对热门产品名做了去重：ChatCut、OpenChatCut、AutoClip、FunClip、VideoFusion、DramaClaw 等不再混为一谈。

### 当前缺口

- X 搜索因本机没有 `x.com` 的 `ct0` 登录 Cookie 返回 `AUTH_REQUIRED`。本轮没有伪造或引用二手 X 帖子。
- Star 和维护时间是 2026-08-23 快照，只用于热度和维护判断。
- 仓库许可证与模型权重许可证是两件事；接入模型前仍需再核权重、数据集和商业使用条款。

### 评估口径

本文所有审核结论统一使用 `E0/E1/E2`。仓库许可证继续记录，等 PoC 通过后再进入生产准入评审。

## 3. 粗剪与精剪

### 3.1 建议主栈

| 项目 | GitHub 快照 | License | 核心能力 | Newma 映射 | 决策 |
| --- | ---: | --- | --- | --- | --- |
| [OpenTimelineIO](https://github.com/AcademySoftwareFoundation/OpenTimelineIO) | 1,960★，2026-08-07 | Apache-2.0 | 时间线 API 和交换格式 | 所有视频流水线的 canonical timeline | E0 |
| [OpenCut](https://github.com/OpenCut-app/OpenCut) | 85,486★，2026-08-10 | MIT | Web/桌面/移动编辑器、Rust core、插件、MCP | Newma Desk 人工精剪台 | E0 |
| [OpenChatCut](https://github.com/0xsline/OpenChatCut) | 1,321★，2026-08-20 | AGPL-3.0 | 多轨时间线、Agent/MCP、字幕、FCPXML、可撤销编辑 | Agent 与可视化同步参考 | E0 |
| [FireRed-OpenStoryline](https://github.com/FireRedTeam/FireRed-OpenStoryline) | 3,244★ | 见主仓 | ASR 粗剪、意图编辑、AI 转场、Style Skill、Agent Memory | 粗剪 Agent 与风格训练 | E0 |
| [FunClip](https://github.com/modelscope/FunClip) | 6,173★，2026-08-19 | MIT | FunASR、热词、说话人、多段裁剪、SRT、LLM 辅助 | 真人口播中文粗剪 | E0 |
| [video-use](https://github.com/browser-use/video-use) | 21,256★，2026-07-01 | MIT | Agent 粗剪、调色、字幕、动画叠层、自评循环 | 真人口播 Path C | E1 |
| [freecut](https://github.com/Moh4696/freecut) | 270★，2026-07-01 | MIT | 用本地 Whisper/VibeVoice 替换 ElevenLabs | video-use 的低成本入口 | E1 |
| [AutoClip](https://github.com/zhouxiaoka/autoclip) | 6,931★，2026-06-03 | MIT | 长视频高光提取、切片、项目统计 | 长视频转 Shorts/Reels | E1 |
| [auto-editor](https://github.com/WyattBlue/auto-editor) | 5,041★，2026-08-20 | Unlicense | 静音、音量、运动驱动的自动裁剪 | 底层粗剪算子 | E1 |
| [Cutia](https://github.com/msgbyte/cutia) | 834★，2026-04-24 | MIT | 浏览器内 CapCut 替代 | OpenCut 的轻量备选 | E2 |
| [claude-code-auto-video-edit](https://github.com/DayadaUP/claude-code-auto-video-edit) | 119★，2026-04-06 | MIT | Whisper → 剪辑点 → 达芬奇时间线 + SRT | 达芬奇人工精剪交接 | E1 |
| [claude-shorts](https://github.com/AgriciDaniel/claude-shorts) | 191★，2026-07-11 | MIT | 段落评分、长转短、竖屏动画字幕 | publish 后二创 | E1 |

### 3.2 可保留但不进入主路由

| 项目 | 判断 |
| --- | --- |
| [LosslessCut](https://github.com/mifi/lossless-cut) | 无损人工裁剪很好用，但 GPL-2.0，且不是 Agent 原生；作为外部工具即可 |
| [Kdenlive](https://github.com/KDE/kdenlive) / [Shotcut](https://github.com/mltframework/shotcut) | 成熟 NLE，但 GPL、桌面集成重；适合导出工程，不适合作为 Newma 内嵌主前端 |
| [MLT](https://github.com/mltframework/mlt) / [libopenshot](https://github.com/OpenShot/libopenshot) | 可作为编辑引擎储备；现阶段 FFmpeg + OTIO 已能覆盖主要需求 |
| [SuperAIAutoCut](https://github.com/xiaohu2206/superAIAutoCutVideo) | 社交热度高于工程成熟度，E2 观察 |
| [VideoFusion](https://github.com/271374667/VideoFusion) | 最近主要更新在 2024，能力偏拼接和横竖屏转换，E2 |
| [ChatCut Agent Plugin](https://github.com/ChatCut-Inc/agent-plugin) | E2，观察商业剪辑产品暴露给 Agent 的接口设计 |

### 3.3 Newma 应采用的剪辑分工

```text
原始素材
  → FunASR / WhisperX 转写与强制对齐
  → FunClip / FireRed / freecut 生成 Edit Proposal
  → 规则校验 + 人工预览
  → Commit 到 OTIO 主时间线（保留 Undo）
  → OpenCut 人工精剪或 Newma 自动包装
  → 将人工裁决回写 Style Skill / Agent Memory
  → Remotion / html-video / FFmpeg 渲染
  → AutoClip / claude-shorts 做二次分发
```

任何外部剪辑器都只能读写时间线和素材引用，不得成为唯一的项目真相源。

## 4. 视频生成与完整生产系统

### 4.1 生产系统和 Agent Skills

| 项目 | GitHub 快照 | License | 可借能力 | 决策 |
| --- | ---: | --- | --- | --- |
| [ViMax](https://github.com/HKUDS/ViMax) | 12,060★ | 见主仓 | Director/Screenwriter/Producer/Generator、多模式生产、项目恢复、检查点 | E0，吸收多 Agent 制片协议 |
| [BigBanana-AI-Director](https://github.com/shuyu-labs/BigBanana-AI-Director) | 1,753★ | 见主仓 | Script → Asset → Keyframe、资产库、九宫格、首尾帧 | E0，吸收导演预制片流程 |
| [shuohao-skills](https://github.com/eternityspring/shuohao-skills) | 1,895★ | 见主仓 | 五段式 Skills、确定性时长、镜头门、提示词对账、多道质量门 | E0，吸收 Schema 和门禁 |
| [film-studio-skills](https://github.com/machina-exm/film-studio-skills) | 91★ | 见主仓 | 资产护照、参考/反参考、状态变体、连续性压力测试、生成日志 | E0，吸收资产协议 |
| [vibeframe](https://github.com/vericontext/vibeframe) | 165★ | 见主仓 | CLI/MCP、dry-run、成本上限、逐 beat 重建、恢复、修复报告 | E0，吸收运行与恢复协议 |
| [Inline-Studio](https://github.com/inlineresearch/Inline-Studio) | 238★ | 见主仓 | 节点画布、版本化 take、连续性评分、本地/云模型混合 | E1，吸收交互和版本模型 |
| [Pixelle-Video](https://github.com/ATH-MaaS/Pixelle-Video) | 27,175★ | 见主仓 | 文案、配图规划、逐帧生成、ComfyUI 工作流、合成与进度管理 | E1，吸收任务编排 |
| [VideoClaw](https://github.com/HITsz-TMG/VideoClaw) | 1,719★ | 见主仓 | 对话式创意到成片、多 Agent 影视生产 | E1，吸收对话编排 |
| [30x-video](https://github.com/norahe0304-art/30x-video) | 62★ | 见主仓 | 品牌资产采集、五幕叙事、Taste Codex、证据门、proof frame | E1，吸收广告导演能力 |
| [OpenMontage](https://github.com/calesthio/OpenMontage) | 49,471★，2026-08-22 | AGPL-3.0 | 12 条流水线、工具注册、生产知识、真实素材语料、Backlot 看板、成本追踪 | E1，吸收平台架构 |
| [MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) | 114,628★，2026-08-22 | MIT | 主题到文案、配音、素材、字幕、BGM、成片 | E2，低成本无头口播基准 |
| [video-shotcraft](https://github.com/Vincentwei1021/video-shotcraft) | 6,054★，2026-08-22 | Apache-2.0 | 152 镜头配方、209 预览、Remotion、真实页面、声音设计 | E0，镜头语言库 |
| [video-autopilot-kit](https://github.com/Hao0321/video-autopilot-kit) | 1,860★，2026-08-20 | MIT | Shorts、CapCut JSON、FFmpeg、QA、竞品拆解 | E1，交付 QA |
| [video-spec-builder](https://github.com/feicaiclub/video-spec-builder) | 916★，2026-05-18 | MIT | 精确到秒的分镜规格和变更影响检查 | E0，导演 Schema |
| [jianshuo/claude-skills](https://github.com/jianshuo/claude-skills) | 124★，2026-08-20 | MIT | 转写、翻译、配音、烧字幕、多机位同步、重构画幅 | E1，按子能力拆取 |
| [ComfyUI-Agent-Kit](https://github.com/SlavaSexton/ComfyUI-Agent-Kit) | 81★，2026-08-20 | Apache-2.0 | Agent 工具、模板、硬件识别、GUI 回写、模型知识 | E1，本地生成 sidecar |
| [ComfyUI-Copilot](https://github.com/ATH-MaaS/ComfyUI-Copilot) | 5,481★ | 见主仓 | 工作流生成、调试、重写、参数优化、节点查询、环境感知 | E0，生成工作流 Agent |
| [vox-ai-motion-graphics-generator](https://github.com/Anil-matcha/vox-ai-motion-graphics-generator) | 169★，2026-08-03 | 仓库元数据未识别 | VOX 拼贴、beat map、双人工门禁 | E1，吸收 beat 和审批机制 |

### 4.2 生成模型储备

| 项目 | GitHub 快照 | License | 结论 |
| --- | ---: | --- | --- |
| [Wan2.2](https://github.com/Wan-Video/Wan2.2) | 17,249★，2026-03-17 | Apache-2.0 | E1；社区和 ComfyUI 生态成熟，适合独立 GPU Worker |
| [LTX-Video](https://github.com/Lightricks/LTX-Video) | 10,886★，2026-01-05 | Apache-2.0 | E1；适合作为本地视频生成后备 |
| [MiniMax-H3](https://github.com/MiniMax-AI/MiniMax-H3) | 6,721★，2026-08-15 | 未声明 | E2；先测真实质量、显存、速度和工作流兼容性 |
| [HunyuanVideo](https://github.com/Tencent-Hunyuan/HunyuanVideo) | 12,453★，2026-06-29 | 腾讯社区许可 | E1；评估人物、运动和中文语义表现 |
| [LTX-2](https://github.com/Lightricks/LTX-2) | 9,210★，2026-08-16 | LTX-2.x Community License | E1；新模型，先评估硬件成本和镜头可控性 |
| [Open-Sora](https://github.com/hpcaitech/Open-Sora) | 29,290★，2026-04-09 | Apache-2.0 | E2；研究价值高，生产质量和成本需单独验证 |
| [CogVideo](https://github.com/zai-org/CogVideo) | 12,968★，2025-11-04 | Apache-2.0 | E2；作为兼容模型，不做默认 |
| [SkyReels-V2](https://github.com/SkyworkAI/SkyReels-V2) | 7,425★，2026-01-29 | 未识别 | E2；观察电影化镜头与本地部署表现 |

### 4.3 数字人和口型

| 项目 | License | 用途 | 决策 |
| --- | --- | --- | --- |
| [JoyVASA](https://github.com/jdh-algo/JoyVASA) | MIT | 单图、人物和动物音频驱动 | E1，本地 fallback |
| [EchoMimic](https://github.com/antgroup/echomimic) / [EchoMimicV2](https://github.com/antgroup/echomimic_v2) | Apache-2.0 | 半身人物动画 | E1，适合独立 CUDA Worker |
| [LatentSync](https://github.com/bytedance/LatentSync) | Apache-2.0 | 口型同步 | E1，作为后处理算子 |
| [VideoReTalking](https://github.com/OpenTalker/video-retalking) | Apache-2.0 | 已有视频的口型重定向 | E2，项目更新较弱 |
| [LivePortrait](https://github.com/KlingAIResearch/LivePortrait) | 未识别 | 肖像动画 | E1，重点测试身份、眨眼和头部动作稳定性 |
| [Duix-Avatar](https://github.com/duixcom/Duix-Avatar) | 未识别 | 离线数字人克隆 | E1，研究离线克隆和实时驱动架构 |

本地视频模型不应运行在 Newma Desk 前端进程中。标准方式应是：Desk 发任务，GPU Worker/ComfyUI 执行，产物和日志回写 Artifact Store。

## 5. 动画与确定性渲染

| 项目 | GitHub 快照 | License | 最适场景 | 决策 |
| --- | ---: | --- | --- | --- |
| [HyperFrames](https://github.com/heygen-com/hyperframes) | 42,111★，2026-08-22 | Apache-2.0 | HTML/CSS/GSAP、Agent 视频 | E0，继续保留 |
| [html-video](https://github.com/nexu-io/html-video) | 4,448★，2026-06-21 | Apache-2.0 | HTML/React/GSAP/Lottie 到 MP4 | E0，现有主链 |
| [Remotion](https://github.com/remotion-dev/remotion) | 57,091★，2026-08-22 | Remotion License | React 视频、字幕、合成、模板 | E0，现有主链 |
| [Motion Canvas](https://github.com/motion-canvas/motion-canvas) | 18,993★，2026-07-02 | MIT | 代码动画、解释型视频 | E1 |
| [Revideo](https://github.com/redotvideo/revideo) | 3,997★，2026-07-15 | MIT | TypeScript 程序化视频 | E1 |
| [Manim](https://github.com/3b1b/manim) | 91,906★，2026-08-18 | MIT | 数学、机制、公式动画 | E1，按镜头调用 |
| [lottie-web](https://github.com/airbnb/lottie-web) | 32,055★，2025-09-01 | MIT | AE/Lottie 动画播放 | E1，继续作为素材格式 |
| [Theatre.js](https://github.com/theatre-js/theatre) | 12,626★，2024-08-14 | Apache-2.0 | Web motion editor | E2，维护弱 |
| [Blender](https://github.com/blender/blender) | 19,798★，2026-08-22 | GPL 系 | 3D、科学和电影镜头 | E2，外部 Worker，不进默认链 |

### 动画路由原则

- 字幕、图表、UI、标题、说明卡：优先 HTML/GSAP/HyperFrames/html-video。
- 复杂 React 合成和多人多层时间线：Remotion。
- 数学、机制和几何推演：Manim。
- 复杂 3D：Blender 外部 Worker。
- 不为同一个场景同时暴露五个渲染器；由导演按镜头能力选择。

## 6. 漫画、漫剧和电影短剧

| 项目 | GitHub 快照 | License | 可借能力 | 决策 |
| --- | ---: | --- | --- | --- |
| [drama-skills](https://github.com/worldwonderer/drama-skills) | 969★，2026-08-22 | MIT | 十个 Skills、剧本、资产、LookDev、分镜、连续性、生产确认 | E0 |
| [BigBanana-AI-Director](https://github.com/shuyu-labs/BigBanana-AI-Director) | 1,753★ | 见主仓 | 世界观、人物衣橱、场景/道具资产、九宫格、首尾帧 | E0 |
| [shuohao-skills](https://github.com/eternityspring/shuohao-skills) | 1,895★ | 见主仓 | 小说大纲、角色、美术、剧本、分镜五类 Skills 和多级质量门 | E0 |
| [film-studio-skills](https://github.com/machina-exm/film-studio-skills) | 91★ | 见主仓 | 资产护照、反参考、状态变体、压力测试、锁定与生成日志 | E0 |
| [Toonflow](https://github.com/HBAI-Ltd/Toonflow-app) | 14,351★，2026-07-28 | Apache-2.0 | 小说/剧本到动画短剧、桌面工作台 | E1，重点研究项目结构 |
| [Jellyfish](https://github.com/Forget-C/Jellyfish) | 6,152★，2026-07-30 | Apache-2.0 | 分镜、角色一致性、镜头准备、生成和导出 | E1 |
| [LumenX](https://github.com/alibaba/lumenx) | 1,127★，2026-08-11 | MIT | 小说到短漫剧、角色、场景、分镜、视频 | E1 |
| [DramaClaw](https://github.com/dramaclaw/dramaclaw) | 3,851★，2026-08-22 | Elastic License 2.0 | 通用 AIGC 视频引擎、合规清单、供应商路由 | E1，拆解完整功能面 |
| [WaooWaoo](https://github.com/waooAI/waoowaoo) | 13,778★，2026-08-13 | CC BY-NC-SA 4.0 | 工业化虚拟制片、多人协作和生成网关 | E1，拆解协作和网关 |
| [Huobao Drama](https://github.com/chatfire-AI/huobao-drama) | 14,064★，2026-08-18 | 未声明 | 一句话到剧本、角色、分镜、配音和成片 | E1，做完整功能对照 |
| [printfilm](https://github.com/yuanzhongqiao/printfilm) | 3,845★，2026-08-11 | 未声明 | 短剧/漫剧工业工作台 | E1，研究工作台交互 |
| [AIComicBuilder](https://github.com/LingyiChen-AI/AIComicBuilder) | 1,804★，2026-04-27 | Apache-2.0 | 脚本到角色、分镜和动画漫画视频 | E1 |
| [baoyu-comic](https://github.com/JimLiu/baoyu-skills) | 仓库 25,249★ | MIT | 知识漫画和多面板脚本 | E0，Boutique 已有 |

### 角色一致性组件

| 项目 | 作用 | 判断 |
| --- | --- | --- |
| [StoryDiffusion](https://github.com/HVision-NKU/StoryDiffusion) | 长故事和多图角色一致性 | E1 方法参考，主仓更新较弱 |
| [InstantID](https://github.com/instantX-research/InstantID) | 身份保持 | E1 组件 |
| [IP-Adapter](https://github.com/tencent-ailab/IP-Adapter) | 参考图条件控制 | E1 组件 |
| [PuLID](https://github.com/ToTheBeginning/PuLID) | 身份定制 | E1 组件 |
| [PhotoMaker](https://github.com/TencentARC/PhotoMaker) | 人物身份保持 | E2，对比身份保持效果 |

电影短剧流水线应优先吸收 `drama-skills`、BigBanana、shuohao 和 film-studio-skills 的 Schema 与质量门；一体化平台按对象和接口拆解，不整体移植成新的单体系统。

## 7. 插图、封面和视觉素材

### 7.1 Boutique/现有能力

| Skill | 能力 | 决策 |
| --- | --- | --- |
| `baoyu-image-gen` | GPT Image、Gemini、OpenRouter、DashScope、Seedream 等多 Provider 生图 | E0，统一图片生成入口 |
| `baoyu-article-illustrator` | 分析文章结构和插图位 | E0/E1，连接文章与视频素材计划 |
| `baoyu-cover-image` | 文章和视频封面 | E0 |
| `baoyu-infographic` | 信息图和高密度视觉 | E0 |
| `baoyu-xhs-images` | 小红书和社媒卡片 | E0 |
| `ian-xiaohei-illustrations` | 中文小黑手绘正文配图 | E1，风格型能力，不做通用默认 |
| `scientific-illustrator` | 可编辑 PPT/WPS/draw.io 科研和框架图 | E1，适合财经机制图和研报图重绘 |
| `animated-financial-display` | 金融数据动效 | E1，接无头和 VOSX 数据镜头 |

### 7.2 外部项目

| 项目 | GitHub 快照 | License | 判断 |
| --- | ---: | --- | --- |
| [ComfyUI](https://github.com/Comfy-Org/ComfyUI) | 129,005★，2026-08-22 | GPL-3.0 | E0 外部服务；节点图、API 和生态最完整 |
| [InvokeAI](https://github.com/invoke-ai/InvokeAI) | 27,927★，2026-08-20 | Apache-2.0 | E1，专业图片生产和人工编辑参考 |
| [Krita AI Diffusion](https://github.com/Acly/krita-ai-diffusion) | 10,490★，2026-08-22 | GPL-3.0 | E1，人工精修入口 |
| [Fooocus](https://github.com/lllyasviel/Fooocus) | 52,484★，2025-12-01 | GPL-3.0 | E2，易用但不适合做 Newma 统一编排底座 |
| [svg-creator-skill](https://github.com/upbrew-tech/svg-creator-skill) | 25★，2026-07-29 | Apache-2.0 | E1，小体量但适合可编辑 SVG 和动画素材 |

图片生成模型、插图风格和版式 Skill 必须分层：

- 模型/Provider 负责像素生成。
- `baoyu-article-illustrator` 和 Newma 导演负责决定哪里需要图、图承担什么论证任务。
- 风格 Skill 只负责视觉语言，不能替代事实图表。
- 图表、来源截图和统计图必须走证据链，不能用 AI 插图冒充。

## 8. 文案、研究和脚本生成

| 项目 / Skill | GitHub 快照 | License | Newma 价值 | 决策 |
| --- | ---: | --- | --- | --- |
| `content-intake-hub` | Boutique | 本地 Skill | Topic Intake 和来源身份 | E0 |
| `content-brief-builder` | Boutique | 本地 Skill | Brief、角度、证据需求 | E0 |
| `media-planner` | Boutique | 本地 Skill | 一鱼多吃和媒介派生 | E0 |
| [GPT Researcher](https://github.com/assafelovic/gpt-researcher) | 29,085★，2026-07-18 | Apache-2.0 | 深度研究、引用和多 Provider | E1，作为研究后端而非文风引擎 |
| [Local Deep Researcher](https://github.com/langchain-ai/local-deep-researcher) | 9,305★，2026-08-05 | MIT | 本地研究和报告 | E1 |
| [STORM](https://github.com/stanford-oval/storm) | 31,108★，2025-09-30 | MIT | 主题研究、知识整理、带引用长文 | E1，吸收研究和引用结构 |
| [InkOS](https://github.com/Narcooo/inkos) | 9,225★，2026-08-17 | AGPL-3.0 | 小说、剧本和 IP 内容创作 | E1，短剧编剧参考 |
| [NarratoAI](https://github.com/linyqh/NarratoAI) | 10,818★，2026-07-23 | MIT | 影视解说文案和自动剪辑 | E1，影视解说支线 |
| [LongWriter](https://github.com/THUDM/LongWriter) | 1,871★，2025-06-24 | Apache-2.0 | 超长文本生成方法 | E2，模型研究，不直接替换 Newma 写作链 |
| [avoid-ai-writing](https://github.com/conorbronsdon/avoid-ai-writing) | 3,190★，2026-08-22 | MIT | 检测和改写 AI 写作痕迹 | E1，先做中文回归 |
| `humanizer-zh` | Boutique/已安装 | 上游 Skill | 中文自然化 | E1，必须服从账号 DNA |
| [ai-script-generation-skill](https://github.com/FeiFei-AIDev/ai-script-generation-skill) | 48★，2026-06-25 | 未声明 | 5 种 30-45 秒短视频脚本角度 | E2，只借输出字段 |

文案能力不能脱离来源、证据和账号 DNA 独立运行。研究后端负责找证据，Brief 决定论点，Style/DNA 决定表达，导演 Skill 决定视频口语化和留存结构。

## 9. Boutique Skills 审计

### 9.1 立即保留和注册

- `video-shotcraft`
- `video-autopilot-kit`
- `remotion-best-practices` / `remotion`
- `seedance2-skill`
- `baoyu-image-gen`
- `baoyu-cover-image`
- `baoyu-comic`
- `baoyu-xhs-images`
- `content-intake-hub`
- `content-brief-builder`
- `media-planner`
- `dasheng-vox-skills`（历史兼容名，产品展示应统一为 Newma）
- `dasheng-video-talking-head`
- `dasheng-html-video-bridge`
- `dasheng-html-anything-bridge`

### 9.2 作为扩展能力

- `remotion-video-toolkit`
- `video-subtitles`
- `video-download`
- `animated-financial-display`
- `baoyu-article-illustrator`
- `scientific-illustrator`
- `dasheng-video-roughcut`
- `dasheng-video-style-trainer`

### 9.3 仅作参考

- `ian-xiaohei-illustrations`
- `animation-vocabulary`
- `animation`
- `reusable-footage-material`
- `remotion-video`

### 9.4 不应进入媒体超市主货架

| Skill | 原因 |
| --- | --- |
| `writing-skills` | 实际是编写 Agent Skill，不是文案生成 |
| `writing-plans` | 实际是代码实施计划，不是内容写作 |
| `video-agent` | HeyGen 旧接口包装，README 已标 deprecated |
| `remotion-video` | 本地实现硬编码旧个人路径，只能留作历史参考 |

`boutique-skills` 与 `boutique-openclaw-skills` 高度重复，不能双注册。建议以 `boutique-skills` 为主仓，只人工回灌少量较新的差异。

## 10. 社交平台发现与 GitHub 反查

社交平台只作为“发现线索”，正式判断仍以主仓 README、许可证和代码为准。

### B 站代表性线索

| 方向 | 视频 | 反查结果 |
| --- | --- | --- |
| 人工剪辑器 | [OpenCut 爆火出圈](https://www.bilibili.com/video/BV1Tj326uExX) | 对应 `OpenCut-app/OpenCut` |
| Agent 制片 | [OpenMontage 实测](https://www.bilibili.com/video/BV1ymgC6xE4X) | 对应 `calesthio/OpenMontage` |
| 一键短视频 | [MoneyPrinterTurbo](https://www.bilibili.com/video/BV1zM4m1R7Uq) | 对应 `harry0703/MoneyPrinterTurbo` |
| 长视频切片 | [AutoClip 教程](https://www.bilibili.com/video/BV1KFb6z2EwD) | 对应 `zhouxiaoka/autoclip` |
| 漫剧生产 | [DramaClaw 实测](https://www.bilibili.com/video/BV17iKK6eEd9) | 对应 `dramaclaw/dramaclaw` |
| 漫剧工作台 | [Toonflow 快速上手](https://www.bilibili.com/video/BV1oXD7BqEqJ) | 对应 `HBAI-Ltd/Toonflow-app` |
| 漫画/插图 Skill | [baoyu-skills 漫画化](https://www.bilibili.com/video/BV1qboHBwE2P) | 对应 `JimLiu/baoyu-skills` |
| 模型对比 | [MiniMax-H3 与 Wan2.2](https://www.bilibili.com/video/BV14pMR6xERz) | 对应两个模型主仓 |
| 综合横评 | [七个开源 AI 视频工具横向对比](https://www.bilibili.com/video/BV1QrjR6DEfd) | 用于发现，不作为技术结论 |

### 小红书代表性线索

| 方向 | 笔记 | 反查结果 |
| --- | --- | --- |
| OpenCut | [开源 CapCut 一周 6.5 万星](https://www.xiaohongshu.com/explore/6a57a6ef000000001702af3c) | 主仓 MIT，当前已约 8.5 万星 |
| OpenMontage | [ClaudeCode、Codex 集体转岗，组团剪视频](https://www.xiaohongshu.com/explore/6a3e52a3000000001503ca32) | 主仓 AGPL，适合借架构 |
| AutoClip | [开源项目：zhouxiaoka/autoclip](https://www.xiaohongshu.com/explore/6a6f50bc000000002500640b) | 主仓 MIT |
| DramaClaw | [DramaClaw 正式上线与开源](https://www.xiaohongshu.com/explore/6a451472000000000602056d) | 实际为 Elastic License 2.0，不是宽松许可 |
| baoyu / 漫画 Skill | [Codex 实现漫画自由](https://www.xiaohongshu.com/explore/6a4efbcb0000000007011335) | 对应 baoyu Skills 生态 |
| MiniMax-H3 | [MiniMax H3 开源了，但开了一半](https://www.xiaohongshu.com/explore/6a71febb0000000022031714) | 与主仓无标准 License 的核验一致 |

### X

本轮执行 `opencli twitter search` 时返回：`AUTH_REQUIRED / no ct0 cookie`。需用户在 Chrome 登录 X 后再补一轮一手帖子、作者和互动数据。

## 11. 吸收到 Newma 的目标架构

### 11.1 标准制片主链

```text
Brief / 原文章
  → Script Beats（核心观点、数据、证据、留存点）
  → Asset Registry（角色/场景/道具/品牌/事实素材）
  → Keyframe / Proof Frame 低成本预审
  → Shot Plan + Take 生产
  → Edit Proposal
  → OTIO Canonical Timeline
  → Generation QC + Editorial QC
  → 人工审核
  → Render / Publish / Style Skill 回写
```

关键变化是：生成视频不再从脚本直接跳到模型；剪辑 Agent 也不再直接覆盖时间线。

### 11.2 核心数据对象

| 对象 | 必要内容 | 主要来源 |
| --- | --- | --- |
| `ProjectManifest` | 项目、流水线、阶段、预算、目标平台、当前版本 | Newma |
| `ScriptBeat` | 台词、观点、证据、预计时长、留存功能、画面意图 | video-spec-builder、shuohao |
| `AssetPassport` | 身份、参考/反参考、服装/状态变体、连续性规则、锁定状态 | film-studio-skills、BigBanana |
| `KeyframeReview` | 首帧/尾帧/九宫格、视觉一致性、人工批注、是否准许动画化 | BigBanana、30x-video |
| `ShotPlan` | 镜号、精确帧、global prompt、shot prompt、镜头运动、声音 | ShotPlan、DramaDirector、video-shotcraft |
| `Take` | 输入、Provider、模型、参数、seed、成本、输出、父版本、裁决 | Inline-Studio、ViMax |
| `EditProposal` | 操作列表、理由、影响范围、预览、校验结果、提交/撤销状态 | OpenStoryline、OpenChatCut |
| `Timeline` | clip、caption、overlay、transition、audio、evidence、lock | OTIO、OpenCut |
| `RunPlan` | dry-run、依赖、预计耗时、成本上限、替代路线、恢复点 | vibeframe |
| `QCReport` | 自动指标、问题镜头、证据、修复建议、人工结论 | VBench、ViStoryBench、Evaluation-Agent |
| `StyleSkill` | 节奏、字幕、花字、转场、B-roll、音效及适用条件 | OpenStoryline + Newma 人工裁决 |
| `Event` | 谁在何时对哪个对象做了什么、前后版本和结果 | Newma Event Store |

这些对象应成为 Desk、Agent 对话和 CLI 共用的合同。前端不另建一套状态，Agent 也不能只写 Markdown 而不回写对象。

### 11.3 多 Agent 的职责边界

| Agent | 必须交付 |
| --- | --- |
| 编剧 | `ScriptBeat[]`，同时标明核心观点、数据、证据和口语化台词 |
| 导演 | `ShotPlan[]`、视觉节奏、互动点、留存设计和镜头取舍 |
| 资产导演 | `AssetPassport[]`、参考板、反参考、状态变体和锁定结果 |
| 摄影/提示词 Agent | global/shot 分层提示、镜头、景别、光线、首尾帧 |
| 制片 | `RunPlan`、Provider 路由、预算、依赖、并发和恢复点 |
| 剪辑 Agent | `EditProposal`，不得越过校验直接覆盖母版 |
| 审片 Agent | `QCReport`、问题定位、修复建议；最终放行权仍归人工 |

### 11.4 六条流水线如何吸收

| 流水线 | 本轮新增能力 |
| --- | --- |
| 真人出镜口播 | OpenStoryline/FunClip 粗剪提案；人工共用时间线；口水词裁剪、字幕、花字、B-roll 和音频处理沉淀为 Style Skill |
| VOSX | 原文观点和数据先转 `ScriptBeat`；事实图片进入证据资产；拼贴镜头先做 keyframe；字幕、实体标签和重点花字进入强制 QC |
| 无头口播 | Pixelle 式素材规划；每个 beat 绑定旁白、论据、画面和来源；html-video/Remotion 只负责确定性渲染 |
| AI 数字人 | 人物 Asset Passport；多角度/光线/双人同框压力测试；嘴部、眼部、身份和声画同步单独评分 |
| 电影短剧 | 世界观、角色、衣橱、场景、道具资产库；多 Agent 制片；首尾帧预审；镜头级重试和连续性门禁 |
| 广告宣传片 | 官网品牌资产优先；五幕叙事、Taste Codex、证据门、proof frame 和品牌合规检查 |

### 11.5 `generation_qc` 应注册的质量门

| 类别 | 指标 |
| --- | --- |
| 生成质量 | 主体一致性、背景一致性、闪烁、运动平滑、动态程度、美学、清晰度 |
| 叙事连续性 | 剧情对应、角色一致性、视觉风格、镜头视角、出场人物和动作对齐 |
| 剪辑质量 | 跳切、黑帧、坏帧、音画错位、节奏异常、转场污染、镜头重复 |
| 内容完整性 | 文章核心观点、关键数据、论据、结论是否被脚本和镜头覆盖 |
| 字幕与包装 | 字幕字级对齐、断句、重点花字、人物/机构标签、图表小字说明 |
| 证据相关性 | 新闻图、官网通知、数据图表是否真正支撑当前台词，是否记录来源 |
| 音频 | 响度、峰值、底噪、爆音、静音段、说话人切换和配乐遮挡 |

VBench 提供通用视频指标，ViStoryBench 负责长叙事连续性；Newma 还必须补内容、字幕、证据和金融数据镜头的领域检查。

### 11.6 超市注册必须补齐的信息

每个 Skill、仓库和模板卡片至少展示：

- 它解决什么问题，以及不解决什么问题。
- 已注册、已安装、可运行、缺依赖、实验中或已停用状态。
- 适用流水线和节点；输入、输出及可接收的上游 Artifact。
- 一张真实界面/样片示意图和一个最小演示任务。
- 运行方式、CLI/MCP/API、本地硬件、Provider 和预计成本。
- 当前 E 级、PoC 结果、已知问题及生产准入状态。

## 12. 实验 PoC 顺序

### PoC-01：共享时间线和可撤销编辑

- OTIO 作为 canonical timeline。
- OpenStoryline/FunClip 只生成 `EditProposal`。
- Desk 展示差异，人工提交后同步 OpenCut，并验证 Undo 和事件回写。

验收：Agent 对话、前端拖动和 CLI 修改看到的是同一个版本，不发生时间线分叉。

### PoC-02：资产护照和关键帧预审

- 为角色、场景、道具和品牌建立 `AssetPassport`。
- 用九宫格、多角度、不同光线和双人同框做压力测试。
- Keyframe 通过后才允许生成视频 take。

验收：角色和关键资产在跨镜头时能被识别、锁定、复用和追责。

### PoC-03：可恢复生成与成本闸门

- 生成前输出 dry-run 和硬成本上限。
- 每个 shot/beat 保存 checkpoint、take 和父版本。
- 单镜失败只重跑本镜，自动生成机器可读修复建议。

验收：中断后可续跑；替换一个镜头不重做整片；能看见实际和预计成本差异。

### PoC-04：自动 QC

- 接入 VBench、ViStoryBench 指标子集。
- 增加字幕、实体标签、重点花字、证据相关性和音频门禁。
- QC 报告必须定位到镜头/时间码，并能创建重试任务。

验收：对历史三个问题视频能稳定找出已知缺陷，而不只是给出笼统评分。

### PoC-05：Style Skill 闭环

- 记录人工对剪辑、字幕、花字、B-roll、转场和声音的修改。
- 将稳定模式归档为带适用条件的 Style Skill。
- 新项目先生成提案，审核后再提高自动应用比例。

验收：同一账号第二条视频的人工修改量明显下降，且能逐条解释 Style Skill 的命中依据。

## 13. 生产准入元数据

本节只在 PoC 通过、准备进入正式产品时使用，不影响 E0/E1/E2 排序。

| 类型 | 项目示例 | 生产阶段处理方式 |
| --- | --- | --- |
| MIT / Apache-2.0 | OpenCut、FunClip、OTIO、video-shotcraft、drama-skills | 代码审查、NOTICE、依赖和安全检查后适配 |
| AGPL-3.0 | OpenMontage、OpenChatCut、InkOS | 评估隔离运行、进程边界和源码开放义务 |
| Elastic License 2.0 | DramaClaw | 单独评估托管、商业替代和分发限制 |
| CC BY-NC-SA | WaooWaoo | 单独评估非商业和衍生作品限制 |
| 未声明许可证 | MiniMax-H3、Huobao、printfilm、部分 Skills | 在正式复制、修改或分发前取得明确授权 |
| 自定义社区许可 | HunyuanVideo、LTX-2 | 按地域、规模、分发、模型和输出用途核验 |
| Remotion License | Remotion | 按组织规模和产品形态核验公司许可 |

## 14. 本轮储备审核清单

建议立即批准 E0：

- [ ] OTIO + `EditProposal` + Undo 作为统一剪辑协议
- [ ] OpenStoryline 的意图编辑、Style Skill 和 Agent Memory PoC
- [ ] OpenCut/OpenChatCut 的 Agent 与人工共享时间线设计 PoC
- [ ] BigBanana 的 Script → Asset → Keyframe 预制片主链
- [ ] film-studio-skills 的 Asset Passport、反参考和压力测试
- [ ] shuohao 的确定性时长、镜头门和提示词对账
- [ ] ViMax 的编剧/导演/制片/生成多 Agent 交付协议
- [ ] vibeframe 的 dry-run、成本上限、局部恢复和修复报告
- [ ] ComfyUI-Copilot 的工作流生成与调试能力
- [ ] VBench + ViStoryBench + Newma 领域 QC

建议批准 E1 方法吸收：

- [ ] Pixelle 的素材规划和逐帧生产任务树
- [ ] Inline-Studio 的版本化 take、连续性评分和项目导入导出
- [ ] 30x-video 的广告 Taste Codex、证据门和 proof frame
- [ ] ShotPlan/DramaDirector 的精确帧和分层 shot schema
- [ ] OpenMontage、DramaClaw、WaooWaoo、Huobao 的完整功能面拆解
- [ ] AutoClip/claude-shorts 的母版完成后长转短节点
- [ ] `jianshuo/claude-skills` 的多机位和本地化子能力

暂不作为主线：

- [ ] 不再继续堆叠“一句话生成整片”的同类壳项目
- [ ] 不把任何单一生成模型写死到导演或流水线 Schema
- [ ] 不让外部 NLE、ComfyUI 或 Agent 平台成为唯一项目真相源
- [ ] 电影研究 Agent 和 MCTS 动画导演先留在 E2，不阻塞当前五个 PoC

## 15. 与现有文档的关系

- 历史全量索引：[video-self-media-skills-github-index.md](video-self-media-skills-github-index.md)
- 当前六条视频流水线：[video-production-lines.md](video-production-lines.md)
- 流水线治理：[video-pipeline-governance.md](video-pipeline-governance.md)
- 既有 Boutique 复核：[boutique-skills-video-media-reserve-review-20260802.md](boutique-skills-video-media-reserve-review-20260802.md)

本文件是 2026-08-23 的实验研究优先级和增量技术储备审核，不替代历史索引。正式接入时仍需另做生产准入、安全、性能和维护性审核。
