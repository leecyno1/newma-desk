# 前端模块化约束

`static/index.html` 仍是当前统一入口，但已经过大。为了避免继续恶化，后续前端改动遵循以下规则：

1. 新增大段 JS/CSS 不再直接塞入 `index.html`，优先放入 `static/modules/`。
2. 只允许在 `index.html` 保留入口、挂载点和少量兼容函数。
3. 所有前端改动必须通过 `bash scripts/release_check.sh` 的 `node --check`。
4. 微信、邮件、新闻、自媒体、公众号、联系人评分等模块后续按业务域逐步拆分。

建议拆分顺序：

- `static/modules/wechat-sync.js`：微信三轨同步、消息拉取、消息表格刷新。
- `static/modules/settings.js`：功能设置导航、配置保存、状态卡片。
- `static/modules/contact-scoring.js`：联系人评分卡、图表、历史观点验证。
- `static/modules/dashboard.js`：数据看板、趋势关键词、地图和信号卡片。

拆分期间保持一个原则：每次只搬一个模块，先保留原函数名，再替换调用点，避免大面积 UI 回归。
