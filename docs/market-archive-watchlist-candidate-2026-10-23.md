# 私有布局、复盘归档与共享自选候选

基于 Desk `2ab562d16b0be944601d61066466b2267b81231e`，仅收录本轮 28 个业务/共享文件及本说明。未提交其他 dirty 改动，不操作远端、正式本地服务或真实数据库。c10375 仍由 newma 主发布会话唯一部署；10378 已由其登录候选占用，本会话不使用。

## 固定来源与同步

- 市场主仓：`/Volumes/PSSD/Projects/newma-desk-projects/market-daily`，固定 `f205e8d59a427d968454705976d4c3c6ada381f9`，含前一项 `1c6509f`。原生 76 项测试、类型及 Desk/独立双构建通过。
- Research 主仓：`/Volumes/PSSD/Projects/newma-desk-projects/vibe-research`，固定 `48df069638f4451bd55abf40d2e26ec795e8094d`。原生 279 项前端测试及双构建通过；保留原有 QODER_HANDOFF dirty，后端未改。
- 两侧业务源码/测试按共同基线逐项比较后同步；七份声明的 version/permissions/actions/storage/dataServices 完全配对。声明变动触发同步工具保护，人工核验后仅推进两项目本机版本字段；两项目最终同步预览均 `files: []`，未将整份本机版本配置纳入提交。

## 已修复的核心链路

1. 五个市场工作页布局使用既有签名 Mod Storage、`layouts` 命名空间及 `storage.write`，保存确认后才反馈。嵌入不读写/迁移旧浏览器布局。布局 Context 只输出名称与时间，不包含内部会话/令牌。
2. 复盘创建、列表、详情、latest、publish、HTML 查看均沿现有签名身份；验证模块、实例、权限、发布修订和 Website 登录绑定。归档按用户/工作区隔离，外账户 ID 为 404；旧未归属归档不自动接管。`published` 仍是私有归档状态，不代表匿名发布。
3. 签名 HTML 查看不在 URL 带令牌，使用 `sandbox="allow-scripts"` 且无 allow-same-origin。响应与 HTML meta 均有 CSP，禁止联网/表单/base，私有响应 no-store；保留旧渲染器必要 inline 脚本/样式，不据此宣称已消除全部 CSP 兼容债务。
4. 市场账号/实例/授权变化清除旧布局、模拟订单、归档和预览；迟到归档列表不能覆盖新保存，旧请求不能写回新账户 UI。原生明确本机模式保留原行为，不是可匿名开放的多租户接口。
5. 新闻/催化剂只读签名共享自选，不使用旧匿名浏览器自选或原生持仓兜底。催化剂跟踪保持空账户为空、失败保留草稿、冲突不覆盖；只读禁用保存，切账户清除草稿。

## 页面准入边界

下表的“候选”只表示可进入隔离云端验收，不是已上线或真实内容/账号/Hermes 验收通过。原七页白名单不自动扩大；主发布侧只按实际验收页面追加精确 ID。

| 页面 ID | 本次可验范围 / 不包含内容 |
| --- | --- |
| global-situation | 沿用原总览签名只读候选，无本轮功能修改 |
| fed-rates | 沿用原专题签名候选，无本轮修改 |
| hormuz-conflict | 同上 |
| us-china-trade | 同上 |
| macro-monitor | 沿用原宏观只读候选，无本轮修改 |
| news-radar | 0.3.3，共享自选读取与原资讯 Action；不启动采集，空/陈旧快照不算内容通过 |
| catalyst-calendar | 0.1.2，共享自选与私有跟踪；自定义研究分组仅按账户保存在本机，不是云同步；嵌入暂不接组合中心持仓 |
| market-daily | 沿用 0.4.2 自选/预警签名候选，须真实行情及账号验收 |
| market-technical | 0.1.3，签名预警与布局保存；布局恢复/管理交互不是本轮交付 |
| multi-timeframe | 0.1.3，同上；行情仍区分日线复权与分钟不复权 |
| relative-strength | 0.1.3，同上；仍按共同时间窗口比较 |
| event-timeline | 0.4.2，签名预警与布局保存；按实际菜单归属单独准入 |
| trading-replay | 0.1.3，私有模拟归档与布局保存；仅研究模拟，不交易、不公开归档，不自动扩大原30页发布范围 |
| market-sentiment | 本轮未改声明或存储；日频读取按原候选单独验收，不能由归档测试替代 |

Research 通用 `watchlist` 编辑页仍用旧客户端，不能开放云端写入。`instock-market-map / instock-market-workbench / instock-czsc / instock-rotation / industry-prosperity / capital-sectors / industry-map / instock-industry-chain / seven-cycle-research` 的独立身份/业务验收及所有 `orchestra-*` 的鉴权、Skills、实际执行均不由本轮宣布通过；不开放全部30页或117页。

## 配套发布要求

- API、Shell 内置市场动态包、Research 集成前端及七份新声明一起取固定提交；只发独立市场 dist 不会更新 Shell 内嵌组件。声明发布后重建会话，不能沿用旧 revision。
- 云端 Shell 构建须同时指定：

```text
VITE_NEWMA_WEBSITE_AUTH_ENABLED=1
VITE_MOD_ORIGIN=https://c10375.runtime.drlemon.cc:10444
```

- 保留 `NEWMA_DESK_MOD_ADMISSION_ALLOWLIST` 原七页配置，市场由主发布侧逐页选择。此开关不是独立后端端口/通用管理路由防火墙，不能只靠菜单或 Mod 白名单放开旧原生 API。
- 不迁移旧无归属数据、不复制 Cookie/密钥、不降低 Website 绑定校验。主发布侧继续实际 HTTPS 登录/内容验收，不重复 Linux 安装或 Chrome 最小探针。

## 实际测试

干净候选 `/tmp/desk-archive-candidate-WDFQW1`：从固定父提交只叠加审核文件，原锁安装、禁安装脚本，不借用活动工作树源码。

- 后端 artifacts / mod_storage / watchlists / market_alerts / website_auth / control_plane / mod_store：356 通过。实际七份声明登记、签名权限与归属、冲突/只读/撤销均使用临时库和合成身份。
- 市场 76、Research 279、Shell 199 通过，合计 910 项。Research 本次显式排除其配置中混列的两个基金测试文件；不将其算作通过。
- Shell 带上述两项云端参数构建通过，Research 集成构建通过；原生两工程双模式构建另通过。15项目/117 Mod 归属检查通过。
- 首轮候选漏导出 Archify vendor 导致两项旧图谱测试失败，补入父提交原 vendor 后全组通过；首轮 Research 混列基金测试缺源，明确排除后本项目26文件279通过。没有修改断言或生产依赖掩盖失败。
- 没有本轮真实浏览器、云端用户登录、Hermes 执行或正式服务加载证据，不能把合成测试当真实业务验收。

## 行业与投决公开真实内容核查

`/demo/` 本轮未改。现有 `content.json` 中产业链、投决均 `ready:false` 且无 provenance，仍是方法示例。产业链入口分析显式提供的研究包；Orchestra runs/artifacts/exports 经 current_user，且引擎有演示路径。未找到已审核批准公开的真实产业链快照或非 demo 投决输出。

这不表示用户没有私人结果：本轮未读取私人数据库/历史、不新采集、不运行模型。需要现成且明确获准公开的快照/run、来源日期及脱敏投影审核后才能更新 ready。41行业工业利润不是产业链研究包，不能替代；模型演示输出也不能当真实投决。
