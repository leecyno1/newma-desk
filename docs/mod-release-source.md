# Mods 发布源

Newma 四端的正式 Mods 目录只以 GitHub `leecyno1/newma-dock` 为权威来源，所有同步都必须记录明确 commit。

## 规则

- 唯一权威仓库：`https://github.com/leecyno1/newma-dock`
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
