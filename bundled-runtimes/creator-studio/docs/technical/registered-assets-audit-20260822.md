# 注册资产对齐审计报告（video-self-media-skills-github-index 基准）

审计日期：2026-08-22
基准文档：`docs/technical/video-self-media-skills-github-index.md`（556 行，期望 ~100+ 项）
当前实际：本地 skills 45 个 + Qoder 宿主 84 个 + vendor/reserved 17 个 + configs 49 个

## 一、对齐摘要

index 期望与当前实际的差异本质：index 是**历史全集**（含 16 个旧名入口+40+ 外部参考项），当前是**在役资产**（45 本地 + 17 vendor）。主要问题：**8 项需处理**（4 删/2 冲突/2 重复合并），**37 项健康保留**。

## 二、删除建议（4 项）

| 项 | 功能 | 问题 | 处理 |
| --- | --- | --- | --- |
| **dasheng-daily-clustering** | 旧聚类/入库入口 | index 明确被 dasheng-daily-intake 替代；SKILL.md 内容为 legacy 壳 | **删除**（intake 已是主入口，无调用方） |
| **dasheng-daily-outline** | 旧大纲入口 | index 明确被 dasheng-daily-draft 替代；legacy 壳 | **删除** |
| **dasheng-daily-shared** | 旧共享依赖（无 SKILL.md） | index 明确「不单独路由」；空目录 | **删除**（依赖已被各 skill 内化） |
| **dasheng-media-rewrite-v2** | 旧 EnhancedPromptBuilder/QualityScorer 引擎（无 SKILL.md） | v3 已完整替代 | **降级为 archive**（代码移 docs/archive 或注明 v3 唯一路由——参考实现保留） |

## 三、冲突建议（2 项）

| 项 | index 声明 | 当前实际 | 处理 |
| --- | --- | --- | --- |
| **dasheng-stage-brief-ai** | 「已并入 dasheng-daily-phase2」 | 独立存在，有完整 AI 选题生成功能 | **冲突——功能重叠**。建议：查 phase2 是否调它（调用→降为底层模块；不调用→功能并入 phase2 删独立项）。**需验证** |
| **dasheng-stage-draft** | 「已并入 dasheng-daily-draft」 | 独立存在，Stage 3 初稿基线生成 | **冲突——两入口**。建议：daily-draft 为主路由（已在用），stage-draft 若被 daily-draft 调用则降为底层执行器，否则并入。**需验证调用关系** |

## 四、重复建议（2 项）

| 项 A | 项 B | 问题 | 处理 |
| --- | --- | --- | --- |
| **dasheng-video-vox**（导演叙事：中心问题/证据地图/反证） | **dasheng-vox-skills**（VOX 编排合成：Shotcraft/Gemini/Remotion） | 两个 VOX 入口，叙事层 vs 合成层界限易混 | **保留但明确分工**：vox=导演/叙事层，vox-skills=合成/执行层；registry 描述互注「调用关系」 |
| **dasheng-video-omni-browser**（VOX 逐镜 10s 底片+下载回项目） | **dasheng-omni-video-bridge**（新 omni 引擎插件包：批处理+提示词适配+下载） | **严重重复——两个 omni 入口** | **合并**：omni-video-bridge 为唯一引擎入口（新、结构化、与 html-anything 平行）；video-omni-browser 的「VOX 逐镜下载」逻辑并入 bridge 的 run_omni_batch；browser 项降级为 bridge 的别名或删除 |

## 五、保留建议（37 项——健康主链）

**生产主链（10）**：dasheng-media-sop（总控编排）/ paradigm-profiler（范式学习）/ daily-intake（采集）/ hotspot-radar（热点雷达）/ daily-phase2（Brief 选题）/ daily-draft（初稿）/ daily-postmortem（复盘）/ finance-data（金融数据）/ style-profiler（文风 DNA）/ stage-rewrite-v3（改写）

**文章配图（4）**：lemon-illustrations（柠檬人插图）/ account-illustrations（账号角色插图，新）/ baoyu-diagram+drafter-diagram+image-enhancer+content-research-writer+market-research-reports（宿主注册 5 个——保留）

**视频执行（17）**：video-director（导演）/ talking-head（真人口播）/ roughcut（粗剪）/ explainer-html（无头科普）/ video-vox（叙事）/ vox-skills（合成）/ video-omni-browser（并入 bridge 后删除——见重复）/ broll-generator / caption-motion / editing-bridge / ffmpeg-toolkit / digital-human-talking-head / commercial-promo-video / video-style-trainer / video-self-learning / html-video-bridge / html-anything-bridge / omni-video-bridge

**发布桥（5）**：publish-operations-bridge / xhs-publish-bridge / social-auto-upload-bridge / bilibili-upload-bridge / feishu-doc-creator / jiebang（6 含飞书+交棒）

## 六、vendor/reserved 审计（17 项）

| 域 | 项 | 状态 | 建议 |
| --- | --- | --- | --- |
| design/ | baoyu-skills | 主链（文章视觉） | **保留** |
| design/ | guizang-social-card-skill | 社交卡片辅助 | **保留** |
| design/ | anthropics / emilkowalski / gsap-skills | 视觉/动效参考库 | **保留**（参考资产，无调用路由但供导演/审查参考） |
| render/ | html-anything / html-video | 主链渲染 | **保留** |
| video/ | claude-real-video | 视频读取/风格训练入口 | **保留** |
| video/ | auto-editor / chengfeng-videocut / claude-code-video-toolkit / claude-shorts | 实验/参考状态，无实际调用 | **降级 archive**（保留为参考，明确「非生产路由」——或评估后删除 2-3 个） |
| publish/ | agent-skills-launch-pack / all-in-one / autoclaw-xhs-skills / biliup-rs / opencli | 发布桥上游 | **保留** |
| catalog/ | boutique-openclaw-skills | 目录源 | **保留** |
| audio/ | voicebox | 音频 | **保留** |

## 七、Qoder 宿主 84 个 skills 的处理

**不属于项目资产**（宿主提供）——只处理项目注册关系：

- **已注册 5 个**（baoyu-diagram/drafter-diagram/content-research-writer/image-enhancer/market-research-reports）——**全部保留**（有环节调用方）
- **候选 8 个**：a-stock-data/yfinance/tushare-openclaw（数据——finance-data 已覆盖 A 股，但 a-stock-data 有研报/信号扩展——**保留候选**）；media-downloader/gemini-image-service/agent-browser/theme-factory/analytics-data-analysis/cloudflare-deploy——**备案**（有场景再晋升）

## 八、执行清单（清理动作）

```bash
# 删除（4 项——旧兼容壳，验证无调用后执行）
rm -rf skills/dasheng-daily-clustering skills/dasheng-daily-outline skills/dasheng-daily-shared

# 降级 archive（media-rewrite-v2——代码保留为参考，不再路由）
mv skills/dasheng-media-rewrite-v2 docs/archive/skills-rewrite-v2/

# 冲突验证（stage-brief-ai / stage-draft——查 phase2/daily-draft 调用关系后定）

# 重复合并（omni-browser → omni-video-bridge——把下载逻辑并入 bridge 后删独立项）
```

## 九、维护建议（对齐 index §9）

1. 新增能力用 newma-* 命名（旧 dasheng-* 只做兼容别名——本审计已清理大部分旧壳）
2. 每个 vendor 项记录：URL/许可证/核验时间/用途/调用方/状态——index 已建索引，vendor 实际安装状态需标注（当前多数未在本机安装，按需 ensure_video_external_deps）
3. Skills/仓库/CLI/Provider 分开登记（omni=引擎/mmx=CLI/Gemini=provider——不混类）
4. 文章与视频共用同一份 Draft/Claim/Evidence（chart_data.json 已统一数据侧；claim_evidence_ledger 已统一证据侧）
