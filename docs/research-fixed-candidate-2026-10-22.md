# Research 固定源码候选验收（2026-10-22）

阶段记录：后续Desk集成与原生测试修复已完成候选验证，最新状态见 `research-integration-acceptance-2026-10-22.md`。下文保留本阶段当时的提交与未完成事项，不覆盖后续交付。

## 固定范围

- 唯一主源：`/Volumes/PSSD/Projects/newma-desk-projects/vibe-research`。
- 固定提交：`cbebdcb9dcd563058a9a261ce28aa6e708f5f1ed`，包含前一提交`64e077b`的宏观月度口径修复。本次限定14个已审阅文件，未包含QODER交接草稿；当前原生只有QODER_HANDOFF.md未提交，业务同步范围干净。
- 纳入既有行情候选：实际涨停池日期核验、腾讯复权历史入口与口径、A股日线截止日、显式Tushare日频备用复权、申万当前成员归属和同日全截面行业广度，以及相应测试/说明。不改变默认扫描源，不加入历史点时承诺。
- 新修复：PMI接口无默认输出列，原请求报字段不匹配；现在显式请求`month,pmi010000`，删除并不存在于官方输出定义的UPDATE_TIME依赖。官方文档：<https://tushare.pro/document/2?doc_id=325>。文档技能的Context7工具不可用，本轮直接读取官方文档，并与真实响应交叉验证。
- 已人工合并宏观差异，再运行`projects:sync -- vibe-research to-desk --apply`推进本机共同同步基线；随后预览`files: []`。未重启正式服务、未推送或远端部署。

## 干净环境复现

干净克隆：`/tmp/research-fixed-candidate-20261022-QojMeR/project`，HEAD等于上述固定提交。构建前后工作树均干净，不复制开发目录的node_modules/venv。

1. 后端`uv sync --project backend --frozen --extra test --extra sources --no-editable`：65个锁定依赖安装成功，`uv pip check`通过。
2. 前端`npm ci --ignore-scripts --no-audit --no-fund`成功；`npm test`229项通过；`build:standalone`及`build:desk`通过。产物为克隆内`frontend/dist`及`frontend/dist-desk`。
3. 后端源码测试375项通过（11项live默认未选、3个既有弃用警告）。Desk配对宏观/日频/复权/截止日/情绪日期118项通过。
4. 清除PYTHONPATH，从源码目录之外启动非editable安装的`newma-research`，确认macro_monitor/market_scan_daily/market_terminal均来自隔离venv的`site-packages/newma_research`，不是当前源码路径。未将依赖元数据的安装路径冒充进程版本。

## 安装包真实HTTP验证

临时服务18966，使用新数据目录、禁用后台任务、仅本机监听，显式设置`VR_CN_SCAN_SOURCE=tushare-daily`；未修改正式配置或数据库。

- `/api/macro-monitor?days=7`：200，10项核心指标、9/9流动性，来源错误清单为空。PMI从Tushare主源读取2026-09=50.1、前值49.8，未借用降级源或伪造发布日期。
- `/api/market-terminal/ohlcv?symbol=920096&market=CN&timeframe=1d&limit=40&adjust=qfq&asOf=2026-10-20`：200，腾讯qfq，38条且最后日期为10月20日；保留`latest-window-filter`边界，不等于完整历史点时回测。未在本轮独立复核腾讯原始成交额缺数语义。
- `/api/industry?top=5`：首次502。随后逐来源只读诊断完成trade_cal、证券目录、daily、daily_basic和index_member_all全分页；未改代码，再次请求同一运行服务200、耗时6.18秒。31行业，10月21日5568报价/5576目录/缺8，归属缺失0，partial不伪报完整。首次失败的具体底层原因未保留，不能断言全部网络调用稳定或隐去首轮失败。
- 编译前端`/macro-monitor`返回200。页面真实显示/刷新已在上一轮IAB验证；本轮没有重做新安装包的浏览器、Desk内嵌、真实newma或模型问答验收。

## 尚未交付的边界

这是可重建的独立Research源码候选，不是Desk整栈发行。Desk工作树的Research前端/API/权限与档案集成尚有既存修改，须在干净Desk候选中定向组合、验证并提交到正式发布源。当前Desk GitHub仍为行业候选109bbbe1；不能把本机版本锁或原生提交冒充已经推送上线。

后续优先完成Research与股票消费者、签名研究输入/资料权限和运行配置的配套集成。全球、周期、投决仍按前五组交接逐项收口，不等待其余10个大项目。c10375远端只由主发布会话部署，本会话未操作远端。
