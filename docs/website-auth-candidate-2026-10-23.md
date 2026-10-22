# 登录最小候选交接 · 2026-10-23

## 固定范围与状态

本候选基于 Desk 2653c95b，包含已审阅的 Website 登录接缝、全球四页授权、Research 内部取数及宏观/新闻/催化剂浏览器读取。只固定这些必要文件，不收录活动工作树其他功能。独立 Research 已限定提交 d5777f5276b39479e80b960ab9c9bb2a181ed398（10 文件），QODER_HANDOFF 旧草稿保留；全球独立仓的配对修改尚未单独固定，Desk 内候选源码已固定时以本提交为准。

这是供主发布侧受控部署、真实登录验收的源码候选，不是五组30页已完成。正式本地服务未重启，无远端操作。现有 /demo/ 三项有限历史快照及两项 ready:false 不变；本提交不删除演示文件。

## 可进入本轮云端验收的页面

- global-situation：带签名读取/实时流；来源缺失或陈旧继续如实显示，不保证上游可用。
- fed-rates、hormuz-conflict、us-china-trade：本专题读取/推演保存，按权威用户/工作区隔离；旧匿名记录不归户。
- macro-monitor：research.macro-monitor 已授权读取。
- catalyst-calendar：research.catalysts 及 symbols/concepts/days/include_cycles/include_macro 全参数。私有 Research 原生组合不能读取；工作区自选/研究组合联动仍待接缝收口。
- news-radar：公开已采集快照、主题分页、按明确代码读取公告/新闻及 Crucix。刷新仅重读已采集内容，不启动全量抓取；页面/Agent回执均说明。未配置采集或空缓存不算内容验收通过；自选列表云端同步仍待修复，名称补充暂不请求原生行情。

其他市场存储、行业/周期独立后端身份、Orchestra 原生鉴权/Skills/真实 Hermes 执行均未纳入就绪范围。不能仅打开登录开关就将30页全部暴露；本轮验收入口只发布上述页面，旧的独立后端私有 API 保持不可公开访问，不能仅以 forward_auth 登录成功代替业务归属隔离。如无法隔离旧入口，先只在独立受控候选入口验证，不能覆盖正常私有业务。

## 必须配套的声明与构建

- 三个全球专题 Manifest 0.1.1：market.read + storage.write，未持有新发布修订的旧会话不得保存。
- 宏观 0.1.3、催化剂 0.1.1、新闻 0.3.2；新增读 Action 仍使用 market.read。新闻 local news.refresh 保留 investment.read，不授权后端采集。
- integrations/vibe-research/data-service.json 同步加载；增加只读 /radar/snapshot 与 /radar/topics 能力，补催化剂参数。不登记 /radar/refresh 或私有持仓。
- Research 前端：VITE_NEWMA_DESK_INTEGRATED=1 VITE_BASE_PATH=/mod-runtime/research/ VITE_API_BASE=/api/research npm run build；在 bundled-runtimes/vibe-research/frontend 执行。
- Shell：VITE_NEWMA_WEBSITE_AUTH_ENABLED=1 npm run build -w @newma-desk/desk；全球：npm run build -w @newma-desk/global-intelligence。
- API：NEWMA_DESK_WEBSITE_AUTH_ENABLED=1 与 Shell 配套。Research 的 backend/app.py 和 newsradar.py 必须一起部署，否则新快照 Action 404。原生独立模式、访问密钥与采集行为保留。
- 默认开关关闭，不能把构建完成当作进程已加载。不要整仓复制 .env、数据库、用户资料或本地登录态。

## 登录和运行边界

沿现有 newma.uk 权威契约，不新建账户系统。state + PKCE + 一次性 code POST 回调；专用 HttpOnly/Secure Desk Cookie，不复制 Website 主 Cookie。权威身份签发/绑定 Mod 会话，精确实例/修订/权限；拒绝自报身份、跨模块、匿名降级。模块请求不携带账户 Cookie、不跟随重定向。Website Cookie 单独不能打开 Research 私有原生 API 或直接调用数据服务；拒绝插件请求也不清掉有效 Shell Cookie。

生产仅 loopback、单 API worker，Uvicorn --no-proxy-headers。Caddy 必须公网拦截 /api/auth/verify，并自行重建 forwarded-method/uri；只允许精确10443/10444/10445写入Origin。校验接口只确认登录，独立业务后端归属必须另验。Website 前置已由主侧上线，不需重复部署或取凭据。不要自动开启全量RSS/数据采集、定时分析或模型任务。

同进程 Research 使用限定能力 method/path 的内部ASGI transport，剥离浏览器身份与凭据，仅宿主内部使用原生服务密钥；缺挂载、超时明确失败。维持原生产 Trading/Research 依赖组合，不用本地测试venv覆盖服务器环境。

## 实际验收

- 独立 Research：前端266，后端378（11 live未运行）；Desk/standalone构建通过。
- 干净 Desk 候选 /tmp/desk-website-auth-candidate-gbE0AZ：后端316（含登录、数据服务、领域挂载、全球、控制面）通过；最终Cookie修复后的登录75项通过。Shell199、全球84、Research定向47通过，Shell云端/全球/Research集成构建通过。
- Research候选前端首轮缺 clsx 依赖导致文件组件套件未加载；按原锁文件 npm ci 后重跑47项通过，没有修改测试断言或锁文件。
- 真实临时 FastAPI 应用完成实际Manifest发布→绑定会话→Action→内部Research，覆盖两研究页、新闻读接口、错误参数、原生私有路径和未声明采集拒绝。身份与数据为合成，不是云端用户/行情验收。
- 新闻后端验证缺缓存/陈旧缓存不启动抓取，独立读取/显式刷新行为保留。未在测试中真正执行全量采集。
- 既有33项数据声明检查通过；用户手动同源探针可用，不再重做自动化Chrome空白探针。

主发布会话 019fe457-442d-7372-8009-2280e63f2261 是唯一 c10375 部署者；按固定提交预检、保留回退后受控加载，并核对真实登录/退出、七个页面、数据新鲜度和上下文。未验页面与真实Hermes结果继续单列，不向材料注入私人会话数据。
