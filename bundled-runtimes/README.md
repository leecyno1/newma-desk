# Bundled Mod Runtimes

这里保存当前 Newma-Desk 可见 Mod 所需的完整本地源码快照。干净克隆后不再依赖本机其他项目目录。

## 安装和启动

要求 Node.js 24.15+、npm 10+、Python 3.12。

```bash
npm run runtime:bootstrap
npm run dev:stack
```

只安装 Desk 核心、Research、Trading、World Intelligence、Policy RSSHub 与 Crucix：

```bash
npm run runtime:bootstrap -- --core
```

依赖目录、虚拟环境、数据库、密钥和用户运行数据不会提交。Node 项目按锁文件安装；Python 项目按各自的 `pyproject.toml`、`requirements.txt` 或约束文件安装。Seven Cycle 附带一份只读发布快照，初始化时会在本机生成可移植的数据目录库，不提交包含机器绝对路径的 DuckDB 文件。

## 源码范围

| 运行时 | 主要用途 |
| --- | --- |
| vibe-research | 新闻、宏观、公司、基金基础研究页面与 API |
| vibe-trading | 量化、回测、交易研究页面与 API |
| world-intel-mcp、crucix | 全球情报与 OSINT 数据面 |
| rsshub-policy | 政策资讯采集 |
| deepsee | 深瞳 11 个信息触达页面 |
| seven-cycle | 七周期研究页面 |
| instock-analysis | 市场、个股、CZSC、轮动与产业链页面 |
| fund-analysis | 基金研究工作台 |
| orchestra-prisma、orchestra-agentscope | 投决会前后端、组织角色名册与角色卡 |
| creator-studio、openchatcut | 创作源工程与视频协作编辑器 |

具体来源、基准提交和许可证见 `config/bundled-runtime-sources.json`。各子目录保留自己的许可证；根仓库 Apache-2.0 不覆盖第三方源码的原许可证。
