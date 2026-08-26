---
name: dasheng-account-illustrations
description: Use when a WeChat article or video needs account-bound concept illustrations. Routes by official-account DNA (dna/account_dna.yaml) — 默丘利Lab uses a chubby-cute fixed Greek-mythology cast with finance-role routing; Newma牛马进化论 uses one deliberately crude 牛人+马人 opening comic only; 墨丘利实验室 uses the original ian-xiaohei black stick figure. Data charts are NEVER replaced by illustrations.
---

# Newma Account DNA Illustrations

## Role

Account-bound concept-illustration system for article/production. Each official account has its own character system and visual language, defined in `dna/account_dna.yaml` (single source of truth). This skill routes, composes prompts, and QA-checks per account.

## Account → Character Routing

| Account (slot) | Character | Visual language | Logic layout |
| --- | --- | --- | --- |
| 默丘利Lab (slot-1, invest-market) | **胖版奥林匹斯固定角色组**：墨丘利、宙斯、雅典娜、波塞冬、哈迪斯、赫菲斯托斯、阿波罗、阿瑞斯 | 胖版 Q 萌希腊神话 + 精美陶罐画线条；米白底/墨黑线/赭红+爱琴海蓝 | **角色路由**：按信息、主权、策略、流动性、信用、资本开支、增长、竞争等机制选角 |
| Newma牛马进化论 (slot-3, ai-tech) | **牛人 + 马人**（牛人=土黄+大红，马人=荧光绿+黑；歪歪扭扭小学生手工报美学） | 儿童手绘，故意粗制滥造（廉价配色：荧光绿+土黄+大红） | **仅开篇一图**：牛人提出读者疑问，马人用一句话给出全文核心判断；正文不再出现人物对话 |
| 墨丘利实验室 (slot-2, fin-business) | **原版小黑**（ian-xiaohei 上游原生：黑色简笔小人，非柠檬人） | 严肃科学研究配图；白底黑线+深红单强调 | 单概念单图（一图一动作），科研流程式排布 |

## Required Reading

- `dna/account_dna.yaml` — account DNA (positioning/character/style/tone), the routing source of truth
- `references/character-sheets.md` — the three character prompt blocks (copy into ImageGen prompts)
- `references/qa-checklist.md` — before accepting an image

## Workflow

1. Identify the target account (from channel_pack.account_slot, --account arg, or article media name).
2. Read the account's DNA block; for slot-1 select the fixed Greek character whose duty matches the paragraph, then pick the prompt block from `references/character-sheets.md`.
3. State the single idea the image must explain (one mechanism per image; slot-1 uses at most three characters; 小黑 uses one action; 牛马账号只生成开篇的一问一答).
4. Compose the prompt: character block + scene/action + annotations + account color rules + negative constraints.
5. Generate via host ImageGen (16:9 for article inline, 1:1 for 牛马 four-panel).
6. Place by article rhythm: 默丘利Lab follows 分镜节拍 per section; 牛马 duo appears once at the article opening; 小黑 anchors each mechanism explanation.
7. QA per `references/qa-checklist.md`; record intent id, prompt, path, account id in the task asset manifest.

## Hard Rules

- NEVER replace data charts (matplotlib, Tushare-sourced) with illustrations — illustrations are conceptual only (`evidence_authenticity=schematic`).
- 默丘利Lab fixed cast must always use the chubby-cute body system while preserving each god's identifying symbol; generic unidentifiable cute characters fail QA.
- 牛马 style must stay crude ON PURPOSE: wobbly lines, cheap palette, hand-written labels — polish is a defect there. It is opening-only; never generate 牛马 dialogue illustrations for body sections.
- 墨丘利Lab images must NOT mix in lemon/yellow bodies; 小黑 (slot-2) must stay black-line minimal, no yellow.
- All text annotations in Chinese (牛马: hand-written style; 实验室: serif mixed CN/EN; 默丘利: clean minimal).

## Output Contract

Each generated image records: `{intent_id, account_id, section_anchor, prompt, path, qa}` into the task `asset_manifest` / `illustration_intents.json`.
