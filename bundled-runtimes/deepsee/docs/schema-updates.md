# Schema Updates: Report Artifacts

## Overview
- Added table `report_artifacts` for module级结构化结果（市场观点、会议路演、反驳分析、高分联系人等）。
- `reports` 表新增一对多关系 `artifacts`，用于按模块存储 JSON / Markdown / CSV 等多种格式。
- `report_artifacts` 字段：
  - `id` 主键
  - `report_id` 外键关联 `reports.id`
  - `module` 模块标识（如 `market`, `meetings`, `counter`, `contacts`）
  - `title` 可选标题
  - `content_type` 内容类型（`json`/`html`/`markdown`/`csv` 等）
  - `sequence` 展示顺序
  - `data_json` 结构化数据
  - `data_text` 文本数据（HTML/Markdown/CSV）
  - `meta` 附加元信息
  - `created_at` / `updated_at` 时间戳

## Migration Guide (SQLite)
1. 备份数据库 `cp data/app.db data/app.db.bak`。
2. 通过 SQLite CLI 添加新表：
   ```sql
   CREATE TABLE IF NOT EXISTS report_artifacts (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       report_id INTEGER NOT NULL,
       module VARCHAR(64) NOT NULL,
       title VARCHAR,
       content_type VARCHAR(32),
       sequence INTEGER DEFAULT 0,
       data_json JSON,
       data_text TEXT,
       meta JSON,
       created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
       updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
       FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE
   );
   CREATE INDEX IF NOT EXISTS ix_report_artifacts_report_id ON report_artifacts(report_id);
   CREATE INDEX IF NOT EXISTS ix_report_artifacts_module ON report_artifacts(module);
   ```
3. 若需要兼容旧 summary 记录，可将原 `reports.result_body` 迁移为默认 `report_artifacts` 记录：
   ```sql
   INSERT INTO report_artifacts (report_id, module, content_type, data_text)
   SELECT id, 'legacy', COALESCE(result_type, 'html'), result_body
   FROM reports
   WHERE result_body IS NOT NULL;
   ```
4. 部署后重新启动服务，确保 `Base.metadata.create_all()` 会在新环境自动创建缺失表。

## Next Steps
- summary 逻辑需改造为按模块写入 `report_artifacts`。
- API `/api/reports/{id}` 已准备返回 `artifacts` 列表，可用于前端模块化渲染。
- 后续可增补字段（如 `checksum`、`source_messages`），或扩展为多语言内容。

## Analysis Snapshots 表
- 新增 `analysis_snapshots` 表，用于持久化 AI 总结所需的消息 JSON 快照。
- 字段：
  - `id` 主键
  - `scope_key` 依据 message_ids + filters 生成的哈希，便于复用
  - `filters`、`options`：请求条件
  - `message_ids`：包含在快照中的消息 ID 列表
  - `messages`：消息详情数组（JSON）
  - `contact_ratings`：联系人评分与标签信息（JSON）
  - `meta`：统计数据（总数、时间范围等）
  - `status`：`ready`/`stale`
  - `message_count`、`time_from`、`time_to`：基础统计
  - `created_at`/`updated_at`

### Migration Steps
```sql
CREATE TABLE IF NOT EXISTS analysis_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope_key VARCHAR,
    title VARCHAR,
    filters JSON,
    options JSON,
    message_ids JSON,
    messages JSON,
    contact_ratings JSON,
    meta JSON,
    status VARCHAR DEFAULT 'ready',
    message_count INTEGER DEFAULT 0,
    time_from DATETIME,
    time_to DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_analysis_snapshots_scope_key ON analysis_snapshots(scope_key);
```

> 注：SQLite 无原生 JSON 类型，以上定义以 TEXT 形式存储 JSON。执行迁移前请备份数据库。

### 使用建议
- 消息同步后调用 `upsert_snapshot()` 刷新对应窗口数据。
- AI 总结 (`/api/ai/summary`) 直接读取最新快照，保证结果与消息列表一致。

---

## Message.derived 字段更新（2025-10-20）

- 变更要点
  - 删除 `key_info` 字段；统一使用：
    - `summary`：可见摘要文本（带前缀 `ai:` 或 `fallback:` 便于溯源）。
    - `summary_full`：较长摘要（用于邮件和后续扩展）。
    - `summary_origin`：`fallback` | `tool`，标识来源；前端据此配色。
  - 其余派生字段维持：`keywords`、`meeting_number`、`platform`、`tone`、`category`、`meeting_link` 等。

- 写入策略（两段式）
  - 兜底阶段：`populate_fallback_derived()` 即时写入 `summary` 与基本派生；
  - 覆盖阶段：`ensure_message_features()` 仅在小模型成功时完全覆盖 `summary` 并将 `summary_origin=tool`；不做“填空式合并”。

- 前端渲染建议
  - 绑定 `derived.summary` 并根据 `summary_origin` 上色；展示层去除前缀字符串。
