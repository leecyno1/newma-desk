# Newma-Desk Mod Suite 接入标准

Mod Suite 用一份 `suite.json` 描述一组同属一个业务职责和数据作用域的页面。Suite Discovery 会把每个页面编译成独立 Mod Manifest，因此页面仍然拥有独立权限、Agent Context、数据路由与运行状态。同一来源运行时可以提供多个 Suite，但同一页面只能属于一个 Suite。

导航固定为两层：

1. 一级栏目栏显示 16 个核心投资模块，以及用户安装的自定义项目。
2. 二级栏目面板直接显示该模块的页面，不显示来源项目文件夹；“栏目数据与能力”固定在面板底部。

同一个 Suite 不能跨模块拆分。若同一来源运行时同时包含公司研究、策略筛选和基金研究等独立职责，应声明多个 Suite 并继续复用运行时，而不是把全部页面塞入一个模块。非投研项目可用 Suite ID 作为自定义一级项目 ID。

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
    "baseUrlEnv": "NEWMA_DESK_EXAMPLE_WEB_URL",
    "defaultBaseUrl": "http://127.0.0.1:3000"
  },
  "manifest": {
    "category": "research",
    "navigation": {
      "groupLabel": "宏观",
      "groupOrder": 10,
      "itemOrder": 100,
      "directory": {
        "id": "example-suite",
        "label": "示例项目",
        "order": 10
      },
      "project": {
        "id": "fundamentals",
        "name": "宏观",
        "order": 10,
        "description": "周期叠加、经济基本面、增长通胀、金融条件与经济预测。"
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

## 栏目身份接口

Suite 的共享 Manifest 使用 `navigation.project` 声明稳定的一级模块身份。该 ID 必须来自 16 个核心模块，或与 Suite ID 相同以表示自定义项目；页面不得覆盖：

```json
{
  "id": "equity-research",
  "name": "公司",
  "order": 60,
  "description": "公司基本面、财报、投资逻辑、同业、估值与研究档案。"
}
```

| 字段 | 约束 | 用途 |
| --- | --- | --- |
| `id` | 16 个核心模块 ID 之一，或与 Suite ID 相同 | 跨页面、跨版本稳定的模块键 |
| `name` | 1–80 字符 | 一级栏目名称与二级面板标题 |
| `order` | 非负整数 | 一级栏目默认排序 |
| `description` | 可选，1–240 字符 | 栏目说明与空状态提示 |
| `logo` | 仅旧版兼容，可省略 | 继续通过 Schema 读取，但 Desk 不再用它决定一级标志 |

### 宿主自动栏目标志

一级 Project Rail 的标志由 Desk 根据栏目身份自动生成，Manifest 不再负责视觉标志。生成结果固定为 1–2 个汉字：

1. `project.name` 含中文时，直接取前两个汉字，例如 `市场面 → 市场`、`债券研究 → 债券`。
2. 用户输入英文自定义标题时，宿主按受控词典生成中文短标，例如 `Market Pulse → 市场`；不会重新显示拉丁字母。
3. 无法识别的纯英文标题依次回退默认栏目名、稳定 `project.id` 和业务图标语义，例如 `research → 研究`、`market → 行情`、`module → 模组`。
4. Suite 应直接使用栏目注册表提供的中文 `project.name`，不得用来源项目名称覆盖栏目名称。

这套规则由宿主统一执行，一级栏与界面设置预览必须调用同一个生成函数。用户在界面设置中修改栏目标题后，一级栏的无障碍名称、二级面板标题和中文短标都会同步更新。导入方不需要准备图片、图标或自定义字符，也不能用自定义标志覆盖宿主结果。

旧版 `logo` 仍按严格判别联合读取，以保证既有 Manifest 可以安装和升级，但当前 Desk 展示会忽略该字段：

```json
{ "type": "icon", "name": "research" }
{ "type": "letter", "text": "投研" }
{ "type": "image", "src": "/assets/vibe-research.png", "alt": "Vibe Research" }
```

- `icon` 只使用 Desk 注册的内置图标：`today`、`research`、`market`、`quant`、`trading`、`settings`、`module`。
- `letter` 只接受 1–2 个可见字符，适合无需额外资源的默认接入。
- `image` 只接受无路径穿越的安全相对 URL，或 `http` / `https` URL；拒绝 `javascript:`、协议相对地址、反斜杠和编码后的路径穿越。
- 新项目 SHOULD 省略 `logo`；该字段不得作为项目辨识、排序或路由依据。
- 兼容读取不代表展示承诺，未来主版本可以正式移除旧 Logo 声明。

`navigation.project` 对普通单页 Mod 保持可选。完整 Suite 必须显式选择模块；旧 Suite 未声明时按自身 Suite ID 形成自定义一级项目，不再落入“其他”。

### 栏目内完整项目

`navigation.directory` 是数据路由、项目设置和 Agent Workspace 使用的稳定项目身份，不是可见文件夹。`directory.id` 必须等于 Suite ID；二级面板直接列出页面，内部更细的层级继续由项目自身 UI 承载。

旧 Manifest 把 `groupLabel + directory` 当作一级/二级导航时，Desk 可以兼容读取；新 Suite 必须同时输出栏目 `navigation.project` 和完整项目 `navigation.directory`。Preference Overlay 只能保存排序、冻结和栏目标题覆盖，不能把页面重新分组到其他项目。

## 继承规则

- Suite 的 `version`、`publisher`、`upstream`、运行地址和共享 Manifest 自动传给所有页面。
- 页面只声明自己的 `id`、名称、路由、顺序和差异字段。
- `pages[].manifest` 覆盖共享 Manifest 中的权限、数据服务、Actions、事件或刷新策略。
- 所有页面强制继承 Suite 的 `project`、`directory`、`groupLabel` 和 `groupOrder`；任何不同覆盖都会使 Suite 校验失败。
- 页面只声明自身 `itemOrder`、`label`、`icon`、`role` 和差异化能力字段。
- `navigation.role = "settings"` 只标识业务项目自身的设置页；Desk 的 Provider、权限与 Agent 接入统一由底部“栏目数据与能力”管理。
- `category`、`groupLabel` 和页面 `icon` 仍用于能力分类、兼容旧客户端或页面语义，不改变一级栏目归属。
- 商店目录通过 `suites` 注册描述文件；Suite Discovery 对外仍输出普通 Mod 列表。

## 接入要求

- 完整项目使用一个稳定的栏目 `project.id`；来源项目改名或换服务时不得随意修改栏目归属。
- 同一来源运行时可以按独立业务职责声明多个 Suite；同一页面不得重复出现在多个 Suite。
- 项目原有路由或标签逐项映射为 `pages[]`，不要把多个页面压成一个设置首页。
- 页面 `itemOrder` 在项目内保持唯一且留出间隔，建议 `10`、`20`、`30`。
- 项目设置作为同一 Suite 的普通页面声明，并标记 `navigation.role = "settings"`。
- Manifest 只保存发布默认值；冻结、隐藏、项目内页面排序和栏目标题重命名仍由 Preference Overlay 管理。标题覆盖最多 40 个字符，只保存在当前浏览器 Workspace，“恢复默认”只移除标题覆盖，不改变稳定的栏目 `project.id`、完整项目身份或冻结状态。

## Newma 主题模板

Suite 中的每个页面共享同一主题接入规则，不得各自复制一套蓝白或深蓝色板：

1. 前端入口导入 `@newma-desk/desk-ui/mod-theme.css`。
2. 通过 `@newma-desk/mod-sdk` 建立宿主连接；SDK 默认自动应用 `vibedesk:init.appearance`。
   独立打开且页面未显式选择主题时，SDK 固定回落到 Newma 浅色，不读取操作系统的通用蓝白/蓝黑主题。
3. 组件只使用 `--vibe-*` / `--newma-*` 或模板提供的 shadcn 语义变量。
4. 图表从 `--vibe-chart-*` 读取颜色，并在 `newma:themechange` 或新的 `vibedesk:init` 到达后重绘。
5. 金融涨跌继续使用 `--vibe-positive` 与 `--vibe-negative`，不得把品牌强调色误作涨跌色。

导入器可以自动生成 Wrapper、入口导入和 SDK 初始化代码，因此协作型项目无需逐页手工适配。对硬编码颜色的上游 CSS，导入器只能做静态诊断并生成迁移清单，不能安全地猜测每一种蓝色、白色或灰色的语义。完全跨域且不接入桥接协议的页面不具备自动换肤承诺。

模板同时为 Tailwind / shadcn 提供 HSL 语义变量，为 Bootstrap 5 提供 `--bs-*` 变量映射，并兼容 Bootstrap 3、Ace 与已经编译进产物的 `.btn-primary`、`.text-primary`、`.bg-primary` 等公开品牌语义类；SDK 会同步 `data-theme`、`data-vibedesk-theme` 和 `data-bs-theme`。这些映射只接管“品牌强调”语义，不会覆盖涨跌、成功、警告或错误状态。因此采用标准变量或标准语义类的页面只需接入一次，之后 Newma 浅色、深色或品牌色板变化都会自动继承，不应在每个页面复制色板。

接入和发布前运行：

```bash
npm run mods:theme:check
# 检查某个尚未放入仓库的项目
npm run mods:theme:check -- /absolute/path/to/mod/frontend
# 本地服务启动后，逐页检查浅色 / 深色与遗留蓝白主体
npm run mods:theme:audit
```

检查器会拦截常见 Tailwind Blue / Sky / Indigo / Slate 主体色、默认蓝灰十六进制色板和白色浏览器主题色，并确认内置 Mod 与已发现的外部运行时都保留主题 Adapter。确属金融涨跌、状态或数据系列语义的颜色应先改用 `--vibe-positive`、`--vibe-negative`、`--vibe-warning`、`--vibe-error` 或 `--vibe-chart-*`；只有经过人工确认的例外才可按具体规则使用 `newma-theme-allow:<rule-id>`，该标记不会跳过同一行的其他检查规则。

运行态审计会把浏览器系统主题设为与 Desk 相反的模式，确保页面真正继承宿主而不是碰巧跟随系统；它还会检查大面积蓝色背景、蓝色控件、冷白主体和主题变量。确属数据可视化语义的运行态例外应在最小 DOM 子树上声明 `data-newma-theme-allow` 或 `.newma-theme-allow`，不得给整页加豁免。

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
GET /.well-known/newma-desk-suite.json
Content-Type: application/json
```

响应正文就是上面的 `suite.json`。Desk 商店只登记发现入口，不再逐页维护导航：

```json
{
  "id": "example-suite",
  "discovery": {
    "type": "http",
    "baseUrlEnv": "NEWMA_DESK_EXAMPLE_WEB_URL",
    "defaultBaseUrl": "http://127.0.0.1:3000",
    "path": "/.well-known/newma-desk-suite.json"
  },
  "defaultInstall": true
}
```

- `baseUrlEnv` 允许部署环境覆盖服务地址，未配置时使用 `defaultBaseUrl`。
- 发现地址只接受无账号密码的 HTTP(S) Origin；本地开发可使用 `http://127.0.0.1`。
- 新标准路径固定为 `/.well-known/newma-desk-suite.json`，不跟随重定向。兼容期内，新路径返回 404 时会依次回退 `/.well-known/newma-dock-suite.json` 与 `/.well-known/vibedesk-suite.json`。
- `baseUrlEnv` 新配置使用 `NEWMA_DESK_*`；已有 `NEWMA_DOCK_*`、`VIBEDESK_*` 描述与部署变量继续兼容，并由新前缀优先覆盖。
- Desk 对响应设置超时和 256 KiB 上限，并再次校验 Suite ID、项目身份、旧版兼容 Logo 声明、页面 ID、路由、权限与 Navigation Descriptor。
- HTTP Adapter 不产生新的侧边栏逻辑；它和 Git / 本地文件 Adapter 都进入同一个 Suite Discovery 与 Navigation Compiler。

## 接入选择

- 随 Newma-Desk 一起发布、需要代码审计与版本固定的默认 Mod Suite，使用 Git / 本地文件 Adapter。
- 独立部署、页面会自行增减的导入项目，优先使用 HTTP well-known Adapter。项目更新声明后，Desk 下次读取商店即可自动继承页面与二级项目菜单。
