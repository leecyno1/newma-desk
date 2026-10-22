# 股票云端入口门禁候选（2026-10-23）

本单元只交付原生入口的身份门禁和Website绑定核验，**尚不准入股票云端页面，不代表新分析/真实行情已经贯通**。

## 固定来源与范围

- 原生`/Volumes/PSSD/Projects/stock-czsc-integration`：`d29d2dea1a15c113e482a5d4b0543cbaa97ec32b`，父`2886547a3f9c6fd63fc4d6fecd893bd555d225ef`，限定8文件；已有8份文档dirty保留，原生未推送。
- 7份原生运行/测试文件同步Desk，预览无差异；Desk额外修改既有`/api/mods/runtime/instock-scope`及Website组合测试，无新增Mod权限、无声明版本变化、无新账户体系。
- Desk父版本`f6004294c74a9f5b937259f8a487b73111fa82f1`。包含本文件的Git提交是本单元固定版本；不从活动工作树取整个项目发布。

## 配置和行为

- 公开云端实例必须同时设置`INSTOCK_REQUIRE_DESK_SESSION=1`与`INSTOCK_DESK_SCOPE_URL=http://127.0.0.1:<实际Desk API端口>/api/mods/runtime/instock-scope`。回调严格限定HTTP loopback及该精确路径；禁止凭据、查询参数、重定向和任意外网校验器。8911只是本机默认，不是已核实的云端端口。
- 开关缺失默认0，保留本机同实例独立/Desk兼容；不等于可匿名公开。`--mode desk`仍只表达生命周期归属。开关只接受0/1；开启却缺校验地址时启动失败，不静默降级。
- 开启后所有业务Handler先校验签名，匿名、仅Cookie、缺实例或冲突签名拒绝，失败不执行分析/历史读取。保留现有`X-Newma-Desk-Session`，也接受等价Bearer；两者冲突拒绝。回调不转发浏览器Cookie或自报用户/工作区。
- 身份来源是Desk校验后的userId/workspaceId；Website模式还检查实际登录绑定和撤销，不相信请求提供的身份。原生已有结果/历史/后台任务scope隔离不改变，不把旧ownerless记录迁给当前用户。
- 仅健康、能力目录、Suite元数据Handler免业务scope；页面和静态资源只提供外壳。`X-Instock-Access-Mode: desk-required`用于确认实际加载模式，不替代行情健康、版本身份或业务验收。
- Desk校验继续按已发布Action与数据能力授权，补充当前manifest权限检查、冲突实例别名拒绝和no-store；不因存在Website Cookie而赋予股票读取能力。
- 反向代理只能指向该受控原生进程，不能公开旧匿名实例/数据库/结果目录。保持现有准入名单，**本次不追加任何股票Mod**。

## 验证

- 原生全量695项通过（96.52秒）；之后补1项真实Handler门禁/公共元数据回归，最终定向53项通过，不把重叠测试相加或宣称已重跑696项。
- 干净原生候选`/tmp/stock-website-gate-candidate-uIkows/fixed`来自本地只读源克隆、固定上述提交，53项再次通过。
- 相同干净源码sdist→wheel构建成功；包内release为`d29d2dea1a15c113e482a5d4b0543cbaa97ec32b`、`sourceDirty:false`。产物位于同级`packages/`。未重装依赖、未重新做Linux安装、未将包安装到正式服务。
- 干净Desk候选`/tmp/stock-website-gate-candidate-uIkows/desk`从父版本只叠加本轮9份代码/测试导出。股票scope、Website股票组合、周期scope及Website既有测试91项通过（4.90秒）。测试使用合成Website身份和实际市场Suite声明，验证Cookie-only拒绝、签名身份、伪造归属、撤销、跨入口和移出准入拒绝；不是云端真实登录或行情验收。
- 初次Website测试错误地只取Suite子页manifest且期待接受伪造身份头，已按真实继承合同与现有403规则修正测试；没有修改Schema或放宽身份校验。
- 未改前端代码、业务分析算法、数据源参数或研究数据；无浏览器探针、模型/采集请求、正式服务重启、10378操作或远端部署。

## 下一单元 / 仍不就绪

1. `market_data_provider.py`仍使用进程级配置连接下游能力，未承接当前请求的Website授权。需要在既有Desk数据网关/股票分析权限边界中完成最小委托，不能复制Cookie、给分析会话广泛管理员权限或开放匿名行情接口。健康中的market_data状态应如实保留，不把进程存活当行情可用。
2. `fetchAnalysis`目前主要按用户/工作区比对响应；令牌/实例/权限变化及A→B→A迟到读取还需完善。已有页面级隔离不等于全部前端换代已验。
3. 各股票页面按最小可验入口逐个接通，主发布侧核对实际HTTPS路由/登录/数据和撤销后才追加准入。行业产业链和Orchestra公开readiness仍false；/demo/三true两false不变。
