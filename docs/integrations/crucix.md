# Crucix 接入

Crucix 源码位于 `bundled-runtimes/crucix`，作为 Newma-Desk 的内置本地 OSINT
采集引擎使用。统一开发栈会自动启动它，不需要 Docker，也不会打开 Crucix
自己的 Dashboard。

## 启动

在主仓安装依赖并启动统一开发栈：

```bash
npm run runtime:bootstrap
npm run dev:stack
```

Crucix 固定监听 `127.0.0.1:3117`。可选 API Key 写入
`bundled-runtimes/crucix/.env`，不要提交该文件。

Desk 只允许访问 `http://127.0.0.1:3117`，可用接口：

- `GET /api/crucix/health`
- `GET /api/crucix/snapshot`

标准化层会移除 HTML、危险 URL、无标题新闻和 Crucix 的主观 `ideas`。
Telegram、Discord、SSE、Agent 与密钥仍由采集引擎内部管理，不进入 Desk 页面。

当前 Crucix `/api/data` 没有暴露 OFAC、OpenSanctions、UN Comtrade 和 PatentsView 的原始结果；这些能力要等上游提供结构化接口后再接入。
