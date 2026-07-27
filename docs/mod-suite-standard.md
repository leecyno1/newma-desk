# Newma-Dock Mod Suite 接入标准

Mod Suite 用一份 `suite.json` 描述同一导入项目中的多个页面。Suite Discovery 会把每个页面编译成独立 Mod Manifest，因此页面仍然拥有独立权限、Agent Context、数据路由与运行状态。

## 最小描述

```json
{
  "schemaVersion": "1.0",
  "id": "example-suite",
  "name": "示例项目",
  "description": "示例项目的多个工作页面。",
  "version": "0.1.0",
  "publisher": "Example",
  "upstream": "https://github.com/example/project",
  "runtime": {
    "type": "external",
    "baseUrlEnv": "NEWMA_DOCK_EXAMPLE_WEB_URL",
    "defaultBaseUrl": "http://127.0.0.1:3000"
  },
  "manifest": {
    "category": "research",
    "navigation": {
      "groupLabel": "研究",
      "groupOrder": 10,
      "itemOrder": 100,
      "directory": {
        "id": "example-suite",
        "label": "示例项目",
        "order": 10
      },
      "icon": "research"
    },
    "permissions": [],
    "dataServices": [],
    "agentCapabilities": [],
    "events": { "emits": [], "accepts": [] }
  },
  "pages": [
    {
      "id": "example-overview",
      "name": "项目总览",
      "description": "项目总览页面。",
      "route": "/overview",
      "navigation": { "itemOrder": 10, "label": "总览" }
    },
    {
      "id": "example-settings",
      "name": "项目设置",
      "description": "项目自身的设置页面。",
      "route": "/settings",
      "navigation": {
        "itemOrder": 90,
        "label": "设置",
        "icon": "settings",
        "role": "settings"
      }
    }
  ]
}
```

## 继承规则

- Suite 的 `version`、`publisher`、`upstream`、运行地址和共享 Manifest 自动传给所有页面。
- 页面只声明自己的 `id`、名称、路由、顺序和差异字段。
- `pages[].manifest` 覆盖共享 Manifest 中的权限、数据服务、Actions、事件或刷新策略。
- `navigation.role = "settings"` 的页面自动进入二级侧边栏设置区，不需要 Desk 写项目名称判断。
- 商店目录通过 `suites` 注册描述文件；Suite Discovery 对外仍输出普通 Mod 列表。

## Suite Discovery Adapter

同一份 Suite Descriptor 可通过两种 Adapter 接入，展开页面、导航编译和用户偏好覆盖逻辑完全复用。

### Git / 本地文件

```json
{
  "mods": [],
  "suites": [
    {
      "id": "example-suite",
      "path": "example-suite/suite.json",
      "defaultInstall": true
    }
  ]
}
```

`defaultInstall` 可以在 Suite 目录项设置默认值，也可以由单个页面的 `defaultInstall` 覆盖。

### HTTP well-known 自动发现

目标项目在自己的 Web 服务中提供：

```text
GET /.well-known/newma-dock-suite.json
Content-Type: application/json
```

响应正文就是上面的 `suite.json`。Desk 商店只登记发现入口，不再逐页维护导航：

```json
{
  "id": "example-suite",
  "discovery": {
    "type": "http",
    "baseUrlEnv": "NEWMA_DOCK_EXAMPLE_WEB_URL",
    "defaultBaseUrl": "http://127.0.0.1:3000",
    "path": "/.well-known/newma-dock-suite.json"
  },
  "defaultInstall": true
}
```

- `baseUrlEnv` 允许部署环境覆盖服务地址，未配置时使用 `defaultBaseUrl`。
- 发现地址只接受无账号密码的 HTTP(S) Origin；本地开发可使用 `http://127.0.0.1`。
- 新标准路径固定为 `/.well-known/newma-dock-suite.json`，不跟随重定向。1.x 兼容期内，新路径返回 404 时会自动回退 `/.well-known/vibedesk-suite.json`。
- `baseUrlEnv` 新配置使用 `NEWMA_DOCK_*`；已有 `VIBEDESK_*` 描述与部署变量继续兼容，并由新前缀优先覆盖。
- Desk 对响应设置超时和 256 KiB 上限，并再次校验 Suite ID、页面 ID、路由、权限与 Navigation Descriptor。
- HTTP Adapter 不产生新的侧边栏逻辑；它和 Git / 本地文件 Adapter 都进入同一个 Suite Discovery 与 Navigation Compiler。

## 接入选择

- 随 Newma-Dock 一起发布、需要代码审计与版本固定的默认 Mod Suite，使用 Git / 本地文件 Adapter。
- 独立部署、页面会自行增减的导入项目，优先使用 HTTP well-known Adapter。项目更新声明后，Desk 下次读取商店即可自动继承页面与二级目录。
