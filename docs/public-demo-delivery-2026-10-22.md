# 五页面公开只读演示交付

## 范围与授权

已读取材料会话019f965b-d5f2-7df2-a585-6edc7f07b119原始用户确认：“仅五个模组公开只读免登录”。不是解锁真实session，也不影响正常登录、私人数据和Agent执行路径。

本轮交付**独立只读历史快照视图**，不是把完整业务模组匿名开放。全球、周期、市场使用已有公开/批准研究快照；产业链、投决仅方法示例，保持ready:false。没有接入实时行情、新采集或私人历史资料。它不代表前五组30个业务页已经上线验收。

| 入口 | 内容与原时点 | ready |
| --- | --- | --- |
| global-situation | 已验USGS五条事件，采集2026-10-22T12:09:05Z；只覆盖地震，不是全球风险总览 | true |
| seven-cycle-research | 批准research-20261004的C4模型状态24期与七周期发布限制，观测至2026-08；非真实vintage | true |
| market-daily | 同一批准归档的FRED/SP500原始raw月频24期，至2026-09；剔除10月未完成月份，非原行情终端实时报价 | true |
| instock-industry-chain | 人工方法示例，尚无可公开的实际业务研究输出 | false |
| orchestra-committee | 虚构组织/议事样例，无真实输出；不运行Agent | false |

来源提取：全球仅使用`/tmp/global-source-check-20261022-X56fCD/world-result.json`的real字段；周期仅使用批准`research-20261004/web-data/cycle-research.json`的C4Realtime.date/rt_level、latest及governance发布限制；市场仅选`market-surface.json`的sp500日期/raw。未整包复制104轨道、账户、研究底稿或内部路径。主发布侧对应公开白名单见ACCELERATION.md的23:22交接。此次未重新独立核对SP500供应商数据，不将归档来源标记夸大为本轮实时校对。

## 固定接口契约

正式目标为`https://c10375.runtime.drlemon.cc:10443`，目前本地候选尚未云端部署。

- `/demo/?mod=global-situation`
- `/demo/?mod=seven-cycle-research`
- `/demo/?mod=market-daily`
- `/demo/?mod=instock-industry-chain`
- `/demo/?mod=orchestra-committee`

`GET /demo/status.json`返回：

```json
{"contract":"newma-desk.public-demo.v1","mode":"readonly","readinessScope":"reviewed-readonly-snapshot","live":false,"contentVersion":"2026-10-22.1","modules":[{"id":"global-situation","ready":true,"dataKind":"public-snapshot","asOf":"2026-10-22T12:09:05Z"}]}
```

实际modules包含上述五项及各自reason/coverage。ready表示所列有限历史快照通过本地真实显示/交互验收，不表示实时数据或完整业务服务健康。产业链/投决的示例不计作业务就绪。材料必须校验contract/mode及所选id的ready，用credentials:omit，并展示dataKind/日期；不能把普通SPA返回200当成就绪。

仅状态接口对精确`http://127.0.0.1:8766`返回Access-Control-Allow-Origin；不返回Allow-Credentials，不接受null/*。页面CSP的frame-ancestors仅self与该材料Origin。其他演示API不提供跨域CORS，iframe内同源读取即可。

## 实现与隔离

源码目录：`services/api/vibe_visualization_api/public_demo/`，包含独立FastAPI工厂、五份合并的固定content.json及HTML/JS/CSS。无构建工具或新依赖；不导入Desk main，不创建数据库/调度/模型，不读取.env、Cookie、Authorization或工作区信息。页面仅切图表/阅读说明，无Bridge、LocalStorage或消息回传。

服务端只允许GET/HEAD；所有写方法405，未列出的模组和API404，不做SPA fallback。即使传入真实登录Cookie也不能访问私人内容。Caddy仍应剥离Cookie/身份头作为边界隔离。正常`/api/*`不路由到这个服务。

## 部署操作路径（主发布会话执行，本会话未执行）

1. 从本次限定提交导出`public_demo/`和本文件，不打包活动dirty工作树或未固定登录改动。不要替换当前Desk源码/venv/数据库。
2. 将独立包放入专用只读release目录（例如`/opt/newma-public-demo/<提交>/vibe_visualization_api/public_demo`），父包可用空的`__init__.py`或Python namespace package；沿用已有包含FastAPI/uvicorn的解释器，不安装新依赖。
3. 用独立服务账户启动，仅监听loopback；不加载正式环境文件或密钥，不挂载业务数据库。按实际已核验解释器路径配置systemd，不照抄猜测路径。

```sh
<已有解释器> -B -m uvicorn vibe_visualization_api.public_demo.app:create_app \
  --factory --app-dir /opt/newma-public-demo/<提交> \
  --host 127.0.0.1 --port 18957 --no-proxy-headers --no-access-log
```

建议服务保护：NoNewPrivileges、ProtectSystem=strict、ProtectHome、PrivateTmp；不授予业务目录写权限。不需要重启整个Desk。先核对18957空闲，冲突时只修改该服务和代理的目标端口。

4. 先在loopback验证五页内容、status契约、未知mod404、POST405及私有接口404。然后把`deploy/server/public-demo.Caddyfile.example`的精确handle合并入10443站点，保留既有登录规则；先验证Caddy配置再受控重载。不能让上层forward_auth/SPA捕获/demo，也不能全站取消认证。
5. 公网重复边界检查，再从材料`http://127.0.0.1:8766`验证状态CORS及iframe；file://不加入白名单。记录真实显示结果，不能只检查HTTP200。
6. 回退只撤销该/demo代理块并停独立演示服务，保留release和日志；不操作正常Desk业务库和会话。

## 本地验收

- `PYTHONPATH=services/api services/api/.venv/bin/python -B -m pytest services/api/tests/test_public_demo.py -q`：29项通过，覆盖五页、作用域不继承、写操作拒绝、私有/未知路径、原始日期及发布限制、状态契约、精确CORS和静态安全头。
- `node --check services/api/vibe_visualization_api/public_demo/demo.js`通过。没有增加npm依赖或修改根锁。
- 独立loopback18957、Codex内嵌浏览器：五页导航正确；全球点击事件更新地点/原日期/深度；周期与市场24/12期切换与真实归档相符、完整数据表可读；行业/投决仅静态说明，显示未就绪，未执行后台动作。浏览器未报告脚本错误。此非正常Desk/云端/材料iframe联调。
- 截图目录`/tmp/newma-public-demo-acceptance-tpwEz6/`，以`*-public.png`为修正后真实快照证据；初版market.png/cycle.png为已弃用合成版本，不能当最终证据。
- 初版曾用五页合成示例且ready统一true，验收前已纠正：三页改既有实际公开/批准快照，两页示例false；从未部署该初版。
- 本机临时服务在验收结束后停止；本轮不改正式5888/8911、注册库或其他服务。公网部署及材料iframe由主发布侧验收后记录，当前未完成。

正常业务的Research鉴权、市场存储和独立后端登录仍是另一条交付线；不要因只读演示上线就打开其云端开关。
