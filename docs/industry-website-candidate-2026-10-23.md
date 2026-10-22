# 行业景气 Website 接缝候选 · 2026-10-23

本轮仅 `industry-prosperity`，不是全部行业/产业链/股票验收。基于 Desk `c8404f521bbf20ce517501af2fe1b254400386dd`；原生行业固定 `1ac0799e1b76a8e4e8dbce09e7bb194b66378f5e`，Manifest `0.16.2`。包依赖及 vendor 不变。

## 修复范围

- 利润、历史、生产、价格、产能五类 GET 读取使用可信 Bridge 的 data gateway、Mod 签名与实例；不依赖 Cookie、不跟随重定向、不匿名重试。官方原文发现可能涉及多次请求，前端保留120秒总预算；失败不伪造替代证据。
- Desk API 的行业依赖检查 Website 绑定、Mod、实例、market.read、当前发布修订和页面准入。Website 只放行五个准确路径，未开放整个行业前缀或其他页面。
- 用户/工作区/实例/令牌/权限/网关变化立即取消旧读取，重建选择、草稿、公司证据和跟踪状态；A→B→A 迟到结果不能回填。主题变化不重新请求。会话指纹仅内部使用，不写入 Context/导出。
- 跟踪与关联保存明确要求 storage.write；只读用户仍可加载获准资料。私有请求不带 Cookie、不跟随重定向、不缓存。已有版本冲突处理保留，不自动覆盖。
- 领域后端不导入 Desk 认证；原生服务仍是本机公开行业数据服务，不能直接暴露为公网多租户后端。鉴权适配只在 Desk。

## 配套与候选范围

1. 必须一起加载本轮前端、`industry_access.py`、`main.py` 的四路由依赖、`website_auth.py` 和 0.16.2 声明。旧会话需重新打开页面取得当前修订。
2. 集成前端构建：`VITE_PARENT_ORIGIN=https://c10375.runtime.drlemon.cc:10443 npm run build -w @newma-desk/industry-research`。静态页由既定10444插件来源提供；API 使用 Bridge 下发的 gateway，不硬编码本机8911。
3. `NEWMA_DESK_WEBSITE_AUTH_ENABLED=1` 沿用既有部署配置。若主发布验收接受本单元，在原七页 `NEWMA_DESK_MOD_ADMISSION_ALLOWLIST` 后仅追加 `industry-prosperity`。本轮没有修改任何运行配置或实际扩开准入。
4. 页面：`/?mod=industry-prosperity`。生产/价格按报告月，产能按报告季度；同一页面的五类读取都必须验。跟踪记录、公司关联、财报读取分别沿用签名存储/档案权限。
5. 独立前端必须显式 `npm run build:standalone` 或 `dev:standalone` 并顶层打开。普通集成构建顶层打开会提示等待 Desk，不假装已获宿主授权。原生后端启动和配置不变。

## 实际验证

- 原生：77项前端测试、类型检查、集成与 standalone 双构建通过；本地工作树干净。
- 干净 Desk 候选 `/tmp/desk-industry-candidate-t2YhCU`：77项前端测试、云端父Origin参数构建、175项后端相关测试通过。候选来自 Git 基线加16个定向代码/声明文件；`main.py` 仅三处行业接入改动，不携带其他工作树内容。
- 后端覆盖五接口、Cookie-only拒绝、坏实例/冲突实例、错Mod、缺权限、旧修订、撤销准入/登录、本地公开兼容以及错误签名不得匿名降级。使用合成身份与采集器，未联网采集或运行模型。
- 前端覆盖签名五接口、无权限、显式独立模式、A→B→A、主题不重读、令牌/授权/网关变更、过期和失败不重试。没有用源码字符串或截图断言替代这些行为测试。
- 原生与 Desk 业务同步预览 `files: []`。本地版本记录仅更新行业项目，未混入根配置的其他项目修改。

复验：

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=services/api services/api/.venv/bin/python -m pytest \
  services/api/tests/test_industry_access.py services/api/tests/test_industry_research.py \
  services/api/tests/test_industry_production.py services/api/tests/test_industry_prices.py \
  services/api/tests/test_industry_capacity.py services/api/tests/test_website_auth.py \
  services/api/tests/research_archive/test_industry_inputs.py services/api/tests/mod_storage -q
npm run test:run -w @newma-desk/industry-research
```

## 未完成与发布边界

- 这不是实际 Website 登录、浏览器交互或Linux发布验收；待主发布会话继续。未重做Chrome探针、未改登录核验端口10378、未重启正式服务、未搬移数据库、未部署远端。
- `/demo/`、industry-chain公开材料及Orchestra readiness不变；没有获准公开真实输出就仍不标就绪。
- 后续周期/股票各自按最小页面单元处理。Orchestra身份、Skills和真实执行仍是单独硬缺口，不能以行业/组合测试替代。
