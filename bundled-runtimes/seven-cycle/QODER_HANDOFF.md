# 周期研究交接 · 2026-10-20

## 2026-10-22 固定健康修复与安全补丁

本次仅固定6个工程文件及本交接：网页/API配对健康检查、3份不依赖可变研究数据/调用目录的测试、Vite6.4.5锁文件。保留原有README、研究文档、output和web/public研究修改，不把它们混入本次版本。

原生、Desk快照和`cycle-vite-patch-20261022-vVg3ua/source`在377个工程文件范围一致。本轮重跑候选前端39项；从/tmp使用既有健康候选的非editable安装环境，清除源码搜索路径后259项后端/CLI/配对回归通过（64.69秒）；该环境Python实现与Vite候选一致，不称全新安装。完整构建和双模式实机证据沿用此前同源码候选。

Desk新描述符与当前4174/PID88974的安装入口、products/catalogs/web路径一致，health ok、deployment9450c83a46b68bf4。恢复模拟及相关57项通过；旧总监督器84688仍未加载新描述符，不能说故障恢复已在线生效。用户确认Chrome普通标签同源最小页正常，后续不再以受控Chrome空白阻断业务源码收口；真实newma/云端鉴权仍单独待验。

按既有授权做限定本地提交，不推送、不重启、不发布、不修改研究数据或数据库。准确提交号由Desk版本清单和交接记录。

## 2026-10-22 Desk加载复验

Desk共享Shell恢复声明式iframe src，119项核心回归、类型及正式构建通过；周期业务源码未改。Codex内嵌浏览器首次与刷新通过，Chrome正式周期刷新仍超时、一次手动重试后页面/握手/Context恢复，股票策略也复现Chrome初始超时，不能称周期根因已修。4174仍配对候选PID88974，其他正式服务不动，无提交推送。详情见Desk docs/desk-frame-retry-acceptance-2026-10-22.md。

## 2026-10-22正式本地4174已受控切换

用户明确许可后，Desk只重载周期4174至Vite6.4.5配对候选：PID88974、deployment9450c83a46b68bf4，health ok/available。正式HTTP严格配对和四页实操/Context通过，仍批准10月输入；旧产物保留，不改本仓研究数据/数据库或版本锁，无提交推送。Desk首次打开及两次整页刷新仍空白，重试恢复，不能写为完整通过；总监督器未热加载新.env，其他正式服务未动。证据与回退见Desk docs/cycle-local-switch-acceptance-2026-10-22.md。以下“未获切换许可/正式仍旧PID”是历史记录。

## 2026-10-22 Vite定向安全补丁（最新候选）

本仓/Desk的`web/package-lock.json`仅更新Vite6.4.3→6.4.5的3行字段，保留既有范围，其他依赖与业务代码未变。新候选冻结npm安装、审计0告警、39项行为测试、新sdist→wheel、Python3.12冻结68包兼容、安装CLI完整build及真实HTTP严格配对/业务数据等价通过。材料在Desk `runtime/project-migrations/cycle-vite-patch-20261022-vVg3ua/`，deployment=`9450c83a46b68bf4`；14177临时服务已停止。

未重跑浏览器双模式或Agent，之前四页实机证据仅用于未改业务源码；正式切换后仍须复验。正式4174和两侧旧node_modules未更新，本仓保存锁文件不等于当前开发/正式进程已加载。正式切换仍待明确许可，未提交/推送/部署/推进版本锁。详情见Desk `docs/cycle-vite-patch-acceptance-2026-10-22.md`；下节“Vite未修”仅为此前记录。

## 2026-10-22 新健康wheel实机补验（最新）

Desk用同一新sdist解压`desk-source/`及新建`products-desk/`，独立14178和隔离Desk5894四页筛选/详情/刷新与真实Context一致，严格数据配对通过；deployment=`e49c4b49c5712c63`，研究输入仍批准10月快照。临时14178/8998/5894和67/68标签已关闭，正式4174未切，无新Agent任务或提交/推送/部署。证据在下节候选的`browser-context-acceptance.json`，完整记录见Desk `docs/cycle-health-pairing-acceptance-2026-10-22.md`新增实机节。

同一锁文件本次npm审计新增Vite6.4.3一项high开发工具告警，不再沿用旧0告警。官方注册库已有6.4.5且在既有范围内，尚未升级；下一步单独隔离定向修复、检查差异并测试/构建，再成对回传，不整仓audit fix。正式切换仍待明确许可。

## 2026-10-22 健康配对漏报修复（当前候选）

本仓与Desk成对修改`src/seven_cycle_platform/api/app.py`和`tests/api/test_api_smoke.py`：配置web_root却缺网页deployment声明时明确degraded/inconsistent，读取仍可用；纯API模式保持正常。先复现失败，再修正。原生98项相关回归、新wheel从/tmp以隔离路径测试259项、前端39项及完整安装CLI构建通过；范围重叠不相加。

最新候选为`/Volumes/PSSD/Projects/newma-desk/runtime/project-migrations/cycle-health-pairing-20261022-RS7u67/`，deployment=`a3952e06ce9c2b73`，优先于下节旧包。真实14177缺声明→恢复通过，首页/资产读取未中断；严格配对与5网页JSON/9业务表等价通过，沿用批准10月输入、不改研究结果。临时服务已停止，正式4174/PID33156仍旧版本/inconsistent，未获周期切换许可，不自动替换。未重新跑浏览器双模式，上一轮前端实机证据仅沿用；未提交/推送/部署/更新版本锁。详情见Desk `docs/cycle-health-pairing-acceptance-2026-10-22.md`。

## 2026-10-22 配对候选复验（优先于下方旧运行记录）

Desk已从固定ec08c90与批准10月bundle在新目录完整构建：独立与隔离Desk四页实操/刷新/Context通过，5份网页数据及9张业务表与此前批准版本相同。安装wheel从/tmp测试253项、前端39项、Desk描述符8项通过；不改模型或研究数据。仅本仓与Desk成对修`web/tests/assetHistoryView.test.mjs`、`web/tests/auditPage.test.mjs`的可变public数据耦合，以及`tests/integration/test_duckdb_catalog.py`缺显式project_root的测试辅助路径。工作区保留原有dirty研究数据，本轮没有用于运行候选。

材料在`/Volumes/PSSD/Projects/newma-desk/runtime/project-migrations/cycle-paired-release-20261022-nslVqw/`，详见Desk `docs/cycle-paired-release-acceptance-2026-10-22.md`。本轮临时14177/14178/8998/5894及65/66标签已关闭，候选产物保留。正式4174/PID33156仍旧版本/deployment inconsistent，未获本轮周期切换许可，不自动切换。无提交/推送/远端部署/固定版本更新；真实外部newma及Electron、历史偶发iframe空白根因仍待验。工程独立构建及源码配对已完成，不再沿用旧“尚未固定/完整0/15”否定该事实。

## 独立工程固定版本

- 原生与v17b已验收解压包在源码、测试、配置、脚本和前端依赖范围375文件一致。已将其中62个候选差异合入Desk源码快照；保留Desk专属seed脚本，不复制products、数据库、web/dist或当前研究输入。
- 本次206项Python工程/安装入口回归、38项前端/Bridge测试和TypeScript/Vite构建通过。此前v17b干净安装、完整CLI构建和四页双模式证据沿用，不重跑云端模型任务。
- 工程源码将固定为本次限定本地提交，准确版本由Desk的`config/desk-project-versions.json`记录；下方旧HEAD和“未提交”是历史状态。`projects:sync -- seven-cycle to-desk|to-source`默认预览，业务/测试/脚本按共同提交同步；依赖/配置单独审核，研究输入和部署产物不跟代码回传。
- 实际外部newma结果闭环、正式4174原有deployment不一致仍待验/待处理；工程固定不代表正式运行版本切换。本轮不推送、不重启、不部署。

## 维护路径

- 原生主源码：`/Volumes/PSSD/Projects/1周期模块`（本目录）。
- Desk 发布快照：`/Volumes/PSSD/Projects/newma-desk/bundled-runtimes/seven-cycle`。
- 当前原生 HEAD 仍为 `b54dae62c3421d2c64bde3a459e756e954ec4d60`，有大量原有及本轮未提交修改；HEAD 不能代表候选内容。
- 正式4174仍为原 Desk 快照进程，未切换。IDE工作区现已绑定原生目录，不要把保存代码当作正式已加载。

## 本轮完成

2026-10-20 v17b刷新恢复已在最终候选实机通过：业务项目自己保存当前页和公开UI偏好，按可信父Origin/用户/工作区/Mod隔离，独立模式使用单独scope；不存研究数据、凭据、聊天或任务状态。修复Desk默认iframe带__newma_mod_version参数导致路由恢复失效，显式深链仍优先。原生与解压包38项前端测试、类型/Vite及新venv68包兼容/安装CLI完整build通过；14175现为view-session-v17b-OYLYjw（PID54638/session57125，deployment=77f1ebdd831a830c），5893/8997未重启，正式4174未动。Chrome现有Profile验证整Desk刷新保留C5/展开、2D/20年、校准页及资产两层筛选/选中详情；最终独立入口验证C2深链覆盖旧C5及2D/20年刷新恢复。五份网页数据等于10月配对快照，九张业务表等于v16离线产物，四API仍98/1/24/98条；compare仍stale/partial，其余freshness unknown。无新Agent任务，隔离库仅2项completed，未捕获warn/error。首版v17实际失败及修正、截图、启动记录见候选目录desk-integration-v17.md。历史偶发空白根因仍未定位，新Adapter真实Mod回传/Electron、正式一致性与固定版本仍待验收，完整0/15；无提交/推送/部署。以下旧运行记录仅为历史，不能覆盖本条。

2026-10-20 v16已接入隔离Desk：确认隔离库仅2项completed、无queued/running后，正常停止旧v15/PID59556；14175现为deps-v16-145WMt的新venv/products/解压web（PID42152，exec session50168），deployment=82bbf551b78ccb33、health ok，Shell5893/PID10422及API8997/PID62807未重启，正式4174未动。五份网页JSON仍等于10月配对快照；四组API分别98/1/24/98条，compare仍stale/partial，其余freshness仍unknown，未改成实时。Chrome现有Profile实际完成四页导航、C5选择、3个月商品筛选；隔离库Context与页面一致，原油1条、收益6.1%/波动27.7%，非配置建议。一次整Desk重载ready/acknowledged/received通过、未捕获warn/error；但刷新会回市场首页且筛选重置，列为待完善，历史偶发空白根因仍未定位。证据见同目录desk-integration-v16.md、desk-audit-v16.jpg。此轮无新Agent任务、业务源码改动、正式快照同步、提交/推送/部署；真实新Adapter结果回传与Electron、正式一致性及固定版本仍未过，完整0/15。以下旧运行记录保留为历史。

2026-10-20 真实云端基础验收：按用户许可，Chrome现有登录下新建两测试会话，约5秒明确回复、用户停止明确取消、切页后源任务约3分钟后台完成且目标仍空白，三项均有实机证据。未读旧聊天正文、调用工具、改模型/权限或部署，无已知在途任务。证据在Desk的`deps-v16-145WMt/hermes-live-acceptance.md`和4图；这是线上既有Runtime/会话验收，不是本地新Adapter的Mod结果回传或Electron通过。切页恢复提示和约180秒等待保留为实际限制；不可误写最新宿主已部署。周期14175仍v15，新v16仍待Desk复验，完整0/15。

2026-10-20 v16依赖修复（运行候选仍v15）：仅更新`web/package-lock.json`，保留原有package.json测试脚本及框架版本范围。7项告警来自react-router/dom、PostCSS/nanoid/source-map-js及Browserslist/baseline；采用已声明范围内兼容修复，锁定router7.18.4、postcss8.5.31、browserslist4.29.4等11个包，无新增依赖。当前只用BrowserRouter，不启用受路由告警影响的RSC服务端action；其余主要为构建工具链风险，不将审计等级直接等同本页可利用程度。

新sdist→wheel位于Desk迁移根`deps-v16-145WMt/packages/`，独立解压npm ci（忽略安装脚本）、33项Bridge/页面测试、tsc/Vite构建与npm audit均通过（0告警）。新venv按原uv.lock离线安装68个运行包，兼容检查通过；从/tmp实际运行安装CLI完整build，沿用research-20261004配对输入，run不变、deployment=`82bbf551b78ccb33`。Python src、web/src与web/tests同v15逐目录比较一致，不改研究模型。

临时14176实际HTTP五份网页数据等于配对快照、四组API业务字段等于v15；Chrome既有Profile完成市场→周期→资产→校准四页实际导航，数据显示且未捕获warn/error。证据为同目录`http-verification.json`与`standalone-audit-v16.jpg`。临时服务PID55173已正常停止；14175仍v15，正式4174与Desk发布快照未动。因此0告警只适用于新锁文件/新安装候选，不能声称运行v15或正式依赖已修。尚需将新候选集成到Desk复验、真实宿主验收及固定版本；未提交/推送/部署，完整0/15。用户已允许独立云端合成测试会话，后续只在该测试范围验收，不读旧会话。

2026-10-20 父项目对齐（优先于下文历史记录）：用户提供的父线程`019fe457-442d-7372-8009-2280e63f2261`实际工作目录为`/Volumes/PSSD/Projects/MonkeyAI`。WebUI入口是`MonkeyAI-web/modules/agent-console/static/desk_collaboration.js`，桌面入口是`MonkeyAI-desk/src/renderer/src/screens/Layout/useModAgentResults.ts`及`Chat/hooks/useModAgentDraft.ts`；共享Runtime为`Newma-runtime/src/hermes-adapter.mjs`。不再寻找或使用已废弃Newma-dsh。

WebUI与桌面结果观察均已接源码：页面草稿经用户确认后，绑定实际任务身份回传本轮明确结果，不取历史末条、不新增Agent执行器，Hermes执行权及Desk独立CLI/Copilot保留。此前真实WebUI隔离挂载已验证Context/能力协商；桌面14组274项、Runtime15项、类型及生产构建通过，但不是Electron或真实模型验收。本轮只复核入口并同步交接，没有调用模型、部署或同步正式快照。

当前周期仍v15。Desk同标签按DOMContentLoaded及ready/acknowledged/received等待的三轮重载通过，历史偶发空白未复现、根因仍未定位，不能标记已修。剩余为真实Electron/Hermes完成、取消及切页迟到结果验收，正式deployment一致性、7项npm告警评估及固定版本同步；不再把“父项目入口待提供”列为缺口。仅整项目验收后限定本地提交，完整仍0/15。

2026-10-20 v15：AuditPage/types支持WDI多缓存和旧单缓存，页面逐条路径/时间与Context的longPanelSources共用结果，坏时间保持未知。新增3项组件/Context回归，前端共33项通过；不改研究数据或算法。Desk共享iframe忽略初始blank误报就绪，48项/全Shell230项及隔离生产构建通过，但首次导航根因未解决。

Desk迁移根`integrated-v15-Xa9yCp/`包含新sdist/wheel、冻结76包兼容的新venv、独立解压前端和完整build产物。沿用10月配对输入，run不变、deployment=cfb63dcdd949429e；五份网页数据/四组API业务字段与升级前v13一致。确认两任务均completed后14175换为v15/PID59556/session70572，API8997/Shell5893未重启；正式4174未动。独立及Desk校准页WDI四缓存和隔离库Context一致，无捕获warn/error；同Desk标签首次reload仍timeout，手动重试一次恢复ready/acknowledged/received。截图desk-audit-v15.png、standalone-audit-v15.png已查看；重复14176服务/独立标签已关闭。

7项npm告警（2 moderate/5 high）未自动升级；真实外部newma入口、首次导航可靠性、正式deployment与固定版本仍待完成。此次文档更新晚于v15打包。无新Agent任务/正式快照同步/提交/推送/部署；仅整项目验收后可限定本地提交，完整0/15。以下历史状态以本条为准。

2026-10-20 v14：联合资产预测实现迁入`src/seven_cycle_platform/legacy/asset_cycle_state_forecast.py`，旧script保留原路径、环境参数和参考路径元数据；新CLI `build-asset-forecast`显式输入/新目标/进程数，预测与同步参照配对成功才发布，不覆盖既有目录、不使用原仓库缓存。未改模型、双时钟或发布门槛。相关320项、干净安装4项、ruff及sdist→wheel通过；新venv冻结76包兼容。从/tmp以Python -I运行安装console，真实原油/国债指数完整历史子集用1/2进程计算49.17/28.90秒，两份JSON业务字段均与保存的迁移前实现相同，仅排除生成时间及参考路径。异步截至2026-07、同步截至2026-06，两个资产各期限最终仍阻断；子集类别上下文不同，不能等同98资产全量或实时验收。最终包/基线/证据在Desk迁移根`forecast-v14-XuZaND/`，包用`packages-final/`。

浏览器补验曾确认iframe为about:blank且空body，延后首次导航的尝试无效已完整撤回，ModuleFrame47项通过；原标签受控等待后7次重载成功，根因仍未定位。14175仍v13（health ok）、8997/5893及正式4174进程未替换，本轮无新Agent/常驻服务/正式快照同步/提交/推送/部署。外部newma、完整业务/重载可靠性、正式deployment一致性和固定版本仍未通过，完整0/15。用户允许整项目验收后限定本地提交，当前不提前提交。

2026-10-20 v13整候选：v12最终sdist在Desk迁移根`integrated-v13-26LBRy/`独立解压，前端npm ci/30项Bridge测试通过，从/tmp以v12干净环境安装CLI完整build（含tsc/Vite）。输入沿用配对10月快照，不换成v12较早重算数据；run=`2026-10-04-7180d6f1dc9e-5569654b27ad`，deployment=`2db08f5235e61813`。五份网页JSON与配对输入一致，四组API业务字段与升级前v8d一致，比较仍partial/stale。原生业务源码未新增修改，正式4174/原生public未动。

Desk真实启动描述符已支持显式安装入口和product/catalog/web数据根，修复强制调用本项目不存在的Desk专用seed脚本，相关30项通过；配置见独立运行说明。14175/PID42660已加载上述products/web及`states-v12-cRE7cm/venv/bin/seven-cycle`，旧v8d已正常停止。API8997现为当前源码/PID62807，隔离state=`runtime/project-acceptance/seven-cycle-vy7p36x_`，Shell5893不变。旧API不认识researchScope引起一次422且未创建任务；换当前源码后真实CLI动作task-333fb72c1b9d43d691670e7c0691be82与自动回读task-0b1dc1950c4949ebbdf5a630e3a17997完成。C5收紧/原油1项、83样本/-24.01%/33.07%、截至2026-08，与页面一致，不是未来预测。截图`integrated-v13-26LBRy/desk-agent-v13.png`已保存查看。

独立四页及Desk市场2D/C5/资产/校准导航通过，但同一Desk标签reload仍空白，手动重试一次恢复；没有用新标签掩盖，根因未定位。尚缺完整业务/重载可靠性、真实外部newma、正式deployment一致性及固定版本。用户再次授权整项目验收后限定本地提交，当前未达门槛，无提交/推送/部署，完整0/15。以下为历史记录。

2026-10-20 v12：C5/C7状态及历史资产关联迁入安装包`legacy/c5_liquidity_state.py`、`c7_risk_appetite_state.py`、`state_asset_association.py`。旧三个scripts保留原调用/参数和默认路径；安装代码不再导入scripts。新`build-state-research`显式输入根、FRED目录和新目标；本地文件与主动下载二选一，无隐式联网。三份JSON及实际FRED输入全部成功后发布，失败不留半套结果，不覆盖原始输入/既有目标。不改模型、参数或发布门槛。

相关312项、干净安装11项及ruff通过；sdist→wheel、新venv冻结依赖离线安装76包兼容。从/tmp实际运行安装console命令，真实历史输入完整重算耗时210.14秒；三份JSON与本轮重算的原算法一致，仅排除meta.generated，四份FRED输入原样保留、重复目标拒绝。C5截至2026-06、state_direction_predictable；C7截至2026-07、short_horizon_regime_predictable；均limited，资产预测仍blocked，历史关联各98项。不是真实发布时间vintage或实时数据，未实际调用联网分支。包、旧实现、真实计算基线及verification.json在Desk迁移根`states-v12-cRE7cm/`。

14175仍v8d，正式4174未动；无新浏览器/Agent/常驻服务、提交/推送/发布或Desk正式快照同步。下一步收口整个安装候选及生产所需输入链路，不为源码项目内部探索脚本盲目增加CLI。完整业务双模式、实际外部newma及固定版本仍待完成；用户允许整项目验收后限定本地提交，当前未到门槛，完整0/15。以下为历史记录。

2026-10-20 v11：C4桥接与资产统计实现迁入`legacy/c4_realtime_bridge.py`、`c4_asset_statistics.py`；旧两个scripts仅兼容Adapter，原计算/参数/默认路径不变，C5/C7私有统计函数导入兼容。安装CLI新增`build-c4-research`，显式原始根、through和新目标；本地特征与联网获取二选一，不静默联网。配对结果和实际特征一起发布，验证/统计失败不留下半套结果，已有目标/符号链接拒绝。

相关296项、干净安装13项及ruff通过；sdist→wheel，新venv冻结依赖离线安装76包并兼容。/tmp中Python -I实际加载site-packages，用本地真实PMI/PPI原值及原差分（不补缺）在2025-12窗口通过17个历史截点，C4及98资产统计与迁移前算法逐对象完全一致。PPI只到2025-12，因此2026-06缺失六个月被明确拒绝且无输出；不宣称实时或真实vintage，也未实际调用联网取数。包、旧脚本基线、验证脚本及JSON证据在Desk迁移根`c4-v11-8rkE0q/`。

14175仍v8d、正式4174及原始输入未动；无新浏览器/Agent/服务、无提交/推送/发布或Desk正式源码同步。仍须迁移其余刷新路径、收口完整双模式、实际外部newma与固定版本；未达到整项目限定提交门槛，完整0/15。以下为历史记录。

2026-10-20 v10：年度/月度面板算法迁入`legacy/annual_research_panel.py`与`monthly_research_panel.py`，安装CLI新增`build-research-panels`；两个旧脚本仅保留兼容Adapter，原筛选与旧默认窗口不变。三份原始输入、窗口、新目标目录显式配置；目标已存在/为符号链接均拒绝，双面板成功后统一发布，不留半套结果。未改研究模型、原始数据或uv.lock。

相关275项及干净安装包9项通过、ruff通过；sdist→wheel、新venv冻结依赖76包（含测试）兼容检查通过。安装Python -I与console命令从/tmp实际处理原生真实数据：年度325×118、月度312×226，面板及选择CSV与旧实现完全一致；接续build-cycle-inputs得到15,863观测/29年度成员/27月度成员/60状态日期，仍为pseudo_vintage，不代表实时或真实历史发布时间。包、旧算法基线、验证脚本及隔离结果在Desk迁移根`panels-v10-zMzgq8/`。

14175仍v8d，正式4174未动；本轮无新浏览器/Agent/服务、无提交/推送/发布、未回同步Desk正式源码。剩余其他采集/研究刷新路径、完整双模式、实际外部newma及固定版本同步。用户允许整项目验收后限定本地提交，但当前尚未达到门槛，完整0/15。以下为历史记录。

2026-10-20 v9输入入口（只新增安装包能力，不替换v8d网页服务）：安装CLI新增`build-cycle-inputs`，从显式输入根读取两份Parquet与两份选择CSV，配置与输出可独立放置。日期/验证截点/输出显式必填，复用既有ResearchCycleInputRequest与序列化，不引入另一套研究算法；旧build_research_cycle_input_bundle.py只转交CLI，原2025日期默认值和根目录相对输出兼容。修复as-of在1月至3月30日时上一季度计算空集合，正确取前一年12月31日。pseudo-vintage、发布滞后和非实时限制保持。

先复现4失败/2通过，再补旧脚本兼容用例；最终legacy/CLI/cycles/research-inputs相关266项通过，ruff/diff通过。sdist→wheel产物candidate-v9-input-packages，隔离cycle-input-cli-wLzoX7/venv按既有uv.lock安装68包并pip check通过；从/tmp使用Python -I实际加载site-packages内新CLI，合成输入8条观测/7个周期先验/2个状态日期，Q1先验日期2023-12-31、重复输出拒绝。验证脚本及结果JSON留在隔离目录；未使用正式数据。文档更新晚于此源码包，当前说明优先于包内旧交接。

本轮业务改动4文件：src/seven_cycle_platform/cli.py、legacy/research_cycle_input.py、scripts/build_research_cycle_input_bundle.py、tests/unit/legacy/test_research_cycle_input.py。上游面板生成和C4/C5/C7刷新仍有源码根输入依赖，本轮仅静态审查，不宣称全链路可迁移。14175保持v8d、正式4174及数据库未动；无浏览器/Agent新验收，无提交/推送/发布/Desk正式快照同步，五阶段仍0/15。

2026-10-20 v8d最新（覆盖下方旧候选路径）：快照文案及窄屏收口。AppShell常驻“研究快照/非实时/刷新不更新研究数据”；资产current/source_lag/stale仅相对快照截点，C4滞后标注构建时而非距今，Context同口径。校准来源表内部滚动，预测控件换行，模型列表按宽度自动排布，修复手机仍四列造成的指标溢出。8个前端文件与最终源码包一致，不改算法/数据/发布门槛。

原生及解压包各30项test:bridge通过，sdist→wheel成功，/tmp中使用inputs-Tnf09c/venv既有冻结环境及安装CLI完整build/tsc/Vite成功（本轮Python未变，没有另建/重装Python环境）。Desk迁移根seven-cycle-20261020-kVpugP中，包candidate-v8d-packages、解压responsive-verified-owk6Ca/seven_cycle_platform-0.1.0、产品responsive-verified-owk6Ca/products。run仍2026-10-04-7180d6f1dc9e-5569654b27ad，deployment=6a38cca9848259f5。14175/PID58363/session78490已加载；旧v8c/PID30552/session88655确认任务终态/无连接后正常停止。API8997/Shell5893沿用，正式4174/旧14174不动。health正常，五份网页HTTP数据与research-20261004逐对象一致。

Chrome真实独立四页320×844（client/scroll均305）、C4另验390（375/375）通过；Desk深色四页390（iframe333/333），浅色桌面四页1471/1471与导航通过。主题恢复深色、viewport已reset；同一Desk标签reload一次成功，无捕获warn/error。此前偶发空白根因仍未定位，不扩大为全控件/全部主题矩阵通过，也没有新增Agent/外部newma任务。截图在迁移根standalone-*-v8d-320.png、standalone-cycles-v8d-narrow.png、desk-*-v8d-light.png、desk-cycles-v8d-narrow.png，已查看。

后续转向其他原始研究脚本/输入交付、完整业务双模式、实际外部newma与固定版本同步；正式deployment一致性仍未修。本轮没有回同步Desk正式源码、提交/推送/发布；15项目完整交付仍0/15。npm依赖7项告警保留。以下记录仅作历史。

2026-10-20最新v7b及10月配对候选（以下旧记录仅作历史）：新增`assetHistoryView.ts`，C4与C2/C5/C7共用历史筛选/选中派生，AssetsPage统一UI handler；`research.configure-asset-history`支持周期、相位、搜索、类别、置信度、排序和资产，React提交后回执。C1/C3/C6只显示阻断，空筛选清选中。跨周期ID须取`availableHistoryCycles[].assets`，不猜分隔符；首次真实Agent误用C4 ID被正确拒绝后已补目标目录。Manifest0.1.5输入Schema与原生一致。原生及源码包30项test:bridge、完整CLI build/tsc通过。

正式10月输入已找到：Desk的`runtime/circle-refresh.mcJNyP/output`三份派生输入，与正式run保存的五份网页JSON通过配对导出。结果在Desk迁移根`seven-cycle-20261020-kVpugP/research-20261004/`。未覆盖本仓8月public或正式数据；构建时通过`--research-bundle-dir`显式选用。v7b源码包解压`october-m6ar48/seven_cycle_platform-0.1.0/`，npm ci --ignore-scripts，从/tmp以inputs-Tnf09c/venv和Python -I独立build。新run为`2026-10-04-7180d6f1dc9e-5569654b27ad`，deployment为`e1156684c3b878a0`，重建本机catalog，无数据库搬迁。

当前14175/PID17947/session31288加载october-m6ar48/products及其解压源码web/dist；旧v7b/PID58597已在任务终态后停止，14174仍旧v6。隔离API8997/PID57646、Shell5893/PID10422沿用，state为`seven-cycle-y6py2r1i`，不启用服务端重开截图。五份网页HTTP与正式4174和导出快照完全一致；资产98、当前周期1、预测24、6个月比较98行，除run_id外业务字段与正式相同；比较仍partial/stale。

独立/Desk实际C5、contraction、商品/原油1项、n=83、历史年化-24.01%、波动33.07%通过。真实CLI动作`task-f6bdc56e95994b0caea681d906cc3a2d`及回读`task-f0e16942a298450da85454d65266892a`成功，区分当前C5紧张加剧与历史相位，统计截止2026-08、联合预测截止2026-09。截图desk-history-october-agent.png、standalone-history-october.png在迁移根；旧8月v7b样本81/-28.03%/32.14%另存desk-history-v7b-agent.png，不能混用。

未完成：四页完整主题/窄屏；Chrome旧标签重载空白（新标签可用）、IAB跨域导航点击不可用；静态研究版2026.08和历史“已更新”措辞；其他研究脚本依赖；外部newma；固定版本同步。正式4174仍deployment inconsistent，未修。npm ci 7项告警未自动升级。未提交/推送/发布、未同步Desk正式源码；完整15项目交付仍0/15。以下数据/端口和缺口按历史阅读。

最新研究输入交付：新增`src/seven_cycle_platform/research_inputs.py`、CLI的`export-research-inputs`与`build --research-bundle-dir`、`tests/unit/test_research_inputs.py`。仅导出5网页+3后端派生JSON及清单；校验联合资产预测、历史统计、C4预测重复结果及日期，不声称全七周期一致。`circle_deployment.py`使用固定逻辑输入身份，移动快照目录不改变run，旧不传bundle的构建路径保留。

Desk迁移目录`inputs-Tnf09c/`含packages、新venv、源码解压、relocated-snapshot和products。源码包完整构建后，快照搬目录复建，仍为run`2026-08-22-7180d6f1dc9e-b2325d25826f`、deployment`414b03fc1689d34b`，foundation/deployment均复用。本轮重跑相关回归136项通过、ruff通过；新venv从/tmp以Python -I启动14175/PID69784，health=ok，五份HTTP网页数据与快照一致，API资产98/当前周期1/预测24/比较98条且同run。比较结果仍partial/stale。临时服务验收后停止，无浏览器/Agent新验收。已核对3个业务源码文件与解压包一致；随后文档更新未重出包。

操作命令见`docs/standalone-runtime.md`。这是8月构建快照、7月资产观测与6月C4输入，不是实时刷新或批准发布；不覆盖正式10月数据、不复制正式数据库。14174/8996/5892经进程核对仍v6链路。本轮未同步Desk发布快照/提交/推送/发布；下步为单周期历史查询动作、正式数据版本对齐、全页双模式、外部newma与固定版本。以下记录按历史阅读。

最新安装路径改造（不切换v6页面服务）：新增`seven-cycle discover-cycles --project-root ... --output-dir ...`，main默认cwd，四份输入先校验，结果写显式目录；旧robust脚本显式传_ROOT，兼容导出保留。报告prior结论来自本次计算，去掉写死的历史叙述及固定下一阶段频段。算法、配置和发布门槛不改。

最终cycles+CLI回归233项通过、ruff/diff通过。新增4项路径测试；扩大回归曾232通过/1失败，为既有C1配置35–70年与旧16.5带宽断言不一致，仅将断言更新35后全绿。迁移目录`discovery-efsHwJ/`含源码包、wheel、新建venv（冻结uv.lock，68包兼容）、合成输入及installed-results。实际从/tmp以Python -I加载site-packages并运行，产出5文件，不依赖原仓库源码。不是全量研究算法或真实市场有效性验收。

本轮业务文件：src/seven_cycle_platform/cycles/discovery.py、cli.py、scripts/discover_cycle_periods_robust.py；测试：tests/unit/cycles/test_discovery_paths.py及test_seven_cycle_engine.py。cli.py原有构建/修复变更保留。运行中的14174仍v6，正式4174未切；未同步Desk快照/提交/推送/发布。后续研究输入交付、其他旧脚本路径、单周期历史查询、外部newma与固定版本仍待做。

最新v6（优先于以下历史记录）：资产预测使用`assetForecastView.ts`统一页面和Context，新增`research.configure-asset-forecast`；父页拥有唯一provider/handler，等待React提交才回执。单周期映射通过子组件回传真实相位/筛选，C5不再沿用C4标签；C1无映射时为null。原生及解压源码24项行为测试、tsc、sdist→wheel和完整CLI构建通过，本轮再次复跑24项通过。

候选14174/PID57166/session93229，source-v6/deployment-products-v6，deployment=352ae3c65c204d86，health ok。隔离Desk8996/PID57286/session43593，state=seven-cycle-t7xv3xl9，Mod0.1.4，Shell5892未重启。真实CLI动作a0c2d40e83ad46108d71b4ac3cc399c1→自动回读6758202f6a1a4c94bd9095aa9ec584fd（均task-前缀）完成3个月/商品/原油/仅通过，1项有限发布估计；只读e57f85df14e241b999d748e95bc842cb正确区分C5历史“流动性修复”、当前2026-06“中性收紧”和上方联合预测。C1 Context相位清空。独立页空筛选、未通过研究值提示及3个月1项通过实测，无捕获error；截图desk-assets-c5-v6.png、standalone-assets-v6.png。

下一步仍需单周期历史查询动作、研究输入交付/安装路径、全页主题窄屏、外部newma和固定版本。空结果图默认大范围坐标及历史快照“已更新”文案待改善。未覆盖正式10月数据、未提交/推送/发布；最新代码仍未回同步正式Desk快照。以下v5及更早记录是历史，不能当作当前运行状态。

最新v5（优先于以下旧记录）：市场页已接research.configure-market，支持视图/范围/1–24条轨道/热图比较月；与页面共用日期窗口及最近完整月规则，错误输入不改页面，React提交后回执，手动覆盖/卸载取消待确认结果。修复移除轨道后沿用旧点位、关闭预测仍显示预测终点。19项Bridge/周期/市场行为测试及tsc通过；源码包解压复测、sdist→wheel及安装后完整CLI build通过。

当前候选14174/PID84728/session12981加载source-v5/deployment-products-v5，deployment=0b2ad2dc49905ff4；后端仍installed/。隔离Desk API8996/PID84834/session34276，state=seven-cycle-0oe4norf，Mod0.1.3；真实Codex CLI两组动作及自动回读4任务均completed：2d/20y/dxy+sp500/仅历史，以及heatmap/5y/2026-07截面2/2。独立IAB3d/20y/仅历史通过，截图在既有迁移目录（desk-market-action-v5.png、desk-market-heatmap-v5.png、standalone-market-v5.png）。Chrome旧标签加载停滞仍未定位，新标签成功。

下一步补CurrentAssetForecast子面板实时Context和资产查询动作；不要让子组件另注册全局provider。父页非C4仍带phase=recovery的语义须核查。候选仍8月研究数据，禁止替换正式10月数据；外部newma、固定版本和正式数据对齐未完成。未提交、推送、发布；最新代码未回同步正式Desk快照。

最新v4：七周期页已接research.select-cycle，只切C1–C7及证据展开，等React提交后回执；Bridge1.5.0校验宿主grants/实例/页面，14项行为测试、tsc与Desk Manifest合同通过。修复周期标签CSS网格冲突及嵌入重复品牌。原生和source-v4解压源码测试通过，完整安装后CLI build通过；候选14174/PID89341/session7199，deployment=57190fd43c3689a0，source-v4/deployment-products-v4，Python后端仍复用installed/。

隔离API8996/PID89343/session30672，state=seven-cycle-p42glr4c。真实CLI动作task-5004bd66df6a4e5697c946f4be319c84、回读task-942680f291704632a4f1eee5b978e7eb均completed：C4/false→C5/true，实际按钮与Context一致，未生成服务端重开截图。资产页C5和audit页Context切换已核对；市场/资产动作、资产预测子面板Context、真实外部newma与固定版本仍待完成。独立C7手动切换及390px图表重排通过，viewport已恢复。Chrome旧标签重载延迟未定位，不能宣称已修复。

2026-10-20 接续：Bridge升级1.4.1，仅信任构建配置的精确父Origin（未配置限同源），独立主题默认浅色，宿主实例/页面provider变更丢弃迟到Context与PNG。web/tests/vibedesk.test.mjs共8项通过，tsc通过。新源码包candidate-v3-packages及source-v3解压环境npm ci/test:bridge/完整CLI build通过；候选14174加载v3前端和deployment-products-v3，PID13896/session54824，deployment=c7ebcd0fff2786ad，健康ok。Python后端仍复用既有installed/，本轮未改后端。

隔离Desk5892/API8996实际C5切页读取通过：task-3bfd474f23274f83a99b7f64b56019c7完成，返回cycles/C5，不混入市场旧状态。当前仍actions=[]。原API测试过程发现服务端会重开浏览器做视觉兜底，已在共享验收工具禁用该能力并在无在途任务后重启隔离API（新state=seven-cycle-y71mmgqj）。正式服务未变。

候选构建显式设置VITE_NEWMA_DESK_PARENT_ORIGIN=http://127.0.0.1:5892；正式集成必须用实际审核过的宿主Origin重新构建。新Bridge与构建解耦代码尚未回同步Desk正式快照。解压环境npm ci提示7项依赖告警（2 moderate/5 high），未自动升级，待单独评估。

1. 逐文件审阅并合回10项 Desk 增量：四页实时Context、DOM/HTML回退、市场曲面PNG、热图/5年窗口/同月截面与样式、HTML缓存头及测试、Excel路径环境变量。没有覆盖五份研究JSON、模型、原始数据或数据库。
2. `FoundationSources.project_root` 显式指定批准研究根目录，CLI传入它；不再从Python安装位置推断研究根。保留原有文件身份、内容和发布门槛校验。
3. 完整build新增 `--research-output-dir`，分离代码与当前研究输入，缺少必需输入时在发布前报错。目录和数据时点不能猜测。
4. 原生前端构建、sdist→wheel、全新环境wheel安装、冻结锁文件依赖安装、解压源码包npm ci/build及安装后CLI完整研究构建均通过。

## 证据与隔离候选

- 迁移目录：`/Volumes/PSSD/Projects/newma-desk/runtime/project-migrations/seven-cycle-20261020-kVpugP/`。
- 恢复点：`native-before.tar.gz`、`native-build-before.tar.gz`、`native-history.bundle`；只用于本轮精确恢复，不整仓还原。
- 候选包：`candidate-v2-packages/`；安装：`installed/`；源码解压：`source-v2/seven_cycle_platform-0.1.0/`。
- 产品：`deployment-products-v2/`，在此路径重新生成catalog，未复制正式DuckDB。
- 运行：`http://127.0.0.1:14174/`，本轮PID6282/session95034，从/tmp清除PYTHONPATH/PYTHONHOME并以Python -I运行。接续必须重新核对进程。
- run `2026-08-22-7180d6f1dc9e-114cb24a0dfb`，deployment `d2bd433fc177d8c6`；这是历史研究快照，不是10月实时数据。
- `/healthz` status=ok、deployment=available；四页入口200；市场轨道104条，资产API98条。
- 回归：API/CLI/deployment/foundation共125项通过，DuckDB集成62项通过；ruff与diff检查通过。不是全量研究算法测试。
- 独立IAB14已检查四页真实加载、市场热图、周期页C4→C5切换、资产统计和校准来源表；未捕获JS error。完整双模式与所有控件仍未验收。截图 `standalone-market.png` 在迁移目录。

## 下一步

正式4174在本轮收尾返回degraded/deployment=inconsistent：API catalog checksum与产品deployment记录不同，且网页deployment副本缺失；HTTP200不代表健康。只读确认后未修改正式元数据。正式为10月研究快照，比当前原生8月快照新，必须审阅数据差异后再集成，不能用候选直接替换。

1. 用隔离Desk注册库接候选14174；验收四页Context、选择/过滤改变、DOM/视觉、主题和窄屏。
2. 审核Bridge可信父origin与迟到异步响应；当前actions=[]，需要受控UI动作与回读，不能把只读Context当双向完成。
3. 周期页部分“滞后月数”和资产“已更新”来自历史快照基线，与市场页距今口径不同，需统一标注，避免用户当成实时。
4. 核对发现算法 `cycles/discovery.py` 的旧ROOT默认路径、研究输入包交付与CLI相对路径语义。当前完整build从仓外调用必须显式绝对路径。
5. 审阅两仓五份研究JSON的版本，禁止整目录覆盖；原生批准配置/deployment.py等仍untracked，提交前必须纳入审阅。
6. 完成双模式后再绑定IDE主源码与固定commit同步；外部newma真实宿主单独验收。

本轮未提交、推送、发布；未重启正式服务。新增构建解耦代码暂只在原生主源码，Desk正式快照尚未回同步这部分。
