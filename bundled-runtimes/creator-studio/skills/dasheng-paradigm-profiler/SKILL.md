---
name: dasheng-paradigm-profiler
description: Use when users provide standard articles, content templates, successful samples, or channel templates and want Codex to learn article paradigms/frameworks for different scenarios, channels, and styles.
---

# Newma Paradigm Profiler

## 目标

把用户提供的标准文章或内容模板沉淀为可复用的 `Paradigm Profile`，用于指导选题、初稿、改写和发布适配。

它学习的是：

- 文章结构范式
- 章节框架
- 叙事路径
- 论证模型
- 信息密度
- 场景与渠道适配规则

它不学习或复用：

- 样本事实
- 未核验数据
- 原文金句
- 作者专属口头禅

## 默认路径

- `DASHENG_WORKSPACE=${DASHENG_WORKSPACE:-${DASHENG_PROJECT_ROOT:-.}}`
- 范式画像输出：`${DASHENG_OUTPUT_ROOT:-~/Desktop/自媒体创作}/00_范式学习/{run_id}/{profile_slug}/00_范式画像.md`
- 结构化画像：`${DASHENG_OUTPUT_ROOT:-~/Desktop/自媒体创作}/00_范式学习/{run_id}/{profile_slug}/paradigm_profile.yaml`

## 输入要求

1. 范式名或用途名（可选，缺省时根据样本自动命名）
2. 样本类型：标准文章 / 内容模板 / 爆款样本 / 渠道模板 / 历史高质量稿
3. 样本文本或文件路径（至少 1 篇，推荐 3-5 篇）
4. 目标场景：深度长文 / 观点短文 / 行业解读 / 商业分析 / 产品发布 / 社群转发 / 短视频脚本等
5. 目标渠道：公众号 / 小红书 / 抖音 / 视频号 / 微博 / 社群 / 飞书内参等
6. 是否绑定 Style DNA：不绑定 / 绑定已有 DNA / 需要新建 DNA

## 工作流

1. 建立样本清单，记录来源、类型、渠道、字数和使用边界。
2. 抽取开篇机制、章节骨架、论证模型、转场机制和收束方式。
3. 区分结构范式与作者口吻，避免把 `ParadigmProfile` 写成 `Style DNA`。
4. 总结场景适配：适合什么题材、不适合什么题材、使用前置条件。
5. 总结渠道适配：公众号、小红书、短视频、社群等各自如何变形。
6. 输出 `00_范式画像.md`、`paradigm_profile.yaml`、`paradigm_prompt_block.md`、`paradigm_manifest.json`。
7. 请求用户校准，用户确认后固化到当前 run 的 `~/Desktop/自媒体创作/00_范式学习/{run_id}/{profile_slug}/`。

## 执行方式

默认使用 OpenAI-compatible Chat Completions 配置做深度分析；如果缺少 API 配置，会安全降级为启发式骨架画像。

```bash
python3 scripts/build_paradigm_profile.py sample.md --run-id 2026-05-06_120000 --profile-name 结构变化解读 --scenario 行业解读 --channel 公众号
```

禁用 AI，仅生成可编辑骨架：

```bash
python3 scripts/build_paradigm_profile.py sample.md --run-id 2026-05-06_120000 --profile-name 结构变化解读 --no-ai
```

可用环境变量：

- `PARADIGM_AI_BASE_URL` / `PARADIGM_AI_API_KEY` / `PARADIGM_AI_MODEL`
- 或复用 `PHASE3_AI_*`、`PHASE2_AI_*`、`QHAIGC_*`
- 可用 `DASHENG_PARADIGM_PROVIDER_ENV` 指定 provider env 文件

## 推荐接入环节

默认作为阶段 `0.5 Paradigm Learning`，放在 `Brief` 前。

- Brief：为每个题卡标注推荐范式、适配分和不适用风险。
- Draft：继承章节骨架、论证顺序、信息密度，但不注入文风和平台腔。
- Rewrite：与 Style DNA 组合，范式管结构，DNA 管表达。
- Publish：按渠道拆成不同发布框架。

## 输出契约

按以下顺序输出：

1. `样本概况`
2. `范式一句话定义`
3. `适用场景与不适用场景`
4. `开篇机制`
5. `主干章节框架`
6. `论证推进模型`
7. `信息密度与段落配方`
8. `渠道适配矩阵`
9. `与 Style DNA 的边界`
10. `禁用项与风险`
11. `可复用 Prompt Block`
12. `下游注入建议`
13. `文件路径`

## 固化文件

最终画像默认保存到：

- `${DASHENG_OUTPUT_ROOT:-~/Desktop/自媒体创作}/00_范式学习/{run_id}/{profile_slug}/00_范式画像.md`
- `${DASHENG_OUTPUT_ROOT:-~/Desktop/自媒体创作}/00_范式学习/{run_id}/{profile_slug}/paradigm_profile.yaml`
- `${DASHENG_OUTPUT_ROOT:-~/Desktop/自媒体创作}/00_范式学习/{run_id}/{profile_slug}/paradigm_prompt_block.md`
- `${DASHENG_OUTPUT_ROOT:-~/Desktop/自媒体创作}/00_范式学习/{run_id}/{profile_slug}/paradigm_manifest.json`

## 质量红线

- 不允许只输出泛泛的“开头、正文、结尾”。
- 不允许把样本事实挪用到新文章。
- 不允许把范式学习等同于风格模仿。
- 不允许跳过不适用场景。
- 不允许跳过渠道适配矩阵。
- 不允许输出下游阶段无法直接消费的空泛结论。

## 参考 Prompt

使用：`引擎/03_全链路SOP工作流/00_范式学习_prompt.md`
