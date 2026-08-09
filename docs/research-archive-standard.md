# Newma-Desk Research Archive Index 1.0

## 1. 目标

Research Archive Index 为研究流程提供统一的档案发现 Interface。它汇总：

- 用户上传的研报文件；
- 研究记录；
- 投资逻辑；
- 财报研究；
- 同业比较；
- 预测与估值；
- 研究备忘录。

索引只保存或返回引用与最小元数据，不复制底层研究内容。

## 2. 引用合同

每条引用包含：

- 稳定索引 ID；
- 档案类型；
- 来源 Mod ID；
- 来源档案 ID；
- 标题；
- 状态；
- 可选证券身份与截至日期；
- 更新时间、标签和来源 revision。

禁止进入索引的内容：

- 研究记录正文；
- 投资逻辑全文和证据明细；
- 财务预测表、同业明细和估值矩阵；
- 新闻正文、历史行情和财务原始数据；
- PDF、Word、图片或其他文件内容。

TypeScript 合同位于 `packages/contracts/src/researchArchive.ts`，版本为 `newma-desk.research-archive.v1`。

## 3. Desk Interface

```http
GET /api/research-archive
X-User-Id: <user>
X-Workspace-Id: <workspace>
```

Desk 按用户和工作区读取以下已存在的 Mod Storage 文档，并即时编译引用：

| 来源 Mod | namespace | key |
| --- | --- | --- |
| `research-notes` | `research-notes` | `records` |
| `thesis-tracker` | `thesis-tracker` | `portfolio` |
| `earnings-workbench` | `earnings-workbench` | `workbooks` |
| `peer-comparison` | `peer-comparison` | `cases` |
| `valuation-workbench` | `valuation-workbench` | `models` |
| `research-memo` | `research-memo` | `memos` |

该 Interface 不新增数据库表、端口、后台任务或重复持久化。SQLite 与未来 PostgreSQL Adapter 切换时，Research Archive Index 的 Interface 保持不变。

## 4. 文件 Adapter

上传研报继续由 Research Integrated Domain Runtime 的文件 Adapter 管理。研究档案页面只把文件 ID、名称、行业、格式、大小和上传时间转换为 `uploaded-report` 引用；下载和删除仍调用原文件 Interface。

## 5. Agent Context

研究档案页面向 Desk Agent 提供：

- 总档案数、可见档案数和分类型数量；
- 草稿、待更新和失效档案数量；
- 当前选中的引用；
- 当前搜索与类型筛选。

Agent 需要正文时，应根据 `sourceModId + artifactId` 回到来源 Mod 读取，不得把索引误当成完整研究材料。

## 6. 验收

1. 不同用户和工作区的索引互不可见；
2. 来源文档不存在或格式异常时独立降级；
3. 索引响应不包含来源正文；
4. 上传文件与结构化档案在同一页面可检索；
5. 选择引用后，Desk Agent Context 包含来源和档案 ID；
6. 点击来源引用可回到对应 Mod。
