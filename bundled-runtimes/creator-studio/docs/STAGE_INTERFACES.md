# Newma 主链阶段接口

这是公开文档入口。当前唯一正式阶段契约以仓库内主文档为准：

- `引擎/03_全链路SOP工作流/STAGE_INTERFACES.md`

正式主链：

`intake -> brief -> draft -> transwrite -> publish -> postmortem`

核心边界：

- Draft：事实、数据、图表、配图、比喻/举例漫画意图、自包含 HTML。
- Transwrite 无真人方形视频：遵循 `docs/technical/no-human-square-video-production-standard.md`，以真实音频驱动 live HTML Video + Remotion 分层总合成。
- Transwrite：公众号 DNA/humanize/封面/段后柠檬漫画、口播视频柠檬漫画分镜、播客 API 请求包。
- Publish：验收、打包、推草稿/人工发布包、链接回收。
- 可选资产：`paradigm-learning` 学文章范式；`video-style-training` 学样板视频剪辑风格，默认输出到 `~/Desktop/自媒体创作/00_范式学习/视频训练/`，不写入项目根目录。

已删除独立 Material 阶段；Rewrite 只作为 Transwrite 按需工具，不再是主链 gate。

主链总账本：

- 正式运行推荐通过 `scripts/run_mainline_stage.py`，它会在阶段成功后回写 `~/Desktop/自媒体创作/<run_id>/project_run_manifest.json`。
- 可用 `--project-manifest <path>` 指定账本路径。
- 调试时可用 `--no-project-manifest` 跳过回写。
- 总账本 schema 位于 `configs/workflow/project_run_manifest.schema.json`。
