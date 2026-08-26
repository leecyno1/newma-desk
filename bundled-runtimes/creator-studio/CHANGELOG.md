# Changelog

重要变更遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/) 与语义化版本。

## [Unreleased]

### 变更

- 项目品牌由 Dasheng Media Workflow Skills 更名为 Newma Media Studio。
- 公开仓库、安装目录与导出包统一使用 `newma-media-studio`。
- 保留 `dasheng-*` Skill ID、`DASHENG_*` 环境变量与 `dasheng.*` schema，避免破坏现有调用。

## [3.0.0] - 2026-08-03

### 新增

- 六阶段工作流与九个功能模块的机器注册表。
- 42 个保留上游项目、4 个候选储备和 13 个剔除项的完整目录。
- 储备项目检查、克隆和安全快进更新脚本。
- 上游兼容补丁注册表与自动检查/应用脚本。
- 视频导演、真实 B-roll、HTML/Remotion 动画、渲染 QC 和视频自学习模块。
- 千帆本地 API、异步队列和 Social Auto Upload CLI 三条发布路线。
- 多账号发布窗口策略、表单校验、发布验真和账号矩阵。

### 变更

- 将公开仓库整理为“自研代码 + 注册表 + 补丁”的可复现结构，不再提交第三方源码和运行态。
- 更新 README、安装、上手、贡献和安全文档。
- 统一个人路径为环境变量或仓库相对路径。

### 安全

- 本地密钥、Cookie、浏览器 Profile、抓取快照、视频产物和导出镜像移出 Git 跟踪范围。
- 增加公开发布卫生检查，并要求轮换任何曾进入公开历史的凭证。

完整历史见 [docs/CHANGELOG.md](docs/CHANGELOG.md)。

[3.0.0]: https://github.com/leecyno1/newma-media-studio/releases/tag/v3.0.0
