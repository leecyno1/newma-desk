# Newma Media Studio

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Workflow: 6 stages](https://img.shields.io/badge/workflow-6%20stages-5b67f1.svg)](configs/workflow/module_registry.json)

面向中文自媒体团队的内容生产、普通无头口播、VOX 调查解释视频、真人口播和多平台发布工作流。项目以 Manifest 与质量门禁为核心，把采集、研究、写作、视频导演、动画渲染、账号路由、发布验真和复盘连接成一条可恢复、可审计的生产链。

- GitHub：[leecyno1/newma-media-studio](https://github.com/leecyno1/newma-media-studio)
- Gitee：[leecyno1/newma-media-studio](https://gitee.com/leecyno1/newma-media-studio)
- 完整项目、Skill、储备与依赖目录：[docs/PROJECT_CATALOG.md](docs/PROJECT_CATALOG.md)

Newma Media Studio 是完整系统名称，不是单个 Skill。`skills/` 下的能力单元仍以 Skill 形式安装和路由。为保持现有自动化兼容，`dasheng-*` Skill ID、`DASHENG_*` 环境变量和 `dasheng.*` schema 命名空间在当前大版本继续保留；它们是稳定接口，不再作为对外项目品牌。

## 主流程

```text
Intake -> Brief -> Draft -> Transwrite -> Publish -> Postmortem
  采集      选题      初稿       多通路生产       发布        复盘
```

| 阶段 | 核心职责 | 主要产物 |
| --- | --- | --- |
| Intake | 采集、标准化、去重、聚类、保留来源 | `intake_manifest.json` |
| Brief | 事件归并、选题卡、证据缺口、角度排序 | `brief_manifest.json`、`selected_topics.json` |
| Draft | 事实底稿、数据图表、长文与 HTML | `draft_manifest.json`、结构快照 |
| Transwrite | 公众号、真人口播、无头视频、播客 | `transwrite_manifest.json`、各通路生产包 |
| Publish | 平台包装、账号矩阵、表单校验、发布验真 | `publish_manifest.json`、平台回执 |
| Postmortem | 数据聚合、差异归因、规则与 DNA 回写 | `postmortem_manifest.json`、复盘报告 |

可选的范式学习、视频风格训练和视频自学习只提供知识资产，不改变六阶段主链。

## 功能模块

- 总控与契约：统一入口、Manifest、Gate、失败恢复。
- 内容与证据：热点采集、选题、写作、财经数据、命题—证据台账。
- 视频导演：口播节奏、真实 B-roll、分镜、构图、工具路由和导演审片。
- 动画与剪辑：HTML Video、Remotion、HyperFrames、GSAP/Lottie、ASR、FFmpeg、EDL 和渲染 QC。
- 发布中心：多账号、多平台、封面、标签、原创声明、活动字段、发布队列和链接回收。
- 学习与治理：范式画像、视频 DNA、导演记忆、契约测试和公开仓库卫生。

机器可读的模块注册表位于 [configs/workflow/module_registry.json](configs/workflow/module_registry.json)。

## 快速开始

```bash
git clone https://github.com/leecyno1/newma-media-studio.git
cd newma-media-studio
./scripts/install.sh
source .venv/bin/activate
```

复制环境模板并填写自己需要的服务：

```bash
cp .env.template .env
cp configs/paths.default.yaml configs/paths.local.yaml
```

安装项目 Skills：

```bash
bash install_to_openclaw.sh
```

检查或克隆外部储备，并应用兼容补丁：

```bash
python scripts/sync_reserved_projects.py --mode check
python scripts/sync_reserved_projects.py --mode clone
python scripts/apply_upstream_patches.py --mode apply
```

按需安装媒体依赖：

```bash
python -m pip install -r requirements-media.txt
python scripts/ensure_video_external_deps.py --dep all --mode check
```

## 运行

统一入口：

```bash
python scripts/run_mainline_stage.py doctor --latest --strict
python scripts/run_mainline_stage.py intake --run-id 2026-08-03_demo
python scripts/run_mainline_stage.py brief --run-id 2026-08-03_demo
python scripts/run_mainline_stage.py draft --run-id 2026-08-03_demo
python scripts/run_mainline_stage.py transwrite --run-id 2026-08-03_demo
python scripts/run_mainline_stage.py publish --run-id 2026-08-03_demo
python scripts/run_mainline_stage.py postmortem --run-id 2026-08-03_demo
```

每个下游阶段都从上游 Manifest 解析输入，并校验对应 Gate。不要用“最新目录”或手写临时路径绕开契约。

统一入口生成待审核产物后，项目 Manifest 会保持 `pending_review`；只有人工批准对应 Gate、完成渠道执行并验真后，才算阶段完成。

## 发布路线

当前默认采用千帆云递本地 API：

```text
channel pack -> local API -> platform adapter -> CloakBrowser/Playwright -> receipt verification
```

批量场景可走千帆异步队列，`social-auto-upload` CLI 作为后备。账号 Cookie、浏览器 Profile、验证码和平台回执保存在仓库外；有头发布浏览器默认小窗、优先附属屏、禁止最大化，并尽量恢复原前台应用焦点。

## 外部项目与储备

本项目登记 40 个保留上游项目和 4 个候选储备。第三方源码不会被复制进公开 Git 历史，而是由 [configs/external/reserved_projects.json](configs/external/reserved_projects.json) 和 `scripts/sync_reserved_projects.py` 复现。Newma 对上游的必要兼容修改保存在 `patches/upstreams/`。

## 测试

```bash
python -m pytest tests -q
python scripts/verify_installation.py
python scripts/build_project_catalog.py --check
python scripts/apply_upstream_patches.py --mode check
```

## 安全与公开边界

公开仓库只包含自研代码、Skills、非敏感配置、契约、测试、文档、上游注册表和补丁。不要提交 API 密钥、Cookie、OTP、浏览器 Profile、抓取快照、成品视频、运行产物、虚拟环境、`node_modules` 或第三方源码副本。详见 [SECURITY.md](SECURITY.md)。

## 文档

- [安装指南](INSTALLATION.md)
- [项目目录](docs/PROJECT_CATALOG.md)
- [新成员上手](docs/ONBOARDING.md)
- [阶段接口](docs/STAGE_INTERFACES.md)
- [API 参考](docs/API_REFERENCE.md)
- [贡献指南](CONTRIBUTING.md)
- [更新日志](CHANGELOG.md)

## 许可证

自研部分采用 [MIT License](LICENSE)。外部项目及素材仍受各自上游许可证和平台条款约束。
