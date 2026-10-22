# 市场复盘主快照委托候选 · 2026-10-23

原生固定`0259dd29b37b9e73f48d6de18134b7578f10779c`（父ad6b7a0），限定9文件；8份业务/测试已同步Desk，运行说明人工对齐。Desk本报告所在提交基于`0673fb08a6a7ac2ed8dd8376b42a1e9e4c640368`。不包含其他项目dirty、API main.py原有修改、权限/声明或依赖变更。

## 已接入与未接入

| 范围 | 候选状态 |
| --- | --- |
| 市场复盘主快照 `analysis.market-workbench` | 当前签名委托、线程上下文传递、页面及历史换代隔离已接入 |
| 市场宽度/情绪/成交额榜 | 仅本页允许三个既有GET能力，参数必须为空 |
| 扫描与补报价 | CN扫描50/100/200；四类复盘排序；最多50只报价，不借用云图市值榜授权 |
| 市场结构 | 未声明对应Action，工作区读取明确403，不开放直连资金服务 |
| 主线持续性 | 未授权轮动分析入口，不借本页权限启动轮动 |
| 交叉证据 | 未授权对应入口，不开放通用资金/政策代理 |
| 个人复盘记录 | 仍是独立本机共享账本；工作区读取/写入均拒绝，不认领旧记录、不自动迁移 |

共享`instock-data`按Mod选择固定分析入口及精确依赖集，再复用Website绑定、当前发布修订/准入、Action与数据网关检查。云图不能获得本轮新增的复盘专属能力；其他股票页面仍不因此开放。不新建账号内核、不用静态用户凭据、不复制Cookie。

四个附加区改走既有Bridge请求，无匿名fallback；换会话清空旧证据、选择、记录、草稿及列表，迟到成功不回填。主看板按会话事件撤下旧行情与Context；主题更新保留当前内容，旧请求finally不能解除新请求忙碌状态。Bridge在多面板同步清理期间抑制中间Context，全部清完后再发布，避免夹带尚未清理面板的旧内容。停止观察不声称服务端操作已取消，不自动重发。

## 实测

- 原生相关后端9文件180通过；解包wheel使用相同测试180通过，范围重叠不相加。
- 原生资源及wheel资源分别执行股票页面DOM回归121通过；新增附加面板请求/隔离4例、主看板迟到1例、多面板Context1例。不是浏览器实机。
- 干净Desk根目录Website及委托测试85通过，包含复盘主依赖通过、参数/云图越权拒绝、附加区5类请求拒绝；行情/身份为合成数据。
- 干净原生sdist→wheel成功，包内sourceCommit=0259dd2/sourceDirty:false；没有重新安装依赖或重做云图700项全量、周期Linux、Chrome探针。
- 产物`/tmp/desk-workbench-delegation-NsPbfy/`，含干净Desk测试导出、`stock/`原生克隆、`packages/`源码包/wheel、`wheel/`解包及`build.log`。

测试命令：Desk根目录`PYTHONPATH=services/api <API-python> -m pytest services/api/tests/control_plane/test_instock_website_scope.py services/api/tests/test_website_auth.py -q`；页面`INSTOCK_TEST_SOURCE=<原生或wheel目录> node --test tests/integrations/instock-*.test.mjs`。原生定向：test_market_workbench_delegation、test_market_workbench、test_market_journal、test_market_continuity、test_analysis_scope、test_market_data_provider、test_web_handlers、test_vibedesk_contract、test_web_service_routes。

## 发布边界

这是**市场复盘主快照的候选**，不是整页全部子功能已就绪。主发布如采纳，应明确接受上表四个附加区不可用的边界后，仅定向验收该页；不自动扩大准入、不整包替换已有11页本地服务。保留`INSTOCK_REQUIRE_DESK_SESSION=1`和固定loopback scope回调，API与原生包配套。

真实Website登录、HTTPS Top榜取数、历史与换用户/撤销仍由主发布验收；本轮未操作浏览器登录、远端、10378、正式进程、数据库、模型或/demo/。三true两false及产业链/投决未授权演示材料保持不变。下一最小项是为附加区逐项设计明确Action与数据归属；个人复盘须先解决工作区存储，不可只补读写白名单。
