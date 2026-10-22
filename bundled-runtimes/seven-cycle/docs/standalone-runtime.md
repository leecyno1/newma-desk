# 周期研究独立构建与 Desk 接入

2026-10-20 v17b刷新恢复已在最终候选实机通过：业务项目自己保存当前页和公开UI偏好，按可信父Origin/用户/工作区/Mod隔离，独立模式使用单独scope；不存研究数据、凭据、聊天或任务状态。修复Desk默认iframe带__newma_mod_version参数导致路由恢复失效，显式深链仍优先。原生与解压包38项前端测试、类型/Vite及新venv68包兼容/安装CLI完整build通过；14175现为view-session-v17b-OYLYjw（PID54638/session57125，deployment=77f1ebdd831a830c），5893/8997未重启，正式4174未动。Chrome现有Profile验证整Desk刷新保留C5/展开、2D/20年、校准页及资产两层筛选/选中详情；最终独立入口验证C2深链覆盖旧C5及2D/20年刷新恢复。五份网页数据等于10月配对快照，九张业务表等于v16离线产物，四API仍98/1/24/98条；compare仍stale/partial，其余freshness unknown。无新Agent任务，隔离库仅2项completed，未捕获warn/error。首版v17实际失败及修正、截图、启动记录见候选目录desk-integration-v17.md。历史偶发空白根因仍未定位，新Adapter真实Mod回传/Electron、正式一致性与固定版本仍待验收，完整0/15；无提交/推送/部署。以下旧运行记录仅为历史，不能覆盖本条。

### 页面会话恢复

`web/src/hooks/usePageSession.tsx`和`web/src/lib/pageSession.ts`由业务页持有状态。只写入当前标签的sessionStorage；关闭标签或禁用存储不保证恢复。身份切换按scope重挂页面，相同身份的主题/配置init不清空选择。嵌入默认入口恢复已存路由，显式业务路径/周期参数优先；Desk版本参数不算业务深链。仅保存组件声明的筛选、视图和选中ID，不保存异步结果、在途动作或网关身份。刷新仍重读当前研究快照，不产生新观测。

2026-10-20 v16已接入隔离Desk：确认隔离库仅2项completed、无queued/running后，正常停止旧v15/PID59556；14175现为deps-v16-145WMt的新venv/products/解压web（PID42152，exec session50168），deployment=82bbf551b78ccb33、health ok，Shell5893/PID10422及API8997/PID62807未重启，正式4174未动。五份网页JSON仍等于10月配对快照；四组API分别98/1/24/98条，compare仍stale/partial，其余freshness仍unknown，未改成实时。Chrome现有Profile实际完成四页导航、C5选择、3个月商品筛选；隔离库Context与页面一致，原油1条、收益6.1%/波动27.7%，非配置建议。一次整Desk重载ready/acknowledged/received通过、未捕获warn/error；但刷新会回市场首页且筛选重置，列为待完善，历史偶发空白根因仍未定位。证据见同目录desk-integration-v16.md、desk-audit-v16.jpg。此轮无新Agent任务、业务源码改动、正式快照同步、提交/推送/部署；真实新Adapter结果回传与Electron、正式一致性及固定版本仍未过，完整0/15。以下旧运行记录保留为历史。

最新依赖候选（2026-10-20 v16，尚未替换14175）：`web/package-lock.json`在原声明范围内修复7项告警，新sdist/wheel与完整安装构建位于Desk迁移根`deps-v16-145WMt/`。干净npm ci、33项测试、前端/安装CLI完整构建及68个Python运行包兼容检查通过，npm审计0告警。临时14176四页实际导航与网页/API配对检查通过并已停止，数据沿用10月历史快照，deployment=`82bbf551b78ccb33`。业务源码同v15；运行中v15与正式快照仍用旧锁，不能扩大为线上已修。仍须Desk集成复验、真实宿主及固定版本验收。

当前隔离候选（2026-10-20 v15）：Desk迁移根`integrated-v15-Xa9yCp/`的新venv/products/解压web在14175运行（PID59556/session70572），deployment=`cfb63dcdd949429e`；API8997/Shell5893沿用，正式4174未切换。完整安装构建、10月配对数据与API等价通过；校准页WDI四条缓存在独立/Desk及Context一致。历史首次Desk重载超时尚无根因，最近受控三轮重载通过，不能据此标记修复。npm仍7项告警，真实Electron/模型结果与固定版本未过；未提交/推送/发布。本段文档晚于v15打包，以下各轮旧运行路径仅为历史。

## 真实 newma 父项目

父线程`019fe457-442d-7372-8009-2280e63f2261`对应`/Volumes/PSSD/Projects/MonkeyAI`，不是本项目或废弃Newma-dsh。WebUI位于`MonkeyAI-web/modules/agent-console`，桌面位于`MonkeyAI-desk`，共享Runtime位于`Newma-runtime`。入口及协议见`/Volumes/PSSD/Projects/newma-desk/docs/integrations/newma-agent-result-protocol.md`。

挂载链路为原生newma菜单 → Desk Shell → 周期页面；结构化Context与HTML/DOM通过Bridge传递，Agent请求仍经用户确认并由Hermes执行。WebUI及桌面均已接入可选结果观察，独立Desk的CLI、设置与Copilot不删除。真实WebUI隔离挂载已通过Context/能力协商；桌面构建和合成回归不能替代Electron及真实模型终态验收。父源码已经找到，不再等待用户另提供路径；启动实际宿主和真实模型测试仍需按授权范围进行。

## 三类产物

- 源码：Python `src/seven_cycle_platform`、React `web/`、批准配置与历史研究基线；通过 sdist → wheel 构建。
- 研究输入：5份网页研究 JSON 与3份后端派生输入，使用`export-research-inputs`交付为配对快照。保留各自观测期；不能只改生成日期冒充更新。
- 运行产物：在目标运行目录新建的研究 run、DuckDB catalog、配对 deployment 元数据与 web/dist。Catalog 保存目标路径及文件身份，不能复制旧数据库当作可迁移产物。

## 源码模式

```sh
uv sync --frozen
npm ci --prefix web
uv run seven-cycle build --as-of 2026-08-22 --research-output-dir /absolute/path/research-output
uv run seven-cycle serve --host 127.0.0.1 --port 14174
```

日期仅为命令示例，应与实际发布快照对应。端口须先检查空闲；不能覆盖正式4174。
`build` 的其余路径参数保持既有当前工作目录语义；从仓外调用时全部使用绝对路径，不能只给 `--project-root` 就假定其他参数也自动锚定它。

## 安装包验收

先从批准的研究源导出配对输入，目标目录必须不存在：

```sh
seven-cycle export-research-inputs \
  --project-root /absolute/path/research-source \
  --destination /absolute/path/new-research-snapshot
```

默认读取研究源`web/public/data/`五份JSON，以及`output/asset_cycle_state_forecast.json`、`output/c4_asset_statistics_current.json`、`output/c4_forecast_reproducible_latest.json`。可显式给`--web-data-dir`、`--research-output-dir`、`--c4-forecast-path`；导出命令不静默回退旧C4基线。

快照包含`web-data/`五份JSON、`research/`三份JSON（C4归一命名为`c4_forecast.json`）和`research-inputs.json`。仅复制这8个数据文件，清单记录真实源日期。联合预测、历史资产统计、C4预测的网页/后端重复业务结果必须一致，日期相同但内容不同也拒绝；这不是全部七周期研究的真实性认证。失败不发布目标目录，不刷新数据、不含数据库/原始面板/凭据。

1. `uv build --out-dir /absolute/path/packages`；构建器从 sdist 再构建 wheel。
2. 将 sdist 解压到独立目录。在全新虚拟环境安装 wheel，按其中 `uv.lock` 的冻结导出安装运行依赖；不使用 editable 安装或原仓库 PYTHONPATH。
3. 解压目录 `web/` 执行 `npm ci`，再用安装后的 CLI 执行：

```sh
seven-cycle build --as-of 2026-08-22 \
  --project-root /absolute/path/unpacked-source \
  --config-dir /absolute/path/unpacked-source/config/seven_cycle \
  --web-project-root /absolute/path/unpacked-source/web \
  --research-bundle-dir /absolute/path/new-research-snapshot \
  --product-root /absolute/path/candidate-products

seven-cycle serve --host 127.0.0.1 --port 14174 \
  --product-root /absolute/path/candidate-products \
  --catalog-root /absolute/path/candidate-products/catalogs \
  --web-root /absolute/path/unpacked-source/web/dist
```

`build-foundation --project-root ...` 使用显式项目根定位批准基线；校验文件名、目录位置、内容和发布门槛，不再依赖 Python 包安装位置。
`--research-bundle-dir`与旧`--research-output-dir`互斥；构建发布前验证快照，网页编译后只替换dist中五份研究数据，API使用同快照的三份后端输入。不会修改源码包public数据。旧非bundle构建保持兼容，但需要调用者自行保证网页/API配对。

输入身份使用固定逻辑路径，不包含快照目录名；同数据移动目录后可复用相同run。Catalog仍在目标机器重建，不把旧数据库当作可迁移输入。

2026-10-20实际验证：Desk迁移目录`seven-cycle-20261020-kVpugP/inputs-Tnf09c/`的新venv从/tmp以Python -I完成完整build，快照搬到relocated-snapshot复建仍复用run`2026-08-22-7180d6f1dc9e-b2325d25826f`和deployment`414b03fc1689d34b`。相关136项回归通过；临时14175安装包服务健康正常，五份HTTP网页数据与快照一致，API资产98/当前周期1/预测24条均同run；比较仍partial/stale。验收后停止临时服务，14174仍旧v6，正式4174未动。本次未运行浏览器或Agent新任务，交接文档更新晚于已验证源码包。

完整 build 仍需匹配的外部研究输入。仅构建 wheel 或健康接口200，都不能代替四页双模式业务验收。

## 独立运行周期发现工具

安装后的`seven-cycle discover-cycles`与旧脚本共用同一计算实现，不依赖Python安装位置寻找研究数据：

```sh
seven-cycle discover-cycles \
  --project-root /absolute/path/discovery-inputs \
  --output-dir /absolute/path/discovery-results
```

输入根须包含四个文件：

- `data/research_input_annual_long.parquet`：年度面板，整数年份索引。
- `data/research_input_monthly_macro.parquet`：月度面板，日期索引。
- `output/research_input_annual_long_selection.csv`：status、column、source、value_type、family_key。
- `output/research_input_monthly_macro_selection.csv`：status、panel_main_column、primary_source、value_type、family_key、universe_category。

元数据沿用既有`selected`规则与研究计算口径；不自动抓取、补齐或替换输入。缺文件会在计算及创建结果目录之前失败。`--project-root`省略时使用当前工作目录，`--output-dir`省略时使用输入根的output；显式相对路径按当前工作目录解释。建议给出独立输出目录，避免覆盖既有同名研究结果。

旧`python scripts/discover_cycle_periods_robust.py`仍显式使用脚本所在项目根；兼容导出的ROOT/PANEL_SPECS仅供旧源码脚本使用，不是安装包数据目录。报告摘要来自本次prior验证，不再复述固定的旧研究结论；输出不自动获得发布资格，也不切换Desk产品。

2026-10-20：独立新环境按现有uv.lock安装68包，sdist→wheel后从/tmp以Python -I执行成功，输出5个文件。验收使用明确标记的合成面板，只证明安装/计算/路径链路，不证明真实市场研究有效。产物见Desk迁移目录`seven-cycle-20261020-kVpugP/discovery-efsHwJ`；运行中的14174/正式4174均未替换。

## 原始面板生成离线周期输入

安装包提供`seven-cycle build-cycle-inputs`，复用原有`ResearchCycleInputRequest`和周期输入序列化实现。它不是`export-research-inputs`：前者把研究面板转换成离线算法输入，后者打包网页/API已经生成的研究结果。两种输入不能互换。

```sh
seven-cycle build-cycle-inputs \
  --project-root /absolute/path/research-panels \
  --config-dir /absolute/path/source/config/seven_cycle \
  --output-dir /absolute/path/new-cycle-inputs \
  --as-of 2024-03-31 \
  --state-start 2023-01-31 \
  --state-end 2023-12-31 \
  --verification-cutoff 2023-12-31
```

日期仅为命令示例，必须按实际研究窗口填写。`--as-of`、状态起止日期、至少一个验证截点及输出目录均必填，不默默沿用旧脚本的2025年窗口。验证截点可重复传入，排序去重；不得晚于as-of，状态结束不得早于开始或晚于as-of。

输入根需要以下四份文件，配置可单独放置：

| 文件 | 内容 |
| --- | --- |
| data/research_input_annual_long.parquet | 年度面板，年份索引 |
| data/research_input_monthly_macro.parquet | 月度面板，日期索引 |
| output/research_input_annual_long_selection.csv | column、coverage_pct、status、source、value_type |
| output/research_input_monthly_macro_selection.csv | panel_main_column、coverage_pct、status、primary_source、value_type、universe_category |

月度类别沿用原有中文分类映射，不能把discovery测试所用英文family名当成此接口输入。只使用selected、覆盖率合格且面板真实存在的列，月度日期归一到月末。输出`cycle_pipeline_input.json`由既有`load_cycle_pipeline_input`/`build-cycles --input-dir`消费，已有文件拒绝覆盖。

project-root默认当前目录，不从Python安装位置推断。config-dir省略时使用输入根的config/seven_cycle；显式相对config-dir/output-dir按调用工作目录解析。旧`scripts/build_research_cycle_input_bundle.py`仍保留原日期默认值及相对项目根的输出路径，但内部只转交同一CLI，不再复制生成流程。

输入继续明确标为`pseudo_vintage`，沿用既有年度90天/月度15天发布滞后假设及合成retrieval_time，不是真实历史发布/抓取时间。转换不抓取新数据、不训练或发布模型、不解除严格vintage限制、不改变当前网页和Desk服务。

2026-10-20：新增路径/旧入口/拒绝覆盖/Q1上一季度回归；相关legacy、CLI、cycles、research-inputs共266项通过，ruff通过。v9源码包→wheel、新venv冻结依赖68包兼容检查通过；从/tmp以Python -I实际运行site-packages内CLI，以合成面板生成8条观测/7个周期先验/2个状态日期，并确认重复输出被拒绝。这是安装与数据路径验收，不是正式市场研究结果。产物在Desk迁移根`cycle-input-cli-wLzoX7/`，包在`candidate-v9-input-packages/`；现有14175仍v8d，没有切换服务。

年度/月度面板生成、C4及C5/C7研究已提供下述安装入口；仍须交付各自真实输入，不能据此宣称全部采集和研究刷新可迁移。

## 原始数据生成研究面板

安装后的CLI与旧源码脚本复用同一筛选实现，输入根、日期窗口与新输出目录显式分开：

```sh
seven-cycle build-research-panels \
  --project-root /absolute/path/raw-inputs \
  --destination /absolute/path/new-prepared-inputs \
  --annual-start 1700 --annual-end 2024 \
  --monthly-start 2000-01-31 --monthly-end 2025-12-31
```

日期是示例，不代表数据已经更新。输入根默认当前工作目录，需要三份文件：

- `data/indicator_panel_annual_very_long_history_year.parquet`
- `data/indicator_panel_monthly.parquet`
- `output/cycle_bandpower_scores_monthly.csv`

输出为两份研究Parquet及两份选择CSV，可直接作为`build-cycle-inputs --project-root`的输入根。年度至少80个观测、月度至少60个观测、家族去重、扩展序列与值类型优先级、累计/收益排除及缺失值语义沿用旧实现。旧两个脚本保留原窗口与原位输出，仅作兼容Adapter。

目标必须不存在，已有目录或目标符号链接均拒绝；两套面板及报告全部成功后才从临时目录发布，缺文件、错误元数据、无合格序列或非法窗口不会留下半套目标。不会抓取数据、生成真实vintage、刷新网页或切换服务。

2026-10-20 v10：相关legacy/CLI/cycles/research-inputs共275项、独立安装包9项通过，ruff通过；sdist→wheel及新venv冻结依赖（含测试依赖共76包）兼容检查通过。从/tmp使用安装CLI与真实输入生成年度325行/118列、月度312行/226列，面板和选择CSV与迁移前实现逐对象完全一致。继续生成15,863条观测、29个年度成员、27个月度成员和60个状态日期，仍明确为pseudo_vintage。安装后的console命令亦成功生成两套面板；重复目标被拒绝。证据在Desk的`runtime/project-migrations/seven-cycle-20261020-kVpugP/panels-v10-zMzgq8/`，仅隔离派生输出，不改原始数据。14175仍加载v8d，正式4174未动；未新增浏览器/Agent验收或提交发布。

## C4 桥接与资产统计

安装包可生成配对的C4桥接及资产统计，不再需要导入源码树的scripts：

```sh
seven-cycle build-c4-research \
  --project-root /absolute/path/c4-inputs \
  --features /absolute/path/monthly-c4-features.parquet \
  --through 2025-12-31 \
  --destination /absolute/path/new-c4-output
```

输入根的output下须有`c4_pseudo_realtime_prototype_2026-07-19.json`、`c4_c5_phase_display_prototype_2026-07-19.json`、`monthly_returns_20y.parquet`。根目录默认cwd，不读取安装位置；features相对路径也按cwd解释。特征表以月末日期索引，沿用PMI_FIELDS九项PMI水平及各自d1/d3、ppi_yoy及其d1/d3，不插值填缺。`--through`必填YYYY-MM-DD、按整月处理，仅为桥接目标月，不提供真实发布vintage或历史重建；早于基线末月拒绝。

需要联网时，显式用`--fetch-features`替代`--features`，沿用调用环境已配置的TUSHARE_TOKEN；不自动联网回退或保存凭据。本轮未调用真实联网分支，行为测试只替换取数函数。

成功目标含`c4_realtime_bridge_latest.json`、`c4_asset_statistics_current.json`、本次实际使用的`c4_bridge_features.parquet`，便于重复计算。沿用原历史截点验证、发布门槛、回归/非因果归因和缺失规则；已有目标/符号链接拒绝，验证/计算/序列化失败不发布半套目录，不刷新网页或切换服务。旧两个scripts仍接受原参数、默认路径和输出方式，仅转接同一实现；C5/C7原有统计复用保持兼容。

2026-10-20 v11：先复现11项失败，最终相关296项及干净安装13项通过，ruff通过。sdist→wheel、新venv按冻结uv.lock离线安装76包并兼容检查通过；从/tmp以Python -I实际加载site-packages。利用本地真实PMI/PPI面板、不补缺，2025-12窗口17个历史截点验证通过，C4输出及98项资产统计逐对象等于迁移前实现。PPI仅覆盖至2025-12，2026-06窗口明确拒绝六个缺失月份且不发布目标；不是数据已更新或实时模型验收。产物在Desk迁移根`c4-v11-8rkE0q/`；14175仍v8d，正式4174不变，无新浏览器/Agent/服务、无提交/推送/发布。

## C5 / C7 状态研究与资产关联

安装包依次计算C5、C7，再用本次结果计算历史资产关联，不导入源码树的scripts：

```sh
seven-cycle build-state-research \
  --project-root /absolute/path/state-inputs \
  --public-signal-dir /absolute/path/fred-inputs \
  --destination /absolute/path/new-state-output
```

输入根默认cwd，必须含`data/indicator_panel_monthly.parquet`及`output/monthly_returns_20y.parquet`。本地FRED目录需要`fred_VIXCLS.csv`、`fred_NFCI.csv`、`fred_BAA.csv`、`fred_AAA.csv`；省略目录时使用输入根的`data/raw/web_public`。显式相对路径按cwd解释，不按Python安装位置猜数据目录。

需要重新下载FRED时，用`--refresh-public`替代`--public-signal-dir`，仅写入新目标的临时准备目录，不修改原始输入；缺本地文件不会自动联网。目标必须不存在，已有目录或符号链接拒绝。

成功输出`c5_liquidity_state_research.json`、`c7_risk_appetite_state_research.json`、`c5_c7_asset_association.json`，并在`public-signals/`保留实际使用的四份CSV。任一步失败不发布半套结果。原状态模型、验证及发布门槛不变；历史关联不是已获准的资产收益预测。旧三个scripts保留原参数、默认输入/输出方式，仅作兼容Adapter。该命令不更新网页、API或Desk服务。

2026-10-20 v12：相关312项回归、干净安装11项及ruff通过；sdist→wheel，新venv按冻结uv.lock离线安装76包并兼容。从/tmp使用安装console命令和真实历史输入完整重算，210.14秒生成三份结果；与本轮重新计算的迁移前算法逐对象一致，仅排除`meta.generated`时间戳。四份FRED输入原样保留，重复目标被拒绝。C5观测截至2026-06、状态`state_direction_predictable`；C7截至2026-07、状态`short_horizon_regime_predictable`；两者publicationStatus均limited、assetForecastStatus均blocked，历史关联各98项。输入为最新修订历史序列，不是真实发布时间vintage或实时数据。真实联网分支未调用。证据在Desk迁移根`states-v12-cRE7cm/verification.json`；14175仍v8d，正式4174未动，无新浏览器/Agent/服务或提交发布。

## 联合资产预测与同步参照

安装包与旧脚本共用同一模型实现，不再从安装位置推断研究目录：

```sh
seven-cycle build-asset-forecast \
  --project-root /absolute/path/forecast-inputs \
  --destination /absolute/path/new-forecast-output \
  --workers 1
```

输入根默认cwd，output下需要`monthly_returns_20y.parquet`、`c4_realtime_bridge_latest.json`、`c5_liquidity_state_research.json`、`c7_risk_appetite_state_research.json`。destination必填且不得已存在，workers默认1、须为正整数；相对路径按cwd解释。旧script保留原生路径及CIRCLE_FORECAST_WORKERS/CIRCLE_REFRESH_SYNC_REFERENCE兼容，不作为安装包输入定位依据。

命令重新计算异步预测和同步参照，完整成功后发布`asset_cycle_state_forecast.json`与`asset_cycle_state_forecast_synchronous_reference.json`；不使用或覆盖原仓库缓存，失败不留下半套目标。参考路径元数据为同目录文件名，旧script仍保留原output/相对路径。保留原1/3/6月模型、滞后规则、样本外及发布门槛，不自动更新网页、API或Desk；未通过预测继续阻断，不生成组合权重或交易指令。

2026-10-20 v14：相关320项/干净安装4项及ruff通过，sdist→wheel、新venv冻结76包兼容。从/tmp以Python -I执行安装console，原油/国债指数真实完整历史子集在1/2进程下，两份结果业务字段均等于迁移前算法，仅排除生成时间及参考路径。异步截至2026-07、同步截至2026-06，两资产最终各期限仍阻断。子集会影响类别上下文，不代表98资产全量验收，也不是真实vintage或实时数据。证据在Desk迁移根`forecast-v14-XuZaND/`，运行候选仍v13、正式4174未切换。

## Desk / newma

### Desk启动已安装版本

Desk的`dev-stack`支持显式选择安装入口与已构建产物；这些是启动配置，不是IDE源码目录配置。启用前先确认端口、已有进程及产物配对，不因修改此配置重启正式服务：

```sh
export NEWMA_DESK_SEVEN_CYCLE_WORKSPACE=/absolute/path/to/runtime-workspace
export NEWMA_DESK_SEVEN_CYCLE_EXECUTABLE=/absolute/path/to/venv/bin/seven-cycle
export NEWMA_DESK_SEVEN_CYCLE_PRODUCT_ROOT=/absolute/path/to/products
export NEWMA_DESK_SEVEN_CYCLE_CATALOG_ROOT=/absolute/path/to/products/catalogs
export NEWMA_DESK_SEVEN_CYCLE_WEB_ROOT=/absolute/path/to/web/dist
```

路径相对WORKSPACE解析。显式EXECUTABLE不存在直接失败，不回退旧包；指定任一数据根时明确传递product/catalog/web三根，catalog缺省为product下的catalogs，web缺省为workspace下的web/dist。指定安装入口或数据根时不执行Desk旧seed脚本；原生本就没有该脚本，也不调用。未显式配置的旧Desk快照保留原启动/seed行为，原Catalog修复仍须显式选择。兼容NEWMA_DOCK_/VIBEDESK_前缀。业务健康以候选`/healthz`的catalog/web/deployment为准，不以进程存活代替。

2026-10-20 v13：真实Desk描述符在独立workspace启动v12安装CLI与配对10月产物，health正常、5份网页数据及4组API业务结果一致。14175候选deployment=`2db08f5235e61813`，真实CLI历史查询和自动回读通过。旧隔离API因版本落后拒绝researchScope，换当前源码后正常；Desk同标签reload空白仍未定位，单次手动重试可恢复。此配置及局部验收不等于正式发布或外部newma已联通。当前路径/任务ID以QODER_HANDOFF顶部为准。

四页共用 `web/src/lib/vibedesk.ts` 可选 iframe Adapter。独立网页不启动 Desk Gateway，也不直接执行 CLI；嵌入时向宿主提供当前页 Context，结构化数据不可用时提供 DOM/HTML，市场曲面可返回受限 PNG。
跨域嵌入必须在构建前显式配置审核过的父 Origin，例如
`VITE_NEWMA_DESK_PARENT_ORIGIN=http://127.0.0.1:5892 npm run build --prefix web`。
完整 CLI `build` 同样继承这个环境变量。该值为精确 HTTP(S) Origin，不带路径或结尾斜杠；
未配置时只信任页面自身 Origin，不从 referrer、ancestorOrigins 或消息自报地址授权。
部署到不同宿主 Origin 需重新构建；不要用此候选直接替换现有跨域正式部署。
独立模式保留显式 `data-theme`，未指定默认浅色；握手成功后跟随宿主。
Bridge 在宿主实例或页面 provider 更新后丢弃旧异步 Context/PNG，不给旧结果换上新实例身份。
核心行为测试：`npm run test:bridge --prefix web`。
七周期页已提供 `research.select-cycle`：显式选择C1–C7及模型细节展开状态，仅调整当前页面，不更新研究数据。Bridge只执行宿主grants授权的动作；React提交新状态后才返回结果并发布Context，页面卸载或手动覆盖时不伪报成功。
市场页提供 `research.configure-market`：必填view（heatmap/2d/3d）、timeRange（5y/20y/50y/all）和trackIds（1–24个已加载且不重复的ID）；showForecast默认false，热图不接受true。comparisonDate仅热图有效，必须落在所选轨道窗口内，省略则与页面共用最近完整月回退规则；回执报告实际选择、范围、预测层及截面月。可选轨道ID/名称见Context的data.summary.availableTracks。该动作仅改页面，不抓取或刷新研究快照。校准页保持只读；不能把局部动作验收当作四页全部完成。
资产联合预测提供`research.configure-asset-forecast`：必填horizon（字符串1/3/6），可选query、majorCategory、category、onlyQualified、attributionFilter、sortKey、assetId。省略筛选恢复默认；指定资产必须在目标筛选结果内，否则拒绝，不默默换选。页面和Context共用派生逻辑，回执等待React提交；手动改条件或卸载会取消待确认结果。该动作不修改下方单周期历史映射、不刷新研究输入。可选资产见data.summary.availableForecastAssets。v6真实CLI动作与自动回读已验收3个月原油。

单周期历史查询提供`research.configure-asset-history`：必填cycleId（C1–C7），可选phase/query/category/confidence/sortKey/assetId。C4放缓相位为downturn，其余为slowdown；impact排序仅C4、spread仅其他映射。省略筛选恢复目标周期默认，省略assetId关闭详情；指定ID必须来自`data.summary.availableHistoryCycles`中目标周期的assets并在目标筛选内。C4原油ID为`商品||原油`、C5为`商品::原油`，不可沿用当前周期ID或全局替换。C1/C3/C6阻断周期仅能传cycleId查看说明。页面、Context和回执共用`assetHistoryView`，React提交后回执，手动覆盖/卸载取消待确认结果；不刷新研究数据，不改联合预测。

2026-10-20验收：原生/解压包30项Bridge行为测试和完整安装包build通过。正式10月研究输入从Desk的`runtime/circle-refresh.mcJNyP/output`与正式run的`research_data/`配对导出为`research-20261004/`，源码包v7b在`october-m6ar48/`独立构建；父Origin为5893，14175候选health ok，run=`2026-10-04-7180d6f1dc9e-5569654b27ad`。五份HTTP网页数据与正式完全一致，四组API业务字段除run_id外一致；不复制数据库、不覆盖原生public，不把新catalog身份误当业务数据变化。独立/Desk实际C5原油历史收紧样本83、-24.01%/33.07%，真实CLI动作及回读成功。统计截至2026-08、联合预测截至2026-09，不是实时行情。详细任务/截图在两仓HANDOFF；正式4174仍不一致，未切换或发布。

资产Context区分data.summary.jointForecast与singleCycleMapping：前者是C4+C5+C7联合预测；后者的phase是历史筛选，currentState是已有最新观测，二者不能互相替代。预测源current仅通过freshnessRelativeToBuild标为相对构建时点，不保证当前实时。

原生业务改动经逐文件审阅回到 Desk 发布快照，不覆盖双方研究 JSON、数据库、密钥或未提交研究修改。代码保存、进程实际加载和固定提交发布分别记录。

## 本轮仍待验收

- 四页基础显示与导航已在v8d候选实测：独立320px、Desk深色390px、浅色桌面无整页溢出；全控件/全部主题组合与完整业务双模式仍需验收。精确父Origin和迟到消息隔离已有行为回归。
- 注册与验收必要页面动作；外部 newma 真实宿主联调。
- 正式10月配对数据已在独立候选验证，正式部署一致性仍未修复；派生快照交付和周期发现安装入口已验证，其他旧研究脚本仍需逐项核对，不代表全套原始输入/研究刷新已可迁移。
- Chrome旧标签重载偶发空白、IAB跨域导航点击失败仍待定位；v8d同标签一次reload成功不证明根因解决。静态研究版2026.08及资产“已更新”已统一为非实时研究快照，C4滞后仅指构建时，网页刷新不更新数据。
- 固定提交、发布快照同步。当前候选不等于正式版本。

2026-10-20 v8d实际候选：Desk迁移根seven-cycle-20261020-kVpugP/responsive-verified-owk6Ca，解压源码与products分离；14175/PID58363使用既有冻结环境的安装CLI从/tmp启动，deployment=6a38cca9848259f5。原生/解压包各30项Bridge测试、sdist→wheel、完整CLI构建通过；五份HTTP网页数据与research-20261004一致。此轮仅前端调整，不冒称新Python环境重装。正式4174与原生public未改；未回同步Desk正式快照、提交或发布。具体截图和接续信息见QODER_HANDOFF最新记录。
