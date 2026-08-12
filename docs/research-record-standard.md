# Newma-Desk 研究记录标准

Mod：`research-notes`
合同：`newma-desk.research-records.v1`
存储：`research-notes/records`
兼容级别：Level 3

## 1. 定位

研究记录用于沉淀每日复盘、资讯要点和 Agent 问答。它保存研究过程，不替代投资逻辑、财报、估值或研究备忘录，也不生成买卖、评级或仓位建议。

## 2. 最小结构

每条记录包含稳定 ID、类型、标题、正文和创建时间。工作区最多保存 200 条，单条正文最多 120,000 字符。

```text
id + kind + title + content + ts
```

正文使用安全的 ResearchText 子集：标题、段落、加粗、斜体、删除线、列表、引用、代码块、表格和 HTTP(S)/mailto/页内链接。原始 HTML 与脚本不会执行。

## 3. 存储与迁移

- Desk-managed Storage namespace：`research-notes`；
- 文档键：`records`；
- 本地缓存：`newma-desk.research-records.v1`；
- 旧缓存：`vr-notes`。

首次读取时自动规范化旧 `vr-notes`，写入新缓存，并在 Desk Storage 可用时迁移到用户工作区。迁移期继续镜像旧缓存，便于旧版本回退；远端不可用时保持本地离线可用。

## 4. Agent Context

页面向 Desk Agent 发布记录总数、类型、当前展开记录和存储新鲜度。标准操作包括总结当前记录、查找相关研究档案和形成后续研究清单。

Agent 可以读取页面之外的财务、公告、新闻、产业链和相关研究档案，但必须保留来源与截至日期，不得把过程记录解释成投资结论。

## 5. 依赖边界

- 不新增数据库、端口、常驻进程或独立 Agent；
- 复用 Desk Mod Storage Interface；
- 页面不接触数据库地址或凭据；
- ResearchText 不依赖通用 Markdown 运行时或 HTML 注入。
