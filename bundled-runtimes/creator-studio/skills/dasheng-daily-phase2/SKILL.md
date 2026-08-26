---
name: dasheng-daily-phase2
description: Use when the workflow enters Stage 2 Brief and the current Agent must generate 8-10 candidate topic cards from canonical intake evidence under the Newma mainline.
---

# dasheng-daily-phase2

## 目标

这是本仓库 Stage 2 的唯一正式 Brief skill。

职责只有两层：

- 代码层：读取 intake、整理证据包、做显性噪音隔离、校验结构、落盘
- Agent 层：当前 Agent 直接阅读证据包并生成最终独立题卡

失败就失败，不再回退规则造题。

## canonical 输入

按这个优先级读取：

1. `brief_input.json`
2. `channel_top10.json`
3. `event_clusters.json`
4. `raw/intake_records.json`

默认来源目录：

- `${DASHENG_OUTPUT_ROOT:-~/Desktop/自媒体创作}/{run_id}/01_采集/`

## canonical 输出

输出目录：

- `${DASHENG_OUTPUT_ROOT:-~/Desktop/自媒体创作}/{run_id}/02_选题/`

标准产物：

1. `02_编辑Brief库.md`
2. `02_研究Brief库.md`
3. `02_编辑Brief_报告.md`
4. `topic_cards.json`
5. `selected_topics.template.json`
6. `selected_topics.json`
7. `brief_manifest.json`

## 当前规则

- 输出是 **8-10 个平铺独立题卡**
- 不再强制母题 / 变体作为业务主语义
- Agent 可以跨渠道、跨事件综合提炼，但不得脱离 intake 证据池
- Agent 生成的选题标题、判断句和核心题卡字段必须使用中文主体表达；英文来源要先提炼成中文选题
- Brief 记录来源材料大致内容、争议点和已见观点，供 draft 讨论热点，不在本阶段生成完整文章大纲
- Brief 额外沉淀 `question_units` / `opinion_units` / `case_units` / `solution_units`，供 draft 直接取用问题、观点、案例和证明方案，防止只按标题发挥
- 高优先证据池按 `信号强度 × 逻辑独立性 × 主题新颖度` 做弱重排
- intake/hotspot 的 `radar.macro_policy_score` 与 `radar.source_role` 会作为排序元数据进入 Brief，但不得作为硬过滤器
- 不做硬题材配额，但会对同一逻辑链和高重叠签名做边际递减
- Agent 返回的 `existing_evidence` 会回贴到 canonical evidence，并自动补齐 `logic_chain_id`
- 如果同一逻辑链占比超过半数，阶段直接失败
- 默认不调用项目内置 provider；provider 仅作为显式 `--mode provider` 的 legacy/回滚路径

## 执行入口

### 1）准备 Agent 证据包

```bash
python3 scripts/run_mainline_stage.py brief --run-id <run_id>
```

该命令默认生成：

- `brief_signal_bundle.json`
- `brief_agent_prompt.md`
- `brief_manifest.json`（`status=pending_agent_generation`）

### 2）当前 Agent 生成题卡

阅读 `brief_agent_prompt.md` 与 `brief_signal_bundle.json`，生成：

- `topic_cards.agent.json`

根键必须是 `topic_cards`。

### 3）校验并落盘正式 Brief

```bash
python3 scripts/run_mainline_stage.py brief \
  --run-id <run_id> \
  --agent-cards-file "~/Desktop/自媒体创作/<run_id>/02_选题/topic_cards.agent.json"
```

### 带手动指定题

```bash
python3 scripts/run_mainline_stage.py brief \
  --run-id <run_id> \
  --manual-topic "你的人工题目"
```

## 参考资料

- Prompt 规则：`../../引擎/03_全链路SOP工作流/02_Brief_AI生成规则.md`
- AI 选题指南：`references/ai-generation-guide.md`
- 选题评估：`references/topic-evaluation.md`
- 写作框架：`references/frameworks.md`
- 内容增强：`references/content-enhance.md`

## 实现说明

- 主脚本：`../../scripts/phase2_rebuilder.py`
- 主链入口：`python3 ../../scripts/run_mainline_stage.py brief --run-id <run_id>`
- Agent finalize：`python3 ../../scripts/run_mainline_stage.py brief --run-id <run_id> --agent-cards-file <file>`
- Schema：`brief_card_schema.json`
- 正式阶段状态：以 `brief_manifest.json` 为准

## 迁移说明

导出仓 `dasheng-stage-brief-ai` 的文档能力已被吸收到这里。

以后不要再把：

- `dasheng-stage-brief-ai`
- `dasheng-daily-brief`
- `dasheng-daily-clustering`

当成正式 Brief 入口。
