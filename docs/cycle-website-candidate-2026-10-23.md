# 周期 Website 签名读取候选（2026-10-23）

## 固定范围

- 原生源码：`/Volumes/PSSD/Projects/1周期模块`，提交 `91ca85943be184c1aef0529dc75d0eea18d30562`；共同前基线 `3abe177960c808299a043f0fd47e6c1bd240434b`。原生研究草稿及数据保留，未推送原生仓库。
- Desk 基于 `495520b33b6f855ac066ab7115465d76db6c3cbf`，仅合入周期9份源码/测试、周期声明及授权回调/Website名单/测试。本报告随候选提交，提交身份以包含本报告的 Git 提交为准。
- Mod `seven-cycle-research` 版本 `0.1.6`，不扩大 permissions/actions。同步工具预览已无差异，不同步研究JSON、数据库、dist或其他项目。
- 未新建账户体系：周期只向 Desk 核验签名，账户、工作区、发布修订、准入均由既有 Desk/Website 决定。

## 实际开放的读取

五个精确GET路径：`/data/market-surface.json`、`/data/cycle-research.json`、`/data/asset-statistics.json`、`/data/forecast-extension.json`、`/data/data-calibration.json`，不接受查询参数。

资产归因：`GET /v1/assets/{asset_id}/attribution?horizon=12`，只接受页面当前使用的12个月参数，拒绝额外参数和路径别名。资产身份仍由领域API检查，不改变研究模型和发布门槛。

前端等可信Bridge init后才加载，携带Bearer与实例签名，不带Cookie、不跟随重定向、不缓存。用户/工作区/实例/令牌/授权变化取消旧请求并清除旧Context；主题变化不重载研究数据。会话失败不匿名重试；令牌不进入URL、页面偏好或Context。

## 配套配置与部署边界

1. Desk API部署本提交；保留 Website 登录、单worker、loopback和`--no-proxy-headers`约束。新内部回调为`POST /api/mods/runtime/cycle-scope`，兼容`/api/modules/runtime/cycle-scope`；回调只核验，不返回研究数据。只有来自loopback的核验可省略浏览器Origin，仍要求已绑定Website的Mod签名、实例、analysis.read、当前发布revision与准入。
2. 周期进程明确设置`SEVEN_CYCLE_DESK_SCOPE_URL=http://127.0.0.1:<实际Desk API端口>/api/mods/runtime/cycle-scope`。8911只是本机默认示例，云端端口由主发布侧实际配置确认。仅允许固定HTTP loopback回调，不经环境代理、不转发Cookie或自报身份。未配置时保持本地独立模式，**不能将未配置进程公开为已鉴权的挂载服务**。
3. 前端使用锁定Vite6.4.5，构建参数`VITE_NEWMA_DESK_PARENT_ORIGIN=https://c10375.runtime.drlemon.cc:10443`。加载新版前端、原生后端及0.1.6声明须配套；不能只更新HTML或复用旧site-packages。
4. 原生`/healthz`响应头`X-Cycle-Access-Mode: desk-required`用于确认实际加载模式；健康正文原有catalog/产品配对判定继续保留。头为standalone不能算挂载验收通过。
5. 反向代理必须把所有`/data/`与`/v1/`读取送到上述受控原生API，禁止静态文件服务绕过授权，也不公开旧周期端口或产品目录。静态页面、规范构建资源和既有公开方法文档允许匿名获取，不包含私有研究读取授权。
6. 主发布验收后，只在现有准入名单追加`seven-cycle-research`，不替换现有名单、不自动准入股票、产业链或Orchestra。原生已批准的网页/产品/catalog须配对打包；本候选没有重算/覆盖正式10月研究数据。

## 测试与证据

干净候选：`/tmp/desk-cycle-website-candidate-lw0CHr`，从父提交只叠加本轮14份代码/声明文件导出。未复制活动工作树其他dirty内容。

- `web`内`npm ci --workspaces=false --ignore-scripts --no-audit --no-fund`成功；沿用固定锁，不更新原生旧node_modules。最初使用`--prefix`被当前npm工作区解析拒绝，改为在web目录关闭workspace后成功，未修改锁文件。
- `npm run test:bridge --workspaces=false`：42项通过。
- 带上述云端父Origin的`npm run build --workspaces=false`：TypeScript及Vite6.4.5通过；已有Plotly大包警告保留，不宣称性能问题已解决。
- 干净候选的`test_cycle_scope.py`、`test_instock_scope.py`、`test_website_auth.py`：89项通过，使用已有Desk Python环境并显式`PYTHONPATH=services/api`。
- 干净周期`tests/api`：99项通过（40.67秒），使用已有原生Python环境并显式`PYTHONPATH=src`。这是干净源码回归，不是本次新wheel安装验收。
- 新组合测试把实际周期中间件连接到真实Desk测试应用的会话与发布校验：匿名不读数据、有效签名只读一次、未批准API拒绝、Website撤销后不再读取。另有原生真实临时HTTP测试确认不转发Cookie、不跟随重定向；临时服务器已关闭。均为合成身份/数据，不是云端真实用户。
- 原生先前7项访问测试及Ruff通过；Desk工作树差异检查通过，原生→Desk同步预览无差异。

## 尚未通过 / 不在本次范围

- 未操作远端、10378、正式4174/API/Shell；未重新登录、调用模型、启动采集、重算研究或迁移数据。
- 本次未做实际Website浏览器/HTTPS代理验证；仍需主发布侧核对直链、刷新、过期/撤销、网络绕过和实际健康配对。用户手动Chrome最小同源探针正常，仅说明该探针可加载，不能证明历史iframe空白根因已修复。
- `/v1/assets`、`/v1/cycles/current`、其他预测/比较/映射及任意数据文件在挂载模式仍不开放；其他模块如组合读取这些接口需单独接入授权，不能为兼容而关闭本门禁。
- `/demo/`内容不变；行业产业链/Orchestra公开readiness继续false，Orchestra认证、Skills和真实执行仍为独立阻塞。
- 股票是下一最小验收单元；这份周期候选不代表前五组或15项目已完整发布。
