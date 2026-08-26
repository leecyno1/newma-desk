# 自媒体创作工作台（SOP 版）

当前仓库已收敛为一条唯一主链：

`intake -> brief -> draft -> material -> rewrite -> publish -> postmortem`

对象真相统一为：

`Run -> TopicPool -> SelectedTopic -> Draft -> FinalDoc -> MaterialPack -> RewritePack -> PublishPack -> Postmortem`

文档是交付视图；manifest、gate 文件和对象 JSON 才是正式状态源。

## 目录结构

- `素材/`
  - `来源文章/`：公众号、笔记、新闻等原始链接与抓取文本
  - `研究数据/`：TuShare、表格、统计口径、证据底稿
  - `图表/`：图像、封面、正文插图、数据图
- `项目/`
  - `进行中/`：按单个选题管理的工作目录
  - `已完成/`：已发布或已归档项目
  - `模板/`：项目模板、阶段字段、复盘结构
- `引擎/`
  - `00_控制中心/`：控制文件与模板统一入口
  - `01_调性分析引擎/`：调性入库、风格知识库、风格迭代
  - `02_三版写作引擎/`：A/B/C 三版正文生成
  - `03_全链路SOP工作流/`：7 阶段总控、对象映射、渠道分发模板
- `skills/`
  - `dasheng-daily-*`：当前项目保留的执行层能力
- `openclaw-skill-exports/`
  - 技能导出快照；真正运行时使用根目录 `skills/`

## 当前执行的 7 段 SOP

1. **内容采集**
   - 执行器：`skills/dasheng-daily-intake`
   - 产物：`intake_records`、`entity_rankings.json`、`event_clusters.json`、`source_quality_report.json`
   - Gate：`intake_review.json`
2. **内容聚合及选题分析（Brief）**
   - 执行器：`skills/dasheng-daily-phase2`
   - 产物：`TopicCard`、编辑 Brief、研究 Brief、`selected_topics.json`
   - Gate：`selected_topics.json`
3. **初稿生成**
   - 执行入口：`scripts/build_stage3_draft.py`
   - 产物：`Reasoning Sheet` + `03_标准初稿_<topic>.md`
   - Gate：`final_structure_snapshot.json`
4. **转写生产**
   - 执行入口：`scripts/build_stage4_transwrite.py`
   - 产物：公众号文章、口播视频、播客生产包，`transwrite_manifest.json`
   - Gate：`transwrite_decision.json`
5. **发布执行**
   - 执行入口：`scripts/build_stage5_publish.py`
   - 产物：发布包、执行清单、链接回收与验真报告
   - Gate：`publish_decision.json`
6. **分析复盘**
   - 执行器：`skills/dasheng-daily-postmortem`
   - 产物：复盘报告与 Pattern Library 回写

## 桌面交付

- 对外审阅、每日协作和正式内容沉淀，统一使用：`${HOME}/Desktop/自媒体创作/`
- `intake / brief / draft / transwrite / publish / postmortem` 的报告、底稿、清单与素材，按阶段目录落盘
- 视频、音频、字幕、审核页、图片、HTML 文章、训练缓存全部放在桌面创作目录
- 仓库只放代码、配置、SOP、skills 与测试；不再把 `产物/` 作为正式沉淀层
- 当前自动导出由各阶段脚本内置完成，批量脚本 `scripts/export_daily_delivery.py` 仅保留为兼容工具

## 飞书协作执行入口

- 统一配置：`${LEGACY_OPENCLAW_ROOT}/configs/feishu_api.conf`
- 阶段契约：`${DASHENG_PROJECT_ROOT}/configs/feishu/stage_review_contract.json`
- 直接执行 live 同步：
  - `node ${DASHENG_PROJECT_ROOT}/skills/dasheng-daily-shared/runtime/feishu-live.js <run_id>`
- 直接执行 live 断点续跑：
  - `node ${DASHENG_PROJECT_ROOT}/skills/dasheng-daily-shared/runtime/feishu-live.js <run_id> --resume-only`
- 直接执行 live 强制重跑：
  - `node ${DASHENG_PROJECT_ROOT}/skills/dasheng-daily-shared/runtime/feishu-live.js <run_id> --fresh`
- 推荐包装入口：
  - `python3 ${DASHENG_PROJECT_ROOT}/scripts/feishu_stage_sync.py --latest`
  - `python3 ${DASHENG_PROJECT_ROOT}/scripts/feishu_stage_sync.py <run_id>`
  - `python3 ${DASHENG_PROJECT_ROOT}/scripts/feishu_stage_sync.py --resume-only <run_id>`
  - `python3 ${DASHENG_PROJECT_ROOT}/scripts/feishu_stage_sync.py --fresh <run_id>`
- 包装入口会把摘要写回：
  - `skills/dasheng-daily-shared/runtime-data/runs/<run_id>/bridge/feishu-sync-summary.json`
  - `skills/dasheng-daily-shared/runtime-data/runs/<run_id>/bridge/feishu-sync-summary.md`
- live 执行进度会写到：
  - `skills/dasheng-daily-shared/runtime-data/runs/<run_id>/bridge/live-execution-progress.json`

### 飞书同步开关说明

- 常规执行：直接运行 `<run_id>` 或 `--latest`，适合首次同步。
- `--resume-only`：用于飞书同步中断、超时、手动终止后的断点续跑；会读取 `live-execution-progress.json`，跳过已完成 action，只继续未完成部分。
- `--fresh`：用于放弃旧进度、从头重建本次 run 的飞书文档和同步状态；会清理本次 run 的 live 进度与包装摘要后重跑。
- `--fresh` 和 `--resume-only` 不能同时使用。
- 编辑团队默认规则：**先试 `--resume-only`，只有确认旧进度不可用时才用 `--fresh`**。

## 固定使用方式

1. 从控制中心进入：`引擎/00_控制中心/00_控制文件导航.md`
2. 按唯一主链推进：每阶段必须同时产出 manifest 与 gate 文件
3. 飞书只负责协作显示；选题、终稿结构、素材接受、发布决定必须回写 gate 文件
4. 调性回写：阶段 7 完成后，将有效模式回写 `引擎/01_调性分析引擎/STYLE_KNOWLEDGE_BASE.md`
5. 主链统一命令：`python3 scripts/run_mainline_stage.py <stage> --run-id <run_id>`
6. 每次开始前先跑自检：`python3 scripts/workflow_doctor.py --latest`

## 合并原则

- 不再并存多套阶段定义；主链与阶段顺序以 `STAGE_INTERFACES.md` 为准
- `skills/` 是执行层，`引擎/` 是方法层，`~/Desktop/自媒体创作/` 是正式内容沉淀层
- `openclaw-skill-exports/` 仅保留为快照来源，不作为运行真相
- `intake/brief/draft/material` 解决“值不值得写、能不能证明、素材够不够”
- `rewrite/publish` 解决“怎么发、发到哪、如何适配渠道”
- `postmortem` 负责把经验沉淀成下一轮可复用能力

## 兼容说明

- 历史目录 `data/` 与 `figures/` 继续保留，不破坏旧脚本
- 历史 `产物/` 目录只作为迁移兼容，不再写入新内容
- `03_选题生成_prompt.md` 保留但不再作为独立阶段
- `dasheng-daily-clustering`、`dasheng-daily-outline`、`dasheng-daily-brief`、`dasheng-daily-draft`、`dasheng-daily-final` 均已降级为迁移提示入口
