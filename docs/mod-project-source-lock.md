# Mod Runtime Source Snapshot

日期：2026-08-26

当前可见 Mod 的运行源码已经复制到 `bundled-runtimes/` 并由主仓直接追踪。干净 clone 不再依赖 `mod-projects/`、同级项目目录或桌面目录。

- 来源、基准提交和许可证：`config/bundled-runtime-sources.json`
- 完整性检查：`npm run mods:sources:check`
- 统一依赖安装：`npm run runtime:bootstrap`
- 统一启动：`npm run dev:stack`

Node 项目保留各自锁文件；Python 项目保留 `pyproject.toml`、`uv.lock`、`requirements.txt` 或约束文件。依赖安装目录、虚拟环境、数据库、密钥、缓存和用户运行数据不进入 Git。

`config/mod-project-source-lock.json` 仅保留为旧嵌套仓库的历史记录，不再参与公开仓库的启动和发布判断。
