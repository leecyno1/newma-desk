# Newma Media Studio Export v2 (2026-04-01)

## 版本命名规范

- 导出目录：`newma-media-studio-YYYYMMDD-vX`
- 压缩包：`newma-media-studio-YYYYMMDD-vX.tar.gz`
- 当天多次导出按 `v1/v2/v3` 递增，禁止覆盖历史版本

## 包含技能

- `dasheng-media-sop`
- `dasheng-paradigm-profiler`
- `dasheng-stage-publish`
- `dasheng-daily-intake`
- `dasheng-daily-phase2`
- `dasheng-daily-material`
- `dasheng-daily-postmortem`
- `dasheng-style-profiler`
- `feishu-doc-creator`

## 默认工作区

- 主工作区：`${DASHENG_PROJECT_ROOT}`
- 动画图表工程：`${PROJECTS_ROOT}/finance-motion-8787`
- 可通过环境变量覆盖：
  - `DASHENG_WORKSPACE`
  - `FINANCE_MOTION_WORKSPACE`
  - `DASHENG_OUTPUT_ROOT`
  - `DASHENG_FEISHU_ROOT_URL`
  - `DASHENG_FEISHU_CHAT_ID`

## 环境模板

- 模板文件：`ENV_TEMPLATE.env`
- 建议复制为本地私有文件（例如 `~/.openclaw/dasheng.env`）并按实际值填写
- 运行前加载：
  - `set -a; source ~/.openclaw/dasheng.env; set +a`

## 每日首跑自检

- 自检提示词文件：`SMOKE_PROMPTS.md`
- 建议每天第一次运行前先执行其中“全链路最小自检”

## 导入方式（龙虾/OpenClaw）

1. 复制 `skills/*` 到你的 skill 目录（例如 `~/.openclaw/skills`）。
2. 如工作区路径不同，修改每个 `SKILL.md` 中的默认路径或设置环境变量。
3. 用 `ENV_TEMPLATE.env` 生成你的本地环境文件并加载。
4. 验证入口技能：
   - `dasheng-media-sop`

## 当前口径

- 主链：`intake -> brief -> draft -> material -> rewrite -> publish -> postmortem`
- `publish` 阶段已包含：
  - 互动图表视频（CSV -> finance-motion-8787 -> webm/mp4）
  - motion 叙事视频（改写稿 -> 场景 -> webm/mp4）
