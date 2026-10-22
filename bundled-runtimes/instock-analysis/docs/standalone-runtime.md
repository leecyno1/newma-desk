# 独立构建与 Desk 接入

项目可独立构建、安装和运行分析网页，无需导入 Desk Python 源码、npm workspace 或 MySQL。数据仍需兼容的 HTTP 研究接口；当前已实现的协议来自 Desk，不代表所有功能已有其他数据 Provider。

## 安装与启动

使用 Python 3.12。首次安装在本项目环境执行：

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -c requirements-attached.constraints.txt .
.venv/bin/instock-research --data-url http://127.0.0.1:8911/api/research
```

源码调试可运行 `.venv/bin/python -m instock.runtime --data-url <URL>`。默认仅监听 127.0.0.1:9988，首页跳到市场复盘；11 个 Mod 使用同一运行时。

独立页面在“功能目录”选择跟随系统、浅色或深色；窄屏先打开“模块”菜单。偏好仅保存在当前服务origin，跨标签同步，不清空当前筛选和结果。嵌入Desk时隐藏该入口，主题完全由宿主控制。

- `INSTOCK_DATA_URL/TOKEN/TIMEOUT`：项目自身的数据连接配置；凭据只用环境变量，不写 URL、日志或命令参数。
- 财务快照/比较的客户端等待至少50/60秒；Desk侧对应能力预算45/55秒，其他数据请求沿用配置。Desk模式两项均走授权数据网关，独立模式仍用显式Research地址与token。鉴权失败或超时不绕回直连、不整批逐只重试；保留财务不可用及partial，不将失败视作零值或完整排序。
- `INSTOCK_MARKET_SERVICES_URL` / `--market-services-url`：基础市场服务的 HTTP(S) origin，不带路径。交易日历、未复权成交价、市场结构和市场证据分别使用其 `/api/capital-flow/trading-calendar`、`execution-prices`、`market-structure`、`market-evidence` 接口；不复制 Desk 的业务实现。
- `INSTOCK_MARKET_SERVICES_TOKEN`：显式基础服务的独立凭据，不继承 Research token。直连 Research（根地址或 `/api`）时，相关功能需要单独配置基础服务；未配置直接提示，不能猜测同域接口。
- 兼容原有 Desk 网关 `/api/research`：没有显式基础服务配置时沿用该网关 origin 和原凭据；显式配置后使用独立地址及凭据。直接配置 Research 的示例：`instock-research --data-url http://127.0.0.1:8992/api --market-services-url http://127.0.0.1:8994`。端口仅为示例，不自动启动服务；行情正常不代表四项基础能力均可用。
- `INSTOCK_STATE_DIR` / `--state-dir`：运行数据位置，默认用户本地状态目录；现有各数据库路径覆盖继续有效，不自动搬移数据。
- `INSTOCK_LOG_DIR`：日志目录，不向已安装包写入日志。
- 未配置数据 URL 时启动及底层 `get_market_data_provider()` 均明确报错，不再默认连接本机8911。原有显式配置的 Desk 地址和旧环境变量别名继续兼容；`instock` 爬虫仍须显式选择。
- A 股扫描可由所连接的 Research 服务显式配置 `VR_CN_SCAN_SOURCE=tushare-daily`；Tushare 凭据只放数据服务端，股票端仍用原 HTTP 合同。默认源不自动切换。日频数据取前一已完成交易日，保留非实时、数据日期与覆盖数量；11轴合并是候选并集，不是完整证券主表，不用于历史回测。
- 日频扫描不混入实时补价；缺失指标保留空值，真实0保留。两筛选页和Agent Context显示同一`scan_observations`；数据源未接通或缺权限不能解释为没有候选。新源须与本次配套消费者一起验收后再加载。
- 日频筛选的技术日线以每条扫描记录的 `scan_as_of` 为截止日，排除之后的K线再取请求窗口；缺截止日拒绝混用最新日线。此规则只对齐扫描与技术窗口，不代表已有历史证券主表或历史财务点时数据。修改条件后，页面保留旧结果并显式提示尚未重算。
- 独立入口不会自动获得宿主 Agent；需要 Desk Gateway 或真实 newma Bridge 配置才可使用对应能力。

## 构建与测试

复权口径只采纳数据服务返回的 `qfq/hfq/none`；未返回或未知值标 `unknown`，不能用请求口径代替事实。两筛选结果分开统计未复权和口径未知，未知仍可展示行情但需复核，不额外改变评分。

轮动引擎2.3.3只接受有日期且与价格窗口对齐的市场/行业广度。缺日期、日期不匹配或计数异常时，比例与行业确认分保持null；不影响原量价排名。行业平盘数未提供时明确分母为上涨+下跌，已提供但不是非负整数则拒绝计算，不能截断或忽略异常值。

```sh
.venv/bin/python -m pip wheel --no-deps . --wheel-dir dist
.venv/bin/python -m pytest tests -q
```

构建后端固定版本见 pyproject.toml，业务依赖版本沿用 requirements-attached.txt 及 constraints。wheel 包含页面、静态资源和从唯一源生成的 Suite 声明，不包含数据库、密钥和运行日志。Python 包版本和各 Mod 页面版本分别管理。

## 构建身份与运行版本

构建时将 `projectId/packageVersion/sourceCommit/sourceDirty` 写入包内 `instock/_release.json`，sdist→wheel保留同一身份。仅本项目Git根目录可提供提交，不借用父Desk仓库HEAD；从无Git的源码包构建时保留嵌入身份，不允许更换包版本重新贴标。

运行时只在首次导入时读取包内身份，不查当前Git、不从环境变量注入提交。健康接口 `/api/v1/health` 的 `data.release` 与全部11页HTML的 `instock-source-commit/source-dirty/package-version` meta采用同一进程身份。替换磁盘文件不改变已启动身份，更新安装后仍需受控重启；这不是热更新机制。

干净且与Desk固定提交相符的产物才可能显示matched；含未提交修改为candidate，缺少有效身份为unknown。安装来源不能替代进程上报；HTML标识也不证明浏览器缓存的全部静态资源已更新。2026-10-21候选已完成两种启动模式的HTTP身份验收，正式旧包未切换；不等于真实Bridge、Agent或业务功能全量验收。

## Desk 模式

数据健康与行情使用同一连接通道：独立Research走配置API前缀下的GET /health；Desk连接走已有数据网关的market.health能力，不再要求宿主挂载旧Research健康地址。新包须与Desk的该只读能力声明配套加载，仍复用market.read和服务端认证，不把Research密钥复制给股票Desk进程。源码/声明更新不改变旧进程，须在明确授权后受控加载。

Desk 通过 HTTP iframe/Bridge 接入，而不是导入本项目代码。使用同一个进程可以独立打开或嵌入，但嵌入会话必须额外设置：

- `NEWMA_DESK_PARENT_ORIGIN`：Desk 的精确 origin。
- `INSTOCK_DESK_SCOPE_URL`：Desk 会话范围校验接口；缺失时带 Desk 身份的请求必须失败，不能回退到独立用户数据。

产业链的“读取工作区财报”属于Desk私有研究输入：必须通过Bridge收到签名会话、实例和`analysis.read`授权，使用宿主HTTP接口读取；不能用用户/工作区ID代替凭据。独立页未接入该会话时明确不可用，仍可导入自己的结构化研究包，不匿名访问Desk底稿。宿主更新输入鉴权时须配套加载本项目新包；源码同步并不改变已运行的旧安装包。

Desk 开发配置可设置 `NEWMA_DESK_INSTOCK_WORKSPACE` 指向本仓库；首次切换需确认实际进程 cwd、既有数据库路径、在途任务和页面版本。未验收前不改生产入口。当前相邻 Desk 的复制版本与本仓库只是候选同步，不构成已发布版本。

Desk 启动描述符现使用 `python -I -m instock.runtime --mode desk`，只加载环境中已安装的项目，不再直接执行源码脚本。启用此候选配置前，须在对应 workspace 的 `.venv` 中执行上面的项目安装命令（只装 requirements 不够）；修改源码后也须重新构建/安装，IDE 保存不会自动更新运行包。Desk bootstrap 已改为安装项目本身，本轮未执行整栈 bootstrap 或切换正式进程。

为保留原数据，Desk 描述符传入 `--state-dir <workspace>/instock/cache --log-dir <workspace>/instock/log`。单独配置的三个数据库路径及 `INSTOCK_LOG_DIR` 仍优先；不迁移文件、不改变历史记录归属。`--mode desk` 只标识进程生命周期由 Desk 管理，不授予 Agent 或嵌入权限。独立启动默认仍为 operator 管理和用户状态目录。

## 版本同步门槛

产业链人工复核在独立页仅保存到当前浏览器、当前网址的本机存储；不是服务器持久化、认证账户或跨设备同步。公司档案和研究组合从同一存储读取最新意见，不改变研究评分。保存须先读取并人工确认；多页面通过浏览器写锁和记录版本防止覆盖。无安全写锁时仅支持读取、导出；禁用存储、空间不足或损坏记录必须明确失败，不能当空库覆盖。更换端口、浏览器或清理站点数据后无法沿用，请及时导出留档。

嵌入 Desk 始终使用签名会话的工作区存储；未握手、无权限或接口失败不回退本机，也不迁移独立记录。独立页不能核验 Desk 财报归档原文，关联旧归档的意见必须标记待复核，不能沿用归档确认。

差异合并 → 独立 wheel 构建及安装测试 → 独立/嵌入实际验收 → 审核后提交主仓库 → Desk 快照固定该 commit。未提交候选只能记录基础 commit 和待提交差异，不能把旧 HEAD 当成新源码版本。无自动双向覆盖、自动推送或自动部署。
