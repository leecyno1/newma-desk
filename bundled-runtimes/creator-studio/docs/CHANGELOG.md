# Changelog

所有重要的项目变更都会记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [3.0.0] - 2026-08-03

### 新增

- 六阶段工作流、九个功能模块和三条发布路线的机器注册表。
- 42 个保留项目、4 个候选储备和 13 个剔除项目的生成目录。
- 外部项目同步器、上游补丁登记与补丁应用器。
- 视频导演、真实素材、HTML/Remotion 动画、渲染质量门禁和视频自学习模块。
- 千帆本地 API、多账号发布矩阵、平台表单校验和发布回执验真。

### 变更

- 公开仓库改为只跟踪自研代码、注册表、契约、补丁、测试和文档。
- 全面更新安装、上手、贡献和安全说明。

### 安全

- 本地密钥、Cookie、浏览器 Profile、抓取数据、导出镜像和运行产物移出 Git 跟踪范围。
- 发布前增加个人路径和秘密模式扫描。

## [2.0.0] - 2026-04-18

### 重大变更 - 通用安装改造

本版本将项目从"个人生产力工具"改造为"可分发的开源产品"，使任何用户都能在任意环境中安装和使用。

### 新增

- **路径配置系统** (`configs/paths.default.yaml`) - 支持环境变量覆盖的路径配置
- **统一路径解析器** (`core/path_resolver.py`) - 自动检测项目根目录，消除硬编码路径
- **一键安装脚本** (`scripts/install.sh`) - 自动化安装流程
- **安装验证脚本** (`scripts/verify_installation.py`) - 验证安装完整性
- **数据源健康检查** (`scripts/check_data_sources.py`) - 检查外部数据源可用性
- **E2E测试套件** (`tests/e2e/`) - 端到端工作流测试
- **集成测试** (`tests/integration/`) - 跨模块集成测试
- **Docker支持** (`Dockerfile`, `docker-compose.yml`) - 容器化部署
- **文档重组** - 清晰的文档结构（guides/technical/archive）

### 修复

- **移除所有硬编码路径** - 项目可在任意目录运行
- **WeChat采集容错** - 添加fallback机制和缓存层，解决慢速源超时问题
- **Skill版本整合** - 每个Stage只保留一个正式版本，废弃重复skill

### 变更

- **文档精简** - 根目录从29个markdown文件精简至2个核心文档（README.md, CLAUDE.md）
- **路径配置化** - 所有路径通过配置文件或环境变量指定
- **测试覆盖提升** - 从87个单元测试扩展到110个测试（87单元 + 15集成 + 8 E2E）

### 废弃

- `dasheng-daily-phase2` → 使用 `dasheng-stage-brief-ai` 替代
- 硬编码路径 `${DASHENG_PROJECT_ROOT}` → 使用自动检测或环境变量

### 技术债务清理

- 归档20+个过程性文档到 `docs/archive/`
- 统一JavaScript skill的项目根目录检测逻辑
- 更新所有Python脚本使用 `path_config.get_project_root()`

## [1.0.0] - 2026-04-04

### 初始生产就绪版本

- 7阶段工作流完整实现
- 87个单元测试，98%通过率
- 生产就绪评分：100/100
- 飞书协作集成
- DNA系统配置
- 多平台适配（微信/小红书/微博）

### 核心功能

- Stage 1: 内容采集 (Intake)
- Stage 2: 选题分析 (Brief)
- Stage 3: 初稿生成 (Draft)
- Stage 4: 素材收集 (Material)
- Stage 5: 改写 (Rewrite)
- Stage 6: 渠道分发 (Publish)
- Stage 7: 分析复盘 (Postmortem)

### 技术栈

- Python 3.10+
- Node.js 18+
- Claude 4.6 (Opus/Sonnet)
- Tushare/AkShare (数据源)
- 飞书API (协作)

---

## 版本说明

### 版本号格式

`主版本号.次版本号.修订号`

- **主版本号**: 不兼容的API变更
- **次版本号**: 向下兼容的功能新增
- **修订号**: 向下兼容的问题修正

### 变更类型

- **新增**: 新功能
- **变更**: 现有功能的变更
- **废弃**: 即将移除的功能
- **移除**: 已移除的功能
- **修复**: 问题修复
- **安全**: 安全相关的修复

---

[2.0.0]: https://github.com/leecyno1/newma-media-studio/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/leecyno1/newma-media-studio/releases/tag/v1.0.0
