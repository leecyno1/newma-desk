# Crucix 接入

Newma-Desk 把 Crucix 作为独立本地数据源使用，不复制其 AGPL-3.0-only 源码，也不嵌入其 Dashboard。

## 启动 Crucix

Crucix 原生服务没有接口鉴权，并且直接 `npm start` 会监听全部网络接口。推荐用 Docker 只映射到本机回环地址：

```bash
git clone https://github.com/calesthio/Crucix.git
cd Crucix
docker build -t newma-crucix .
mkdir -p runs
docker run -d --name newma-crucix --restart unless-stopped \
  -p 127.0.0.1:3117:3117 \
  -v "$PWD/runs:/app/runs" \
  newma-crucix
```

需要 API Key 时，在最后一条命令中增加 `--env-file .env`。不要把 `3117` 暴露到公网或局域网。

如源码不在默认项目目录，设置：

```bash
export NEWMA_DESK_CRUCIX_WORKSPACE=/absolute/path/to/Crucix
```

Desk 只允许访问 `http://127.0.0.1:3117`，可用接口：

- `GET /api/crucix/health`
- `GET /api/crucix/snapshot`

标准化层会移除 HTML、危险 URL、无标题新闻和 Crucix 的主观 `ideas`。Telegram、Discord、SSE、Agent 与密钥仍由 Crucix 自己管理，不进入 Desk。

当前 Crucix `/api/data` 没有暴露 OFAC、OpenSanctions、UN Comtrade 和 PatentsView 的原始结果；这些能力要等上游提供结构化接口后再接入。
