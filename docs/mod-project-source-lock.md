# Mod Project Source Lock

日期：2026-08-09

## 目的

`mod-projects/vibe-research` 与 `mod-projects/vibe-trading` 保留各自独立的 Git 历史，但主仓会在干净 clone 中直接引用这两个目录进行构建、挂载和部署。为避免“主仓可复现、内置源码不可复现”的隐患，Newma-Desk 现在额外保存一个 **source lock**：

- 锁定每个嵌套仓库的 `origin`
- 锁定当前 pinned commit
- 锁定当前 Git 状态、索引内容和工作树内容的指纹与 dirty 计数
- 明确声明当前是否允许生成 overlay

对应文件：

- [`config/mod-project-source-lock.json`](../config/mod-project-source-lock.json)
- [`scripts/check-mod-project-sources.mjs`](../scripts/check-mod-project-sources.mjs)

## 当前状态

两个嵌套仓库的 Newma-Desk 集成改动已经分别保存为干净的本地快照提交，source lock 现在可以稳定验证分支、提交、索引和工作树内容：

- `vibe-research`
  - `origin`: `https://github.com/simonlin1212/Vibe-Research.git`
  - `branch`: `codex/newma-desk-release-baseline-20260809`
  - `commit`: `87aece9a0263113b1d6c6d8f780d667b9d0dbeaf`
  - `working tree`: clean
- `vibe-trading`
  - `origin`: `https://github.com/HKUDS/Vibe-Trading.git`
  - `branch`: `codex/newma-desk-release-baseline-20260809`
  - `commit`: `f159a41033bdb8d3b2c60260bdab9bea045c814f`
  - `working tree`: clean

这些提交当前只存在于迁移后的本地仓库中。由于尚未获得向两个外部上游推送集成分支的授权，overlay publication 仍标记为 `blocked`；不得把“本地已锁定”表述成“外部远端已备份”。

## 如何校验

在主仓根目录运行：

```bash
node scripts/check-mod-project-sources.mjs
```

输出会验证：

1. 嵌套仓库路径存在
2. `origin` URL 与 lock 一致
3. 当前分支与 upstream branch 一致
4. `HEAD` commit 与 lock 一致
5. `git status --porcelain=v1 -z` 的 SHA-256 指纹一致
6. Git index 的内容、stage 与文件模式指纹一致
7. tracked 与 untracked（排除 Git ignored）工作树文件的内容指纹一致
8. staged / unstaged / untracked 计数一致

工作树指纹按原始路径字节稳定排序，逐文件流式读取并记录文件类型、可执行位、符号链接目标和原始内容；已从工作树删除但仍由 Git 跟踪的路径会写入明确的删除标记。这样既能发现“同一路径、同一 dirty 状态下内容被替换”的变化，也不会为了校验而把完整 patch 或大文件一次性读入内存。

如需机器读取：

```bash
node scripts/check-mod-project-sources.mjs --json
```

如需把“工作树必须干净”作为失败条件：

```bash
node scripts/check-mod-project-sources.mjs --fail-on-dirty
```

## 为什么这是最小安全方案

当前最小安全方案包含：

1. **Pinned source lock**
   - 能回答“主仓当前依赖的本地集成提交是什么”
2. **Clean snapshot commits**
   - 用户改动不再依赖未提交工作树
   - 每个集成快照都可以在本地独立回滚和审阅
3. **Content fingerprint verification**
   - 索引和工作树指纹覆盖文件内容、类型、模式和符号链接目标
   - 能回答“当前嵌套源码是否仍与锁文件记录的提交完全一致”

它仍然**不**声明：

- 本地快照分支已经发布到外部远端
- 未经授权的 clean clone 能自动取得这些本地提交
- 这些集成提交适合直接合并回第三方上游的默认分支

## 何时可以升级到 overlay

只有在以下条件同时满足时，才应把 lock 升级为远端或 bundle 可回放方案：

1. 用户明确授权推送目标远端，或批准把审阅后的 recovery bundle 纳入发布介质
2. recovery 来源能从 clean clone 稳定恢复两个锁定提交
3. 发布介质不包含运行产物、临时文件、会话文件或用户私有内容

在那之前，`config/mod-project-source-lock.json` 是本机可验证的 pinned baseline，不是远端发布证明。
