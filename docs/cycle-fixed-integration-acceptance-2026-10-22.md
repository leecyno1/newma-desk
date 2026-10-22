# 周期固定源码与干净构建验收 · 2026-10-22

## 结论与版本

原生主仓 `/Volumes/PSSD/Projects/1周期模块` 已限定提交
`3abe177960c808299a043f0fd47e6c1bd240434b`，父提交为
`ec08c90e84a7f54d3fe093c207985b9b0dc8d3f7`。本次7文件只含健康配对修复、测试、Vite6.4.5锁及交接；原有研究数据、README和研究文档dirty保留，原生未推送。

Desk以GitHub main `639f2af74aec45f4c0f13c3b8891e257ae28fde2`为干净候选基础，纳入该原生版本的已验工程增量、4个页面查询Action、配对安装启动器及健康检测。`dev-stack.mjs`只纳入周期启动部分，未夹带其他运行版本显示/安装检查改动。正式注册库未发布新声明，仍不能把源码0.1.5当成运行中的0.1.1已更新。

## 本轮发现并修复的真实交付缺口

初次干净完整构建失败：`historical_prototype source path is missing or unreadable`。
原因是Desk根忽略规则屏蔽了原生已跟踪、构建器必需的4份批准历史基线。
本轮仅开放周期output目录遍历，沿用项目自身忽略规则，并明确纳入这4份2026-07-19固定JSON：C4/C5历史相位、C4伪实时、C4预测、C4资产统计。均逐字等于原生固定提交，没有用当前dirty研究结果替换。

采用error-handling技能的边界显式失败原则，保留缺输入时报错，不绕过模型门槛或回退旧数据。重新干净构建成功；源码包包含4份基线，不含数据库、node_modules、环境凭据。没有搬运正式catalog。

## 实际验证

候选根：`/tmp/cycle-fixed-integration-20261022-HMbFlq/`。

- 原生、Desk工作区与此前验收包377个工程文件一致；当前候选在相同工程范围配对，研究数据独立管理。
- 干净Desk冻结安装578包，周期前端75包；两处npm审计0告警。解压包前端再次冻结安装成功。最初从父工作区用npm prefix触发工作区锁错误，切到实际web目录后成功，未修改锁来迁就环境。
- 干净Desk 11个工作区601项通过，Shell类型与生产构建通过；33个官方数据能力声明及Shell依赖检查通过。
- 周期前端39项通过；4个Action输入Schema与原生定义逐对象匹配，Store声明编译通过。
- 干净Desk启动/监督器/描述符46项通过；活动工作区加运行状态测试为57项，范围重叠不相加。新增恢复验证覆盖：复用已运行周期 → 故障且端口释放 → 用同一安装入口与product/catalog/web根恢复；不调用旧seed，不启动真实进程。
- 新sdist→wheel；全新Python3.12.3环境按冻结uv.lock安装含测试共76包，依赖兼容通过。非editable安装；从/tmp以`python -I -m pytest -o pythonpath=`运行API、CLI、服务、输入/部署、foundation/catalog等259项通过（64.17秒）。此前旧隔离环境259项只是补验，不计为另一组覆盖。
- 从/tmp使用新安装CLI、解压源码和批准10月配对bundle完成完整构建，含TypeScript/Vite。`products-installed`与解压web配套，run=`2026-10-04-7180d6f1dc9e-5569654b27ad`，deployment=`aea7012e5f10af33`。
- 新安装服务14179真实HTTP：严格网页/产品/catalog配对、5份网页JSON与批准bundle一致、9张业务表与已验v17b相同；四API分别98/1/24/98条。比较仍stale/partial，其余unknown/available；四页路由200。证据`http-installed-acceptance.json`，验证后子进程正常停止。

本轮不重跑浏览器或真实Agent。已有同业务源码的双模式四页/筛选/刷新/Context实机证据继续有效，不冒充本轮重新操作。用户确认普通Chrome同源最小页正常；受控Chrome差异不再阻断业务源码收口，也不宣称修复Chrome本身。

## Linux交付路径与未完成边界

使用上述固定原生提交，或本次Desk限定集成提交的`bundled-runtimes/seven-cycle`。在目标机器冻结安装、构建源码包并安装wheel；在实际web目录执行npm ci。显式配置审核后的`VITE_NEWMA_DESK_PARENT_ORIGIN`，使用完整`seven-cycle build --research-bundle-dir`生成目标机器products/catalogs/web。不要搬macOS虚拟环境或DuckDB。

研究输入继续使用单独批准的8文件bundle（5网页JSON、3后端派生JSON及清单），不能把源码中历史基线或原生dirty网页JSON当成最新输入。对不同Origin重新构建；本文5888仅为本机验收。

启动必须同时指定`--product-root`、`--catalog-root`、`--web-root`。Desk可用`NEWMA_DESK_SEVEN_CYCLE_EXECUTABLE/PRODUCT_ROOT/CATALOG_ROOT/WEB_ROOT`四项配套配置；端口/工作区分别用既有WEB_URL/WORKSPACE。安装可用与网页可见不是版本已加载证明。

本机4174仍PID88974/deployment9450c83a46b68bf4，health正常；本轮只读核对。总监督器84688仍旧内存描述符，未热加载；新恢复路径通过的是隔离测试，不能写为在线已生效。没有整栈重启、修改研究数据、真实模型调用或远端部署。周期健康接口尚未上报Git源码身份，保留unknown；完整newma鉴权/结果通道由主发布侧与Desk按精确契约继续联调。
