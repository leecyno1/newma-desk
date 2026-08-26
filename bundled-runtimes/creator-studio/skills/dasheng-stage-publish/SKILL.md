---
name: dasheng-stage-publish
description: Use when entering the slim Newma publish execution stage to validate transwrite outputs, create publish packs, push drafts/manual packages, and recover published links.
---

# Newma Stage: Publish｜发布执行

## 定位

这是 `transwrite` 之后的轻量执行层。

正式阶段顺序：

`intake -> brief -> draft -> transwrite -> publish -> postmortem`

Publish 不再改写核心正文、重剪主视频、重做播客或重算图表。上述核心生产动作全部归入 Draft / Transwrite。

Publish 允许生成平台衍生包装：平台标题、主题文案、标签、完整构图封面、短标题、分类、合集/活动候选和必要的比例衍生版。衍生包装不得改变已验收的事实、结论和主视频内容。

Publish 可调用账号运营策略 Skill 审查发布包装、冷启动实验和矩阵角色，但这是轻量 advisory 层，不允许重写核心事实或替代平台发布执行器。

四平台标题、文案、标签、封面、活动和账号路由细则见 [references/platform-packaging.md](references/platform-packaging.md)。

## 正式输入

- `transwrite_manifest.json`
- `publish_decision.json`

`publish_decision.json` 可选提供 `account_stage`、`account_goal`、`account_slot`、`matrix_role`、`target_audience`、`conversion_goal`、`weekly_capacity` 和 `account_operations`。

批量分发应先使用 `configs/publish/publish_matrix.schema.json` 描述“内容版本 × 平台 × 账号槽位”，再展开为任务级 `publish_decision.json`：

```bash
python3 scripts/expand_publish_matrix.py \
  --matrix ~/Desktop/自媒体创作/<run_id>/05_发布/publish_matrix.json \
  --output ~/Desktop/自媒体创作/<run_id>/05_发布/publish_decision.json \
  --fail-on-error
```

每个展开任务必须拥有独立的 `task_id`、`batch_id`、`variant_id`、`channel`、`account_slot`、`artifact_overrides` 和最终 `publish_metadata` 快照。元数据继承顺序固定为：矩阵全局默认 → 矩阵平台默认 → 账号注册表平台预设 → 内容版本 → 账号槽位预设 → 单目标覆盖。不得在执行时重新共享或临时继承另一账号的表单。

账号注册表中的 `account_metadata`、`publish_presets` 和 `network_policy` 只能保存非敏感配置。`owner_alias`、`operator_alias`、分组、主副账号角色和代理策略名称可以进入 Git；密码、Cookie、Token、API Secret 和实际代理凭据禁止进入。

矩阵展开器会递归检查发布预设与平台参数中的敏感字段名；命中后剥离字段并把整个矩阵标记为 `blocked`，禁止敏感值进入任务快照或日志。

缺少 `transwrite_manifest.json` 或 `publish_decision.json` 时禁止执行。

## 职责

1. 验收转写包是否具备对应渠道所需材料。
2. 生成公众号、微博、X、小红书、抖音、B站、播客等发布包。
3. 对可自动/半自动发布的平台生成执行器调用计划。
4. 对缺少执行器的平台导出人工发布包。
5. 发布后回收草稿 ID、正式链接、发布时间、截图或错误状态。
6. 为公众号、小红书、抖音和 X 生成账号运营审查请求，把冷启动/低流量/沉寂/风险/矩阵实验号设为受控执行前必审。
7. 按逻辑账号把多个内容版本路由到不同平台账号槽，并在发布前检查命名登录态。
8. 实时发现平台活动；禁止虚构活动名，只有高度相关且经编辑确认后才能参加。

## 验收规则

Publish 不只看 lane `status`，还必须检查关键最终产物是否存在。

- 文字渠道：需要 `wechat_article.final.html` 或 `wechat_article.final.md`。
- 视频渠道：需要最终 MP4。
- 播客渠道：需要最终音频文件。
- 缺少关键产物时，即使 lane 标记为 `completed`，也必须写成 `blocked_or_waiting`。

## 标准命令

```bash
python3 scripts/build_stage5_publish.py \
  --transwrite-manifest ~/Desktop/自媒体创作/<run_id>/04_转写/transwrite_manifest.json \
  --publish-decision ~/Desktop/自媒体创作/<run_id>/05_发布/publish_decision.json
```

统一入口：

```bash
python3 scripts/run_mainline_stage.py publish --run-id <run_id>
```

安全预演：

```bash
python3 scripts/run_mainline_stage.py publish \
  --transwrite-manifest ~/Desktop/自媒体创作/<run_id>/04_转写/transwrite_manifest.json \
  --publish-decision ~/Desktop/自媒体创作/<run_id>/05_发布/publish_decision.json \
  --dry-run
```

`--dry-run` 只会生成 `publish_dry_run_report.json` 和各渠道执行计划，不会触发真实发布。

发布通路体检：

```bash
python3 scripts/run_mainline_stage.py doctor --publish
python3 scripts/run_mainline_stage.py doctor --publish --channel wechat_article --channel xiaohongshu_video
```

`doctor --publish` 不需要 `transwrite_manifest.json`，只检查本地 skill、外部依赖根目录、CLI 二进制和持久化浏览器 Profile 配置，不会打开浏览器、读取 cookies 或发布内容。

双账号四平台 Campaign：

```bash
python3 scripts/build_publish_campaign.py \
  --spec ~/Desktop/自媒体创作/<run_id>/05_发布/campaign_spec.json \
  --output-dir ~/Desktop/自媒体创作/<run_id>/05_发布

python3 scripts/publish_accounts.py \
  --check-auth \
  --channel xiaohongshu_video,douyin_video,bilibili_video,wechat_channels_video \
  --output ~/Desktop/自媒体创作/<run_id>/05_发布/account_auth_report.json

# 再次构建会合并账号检查结果；只有 account_auth_status=valid 才能进入最终确认。
python3 scripts/build_publish_campaign.py \
  --spec ~/Desktop/自媒体创作/<run_id>/05_发布/campaign_spec.json \
  --output-dir ~/Desktop/自媒体创作/<run_id>/05_发布

python3 scripts/execute_publish_campaign.py \
  --campaign ~/Desktop/自媒体创作/<run_id>/05_发布/publish_campaign.json
```

最后一条命令默认仍是 Dry Run。只有当前会话明确确认后才可追加 `--confirm-execute`；账号主执行器登录态未全部验证时，Campaign 必须整体阻断。

发布批次验收：

```bash
python3 scripts/publish_guard.py \
  --publish-manifest ~/Desktop/自媒体创作/<run_id>/05_发布/publish_manifest.json

python3 scripts/run_mainline_stage.py doctor \
  --publish-manifest ~/Desktop/自媒体创作/<run_id>/05_发布/publish_manifest.json
```

`publish_guard.py` 只检查某个发布批次的回填结果是否自洽，不检查依赖安装，也不会打开浏览器、读取 cookies 或发布内容。它必须同时读取 `publish_manifest.json` 与 `publish_verification_report.json`；缺少验真报告时不得通过。矩阵任务按 `task_id` 独立验收，旧发布包才回退到 `(topic_id, channel)`。每条回填结果都必须能追到磁盘上的 `publish_result.json`，且文件中的核心发布字段必须与 manifest/verification 记录一致。

默认模式会写出报告并回填 `publish_manifest.publish_guard`，即使未通过也返回 0，方便人工查看报告。CI 或正式门禁必须追加 `--fail-on-error`，未通过时返回非 0：

```bash
python3 scripts/publish_guard.py \
  --publish-manifest ~/Desktop/自媒体创作/<run_id>/05_发布/publish_manifest.json \
  --fail-on-error
```

发布结果回填：

```bash
python3 scripts/record_publish_result.py \
  --channel-pack ~/Desktop/自媒体创作/<run_id>/05_发布/channel_packs/<topic_id>/<channel>/<task_id>/channel_pack.json \
  --success true \
  --status draft \
  --draft-id <draft_id> \
  --verification-status verified \
  --account <account_name>
```

执行器或人工发布完成后必须用该入口回填平台 URL、草稿 ID、截图或错误状态。它只写回结果文件和验真报告，不会触发发布。

每次回填都会追加 `publish_result_history.json` 和 `publish_results/attempt-XXXX.json`，不会覆盖历史失败。`publish_result.json` 只保存该任务最新结果。相同平台的两个账号必须分别回填各自 `task_id` 对应的渠道包。

失败回填还会生成 `publish_retry_request.json`。标准失败分类为 `authentication`、`platform_risk`、`rate_limit`、`validation`、`network`、`timeout`、`dependency`、`content_rejected` 和 `unknown`：

- 网络、超时和限流可以计算指数退避时间，但重试仍通过 `publish_retry_request.json` 单独授权，不由定时器自动执行。
- 登录失效、表单错误和依赖缺失必须先完成人工动作，再允许重试。
- 普通声明/协议/封面确认弹窗在任务已授权后自动处理，不逐项请求确认。
- 用户自有账号、已同步到当前电脑、且能与当前平台/账号/时间明确匹配的短信或邮件一次性验证码，自动读取、填写一次并继续；不得输出、持久化或写入日志、回执、截图标注、manifest、仓库和长期记忆。
- 平台风控、图形验证码、滑块、来源或账号不明的一次性验证码，以及内容拒绝不得自动重试；必须停止当次交互并报告。
- `publish_retry_request.json` 永远写入 `automatic_execution=false`，不能由定时器绕过用户确认直接发布。

回填后 `publish_manifest.json` 与 `publish_verification_report.json` 会生成统一的 `publish_summary`：

- `pending_execution`：尚无渠道回填。
- `partially_recorded`：部分渠道已回填，仍有渠道待执行。
- `failed`：任一渠道回填失败。
- `all_drafted`：全部渠道只推送到草稿或定时草稿。
- `all_published`：全部渠道均回收正式发布状态。
- `completed_with_mixed_status`：全部渠道已回填，但草稿、正式发布、人工上传等状态混合。

草稿 ID 只能说明“已推草稿”，不得对外汇报为“已发布”。

`publish_verification_report.json` 中：

- `published_links` 只允许记录 `status=published`、`verification_status=verified` 且有正式平台 URL 的结果。
- `draft_records` 专门记录 `status=draft|scheduled`、`verification_status=verified` 且有草稿 ID 的结果。
- `verification_status=verified` 是进入 `published_links` 或 `draft_records` 的必要条件。
- `record_publish_result.py` 不会因为存在正式 URL 或草稿 ID 自动推断 `verified`；执行器或人工回填必须显式传入 `--verification-status verified`。
- 不得把草稿 ID 塞进 `published_links`。
- `status=published` 但没有正式 URL、或 `status=draft` 但没有草稿 ID 时，整体状态必须是 `needs_manual_verification`。

执行器标准 payload：

```bash
python3 scripts/build_publish_payload.py \
  --channel-pack ~/Desktop/自媒体创作/<run_id>/05_发布/channel_packs/<topic_id>/<channel>/channel_pack.json
```

`publish_payload.json` 是平台执行器的统一输入，执行器完成后必须再调用 `record_publish_result.py` 回填结果。

生成执行器输入前必须运行平台表单预检：

```bash
python3 scripts/validate_publish_form.py \
  --channel-pack <channel_pack.json> \
  --fail-on-error
```

规则位于 `configs/publish/platform_form_rules.json`。确定性的缺失字段和文件错误必须阻断；平台长度等可能变化的限制默认只告警，重新核验后才能提升为阻断规则。预检输出 `platform_form_validation.json`，发布后仍必须运行 Publish Guard，两者不可互相替代。

安全执行入口：

```bash
python3 scripts/execute_publish_request.py \
  --execution-request ~/Desktop/自媒体创作/<run_id>/05_发布/channel_packs/<topic_id>/<channel>/execution_request.json
```

默认只做 dry-run。只有当前会话明确确认后，才允许追加 `--confirm-execute` 调用受支持的本地路线；浏览器、人工包和未配置受控适配器的外部 CLI 仍只输出下一步命令。

`--confirm-execute` 允许两类受控路线：公众号 `skill_draft_push`，以及带登录检查、命令预演和结果回填的 `social-auto-upload` 四平台视频路线。其他 `api_first_cli`、普通 `external_cli`、`mcp_fallback`、`browser_confirm_fallback`、`manual_package` 仍不得由该入口自动调用。

## 标准输出

- `07_发布计划.md`
- `07_发布包.md`
- `publish_preflight_report.md`
- `channel_packs/<topic_id>/<channel>/channel_pack.json`
- `channel_packs/<topic_id>/<channel>/<task_id>/channel_pack.json`（矩阵任务）
- `channel_packs/<topic_id>/<channel>/README.md`
- `channel_packs/<topic_id>/<channel>/publish_payload.json`
- `channel_packs/<topic_id>/<channel>/platform_form_validation.json`
- `channel_packs/<topic_id>/<channel>/publish_result.json`
- `channel_packs/<topic_id>/<channel>/<task_id>/publish_result_history.json`（矩阵任务重试历史）
- `channel_packs/<topic_id>/<channel>/<task_id>/publish_results/attempt-XXXX.json`
- `channel_packs/<topic_id>/<channel>/<task_id>/publish_retry_request.json`
- `channel_packs/<topic_id>/<channel>/account_operations_request.json`
- `channel_packs/<topic_id>/<channel>/account_operations_advice.json`（执行运营审查后）
- `channel_packs/<topic_id>/<channel>/account_operations_advice.md`（执行运营审查后）
- `channel_execution_manifest.json`
- `publish_verification_report.json`
- `publish_manifest.json`
- `publish_guard_report.json`（可选，批次验收输出）

## 平台执行器矩阵

- 公众号：`baoyu-post-to-wechat` / `wechat-multi-publisher` / `md2wechat`
- 微博：`baoyu-post-to-weibo`
- X：`baoyu-post-to-x`
- 小红书：`social-auto-upload-bridge` → API-first/MCP/持久化浏览器 fallback
- 抖音：`social-auto-upload-bridge` → `douyin-upload-skill` / 持久化浏览器 fallback
- B站：`social-auto-upload-bridge` → `bilibili-upload-bridge` / 人工包；归档的 `biliup-rs` 仅作历史参考
- 视频号：`social-auto-upload-bridge` → 持久化浏览器 / 人工包
- 播客：人工上传或音频平台 API
- 验真：`publish-guard`
- 账号运营审查：`dasheng-publish-operations-bridge` → external `agent-skills-launch-pack`
- 可视化账号中心：`qianfan-sync`，数据目录必须位于 `NewmaPublishSessions`
- 浏览器会话后备：`postbot` 公开稳定分支构建产物
- 活动发现/UI 适配：`opencli`；抖音活动优先实时查询

## 浏览器登录态

浏览器型发布必须使用持久化发布 Profile，不得使用 Chrome DevTools MCP 临时 profile、一次性自动化 profile 或项目目录保存 cookies。

有头发布浏览器必须遵守 `configs/publish/browser_profiles.json.window_policy`：禁止全屏/最大化，默认用 `1180×780` 小窗在附属屏幕后台启动；附属屏未连接时才在主屏边缘以小窗降级打开。不得抢占用户当前窗口的全屏状态或主屏工作区。

统一配置：

```bash
configs/publish/browser_profiles.json
```

统一打开命令：

```bash
python3 scripts/open_publish_browser.py xiaohongshu_video
python3 scripts/open_publish_browser.py xiaohongshu_video_2
python3 scripts/open_publish_browser.py douyin_video
python3 scripts/open_publish_browser.py douyin_video_2
python3 scripts/open_publish_browser.py bilibili_video
python3 scripts/open_publish_browser.py bilibili_video_2
python3 scripts/open_publish_browser.py wechat_channels_video
python3 scripts/open_publish_browser.py wechat_channels_video_2
```

每个 `channel_pack.json` 必须写入 `browser_profile`，包括 `profile_dir`、`entry_url` 和 `open_command`。Agent 只允许复用该 profile 目录，不允许读取、导出、复制或提交 cookies。

## 多平台账号中心

- 非敏感账号槽统一登记在 `configs/publish/account_registry.json`。
- 跨平台逻辑账号（例如 `publisher-a` / `publisher-b`）只负责路由，真实昵称保留在平台登录态中；每个平台分别绑定稳定的 `slot-1` / `slot-2`。
- 每个槽位可配置 `account_metadata`、`publish_presets` 和 `network_policy`；矩阵展开后必须固化为任务快照。
- 浏览器登录态保存在 `~/Library/Application Support/NewmaPublishProfiles/`。
- CLI 登录态保存在 `~/Library/Application Support/NewmaPublishSessions/social-auto-upload/cookies/`。
- 公众号 API 凭据从环境变量或 `~/.baoyu-skills/.env` 读取，凭据值不得进入账号注册表、manifest 或日志。
- 初始化安全目录：`python3 scripts/publish_accounts.py --init`。
- 轻量状态检查：`python3 scripts/publish_accounts.py`。
- 深度登录检查：`python3 scripts/publish_accounts.py --check-auth`，只调用上游登录校验，不打开浏览器、不发布、不输出 Cookie 内容。
- 可视化账号中心预检：`python3 scripts/start_publish_console.py`。
- 启动本地千帆云递账号/素材/队列控制台：`python3 scripts/start_publish_console.py --confirm-start`，访问 `http://127.0.0.1:5173`。运行数据只写入 `NewmaPublishSessions/qianfan-sync`。

## 强约束

1. 只允许 `completed` / `packageable` 的 transwrite lane 进入发布执行包；兼容旧文字包时 `ready_base_package` 可视为可打包。
2. 不允许把 `planned_for_render`、`ready_for_agent_execution`、`ready_for_skill_execution`、`blocked_missing_api_key` 等状态误报为可发布。
3. 没有正式执行器的平台，只能导出人工发布包。
4. 任何浏览器/平台发布动作都必须先取得当前任务或 Campaign 的明确授权；用户已明确要求发布后，授权范围内的最终点击、普通弹窗和可明确匹配的一次性验证码不再逐项暂停确认。
5. 未经过链接回收和 `Publish Guard` 验真，不得回报“已发布”。
6. 旧 `scripts/publish_video_supplement.py` 仅作为兼容工具或视频补充参考，不再是正式 publish 主入口。
7. 发布包、截图、平台回执、临时 HTML、上传素材副本不得写入 `skills/` 目录或项目根目录；默认写入 `~/Desktop/自媒体创作/<run_id>/05_发布/...`。
8. 小红书、抖音、公众号等需要登录的平台必须通过 `scripts/open_publish_browser.py` 打开持久化 Profile 完成登录和上传准备。
9. 小红书主路径优先 API-first Skill/CLI/MCP，浏览器自动化只做 fallback；不要把它降级成纯手动搬运。
10. `agent-skills-launch-pack` 只是起号/运营策略上游，不得把它误报为登录、上传、定时或发布工具。
11. 上游默认放在 `${AGENT_SKILLS_LAUNCH_PACK_ROOT:-vendor/reserved/publish/agent-skills-launch-pack}`，通过 `AGENT_SKILLS_LAUNCH_PACK_ROOT` 覆盖；不全局安装，不 vendor 到项目 `skills/`。
12. `publish_campaign.json.summary.account_auth_status` 未达到 `valid` 时，禁止批量 `--confirm-execute`。
13. 活动名必须来自发布当日实时发现；不得根据标题或旧活动记录自动猜测。
14. 竖版封面中的来源图表必须完整显示，禁止为填满画幅而裁掉标题、坐标、图例或数据标签。
