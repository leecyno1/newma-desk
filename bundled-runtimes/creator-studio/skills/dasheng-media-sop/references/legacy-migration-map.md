# 旧链路迁移表

## 目标

把历史 `dasheng-daily-*` 运行时链路，收口到当前 6 阶段主链：

`intake -> brief -> draft -> transwrite -> publish -> postmortem`

## 保留为主入口

- `dasheng-media-sop`

## 保留为底层模块

- `dasheng-daily-intake`
- `dasheng-daily-phase2`
- `dasheng-daily-draft`
- `dasheng-daily-postmortem`
- `dasheng-daily-shared`

这些模块保留，但以后默认不单独对外介绍成“完整工作流”，而是作为主控 Skill 下的执行层。

## 合并到 Brief

- `dasheng-daily-clustering`
- `dasheng-daily-brief`

说明：

- 两者本质上都是旧的 phase2 拆分实现。
- 当前正式对外语义统一叫 `brief`。

## 退出主链

- `dasheng-daily-outline`
- `dasheng-daily-final`
- `dasheng-stage-rewrite-v3`

说明：

- `outline` 在旧链路里位于素材/终稿之后，不符合当前主链。
- `final` 的职责已被 `draft + transwrite` 吸收，不再作为正式阶段保留。
- 独立素材环节删除；独立 `rewrite` 改为 Transwrite 按需工具，只有多版本改写需求出现时调用。

## 归档为历史技能

- `dasheng-caiji`
- `dasheng-clustering`
- `dasheng-xuanti`
- `dasheng-xuanti-skill`
- `dasheng-intake-brief-prod`
- `dasheng-brief-builder`
- `dasheng-stage-distribute`

说明：

- 这些技能保留历史价值，但不应继续作为默认入口。
- 本轮已从运行目录删除，后续只允许在迁移文档中保留名称，不再保留执行目录。
- `dasheng-stage-distribute` 的平台路由与分发知识已并入 `publish` / `dasheng-stage-publish`。
