# 向量库决策记录

**日期**: 2026-05-16  
**状态**: Accepted  
**范围**: 调研报告语义检索、AI 报告证据链、报告切片引用

## 1. 当前状态

项目当前存在两套语义检索路径：

1. FastAPI 后端的 `backend/services/vector_db_service.py` 使用 Qdrant，集合名为 `research_reports`。
2. Next.js 的 `app/api/reports/search/route.ts` 直接调用 OpenAI Embeddings，并尝试使用 pgvector SQL 查询 `ResearchReport.embedding`。

这种双轨实现会导致以下问题：

- Embedding 模型不一致：FastAPI 使用 sentence-transformers，本地多语种 MiniLM；Next.js 使用 OpenAI `text-embedding-3-small`。
- 向量维度不一致：不同模型维度不同，不能混用。
- 检索结果不一致：同一个查询在前后端可能返回完全不同结果。
- 成本和部署不一致：Next.js 路径依赖 OpenAI API，FastAPI 路径依赖本地模型和 Qdrant。
- AI 报告证据链无法稳定引用 chunk 级证据。

## 2. 决策

以 **Qdrant** 作为中期主向量库，FastAPI 作为唯一语义检索权威服务。

原因：

1. 当前 Docker Compose 已包含 Qdrant 服务。
2. FastAPI 已有 Qdrant 服务封装和 warmup/status/similar search API。
3. 报告量增长后，Qdrant 更适合独立扩展、过滤和维护集合。
4. AI 报告生成、报告切片、实体链接都在 Python 后端更易统一。
5. Next.js 应退回 BFF/代理职责，不应直接生成 embedding 或执行 pgvector SQL。

## 3. 主路径

后续报告检索主链路：

1. 上传或导入调研报告。
2. FastAPI 解析报告内容。
3. FastAPI 生成 `ResearchReportChunk`。
4. FastAPI 使用统一 embedding 模型生成 chunk 向量。
5. Qdrant 保存 chunk 向量和 payload。
6. PostgreSQL 保存 chunk 元数据和 `embedding_id`。
7. 搜索返回 chunk 级证据：report id、chunk id、chunk index、content、score、metadata。
8. AI 报告引用 chunk id 作为证据来源。

## 4. Next.js 迁移策略

`app/api/reports/search/route.ts` 不应长期直接调用 OpenAI Embeddings 和 pgvector。

迁移顺序：

1. 保留当前接口 URL，避免破坏前端页面。
2. 内部实现改为代理 FastAPI `/api/research-reports/search/similar` 或后续 chunk search endpoint。
3. 前端搜索结果字段保持兼容。
4. 确认前端无直接依赖 pgvector 后，移除 Next.js 中 embedding 生成逻辑。

## 5. pgvector 角色

短期不删除 Prisma 中 `ResearchReport.embedding` 字段，避免迁移风险。

pgvector 可作为：

- 轻量部署 fallback。
- 历史数据兼容字段。
- 后续小规模单库部署选项。

但在当前项目主线中，pgvector 不作为权威检索路径。

## 6. Embedding 模型策略

短期沿用 FastAPI 当前模型：

`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`

后续如需升级模型，必须：

1. 新建 Qdrant collection 或记录 embedding model version。
2. 批量重建所有 chunk embeddings。
3. 保留旧 collection 直到新索引验证通过。
4. 在搜索结果中返回 `embedding_model`。

## 7. 新增数据结构

新增 `ResearchReportChunk`，用于保存报告切片元数据：

- `reportId`
- `chunkIndex`
- `content`
- `tokenCount`
- `embeddingId`
- `entities`
- `metadata`
- `createdAt`
- `updatedAt`

`embeddingId` 对应 Qdrant point id。

## 8. 验收标准

1. 系统有明确主向量库：Qdrant。
2. FastAPI 是唯一权威检索服务。
3. PostgreSQL 保存 chunk 元数据。
4. 搜索结果可以引用 chunk 级证据。
5. Next.js 语义搜索最终只做代理，不直接生成 embedding。
