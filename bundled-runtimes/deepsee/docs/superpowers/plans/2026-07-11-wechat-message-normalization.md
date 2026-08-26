# 微信消息规范化模块实施计划

> 执行约束：候选 1（AI 报告运行模块）不在本计划范围内，严禁修改 `app/routers/ai.py` 及其报告运行逻辑。保留工作区已有未提交修改，不暂存、不提交。

## 目标

建立一个单一、无数据库副作用的微信消息规范化模块，让 chatlog、WeChatAPI callback、历史消息读取和扩展接口共享一致的内容解析、类型映射和媒体字段规则，同时保持现有 API 与旧私有 helper 的兼容性。

## 设计

- 新增 `app/services/wechat_message_normalizer.py`，只依赖标准库和配置，不依赖 router、ORM 或具体写入流程。
- 对外提供稳定函数：内容字典解析、消息类型规范化、微信 XML payload/appmsg/image 提取、文件 appmsg 判断、chatlog 媒体 URL 构造、canonical 内容归一化。
- canonical 结果使用不可变 dataclass，至少包含 `message_type`、`content_text`、`contents`、`media_url`、`display_title` 和 `source_username`。
- `sync_service.py`、`wechat_gateway.py`、`messages.py` 先改为委托新模块；原私有 helper 暂时保留为薄兼容层。
- `hooks.py`、`extensions.py` 改用公共规范化接口，停止跨模块导入 `sync_service` 私有 helper。

## Task 1：用跨来源契约测试定义 canonical 行为

**Files**

- Create: `tests/test_wechat_message_normalizer.py`

**步骤**

1. 写测试：dict 与 JSON 字符串 contents 得到相同字典；无效输入得到空字典。
2. 写参数化测试：数字与文本消息类型得到一致 canonical 类型；`49/app` 默认归为 `link`，文件型 appmsg 可升级为 `file`。
3. 写测试：带前缀的 WeChatAPI 内容、普通 appmsg XML、收藏/转发 recorditem、image XML 均提取稳定字段。
4. 写测试：同一图片由 chatlog contents 与 callback XML 输入时，得到相同 `type=image`、`media_url` 和 contents。
5. 写测试：公众号链接由 chatlog contents 与 callback appmsg XML 输入时，得到相同标题、链接和来源账号。
6. 运行 `pytest -q tests/test_wechat_message_normalizer.py`，确认因模块不存在而失败（RED）。

## Task 2：实现纯规范化模块

**Files**

- Create: `app/services/wechat_message_normalizer.py`
- Test: `tests/test_wechat_message_normalizer.py`

**步骤**

1. 实现 `parse_contents_dict` 和 XML 内容字符串/payload 提取。
2. 实现 `extract_app_message_fields`、`extract_image_fields`、`is_file_app_message`。
3. 实现 `normalize_message_type`，统一现有数值与文本别名。
4. 实现 `build_chatlog_media_url`，保持当前 URL 编码、默认 host、图片/视频/语音/文件行为。
5. 实现 `NormalizedWechatMessage` 与 `normalize_wechat_message`，以现有 meta contents 为底，再用 XML 补全；只填充可证明的字段，不覆盖显式已有值。
6. 运行新测试直至通过（GREEN），再做小范围去重重构。

## Task 3：迁移写入路径并保留兼容入口

**Files**

- Modify: `app/services/sync_service.py`
- Modify: `app/services/wechat_gateway.py`
- Modify: `app/routers/hooks.py`
- Test: `tests/test_chatlog_media_url.py`
- Test: `tests/test_wechat_gateway_backend.py`
- Test: `tests/test_wechat_message_normalizer.py`

**步骤**

1. 先补测试，证明 callback 图片和文件 appmsg 写入 canonical `type`、`content_text`、`media_url`、`meta.contents`。
2. 运行新增测试确认旧实现失败或字段不一致（RED）。
3. 将 `sync_service` 的旧 helper 改为调用新模块，函数名和签名保持不变。
4. 将 chatlog 写入和 hooks 写入改用 canonical 结果，保持数据库字段兼容。
5. 将 WeChatAPI callback 写入改用 canonical 结果；规则引擎继续使用展示文本，不改变自动回复判定顺序。
6. 运行目标测试确认通过。

## Task 4：迁移读取和扩展路径

**Files**

- Modify: `app/routers/messages.py`
- Modify: `app/routers/extensions.py`
- Test: `tests/test_message_list_wechat_media.py`
- Test: `tests/test_extensions_wechat_messages.py`
- Test: `tests/test_wechat_message_normalizer.py`

**步骤**

1. 写回归测试，覆盖历史 numeric type、XML image、普通 appmsg、文件 appmsg 和公众号来源字段。
2. 将 messages router 的 XML/type 私有 helper 改为兼容转发；读取期修复改用 canonical 结果。
3. 将 media image/file resolver 和公众号派生字段读取改用统一提取接口。
4. 将 extensions 的网关媒体提取改用统一规范化接口。
5. 运行目标测试确认 API 输出保持兼容。

## Task 5：兼容性与边界回归

**Files**

- Test: `tests/test_chatlog_media_url.py`
- Test: `tests/test_wechat_gateway_backend.py`
- Test: `tests/test_message_list_wechat_media.py`
- Test: `tests/test_extensions_wechat_messages.py`
- Test: `tests/test_wechat_message_normalizer.py`

**步骤**

1. 运行上述目标测试集合。
2. 运行 `rg -n "from \.\.services\.sync_service import _build_chatlog_media_url|from \.\.services\.sync_service import _extract_contents_dict" app`，确认生产调用方不再跨模块依赖私有 helper。
3. 运行 `bash scripts/release_check.sh`。
4. 检查 `git diff -- app/routers/ai.py` 与执行前基线一致，确认候选 1 未被触碰。
5. 检查 `git status --short`，确认没有暂存或提交，并只报告本任务新增/修改文件。

## 非目标

- 不改变 AI 报告运行逻辑。
- 不改变自动回复事务顺序；该项留给候选 3。
- 不重构 Sync Run 编排；该项留给候选 4。
- 不拆分前端；该项留给候选 5。
- 不调整后台任务生命周期；该项留给候选 6。
