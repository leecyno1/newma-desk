# 云图请求级委托候选 · 2026-10-23

## 固定范围

- 原生：`ad6b7a016857684cf463b90dbc3b78e3f3aa9d75`，父`d29d2dea1a15c113e482a5d4b0543cbaa97ec32b`；10文件限定提交，旧文档dirty保留。
- Desk：本说明所在提交，基于`195729b527dc40d690ed1ccd447fb2b854172e74`。同步9份业务/测试文件，预览`files: []`；独立运行说明人工同文对齐。
- 未更改Action、Mod权限、依赖、Suite或计算模型；仍用现有`analysis.market-map` / `analysis.read`。固定提交与包内release代表源码身份，不把声明版本当运行版本。
- 共享影响仅控制面新增云图委托端点、Website该端点绑定，以及股票Bridge/历史壳。其他项目dirty和API main.py原有改动不混入。

## 链路与修复

原生入口校验签名 → 请求级ContextVar → 云图并行扫描继承上下文 → 固定loopback `/api/mods/runtime/instock-data` → Website绑定/准入/当前修订及云图Action复核 → 注册的market-data及既有InternalResearch传输。

委托只接受CN的6类云图排序、100/200条扫描和最多50只六位代码的批量报价。拒绝其他Mod、额外参数、错误类型、非loopback、无签名/Cookie-only、撤销、旧修订和未准入会话。注册能力必须仍为GET/market.read。用户签名不传行情上游、不进入Context、结果或缓存；不复制Website Cookie、不使用股票进程静态凭据绕过。

Bridge对令牌/实例/权限/动作变化递增会话代次；A→B→A也不能接纳旧fetch、延迟JSON读取或UI Action回执。主题变化不作换代。云图撤下旧图表、摘要、选择和Context；历史列表与恢复按同一代次隔离。本轮修正清理时调用不存在的函数，以及历史切换后按钮锁住、旧finally解锁新任务的问题。

## 实际验证

| 验证 | 结果 |
| --- | --- |
| 原生后端全量 | 700通过 |
| 干净原生及解包wheel的5份定向后端测试 | 各143通过，范围重叠不相加 |
| Desk同步后 `node --test tests/integrations/instock-*.test.mjs` | 115通过（DOM模拟，不是浏览器实机） |
| 干净Desk根目录，Website与股票委托测试 | 83通过 |
| 官方数据声明检查 | 33通过 |
| 干净原生sdist→wheel | 成功，包内sourceCommit=ad6b7a0、sourceDirty=false |
| 同步预览、限定差异检查 | 无业务差异、无空白错误 |

后端采用合成身份、实际会话发布/授权路由及模拟行情；包括真实InternalResearch ASGI传输，不代表连接真实Website或实时行情。从services/api子目录扩大测试时6项宏观/资讯用例因相对路径未发现集成声明失败；改在干净候选根目录执行后83项全通过，未修改这些旧测试或模块。

产物：`/tmp/desk-map-delegation-HU37d9/`；`stock/`为干净原生克隆，`packages/`为sdist/wheel，`wheel/`为解包验证，根下services/api等为干净Desk基线叠加本批共享修改。无正式安装、数据库搬移或服务重启。

复跑：干净Desk根目录执行 `PYTHONPATH=services/api <Desk-API-python> -m pytest services/api/tests/control_plane/test_instock_website_scope.py services/api/tests/test_website_auth.py -q`；原生定向文件为test_market_map_delegation.py、test_analysis_scope.py、test_market_map.py、test_market_data_provider.py、test_web_handlers.py。

## 发布边界与下一步

1. **云图候选，不是股票11页全部就绪。** 新Provider拒绝未接入的签名直连能力；不能直接替换所有股票页已开放的本地环境。主发布若采纳，仅为`instock-market-map`安排受控准入，不扩开其他股票页。
2. 与Desk API配套，保留`INSTOCK_REQUIRE_DESK_SESSION=1`及固定loopback scope地址；不改为浏览器公网回调、不转发Cookie、不开放通用行情代理。
3. 尚未验证真实Website/HTTPS下登录→Top100/Top500→历史恢复→切用户→撤销；未执行真实行情或Agent，也不声称正式进程已加载。
4. 匿名健康探针没有请求身份，不能证明云端行情可用；数据状态与健康外壳、能力目录分开判断。
5. 用户手动Chrome最小同源页已确认可显示；不重做Chrome空白探针、Linux安装或周期验收。主发布会话继续独占远端部署，10378及/demo/不变。
