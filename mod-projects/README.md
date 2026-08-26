# Local Mod overrides

该目录只用于开发者临时覆盖仓内运行时，并保留外部项目自己的 Git 历史。

公开仓库和干净 clone 所需的完整源码位于 `bundled-runtimes/`。统一启动器优先使用仓内快照；只有显式设置 `NEWMA_DESK_*_WORKSPACE` 时才使用这里或其他外部目录。

此目录中的项目不是 Newma-Desk 正常启动依赖。
