# Newma-Dock Domain Context

## Mod Suite

由同一个导入项目提供的一组相关 Mod 页面。Mod Suite 只声明一次项目身份、运行环境、一级分类、二级目录和共享能力；Suite Discovery 会把页面展开为独立 Mod，使现有权限、数据路由、Agent Context 与运行时隔离继续按页面生效。

## Navigation Descriptor

导入项目提供给 Newma-Dock 的导航声明。它描述 Mod Suite 的一级分类、二级目录、页面顺序、标签、图标和设置入口，不包含用户的拖拽、冻结、隐藏等个人偏好。

## Suite Discovery

读取 Navigation Descriptor 并生成独立 Mod Manifest 的 Module。Git / 本地文件与 `.well-known/newma-dock-suite.json` HTTP 声明是该 Seam 上的不同 Adapter；旧 `.well-known/vibedesk-suite.json` 在兼容期作为回退入口。生成后的 Manifest 继续进入既有 Mod Registry。

## Navigation Compiler

把已发布 Mod Manifest、Suite 默认导航和 Preference Overlay 编译成 Desk 唯一导航树的 Module。一级侧边栏、二级侧边栏、项目设置和当前路由都应读取同一份编译结果。

## Preference Overlay

只记录用户相对默认导航所做的变化，包括排序、冻结、移动和重命名。新页面自动继承 Mod Suite 默认值；已删除页面和空目录的失效偏好由 Navigation Compiler 清理。

## External Mod Runtime

在 Newma-Dock 仓库之外运行、但由 Desk 注册、检查或在本地开发时启动的 Mod 运行环境。External Mod Runtime 可以包含一个或多个工作区、进程和 HTTP 入口；不可用时必须独立降级，不能影响 Desk 核心运行时。

## Runtime Descriptor

External Mod Runtime 的统一声明文件。它描述稳定 ID、工作区发现候选、环境变量、HTTP 入口和健康路径，不包含用户账号、密钥或个人绝对路径。Node 启动器与 Python Agent Gateway 分别通过自己的 Adapter 读取同一个 Runtime Descriptor。

## Runtime Certification

在真实 Desk 与 Mod 运行环境中执行的兼容验收。Manifest 中的等级只是声明；只有 health、embed、Bridge、响应式布局以及等级要求的 Agent Context 检查全部通过，才能获得对应认证等级。
