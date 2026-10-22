# 全球情报固定版本与 Desk 集成验收

日期：2026-10-22。源码交付，不是远端部署或完整 newma 验收。

## 固定来源与范围

全球独立仓库 `/Volumes/PSSD/Projects/newma-desk-projects/global-intelligence` 固定为 `958f2770b42f6e767710f063213dbfc6760090d3`（父 `62bfb04`）。17文件限定提交，工作树干净；四个 Mod 仍属一个项目，不包含新闻/催化剂的 Research 业务。原生仓没有推送。

本 Desk 候选基于 `7ecb133f45d806fd96d0f589aa3659ad042cb08c`，只纳入全球前端/领域后端/宿主 Adapter、四份声明、对应测试以及已审核的共享锁安全补丁。主入口仅替换全球依赖注入，不带政策、资金、组合等未提交改动。

核心改动：

- 地图显式打包 MapLibre Worker；来源缺失不显示零风险。
- 刷新等待真实数据和 Context 发布；切页/并发不假成功；缺源 SSE 终止，不自动重连风暴。
- 保存视图按用户/工作区/Mod隔离。三个专题有明确刷新/保存动作，沿用 market.read，无新增权限。
- 未来采集时间标 unknown；GSCPI观测期与采集时间分离，缺日期不补造；旧缓存和部分失败保持 partial，来源连通不覆盖数据过期。
- 领域包不导入 Desk 配置/网关；`global_intelligence_adapter.py` 注入 Desk 现有配置、数据库和受控数据服务。不是新 Agent 内核。

人工对齐核对：211个源码/测试/引擎文件（仅包名前缀转换）一致；四个编译后 manifest 与原生声明完全一致，宿主 Adapter 相同。本机共同基线更新为958f277，`projects:sync -- global-intelligence to-desk` 预览files=[]。本机15项目版本文件不随本次小提交整体纳入，固定来源以本报告为准。

原生Crucix有独立lock，Desk的Crucix属于根workspace、没有子lock，不能直接复制其锁文件。两侧分别冻结安装及审计；Desk共享15个依赖节点为安全补丁，未修改根package.json或其他项目源码。原生与Desk的qs传递版本分别6.16.1/6.16.0，均在原依赖范围且各自锁审计为0；不宣称所有传递版本逐字一致。MapLibre/Vite/Vitest核心修复版本分别6.4.1/6.4.5/4.1.12，两侧一致。

## 实际验证

候选根：`/tmp/global-fixed-candidate-20261022-r8WsX4/`。

| 范围 | 结果 |
| --- | --- |
| 原生干净候选前端 | npm ci新装263包；75项通过，类型和Desk/standalone两路径构建通过 |
| 原生领域包 | Python3.12 frozen安装25包，非editable；46项通过、依赖兼容；sdist→wheel成功 |
| 最终wheel | 重新安装产物后46项仍通过；源码目录外CLI启动，两种路径各4页及其JS/CSS为200；缺源503、无Agent内核404；推演仅写新建隔离SQLite |
| Crucix | 新装67包；指定5个provider mock文件45项通过，没有真实模型请求 |
| Desk干净候选 | npm ci新装578包；11个workspace共601项通过，其中全球75、Shell184、Contracts103；相关领域/Adapter后端51项通过 |
| Desk构建及声明 | Shell类型/构建、全球模块独立构建、33官方数据能力及Shell业务依赖检查通过 |
| 依赖审计 | 原生前端、原生Crucix、Desk根锁均0项已知告警 |

范围有重叠，不能把表内测试数相加为独立用例总数。Desk API51项复用此前Research验收Python环境，显式PYTHONPATH指向本候选；不声称Desk完整API本轮重新安装。原生Python3.12为本轮新环境；最初工具默认选择的3.14环境未作为交付证据。

源码产物：`dist/newma_global_intelligence-0.1.0.tar.gz`、同目录wheel；分模式前端 `frontend-desk/`、`frontend-standalone/`。安装包HTTP验证见 `installed-verification.json`、`check_installed.py`；两个临时服务均已停止，测试数据库/日志保留。HTTP成功不等于真实浏览器交互；未重复此前四页实机和Codex CLI闭环。

本轮此前公开源验证：USGS5条且受控离线后保留原时间、标陈旧；纽约联储GSCPI取12个月，最新2026-09=1.28；NOAA不可用并明确报错。原始结果位于 `/tmp/global-source-check-20261022-X56fCD/`，并非全部源/完整聚合引擎通过。

## 部署配套与未验边界

1. 配套使用本提交的API全球Adapter/领域代码、四份Mod声明、全球前端dist和共享锁。仅换前端会缺少注入与刷新声明，不能分拆部署。
2. Desk路径构建：`npm ci`，`VITE_PARENT_ORIGIN=<审核后的真实宿主Origin> npm run build -w @newma-desk/global-intelligence`。全球模块仍需其现有静态资源挂载；Shell构建不能替代全球dist。
3. 独立API从原生固定源码包安装到自己的Python3.12环境；用 `GLOBAL_INTELLIGENCE_DATABASE_PATH` 指定业务库，World Intel/Crucix地址显式配置。不得拷贝测试库、Mac虚拟环境或本机地址到云端。
4. World Intel和Crucix真实进程需另行受控启动；Crucix原启动器会定时采集并可能启用已配置模型/外发，不能为测试页面盲目启动全引擎。本轮未启动这些行为。
5. 此版本健康接口还没有包内Git身份；报告中的固定源码不是运行进程身份证明，不将当前配置提交标成实际加载版本。
6. 云端登录保护仍是独立门槛：现有Desk会话签发为trusted-local，客户端自报用户/工作区不是已验证登录身份。Bridge精确Origin/实例隔离也不是认证；主发布侧须接已有Newma受保护入口，不能把匿名直反代当公网验收通过。
7. 新版外部newma、完整有源聚合、Linux启动和五组30页整体验收仍待主发布侧配套完成；本会话未切正式本地进程、未部署远端、未推Gitee。
