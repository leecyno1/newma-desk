# 市场签名存储与候选准入 · 2026-10-23

## 固定范围

基于 Desk 586bf4bc 的限定增量：市场自选/预警签名客户端、共享存储身份依赖、六份市场声明，以及候选 Mod 准入配置。不纳入其他活动 dirty 功能，不修改账号、数据库数据或远端服务。

市场唯一源码：/Volumes/PSSD/Projects/newma-desk-projects/market-daily，固定提交 c5a9b5f307035226169adff26f1575962f940aa1（前一项 a51d954）。src与Desk快照逐文件相同，7份声明的version/permissions/dataServices/actions配对；同步预览files:[]。本机版本清单只推进市场字段，未将整份本机配置打包。

## 七页候选的服务端准入

API启动环境：
```text
NEWMA_DESK_MOD_ADMISSION_ALLOWLIST=global-situation,fed-rates,hormuz-conflict,us-china-trade,macro-monitor,catalyst-calendar,news-radar
```

- 默认空字符串：保持现有本地行为，不启用准入限制。非空必须是精确Mod ID列表；星号、空项、非法ID导致启动校验失败，不退回全开放。
- 通过既有ModuleRepository执行：未准入Mod的草稿注册、包导入、发布/回滚、商店单页/项目安装、获取发布版本、会话签发、Action执行均拒绝403。原有效签名也不能绕过。已发布/已安装列表仅返回准入项。
- 含不准入页面的整组安装整批拒绝，不部分安装；旧数据库记录不删除、不搬移。配置在进程启动读取，修改环境变量不等于旧进程已生效。
- 此配置**不授予**页面权限、不自动安装七页、不改变Website登录校验，也不是原生服务端口/静态资源/通用账户管理接口的网络防火墙。发布侧仍须限制候选公开路由与注册管理面，不公开未验收的旧独立服务；不可只靠隐藏菜单或此列表宣称所有API隔离完毕。
- 586bf4bc本身没有这项配置；必须使用包含本增量的新固定提交。生产fd5981a与已有/demo/由主发布侧保留，源码会话不远端部署。

市场存储子链路受控验收时，可由发布侧明确将需要验收的市场ID追加至列表；不能默认把30页全放开。

## 市场配套

- market-daily 0.4.2；market-technical / multi-timeframe / relative-strength / trading-replay 0.1.2；event-timeline 0.4.1。六页声明storage.read/write、market-data，market.set-alert使用storage.write。market-sentiment未增加存储权限。新声明须正式发布并重建会话，旧会话修订不匹配会拒绝。
- 前端watchlist/alerts使用可信宿主签名及实例，不带Cookie、不发送自报账户头，不重定向、不自动重发；核验响应归属。签名缺失/过期/权限不足不得退回匿名本地API。
- 嵌入模式不读取、写入或自动迁移旧未分账户localStorage；切账号/实例/授权清理可见自选、预警和编辑状态。迟到读写/旧排队写入不更新新账户；初始读取不能覆盖后完成的保存。
- 共享后端在原表上按签名用户/工作区读取，检查Mod允许范围、当前发布修订及存储权限。Website模式另需原登录绑定，只有Cookie不能读写；本机独立且未启用Website、未携带会话字段时保留原本地兼容接口。这不等于匿名多租户安全。
- 部署必须配套API、Shell的EmbeddedMarketFrame动态包与市场前端；只发独立市场dist不会更新Shell内置市场组件。云端Shell仍按既有VITE_NEWMA_WEBSITE_AUTH_ENABLED=1构建。

## 实际验证

独立市场固定源码：67项前端测试、类型、Desk/独立两路径构建通过。
干净Desk候选：/tmp/desk-market-admission-eHT9Op，从586bf4bc导出，只叠加审核文件，原锁安装且禁安装脚本。

```text
PYTHONPATH=services/api <existing-python> -m pytest services/api/tests/control_plane services/api/tests/mod_store services/api/tests/watchlists services/api/tests/market_alerts services/api/tests/test_website_auth.py -q --tb=short
329 passed
npm run test:run -w @newma-desk/market-daily
67 passed
npm run build -w @newma-desk/market-daily
npm run build:standalone -w @newma-desk/market-daily
npm run test:run -w @newma-desk/desk
199 passed
VITE_NEWMA_WEBSITE_AUTH_ENABLED=1 npm run build -w @newma-desk/desk
```

最后补有效旧会话拒绝断言后，准入9项再次通过。真实六份Manifest登记/预警CRUD、跨账户隔离、只读写入拒绝、发布修订失效、Website绑定/撤销等使用临时数据库与合成身份，不触碰真实账户。

活动根工作树扩展回归曾出现87项fixture收尾错误（假设app-settings.db不会创建）；未修改这些既有断言。干净586基线单项复核及本候选上述329项全部通过，不能把活动根环境的结果冒充固定候选失败或通过。项目归属15/117及源码同步预览另在开发根通过。

## 未完成与发布边界

- 本轮没有真实浏览器/HTTPS账号/newma宿主验收，没有重启本机正式服务，没有远端部署。主发布侧无需重复既有Linux安装或Chrome探针。
- 市场存储可以进入受控验收，但不代表六页全部功能云端就绪。布局保存/回放归档的artifact客户端仍待身份适配；新闻/催化剂共享自选前端仍待综合投研接入；行业/周期独立身份、Orchestra实际执行继续单列。
- 七页登录候选的真实内容时效、真实用户成功登录由主发布侧继续。行业/投决公开真实内容仍ready:false，不用方法样例替代。
