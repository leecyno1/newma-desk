# Mods 发布源

Newma 四端的正式 Mods 目录只以 GitHub `leecyno1/newma-desk` 为权威来源，所有同步都必须记录明确 commit。

## 规则

- 唯一权威仓库：`https://github.com/leecyno1/newma-desk`
- 正式分支：`main`
- 正式目录：`mods/store.json` 与其引用的 `mods/*/mod.json`、`mods/*/suite.json`
- Gitee 只作为下载镜像，不参与版本判定。
- 本地工作树只用于开发；未提交、未推送内容不得进入四端同步结果。
- 同步报告必须包含仓库、分支、commit、商店摘要和 Manifest 差异。
- 自动月检不得合并、部署、重启服务或修改用户侧启用顺序。

## 发布流程

1. 在 NewmaDesk 完成 Mod 变更与兼容性测试。
2. 将完整变更提交并推送到 GitHub `main`。
3. 四端从同一个 GitHub commit 生成候选并记录来源。
4. 人工审核差异和兼容风险后，才允许发布或部署。

定制 Newma WebUI 在独立私有仓库 `leecyno1/newma-webui-custom` 维护；其 `upstream` 指向 `nesquena/hermes-webui`，但 WebUI 内的 Mods 清单仍只来自上述 NewmaDesk GitHub commit。

## 运行时同步接口

Newma 不直接拉取或检出 Desk 仓库。Newma-Desk 控制面负责把 GitHub 发布源转换成经过校验的本地目录快照：

- `POST /api/store/sync`：解析 `main` 最新 commit，下载并校验 `mods/store.json` 及全部 Git-backed Mod/Suite 描述，然后原子替换 `runtime/mod-store-catalog.json`。
- `GET /api/store/mods`：离线读取最近一次有效快照，并返回 `catalogSource`、`commit`、`syncedAt`、安装版本和更新状态；同步失败不会删除旧快照。
- `POST /api/store/mods/{modId}/install`：按快照锁定的 commit 安装或更新单页 Mod。
- `POST /api/store/projects/{projectId}/install`：在一个 Registry 事务中安装或更新同一 Newma 项目的全部页面，避免半套升级。

私有 GitHub 仓库优先使用系统已有的只读 Git 凭据；无 Git 的生产镜像通过 `NEWMA_DESK_MOD_STORE_GITHUB_TOKEN` 提供只读 token。token 只由 Desk 服务读取，不进入 Manifest、快照或 Newma Renderer。

月度任务只调用目录同步接口并报告 commit 与差异，不自动安装、重启或改变用户启用顺序。用户在 Newma 的模组管理器确认后，才调用项目安装接口。

## 宿主边界

- Newma Desktop 与定制 WebUI 只消费 Desk 的 `/api/modules`、`/api/store/mods` 和更新接口。
- Renderer 不访问 GitHub，不执行 Git，也不持有 GitHub token。
- 新 Mod 或 Suite 只要进入已校验的 GitHub 商店快照，就能出现在宿主的模组管理器中；宿主无需复制对应页面代码。
- 嵌入仍遵守已审核 Origin、HTTPS/loopback 与 sandbox 规则，目录同步不能扩大运行时权限。
