# 会话看板限定发布交接

2026-10-24。此文件所在提交是 Desk 候选，不是生产验收证明。

## 范围与来源

- 新页面 `workflow-sessions`，归属工作流大项目；不增加第16个业务工程。
- 业务固定源码：独立 workflow-center 提交 `7af9fc47d1b7ce82dbcf082b6c91f427a769edcb`。该仓无远端，正式分发使用 Desk GitHub main 的 `modules/workflow-center` 集成快照。
- Desk 基线 `9d3b99675a8bb9830511765c52503a27a0f6af33`。仅增加看板、只读会话桥、DTO、单页声明/商店项及相关测试；不夹带工作树其他解耦或 Agent 改动。
- newma WebUI 必须配套实现 `newma:sessions-request/result`，协议 `newma:mod-host:v1`。宿主适配仍待固定基线，不可直接复制活跃工作树的整个 desk_collaboration.js。

## 功能与边界

五栏状态、搜索、项目/置顶筛选、原会话链接、可选15秒更新。首次手动读取；30秒后标旧。空闲不是完成。只读当前 Profile 可见的原生云端元信息，不读取消息正文、凭据，不发送消息/改变运行状态。

原生独立页和独立 Desk 没有 newma 父窗口时明确未连接。授权仅 `sessions.read`；快照 Action 是本地桥而非后端任务。失败清卡片，切页丢弃迟到响应。父宿主须复用已有登录 API，并核对请求的 frame/origin/project/workspace/mod 及响应 Profile。

## 构建与加载

在本提交的干净检出中 `npm ci --ignore-scripts --no-audit --no-fund`；随后：

```sh
npm run build -w @newma-desk/desk
VITE_PARENT_ORIGIN=https://实际的Desk域名及端口 npm run build -w @newma-desk/workflow-center
```

`VITE_PARENT_ORIGIN` 必须是直接包裹业务页的 Desk Origin，不是 newma 顶层站点，也不能沿用 localhost 默认值。工作流产物路径 `/mod-runtime/workflow-center/`，声明的 `NEWMA_DESK_WORKFLOW_CENTER_WEB_URL` 使用实际可达 HTTPS Origin。

由唯一主发布会话组装配套宿主、Shell、工作流产物，保留旧产物与注册声明回退。只从固定商店提交安装 `workflow-sessions` 单页，不调用全量注册，不改变其他模块、Hermes 执行器或 `/demo/`。默认不自动安装新看板。不因发布此页重启整个服务栈。

## 实际检查

- 干净候选：Shell类型与生产构建、工作流类型与生产构建通过。
- Shell会话桥/宿主桥/ModuleFrame 41项，新增授权/输入/切页4项；业务模型及Bridge契约9项；商店18项通过。商店测试同时修正原本过期的行业默认项与深瞳页数断言，业务声明未因此改变。
- 独立业务主仓5项及类型检查通过。前轮已有Chrome会话上的7条合成数据验收通过，包括筛选、切Profile、断连、原会话跳转及390px布局；不是本轮真实云端结果。
- 正式服务器未由本会话部署；真实登录会话、生产Origin、安装入口仍须主发布现场验收，不得仅凭构建宣称接通。

真实验收路径：newma登录 → 工作流/会话看板 → 手动读取 → 核对总数与状态 → 搜索/置顶/项目 → 打开原会话 → 切Profile后重新读取 → 切页/断连不残留旧卡片。证据只记录计数与行为，不复制真实标题或消息正文。
