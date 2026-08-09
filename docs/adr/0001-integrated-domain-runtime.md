# ADR-0001: Integrated Domain Runtime 使用分层 Docker 交付

- 状态：Accepted
- 日期：2026-07-29

## 背景

Newma-Desk 需要批量部署到规格不同的云服务器。原先每个 Mod 自带开发服务器、`node_modules`、Python 虚拟环境、模型设置和 Agent 进程，导致重复依赖、端口冲突、常驻内存增长以及难以复现的系统环境。

Research 与 Trading 已经是第一方 Mod Suite。它们需要保留领域能力，但不应继续携带与 Desk 重复的 Agent、模型、频道、调度和前端开发运行时。

## 决策

1. Docker Compose 是标准云端部署入口；宿主机直接安装仅用于开发和故障诊断。
2. 核心交付拆成小型运行镜像：
   - Desk 与 Market 使用 nginx 提供静态产物。
   - API 使用单一 Python 运行环境承载 Desk、Research 与 Trading 的 Integrated Domain Runtime。
   - Node、Git、编译器和前端依赖只存在于构建阶段。
3. Research / Trading 的领域能力通过小型 Interface 挂载到 Desk。生产运行时不得加载嵌套 `.venv`；本地兼容模式必须显式开启。
4. 上游自带 Agent、模型配置、频道、上传、调度和重复后台任务不进入集成模式。所有模型和会话选择均由 Desk Agent Interface 提供。
5. Deepsee、Seven Cycle、InStock 与 Orchestra 等重型或异构 Mod 作为独立 Adapter，通过 Compose profile 按需启动；它们失败时不得拖垮核心运行时。
6. 体积、最大前端文件、Docker build context 和集成依赖黑名单由 `config/production-footprint.json` 持续校验。

## 结果

- 核心 Module 的 Interface 更小，部署行为集中，具有更高 locality。
- Desk、Research 与 Trading 共用依赖可减少重复内存和磁盘，但要求统一约束版本；真正冲突的可选 Mod 必须留在独立容器 Adapter 中。
- 生产镜像不再包含开发工具链，调试需使用 `ops` profile 或独立开发环境。
- 被忽略的上游源码仍需 source lock；在 dirty 工作树完成归属前，不能声称可从干净 clone 回放完整 overlay。

## 否决方案

- 单一巨型镜像：Interface 看似简单，但把全部可选依赖和失败模式混入一个 Implementation，常驻成本过高。
- 每个页面一个服务：产生大量浅 Module、重复环境和端口，删除后复杂度只会散落到部署脚本中。
- 宿主机全局安装：无法为不同 Adapter 隔离版本，批量服务器之间难以保持一致。
