# 行业景气集成候选 · 2026-10-22

## 固定来源与范围

- Desk基线：`e9fdee83a58d239ce1e44ca71a5675cb9f27ad25`。本文件随行业候选提交，发布须取包含本文件的完整提交，不复制活动工作树。
- 行业原生：`abd82e0b385cc8974b88226a9b7350c9bb5d10f4`，目录 `/Volumes/PSSD/Projects/newma-desk-projects/industry-research`；包含此前 `0b36dea` 的统计局利润分页修复。
- 纳入：行业前端、四类公开业务API及测试、行业Manifest/商店登记、businessRevenue契约与导出、必要构建/静态挂载、签名industry-inputs及其存储验收。
- 未纳入：其他项目dirty、共享SDK变更、整套15项目工程工具、其他研究档案端点鉴权迁移。不能称五组整体发行或全接口安全审计完成。

## 最小配套版本与启动

1. Shell：至少上述Desk基线；本次从同一候选构建Shell。市场 `/mods/market-daily/` 是Shell内置，后续市场改动必须重建Shell，单换市场dist无效。
2. API：必须包含本候选四个industry router、静态挂载和签名 `/api/research-archive/industry-inputs`。只更新两个利润文件不够。
3. 前端及Manifest：同一候选的 `modules/industry-research` 与 `mods/industry-prosperity/mod.json`（0.16.1）；保留market.read、storage.read/write和industry-tracking命名空间。以Git提交固定身份，不以页面版本号证明已加载。
4. Desk与external资源必须不同Origin。云端已审核Desk为 `https://c10375.runtime.drlemon.cc:10443`，资源为10444。行业构建必须显式设置 `VITE_PARENT_ORIGIN` 为Desk Origin；跨项目链接可设置同值 `VITE_DESK_URL`。不从referrer/query推断授权，不复制本地测试Origin的产物上云。
5. 根目录 `npm ci`；按顺序执行 `VITE_PARENT_ORIGIN=<Desk Origin> VITE_DESK_URL=<Desk Origin> npm run build -w @newma-desk/industry-research`、`npm run build -w @newma-desk/desk`。Docker路径新增同名build args，但本轮没有执行完整Docker镜像构建。
6. 按现有API依赖安装并启动 `python -m uvicorn vibe_visualization_api.main:app --app-dir services/api --host 127.0.0.1 --port <API端口>`。`NEWMA_DESK_INDUSTRY_RESEARCH_DIST`可显式指向本次dist；默认 modules/industry-research/dist。资源入口提供 `/mod-runtime/industry-research/` 及其同源公开 `/api/industry-research*`，私有资料/存储仍走Desk签名网关。`NEWMA_DESK_INVESTMENT_WEB_URL`是当前行业声明解析用的资源Origin，属于共享设置，部署方须核对其其他消费者后应用，不能盲改全局值。
7. 另一可选部署方式是安装上述原生固定提交并运行 `newma-industry --frontend-dist <本次dist> --port <行业端口>`。原生非editable旧安装不自动随Git变新；不可直接启动旧site-packages冒充新包。Desk的私有输入API仍需配套升级。
8. 使用现有发布流程激活该Manifest及正确资源URL，保留注册库、业务库和回退包；本会话不实施远端部署。

## 实际验收

- 从Desk Git基线建立隔离克隆，仅加入本候选文件；`npm ci --ignore-scripts --no-audit --no-fund`成功，不借根工作树node_modules。
- 候选行业66项前端测试通过、类型及生产构建通过；contracts101项测试、Shell类型及生产构建通过。原生66项前端测试、Desk/独立两种构建通过。
- 候选四类公开后端+研究档案83项测试通过：包含真实行业Manifest的跟踪/公司关联存储回读、修订冲突、跨工作区隔离及签名私有输入。Python解释器复用已安装依赖，`PYTHONPATH`明确指向候选源码；不是全新Python安装验收。
- 隔离编译Shell/API18962 + 行业18963，无正式凭据/资料、禁后台调度。IAB显示2026年1—8月官方利润：41行业、40可同比，全国营收同比6.6%、利润同比15.7%；Bridge ready/acknowledged/received。显式宿主来源修正后重新构建并回读握手。
- 上一轮原生独立页实际点击取得8月生产/PPI、二季度产能和6/7/8月利润历史。本轮IAB嵌入按钮虽可见且启用，接口返回click target unavailable；语义定位和截图定位均未成功，因此嵌入保存/切换的完整人工验收仍待补，不把接口测试当成UI点击通过。
- 截图：`/Users/lichengyin/.codex/visualizations/2026/10/19/01a15412-3a37-7863-ba8c-b0286f247ca0/industry-clean-candidate-20261022.png`。

## 发布边界

未切换正式5888/8911、未操作远端数据库、未发模型请求。只交付行业增量候选；外部newma、真实模型结果、云端路径与资源代理、人工嵌入交互由发布验收单独确认。
