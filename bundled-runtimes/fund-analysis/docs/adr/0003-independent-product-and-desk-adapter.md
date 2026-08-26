# 独立基金产品与 Desk Adapter 分离

状态：Accepted

日期：2026-08-15

## 决策

基金选择助手是独立产品，正式前端固定运行在 `127.0.0.1:3000`，正式后端固定运行在 `127.0.0.1:8005`。Orchestra 使用的 `3001` 不属于本项目。

Newma Desk 只通过独立 Adapter 接入本项目：

- `desk/suite.json` 描述一个完整基金 Suite。
- 五个基金页面属于同一个 Suite 和同一个 `fund-research` 栏目，不是五个独立项目。
- `app/(desk)/` 只复用正式页面并提供 Desk Context。
- `backend/routes/newma_desk.py` 只映射正式基金能力，不复制评价、归因和推荐逻辑。
- 项目不得自行调用 Newma 控制面发布 Mod。
- 人工验收前不得把基金 Suite 或数据能力加入 `desk-mods`。

## 原因

直接发布曾把基金页面写到 Orchestra 的 `3001`，导致基金入口加载投委会页面。把独立产品、Desk Adapter 和 Desk 商店发布拆开后，端口、项目身份和发布权限都集中在各自的 Interface，避免再次串台。
