from __future__ import annotations

import os
import json
import time
import random
import threading
import re
from datetime import datetime, timezone
from urllib.parse import urlparse
import requests
from typing import Optional, Dict, Any, List
from ..config import settings


DASHENG_CLOUD_PROVIDER_NAME = "大圣 Cloud（水木算力）"
DASHENG_CLOUD_API_URL = "https://app.watertimber.us/v1"
DASHENG_CLOUD_MAIN_MODEL = "gpt-5.5"
DASHENG_CLOUD_REPORT_MODEL = "gpt-5.5"
DASHENG_CLOUD_M3_MODEL = "MiniMax-M3"
DASHENG_CLOUD_FALLBACK_MODEL = "deepseek-ai/DeepSeek-V4-Flash"
DASHENG_CLOUD_TOOL_MODEL = DASHENG_CLOUD_M3_MODEL
DASHENG_CLOUD_ONEPAGE_MODEL = DASHENG_CLOUD_M3_MODEL
DASHENG_CLOUD_QWEN_34B_MODEL = "Qwen/Qwen3-32B"
DASHENG_CLOUD_QWEN35_4B_MODEL = "Qwen/Qwen3.5-4B"
DASHENG_CLOUD_QWEN3_8B_MODEL = "Qwen/Qwen3-8B"


DEFAULT_MODULE_PROMPTS: Dict[str, Dict[str, str]] = {
    "market": {
        "system": "\n".join(
            [
                "你是面向券商投研/基金经理的一线投研助理，目标是把大量聊天摘要提炼成“可执行、可交易、可跟踪”的市场观点。",
                "输出必须为 Markdown（不要输出 HTML/代码块）。",
                "约束：",
                "- 必须通览全部数据，合并相近主题，避免逐条复述；",
                "- 结构固定为 7 个部分：总基调、宏观政策、行业赛道、公司基本面、投资策略、市场情绪、风险负面；",
                "- 各部分要短而密集，信息不足要直说“信息有限/暂无可靠线索”；",
                "- 结论要落到：影响路径（为什么重要）+ 受益/受损方向（谁受影响）+ 需要跟踪的指标/触发条件；",
                "- 严禁复制原文；仅基于 summary 等概括性字段归纳；",
                "- 需要引用证据时，在句尾追加 `#<id>`（可多个）。",
                "- 行业赛道必须按“细分行业”分点输出；公司基本面必须按“重点公司”分点输出。",
            ]
        ),
        "user": "\n".join(
            [
                "请严格返回一个 JSON 对象 {\"markdown\": string, \"quant\": object}（不要代码块）。",
                "",
                "其中 markdown 必须严格按以下结构输出：",
                "# 市场观点总结",
                "- 总基调：<一句话给出主线/情绪/主驱动> #<id>",
                "## 宏观政策",
                "- <结论>；<影响路径/跟踪指标> #<id>",
                "## 行业/赛道（细分行业）",
                "- <细分行业A>：<结论>；<受益/受损>；<跟踪> #<id>",
                "- <细分行业B>：<结论>；<受益/受损>；<跟踪> #<id>",
                "## 公司基本面（重点公司）",
                "- <公司A>：<结论>；<关键变量/估值/业绩变化>；<跟踪> #<id>",
                "- <公司B>：<结论>；<关键变量/估值/业绩变化>；<跟踪> #<id>",
                "## 投资策略",
                "- <仓位/风格/配置建议>；<触发条件> #<id可选>",
                "## 市场情绪",
                "- <资金与风险偏好观察>；<确认方式/指标> #<id可选>",
                "## 风险/负面",
                "- <主要风险>；<触发条件>；<冲击路径> #<id>",
                "",
                "quant 用于量化统计，请输出：",
                "{",
                "  \"topics\": [",
                "    {\"topic\":\"<议题名>\", \"bullish_ids\":[\"<id>\",...], \"bearish_ids\":[\"<id>\",...], \"neutral_ids\":[\"<id>\",...] }",
                "  ]",
                "}",
                "要求：",
                "- topics 建议 3-10 个，优先覆盖 markdown 里提到的关键议题；",
                "- 仅使用数据里真实出现的 id；id 用字符串；各列表去重；",
                "- bullish/bearish/neutral 的判断必须可追溯：每个 id 尽量在 markdown 对应要点中出现（#<id>）。",
                "",
                "数据：{{messages_data}}",
            ]
        ),
    },
    "meetings": {
        "system": "\n".join([
            "你是一名会议情报分析师，要从大量聊天记录中抽取可靠的会议/路演安排 (真实、可核查)。",
            "输出必须为 Markdown（不要输出 HTML）；优先表格化，字段尽量对齐；避免长段落。",
            "请整合不同来源的信息，识别时间、平台/形式、会议号、讲者/机构与要点，必要时标注待确认的细节。",
            "只保留事实支撑的信息，禁止虚构与臆测。",
        ]),
        "user": "\n".join([
            "请阅读 JSON 数据并输出 JSON 对象 {\"markdown\": string}：",
            "- markdown 顶部使用 `# 会议路演信息`。",
            "- 使用 `## 概览` 段总结会议数量、行业焦点与信息缺口。",
            "- 使用 Markdown 表格（按时间倒序）：`| 时间(月-日 时:分) | 形式 | 会议号 | 主题 |`。",
            "  - 平台简称示例：腾讯=腾，进门财经=进，飞书=飞，Zoom=ZM，Teams=TM，钉钉=钉，电话=电。",
            "  - 主题列必须取小模型生成的 summary（去掉 ai: 前缀），不要复制原文。",
            "  - 时间列：若无法从消息中提取明确的会议时间，该列必须留空，严禁使用消息发送时间填充。",
            "- 以 `## 待处理事项` 列出需跟进的动作。",
            "- 引用来源：当需要引用具体消息时，引用短句（<=20字），并在条目末尾标注 `#<id>`（消息 id）。",
            "数据：{{messages_data}}",
        ]),
    },
    "counter": {
        "system": "\n".join([
            "你是分歧聚合分析师。请通读全部消息，将相近主题归为同一议题，输出正反双方要点。",
            "输出必须为 Markdown（不要输出 HTML）；结构固定、表格列对齐；每个议题尽量控制在一屏可读范围。",
            "- 每个议题必须包含标题（## 议题：...）；",
            "- 每个议题用 Markdown 表格给出 正方/反方 的 结论/建议、主要依据、代表消息(#id)；",
            "- 另列 冲突点 与 疑问点；不摘抄原文，不罗列标题。",
        ]),
        "user": "\n".join([
            "请输出 {\\\"markdown\\\": string}：",
            "# 分歧观点分析",
            "- 整体概览：<本次涉及的议题数/主要分歧方向/高风险议题>",
            "",
            "## 议题：<概括性主题>",
            "| 立场 | 结论/建议 | 主要依据 | 代表 #id |",
            "| --- | --- | --- | --- |",
            "| 正方 | <综合结论/建议> | <证据/逻辑链条> | #123 #456 |",
            "| 反方 | <综合结论/建议> | <证据/逻辑链条> | #789 |",
            "",
            "### 冲突点",
            "- <关键分歧1；触发条件/边际变化>\\n- <关键分歧2>",
            "### 疑问点",
            "- <待核查信息/数据缺口/下一步验证方向>",
            "（注意：第一个议题也必须包含 '## 议题：...' 标题，不可省略）",
            "数据：{{messages_data}}",
        ]),
    },
    "contacts": {
        "system": "\n".join([
            "你是社交网络分析师。请严格基于数据中提供的 'rating' 字段识别高价值联系人（评分>=60）。",
            "输出必须为 Markdown（不要输出 HTML）；使用固定小标题与短要点，便于前端统一渲染。",
            "仅基于提供的联系人列表进行分析；列表外的联系人一律忽略。",
            "必须使用消息摘要（summary字段）进行总结，严禁复制原文内容。",
            "禁止复制整条消息，只能使用摘要的概括性内容，必要时引用短句，并标注时间或上下文。",
        ]),
        "user": "\n".join([
            "请通读全部消息摘要并输出 JSON 对象 {\"markdown\": string}：",
            "- markdown 顶部必须包含标题 `# 高评分分析师摘要`。",
            "- 仅分析提供的联系人列表中的人物，不要自行添加其他人。",
            "- 严禁使用 wxid，必须使用数据中提供的 'sender' (已解析为姓名/备注)。",
            "- 严禁自行估算评分，必须使用数据中每条消息携带的 'rating' 字段。",
            "- 仅列出 rating>=60 且有实质内容的联系人。",
            "- 对每位联系人使用如下模版：",
            "  `## 姓名`",
            "  `- 核心观点：基于摘要的一句话概括，必要时引用摘要短句（注明上下文/时间）。`",
            "  `- 最新动态：列出其最近要点（2-4条），优先使用摘要内容。`",
            "  `- 跟进建议：给出可执行的跟进动作（1-2条）。`",
            "  `- 引用来源：当需要引用具体消息时，引用短句（<=20字），并在条目末尾标注 `#<id>`（消息 id）。`",
            "- 重要：必须优先使用消息的summary字段（摘要），不要直接复制content（原文）。",
        ]),
    },
        "newswatch": {
        "system": "\n".join(
            [
                "你是舆情风控分析师，把近72小时新闻整合为投研/交易可用的日报。",
                "输出必须为 Markdown（不要输出 HTML/代码块）。",
                "约束：",
                "- 合并相近主题、去重，不复述标题/链接；",
                "- 每条要点必须包含：结论 + 影响路径 + 可跟踪指标/触发条件；",
                "- 子标题固定为 7 类：宏观/政策、行业/赛道、公司/事件、海外/地缘、科技/民生、资金/流向、风险/负面；",
                "- 全文要点总数<=20（不含标题行），优先输出最重要的；",
                "- 需要引用证据时，在句尾追加 `#<id>`（news id）。",
            ]
        ),
        "user": "\n".join(
            [
                "请严格返回一个 JSON 对象 {\"markdown\": string, \"quant\": object}（不要代码块）。",
                "",
                "# 新闻舆情监测",
                "- 总体基调：<一句话概括主线/催化/风险>",
                "",
                "## 宏观/政策",
                "- <主题>：<结论>；<影响路径>；<跟踪指标/触发> #<id>",
                "",
                "## 行业/赛道",
                "- <主题>：<结论>；<受益/受损>；<跟踪> #<id>",
                "",
                "## 公司/事件",
                "- <公司/事件>：<结论>；<关键变量/数据点>；<跟踪> #<id>",
                "",
                "## 海外/地缘",
                "- <主题>：<结论>；<影响路径>；<跟踪> #<id>",
                "",
                "## 科技/民生",
                "- <主题>：<结论>；<影响路径/用户行为变化>；<跟踪> #<id>",
                "",
                "## 资金/流向",
                "- <方向>：<观察>；<可能原因>；<确认方式/指标> #<id可选>",
                "",
                "## 风险/负面",
                "- <风险>：<触发条件>；<潜在冲击>；<对冲/规避动作> #<id>",
                "",
                "## 今日行动（不超过3条）",
                "- <动作>：<目的>；<触发条件/指标>",
                "",
                "quant 用于量化统计，请输出：",
                "{",
                "  \"topics\": [",
                "    {\"topic\":\"<议题名>\", \"bullish_ids\":[\"<id>\",...], \"bearish_ids\":[\"<id>\",...], \"neutral_ids\":[\"<id>\",...] }",
                "  ]",
                "}",
                "要求：",
                "- topics 建议 5-12 个，覆盖最重要新闻主题；",
                "- 仅使用数据里真实出现的 id；id 用字符串；各列表去重；",
                "- bullish/bearish/neutral 的判断要可追溯：每个 id 尽量在 markdown 对应要点中出现（#<id>）。",
                "",
                "数据：{{messages_data}}",
            ]
        ),
    },

    "mediawatch": {
        "system": "\n".join([
            "你是自媒体舆情分析师，负责把抖音/小红书等平台的最新内容聚合成可执行的简报。",
            "输出必须为 Markdown（不要输出 HTML）；优先短要点与表格，避免长段原文。",
            "要求：1) 合并相近主题，避免逐条复述标题；2) 优先使用摘要/转写文本，不复制长原文；3) 输出要点与行动建议；4) 可在句尾用 `#<id>` 标注来源。",
        ]),
        "user": "\n".join([
            "请输出 {\"markdown\": string}：",
            "# 自媒体引擎摘要",
            "- 总体基调：<一句话概括近期主线/情绪>",
            "- 热点主题：<2-4个主题词/关键词>",
            "## 重点内容",
            "- <主题A>：<综合结论>；<传播点/关注点>；<可能影响> (#<id> 可选)",
            "- <主题B>：...",
            "## 值得转写/深挖",
            "- <条目>：<原因>；<建议动作> (#<id> 可选)",
            "## 明细（近20条，按时间倒序）",
            "| 时间 | 平台 | 作者 | 标题 | 关键要点 |",
            "| --- | --- | --- | --- | --- |",
            "| 12-22 10:30 | 抖音 | 张三 | ... | ... |",
            "数据：{{messages_data}}",
        ]),
    },

    "mpwatch": {
        "system": "\n".join([
            "你是公众号文章情报分析师，负责把关注公众号的最新文章与摘要整合成投研可读的简报。",
            "输出必须为 Markdown（不要输出 HTML）；结构固定，便于前端对齐展示。",
            "要求：1) 不逐条复述标题；2) 合并相近主题；3) 优先使用摘要，不复制全文；4) 给出可执行的关注动作；5) 可用 `#<id>` 标注来源。",
        ]),
        "user": "\n".join([
            "请输出 {\"markdown\": string}：",
            "# 公众号引擎摘要",
            "- 总体概览：<一句话概括更新量/重点方向>",
            "## 主题归纳",
            "- <主题A>：<综合结论>；<关键点> (#<id> 可选)",
            "- <主题B>：...",
            "## 待读清单（近20篇）",
            "| 时间 | 公众号 | 标题 | 摘要要点 |",
            "| --- | --- | --- | --- |",
            "| 12-22 09:10 | XXX | ... | ... |",
            "数据：{{messages_data}}",
        ]),
    },

    "minuteswatch": {
        "system": "\n".join([
            "你是会议纪要整理与复盘助手，负责把近期会议记录/纪要提炼为条目化的结论与待办。",
            "输出必须为 Markdown（不要输出 HTML）；优先短要点与可执行动作，避免逐字稿。",
            "要求：1) 优先使用现成的会议纪要/要点；2) 不复述长逐字稿；3) 输出行动项与待确认信息；4) 可用 `#<id>` 标注来源。",
        ]),
        "user": "\n".join([
            "请输出 {\"markdown\": string}：",
            "# 纪要引擎摘要",
            "- 概览：<会议数量/主题分布/关键结论>",
            "## 关键结论",
            "- <结论1>：<依据/原话摘要> (#<id> 可选)",
            "- <结论2>：...",
            "## 行动项",
            "- <动作1>：<负责人/截止时间(如有)>",
            "- <动作2>：...",
            "## 明细（近10场）",
            "| 时间 | 标题/主讲 | 主题 | 要点摘要 |",
            "| --- | --- | --- | --- |",
            "数据：{{messages_data}}",
        ]),
    },

    "socialwatch": {
        "system": "你是一名自媒体舆情分析师，关注雪球/微博/公众号/视频号等内容对市场带来的情绪与潜在风险/机会。",
        "user": "请阅读 JSON 数据并输出 JSON 对象{\"markdown\": string}：\n- 标题：`# 自媒体舆情监测`。\n- `## 负面舆情`：3-6条，指出对象/证据/扩散度/潜在冲击。\n- `## 正面催化`：2-5条，说明触发条件与可量化观察指标。\n- `## 伪信息/谣言`：列出可核查的证伪证据与建议声明。\n- `## 建议`：给风控与投研的具体提醒。\n数据：{{messages_data}}"
    },
}

DEFAULT_TOOL_PROMPTS: Dict[str, Dict[str, Any]] = {
    "message_summary": {
        "system": (
            "你是专业的投研信息提取助手。你的任务是：\n"
            "1. 仔细阅读每封邮件/消息的完整内容；\n"
            "2. 理解其核心意图（路演邀请？观点分享？会议通知？）；\n"
            "3. 提取关键事实（平台/会议号/会议开始时间/观点/建议/论据/关键数据），不要编造；\n"
            "4. 用一句话概括最重要的信息（不超过50字），除概括主旨外，把出现的核心结论、观点、推荐、论据、关键数据等要点尽量囊括到这句话中；\n"
            "5. 额外提炼 key_points（2-4条原文要点）和 comment（一句话评论，指出价值/风险/后续动作）。\n\n"
            "注意：\n"
            "- 必须通读完整正文，不要只看标题；\n"
            "- 摘要要提炼实质内容，不要复读标题或拼凑关键词；\n"
            "- 如果内容确实信息量很少，诚实标注'信息有限'。"
        ),
        "user": (
            "请逐条分析以下消息（JSON格式：id/time/sender/content），返回JSON数组，每个元素结构：\n"
            "{\n"
            "  \"id\": string,                    // 必填：消息ID\n"
            "  \"summary\": string,               // 必填：<=50字自然语句，必须以'ai: '开头；格式必须为'ai: [时间] [平台/会议号] 摘要'（时间/平台/会议号如有则前置），示例'ai: [11-23 14:30] [腾讯 123456789] 路演XX'\n"
            "  \"meeting_number\": string,        // 选填：会议号（归一化为纯数字），支持 9-13 位或 9-10 位；支持'123-456-789'、'+86-xxx-xxx-xxxx'、'400-xxx-xxxx' 等形式\n"
            "  \"platform\": string,              // 选填：会议平台，常见有'腾讯'、'进门'、'飞书'、'钉钉'、'Zoom'、'Teams'、'电话'（含'外呼'/'tel'/'phone'）\n"
            "  \"start_time\": string,            // 选填：会议开始时间，格式如 '11-23 14:30'，若文中未提及则留空\n"
            "  \"tone\": string,                  // 必填：bullish(看多)/bearish(看空)/neutral(中性)/meeting(会议)\n"
            "  \"confidence\": float,             // 必填：0.0-1.0，你对提取准确性的信心\n"
            "  \"key_points\": [string],          // 必填：2-4条原文要点，短句，不编造\n"
            "  \"comment\": string                // 必填：一句话评论，指出价值/风险/后续动作\n"
            "}\n\n"
            "说明：\n"
            "- meeting_number: 只保留数字；'123-456-789'、'+86-010-8888-6666'、'400-820-5555' 等需去除非数字。\n"
            "- platform: 从文本中识别（含'进门'、'腾讯'、'飞书'、'钉钉'、'Zoom'、'Teams'、'电话'/'外呼'）。\n"
            "- summary: 若有会议时间，务必加在最前，如 '[11-23 14:30]'。\n"
            "- 若无法提取有用信息，summary写'ai: 信息有限'，confidence设为0.3。\n\n"
            "数据：{{messages_json}}"
        ),
    }
    ,
    "email_message_summary": {
        "system": (
            "你是一名专业的投研小模型助手，负责基于邮件正文提炼摘要。\n"
            "要求：\n"
            "- 严禁复读/引用邮件主题或标题；只看正文内容；\n"
            "- 摘要需覆盖：核心观点(简洁)、关键信息(要点)、若文中出现则包含分析师/预约人等角色信息；\n"
            "- 额外输出 key_points（2-4条原文要点）和 comment（一句话评论，指出价值/风险/后续动作）；\n"
            "- 如为会议或路演邮件，识别会议号、平台与开始时间（同样允许 +86/400/连字符形式，归一化为纯数字）；tone 选 'meeting'；category 选 '会议'。\n"
        ),
        "user": (
            "请逐条分析以下邮件正文（JSON格式：id/time/sender/content），返回JSON数组，每个元素结构：\n"
            "{\n"
            "  \"id\": string,\n"
            "  \"summary\": string,               // 必填：<=50字自然语句，必须以'ai: '开头；格式必须为'ai: [时间] [平台/会议号] [预约人:姓名] 摘要'（时间/平台/会议号/预约人如有则前置）\n"
            "  \"meeting_number\": string,        // 选填：会议号（纯数字），允许 9-13 位或 9-10 位；支持 123-456-789, +86-xxx-..., 400-xxx-xxxx 等\n"
            "  \"platform\": string,              // 选填：会议平台（'腾讯'/'进门'/'飞书'/'钉钉'/'Zoom'/'Teams'/'电话'/'外呼'）\n"
            "  \"start_time\": string,            // 选填：会议开始时间，格式如 '11-23 14:30'\n"
            "  \"organizer\": string,             // 选填：内部预约人/联系人姓名\n"
            "  \"tone\": string,                  // 必填：meeting/neutral/bullish/bearish 中选；会议邀请用'meeting'\n"
            "  \"confidence\": float,             // 必填：0.0-1.0\n"
            "  \"category\": string,             // 必填：会议/观点/其他 中选；当检测到会议信息时选'会议'\n"
            "  \"key_points\": [string],          // 必填：2-4条原文要点，短句，不编造\n"
            "  \"comment\": string                // 必填：一句话评论，指出价值/风险/后续动作\n"
            "}\n\n"
            "说明：\n"
            "- meeting_number 只保留数字；如 '+86-010-8888-6666' -> '01088886666'；'400-820-5555' -> '4008205555'；\n"
            "- summary: 若有会议时间，务必加在最前，如 '[11-23 14:30]'；若有预约人，加在会议号后，如 '[预约人:张三]'。\n"
            "- 再次强调：不要把邮件主题（Subject）当作摘要，请从正文中提取实质内容。\n\n"
            "数据：{{messages_json}}"
        ),
    }
    ,
    "minutes_summary": {
        "system": (
            "你是会议纪要摘要助手，负责把会议纪要或录音转写文本压缩成“结构化摘要”（<=500字）。\n"
            "要求：\n"
            "- 必须先给出一个【标题】概括会议主题（放在摘要开头）。\n"
            "- 摘要主体用“要点大纲 + 分段/小标题”组织，突出逻辑链条与结构；覆盖所有重要点。\n"
            "- 额外输出 key_points（2-5条原文要点）和 comment（一句话评论/结论，指出价值、风险或待办）。\n"
            "- 不要复述文件名/标题；不要逐句抄原文；但要尽量涵盖细节与关键事实。\n"
            "- 如出现明确的会议/路演安排信息（平台/会议号/时间），可在开头或末尾以一行简短保留。\n"
            "- 禁止编造信息；信息不足时明确写“信息有限”。\n"
            "- 输出必须以'ai: '开头。"
        ),
        "user": (
            "请逐条总结以下会议纪要文本（JSON数组：id/time/sender/content），返回JSON数组，每个元素：\n"
            "{\n"
            "  \"id\": string,\n"
            "  \"summary\": string,     // 必填，<=500字；必须以'ai: '开头；结构示例：ai: 【标题】...\\n要点：\\n- ...\\n- ...\\n结论：...\\n待办：...\n"
            "  \"tone\": string,        // 可选：positive/negative/neutral\n"
            "  \"key_points\": [string], // 必填：2-5条原文要点，短句，不编造\n"
            "  \"comment\": string       // 必填：一句话评论/结论，指出价值、风险或待办\n"
            "}\n\n"
            "数据：{{messages_json}}"
        ),
    }
    ,
    "minutes_refine": {
        "system": (
            "你是一名会议记录整理助手。你会收到一段会议录音的转写文本（可能口语化、断句混乱、含口误/赘词）。\n"
            "你的目标：把转写整理为“通顺、结构清晰、尽量保留细节”的会议详细记录。\n"
            "要求：\n"
            "- 不要删减重要内容；尽可能保留原有详细程度（允许删除重复赘词/口水话/明显口误）。\n"
            "- 修正明显的语序问题、断句、口语化表达与明显的转写错误，使其可读。\n"
            "- 识别多人讨论：根据称呼/语气/问答/上下文，尽量区分角色；不确定时用“发言人A/B/主持/提问者”等占位。\n"
            "- 将 Q&A 片段整理为 Q(角色): / A(角色): 形式；讨论片段按角色分段。\n"
            "- 禁止编造未出现的信息；不要加入你的分析/评价。\n"
            "- 输出为 JSON 数组；每个元素对应一条输入，字段 refined 为整理后的会议详细记录文本（可用 Markdown）。"
        ),
        "user": (
            "请逐条整理下面的会议转写（messages_json 包含 id/time/sender/content）。\n"
            "只返回 JSON 数组，每个元素结构：\n"
            "[{\n"
            "  \"id\": string,\n"
            "  \"summary\": string,     // 简短占位即可，必须以'ai: '开头（例如 ai: ok）\n"
            "  \"refined\": string      // 必填：整理后的会议详细记录（尽量保留细节，结构清晰，可多段）\n"
            "}]\n\n"
            "数据：{{messages_json}}"
        ),
    }
    ,
    "media_content_summary": {
        "label": "自媒体内容摘要",
        "system": (
            "你是投研自媒体内容摘要助手。逐条提炼内容，不复读标题，不合并不同条目。"
            "摘要需说明核心事实、市场影响或待验证点；信息不足时明确写信息有限。"
        ),
        "user": (
            "请逐条分析以下自媒体内容，返回 JSON 数组，每个元素必须包含："
            "{\"id\": string, \"summary\": string, \"tone\": string, \"keywords\": [string]}。\n"
            "summary 不超过100字并以 ai: 开头；tone 只能是 bullish/bearish/neutral。\n"
            "数据：{{messages_json}}"
        ),
    }
    ,
    "mp_content_summary": {
        "label": "公众号内容摘要",
        "system": (
            "你是投研公众号内容摘要助手。逐条基于正文或原始简介提炼实质内容，不复读标题，"
            "不合并文章，不编造正文中没有的信息。"
        ),
        "user": (
            "请逐条分析以下公众号内容，返回 JSON 数组，每个元素必须包含："
            "{\"id\": string, \"summary\": string, \"tone\": string, \"keywords\": [string]}。\n"
            "summary 不超过120字并以 ai: 开头；tone 只能是 bullish/bearish/neutral。\n"
            "数据：{{messages_json}}"
        ),
    }
    ,
    "reply_generation": {
        "label": "旧默认(兼容)",
        "system": "\n".join(
            [
                "你是一名专业的微信沟通助手，负责生成可直接发送的中文回复。",
                "要求：",
                "- 输出纯文本（不要 Markdown、不要代码块、不要解释）。",
                "- 语气礼貌克制、信息密度高、避免夸张与营销腔。",
                "- 不要编造事实；若信息不足，用一句话提出需要确认的问题。",
                "- 若操作类型为“约”，优先给出可执行的时间/方式确认；",
                "- 若为“问”，给出结构化要点并提供下一步建议；",
                "- 若为“答”，直接回应问题并给出明确结论或行动；",
                "- 若为“顶/踩”，分别表达赞同或提示风险，保持专业。",
            ]
        ),
        "user": "\n".join(
            [
                "请根据以下信息生成一段可直接发送的回复（仅输出回复文本）：",
                "- 操作类型：{{operation_type}}",
                "- 对方：{{sender_name}}",
                "- 会话：{{talker_name}}",
                "- 原消息：{{message_text}}",
                "",
                "回复要求：1-6句，必要时可分点；避免空话套话。",
            ]
        ),
    }
    ,
    "reply_yue": {
        "label": "约",
        "system": "\n".join(
            [
                "你是一名专业的微信沟通助手，擅长把“邀约/约时间/约会议/约电话”回复写得明确、可执行。",
                "输出要求：",
                "- 仅输出可直接发送的中文纯文本（不要 Markdown、不要解释）。",
                "- 语气礼貌克制、信息密度高；避免套话。",
                "- 给出 2 个可选时间窗口 + 1 个确认方式（线上/电话/地点/会议号）。",
                "- 若缺少关键要素（时间/地点/主题/时长/参会人），用 1 句追问补齐。",
            ]
        ),
        "user": "\n".join(
            [
                "请基于以下原消息，生成一段“约时间/确认会议”的回复（仅输出回复文本）：",
                "- 对方：{{sender_name}}",
                "- 会话：{{talker_name}}",
                "- 原消息：{{message_text}}",
                "",
                "回复长度：2-5句。优先提供两个可选时间段，并请对方确认。",
            ]
        ),
    }
    ,
    "reply_wen": {
        "label": "问",
        "system": "\n".join(
            [
                "你是一名专业的微信沟通助手，负责提出“高质量问题/澄清需求/追问关键信息”。",
                "输出要求：",
                "- 仅输出可直接发送的中文纯文本（不要 Markdown、不要解释）。",
                "- 语气礼貌克制；避免质问；每句话都要有信息增量。",
                "- 问题要少而关键：优先 2-4 个点，覆盖目标、范围、时间、约束、交付物。",
                "- 若可以给出备选方案/下一步，也用 1 句带出。",
            ]
        ),
        "user": "\n".join(
            [
                "请基于以下原消息，生成一段“追问澄清”的回复（仅输出回复文本）：",
                "- 对方：{{sender_name}}",
                "- 会话：{{talker_name}}",
                "- 原消息：{{message_text}}",
                "",
                "回复长度：2-6句，可分点提问。",
            ]
        ),
    }
    ,
    "reply_da": {
        "label": "答",
        "system": "\n".join(
            [
                "你是一名专业的微信沟通助手，负责给出“明确答复/可执行结论/下一步动作”。",
                "输出要求：",
                "- 仅输出可直接发送的中文纯文本（不要 Markdown、不要解释）。",
                "- 结论先行：第一句给结论或明确态度；后面补 1-3 条依据/安排。",
                "- 不要编造事实；信息不足时，先给临时结论 + 1 句需要确认的问题。",
                "- 尽量给出下一步动作与时间点（如“我今天xx前发你”）。",
            ]
        ),
        "user": "\n".join(
            [
                "请基于以下原消息，生成一段“答复确认”的回复（仅输出回复文本）：",
                "- 对方：{{sender_name}}",
                "- 会话：{{talker_name}}",
                "- 原消息：{{message_text}}",
                "",
                "回复长度：1-6句，结论优先。",
            ]
        ),
    }
}


def _clamp_int(v: Any, lo: int, hi: int, default: int) -> int:
    try:
        iv = int(v)
        return max(lo, min(hi, iv))
    except Exception:
        return default


def _to_channel_list(raw: Any, defaults: List[dict]) -> List[dict]:
    src = raw if isinstance(raw, list) and raw else defaults
    out: List[dict] = []
    seen_ids: set[str] = set()
    for i, item in enumerate(src):
        if not isinstance(item, dict):
            continue
        cid = str(item.get("id") or f"ch-{i+1}").strip()[:64]
        if not cid or cid in seen_ids:
            continue
        seen_ids.add(cid)
        out.append(
            {
                "id": cid,
                "name": str(item.get("name") or cid).strip()[:120],
                "model": str(item.get("model") or "").strip(),
                "weight": _clamp_int(item.get("weight"), 1, 32, 1),
                "enabled": bool(item.get("enabled") if item.get("enabled") is not None else True),
                "api_url": str(item.get("api_url") or "").strip(),
                "api_key": str(item.get("api_key") or "").strip(),
                "max_inflight": _clamp_int(item.get("max_inflight"), 1, 256, max(2, _LLM_MAX_PARALLEL)),
            }
        )
    return out or defaults


def _to_route_map(raw: Any, default_map: Dict[str, List[str]], valid_ids: set[str]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    src = raw if isinstance(raw, dict) else {}
    for k, default_ids in default_map.items():
        vals = src.get(k, default_ids)
        ids: List[str] = []
        if isinstance(vals, str):
            vals = [v.strip() for v in vals.split(",") if v.strip()]
        if isinstance(vals, list):
            for v in vals:
                sid = str(v or "").strip()
                if sid and sid in valid_ids and sid not in ids:
                    ids.append(sid)
        if not ids:
            ids = [sid for sid in default_ids if sid in valid_ids]
        out[k] = ids
    return out


def _default_model_router(conf: Dict[str, Any]) -> Dict[str, Any]:
    main_model = str(conf.get("main_model") or conf.get("model") or DASHENG_CLOUD_MAIN_MODEL).strip()
    report_m3_model = DASHENG_CLOUD_M3_MODEL
    fallback_model = str(conf.get("fallback_model") or DASHENG_CLOUD_FALLBACK_MODEL).strip()
    onepage_model = str(conf.get("onepage_model") or DASHENG_CLOUD_ONEPAGE_MODEL).strip()
    tool_msg_model = str(conf.get("tool_model_messages") or conf.get("tool_model") or DASHENG_CLOUD_TOOL_MODEL).strip()
    tool_email_model = str(conf.get("tool_model_emails") or conf.get("tool_model") or DASHENG_CLOUD_TOOL_MODEL).strip()
    main_channels = [
        {
            "id": "dasheng-report-gpt-55",
            "name": "大圣Cloud 报告生成 GPT-5.5",
            "model": main_model,
            "weight": 18,
            "enabled": True,
            "api_url": DASHENG_CLOUD_API_URL,
            "api_key": "",
            "max_inflight": 32,
        },
        {
            "id": "dasheng-report-minimax-m3",
            "name": "大圣Cloud 报告生成 MiniMax M3",
            "model": report_m3_model,
            "weight": 14,
            "enabled": True,
            "api_url": DASHENG_CLOUD_API_URL,
            "api_key": "",
            "max_inflight": 32,
        },
        {
            "id": "dasheng-report-deepseek-v4-flash",
            "name": "大圣Cloud 报告兜底 DeepSeek V4 Flash",
            "model": fallback_model,
            "weight": 4,
            "enabled": True,
            "api_url": DASHENG_CLOUD_API_URL,
            "api_key": "",
            "max_inflight": 24,
        },
    ]
    mid_channels = [
        {
            "id": "dasheng-onepage-minimax-m3",
            "name": "大圣Cloud 多模态一页通 MiniMax M3",
            "model": onepage_model,
            "weight": 16,
            "enabled": True,
            "api_url": DASHENG_CLOUD_API_URL,
            "api_key": "",
            "max_inflight": 16,
        }
    ]
    tool_channels = [
        {
            "id": "dasheng-tool-minimax-m3",
            "name": "大圣Cloud 小模型 MiniMax M3",
            "model": tool_msg_model,
            "weight": 16,
            "enabled": True,
            "api_url": DASHENG_CLOUD_API_URL,
            "api_key": "",
            "max_inflight": 48,
        },
        {
            "id": "dasheng-email-minimax-m3",
            "name": "大圣Cloud 邮件 MiniMax M3",
            "model": tool_email_model,
            "weight": 12,
            "enabled": True,
            "api_url": DASHENG_CLOUD_API_URL,
            "api_key": "",
            "max_inflight": 48,
        },
        {
            "id": "dasheng-tool-qwen34b",
            "name": "大圣Cloud 小模型 Qwen 34B",
            "model": DASHENG_CLOUD_QWEN_34B_MODEL,
            "weight": 6,
            "enabled": True,
            "api_url": DASHENG_CLOUD_API_URL,
            "api_key": "",
            "max_inflight": 32,
        },
        {
            "id": "dasheng-tool-qwen35-4b",
            "name": "大圣Cloud 小模型 Qwen3.5 4B",
            "model": DASHENG_CLOUD_QWEN35_4B_MODEL,
            "weight": 4,
            "enabled": True,
            "api_url": DASHENG_CLOUD_API_URL,
            "api_key": "",
            "max_inflight": 32,
        },
        {
            "id": "dasheng-tool-qwen3-8b",
            "name": "大圣Cloud 小模型 Qwen3 8B",
            "model": DASHENG_CLOUD_QWEN3_8B_MODEL,
            "weight": 5,
            "enabled": True,
            "api_url": DASHENG_CLOUD_API_URL,
            "api_key": "",
            "max_inflight": 32,
        },
    ]
    main_route_defaults = {
        "default": ["dasheng-report-gpt-55", "dasheng-report-deepseek-v4-flash"],
        "market": ["dasheng-report-gpt-55", "dasheng-report-deepseek-v4-flash"],
        "counter": ["dasheng-report-gpt-55", "dasheng-report-deepseek-v4-flash"],
        "newswatch": ["dasheng-report-gpt-55", "dasheng-report-deepseek-v4-flash"],
        "meetings": ["dasheng-report-minimax-m3", "dasheng-report-deepseek-v4-flash"],
        "contacts": ["dasheng-report-minimax-m3", "dasheng-report-deepseek-v4-flash"],
        "socialwatch": ["dasheng-report-minimax-m3", "dasheng-report-deepseek-v4-flash"],
        "mediawatch": ["dasheng-report-minimax-m3", "dasheng-report-deepseek-v4-flash"],
        "mpwatch": ["dasheng-report-minimax-m3", "dasheng-report-deepseek-v4-flash"],
        "minuteswatch": ["dasheng-report-minimax-m3", "dasheng-report-deepseek-v4-flash"],
    }
    tool_route_defaults = {
        "default": ["dasheng-tool-minimax-m3", "dasheng-tool-qwen3-8b", "dasheng-tool-qwen35-4b"],
        "messages": ["dasheng-tool-minimax-m3", "dasheng-tool-qwen3-8b", "dasheng-tool-qwen35-4b"],
        "emails": ["dasheng-email-minimax-m3", "dasheng-tool-qwen34b", "dasheng-tool-qwen3-8b"],
        "minutes": ["dasheng-tool-minimax-m3", "dasheng-tool-qwen34b", "dasheng-tool-qwen3-8b"],
        "reply": ["dasheng-tool-minimax-m3", "dasheng-tool-qwen3-8b", "dasheng-tool-qwen35-4b"],
    }
    mid_route_defaults = {
        "default": ["dasheng-onepage-minimax-m3"],
        "onepage": ["dasheng-onepage-minimax-m3"],
    }
    return {
        "enabled": True,
        "strategy": "mixed",
        "prefer_router": True,
        "dynamic_weighting": True,
        "breaker_failures": 3,
        "cooldown_seconds": 45,
        "latency_ref_ms": 3000,
        "main_channels": main_channels,
        "mid_channels": mid_channels,
        "tool_channels": tool_channels,
        "main_module_channels": main_route_defaults,
        "mid_route_channels": mid_route_defaults,
        "tool_route_channels": tool_route_defaults,
    }


def _normalize_model_router(raw_router: Any, conf: Dict[str, Any]) -> Dict[str, Any]:
    defaults = _default_model_router(conf)
    router = raw_router if isinstance(raw_router, dict) else {}

    main_channels = _to_channel_list(router.get("main_channels"), defaults["main_channels"])
    mid_channels = _to_channel_list(router.get("mid_channels"), defaults["mid_channels"])
    tool_channels = _to_channel_list(router.get("tool_channels"), defaults["tool_channels"])
    main_ids = {c["id"] for c in main_channels}
    mid_ids = {c["id"] for c in mid_channels}
    tool_ids = {c["id"] for c in tool_channels}
    main_route_defaults = defaults["main_module_channels"]
    mid_route_defaults = defaults["mid_route_channels"]
    tool_route_defaults = defaults["tool_route_channels"]

    normalized = {
        "enabled": bool(router.get("enabled") if router.get("enabled") is not None else defaults["enabled"]),
        "strategy": "mixed",
        "prefer_router": bool(router.get("prefer_router") if router.get("prefer_router") is not None else defaults["prefer_router"]),
        "dynamic_weighting": bool(
            router.get("dynamic_weighting")
            if router.get("dynamic_weighting") is not None
            else defaults.get("dynamic_weighting", True)
        ),
        "breaker_failures": _clamp_int(
            router.get("breaker_failures"),
            2,
            10,
            int(defaults.get("breaker_failures", 3)),
        ),
        "cooldown_seconds": _clamp_int(
            router.get("cooldown_seconds"),
            5,
            600,
            int(defaults.get("cooldown_seconds", 45)),
        ),
        "latency_ref_ms": _clamp_int(
            router.get("latency_ref_ms"),
            300,
            20000,
            int(defaults.get("latency_ref_ms", 3000)),
        ),
        "main_channels": main_channels,
        "mid_channels": mid_channels,
        "tool_channels": tool_channels,
        "main_module_channels": _to_route_map(router.get("main_module_channels"), main_route_defaults, main_ids),
        "mid_route_channels": _to_route_map(router.get("mid_route_channels"), mid_route_defaults, mid_ids),
        "tool_route_channels": _to_route_map(router.get("tool_route_channels"), tool_route_defaults, tool_ids),
    }
    return normalized


def load_ai_config() -> Dict[str, Any]:
    path = os.path.abspath(os.path.join(os.getcwd(), "data", "ai_config.json"))
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                conf = json.load(f)
        except Exception:
            conf = {}
    else:
        conf = {}

    if not conf:
        conf = {
            "api_key": settings.SILICONFLOW_API_KEY or "",
            "api_url": settings.SILICONFLOW_API_URL or DASHENG_CLOUD_API_URL,
            "ai_provider_mode": (
                "custom"
                if settings.SILICONFLOW_API_URL and settings.SILICONFLOW_API_URL.rstrip("/") != DASHENG_CLOUD_API_URL
                else "dasheng"
            ),
            "model": settings.SILICONFLOW_MODEL or DASHENG_CLOUD_MAIN_MODEL,
            "main_model": conf.get("main_model") or DASHENG_CLOUD_MAIN_MODEL,
            "fallback_model": DASHENG_CLOUD_FALLBACK_MODEL,
            "onepage_model": DASHENG_CLOUD_ONEPAGE_MODEL,
            "tool_model": settings.SILICONFLOW_TOOL_MODEL or DASHENG_CLOUD_TOOL_MODEL,
            "tool_model_messages": settings.SILICONFLOW_TOOL_MODEL or DASHENG_CLOUD_TOOL_MODEL,
            "tool_model_emails": settings.SILICONFLOW_TOOL_MODEL or DASHENG_CLOUD_TOOL_MODEL,
            "max_tokens": 4000,
            "model_temperature": 0.7,
            "onepage_output_mode": settings.ONEPAGE_IMAGE_MODE,
            "onepage_image_api_url": settings.ONEPAGE_IMAGE_API_URL or "",
            "onepage_image_api_key": settings.ONEPAGE_IMAGE_API_KEY or "",
            "onepage_image_model": settings.ONEPAGE_IMAGE_MODEL,
            "onepage_image_size": settings.ONEPAGE_IMAGE_SIZE,
            "onepage_image_quality": settings.ONEPAGE_IMAGE_QUALITY,
            "message_filters": {"external_only": True, "exclude_short": True, "exclude_system": True},
            "derive_defaults": {"batch_size": 100, "concurrency": 3, "temperature": 0.1, "force": False},
            "desk_agent": {
                "enabled": bool(getattr(settings, "DESK_AGENT_ENABLED", False)),
                "base_url": str(getattr(settings, "DESK_AGENT_BASE_URL", "http://127.0.0.1:8911") or "").strip(),
                "token": str(getattr(settings, "DESK_AGENT_TOKEN", "") or "").strip(),
                "module_id": str(getattr(settings, "DESK_AGENT_MODULE_ID", "deepsee-news") or "deepsee-news").strip(),
                "adapter": "",
                "model": "",
                "command_profile": "batch",
                "timeout_seconds": int(getattr(settings, "DESK_AGENT_TIMEOUT_SECONDS", 180) or 180),
            },
        }
    else:
        conf.setdefault("api_key", settings.SILICONFLOW_API_KEY or conf.get("api_key", ""))
        conf.setdefault("api_url", settings.SILICONFLOW_API_URL or conf.get("api_url", DASHENG_CLOUD_API_URL))
        mode = str(conf.get("ai_provider_mode") or "").strip()
        if mode not in {"dasheng", "custom"}:
            mode = "dasheng" if str(conf.get("api_url") or "").strip() == DASHENG_CLOUD_API_URL and bool(conf.get("api_key")) else "custom"
        conf["ai_provider_mode"] = mode
        conf.setdefault("model", settings.SILICONFLOW_MODEL or conf.get("model", DASHENG_CLOUD_MAIN_MODEL))
        conf.setdefault("main_model", conf.get("main_model") or DASHENG_CLOUD_MAIN_MODEL)
        conf.setdefault("fallback_model", conf.get("fallback_model") or DASHENG_CLOUD_FALLBACK_MODEL)
        conf.setdefault("onepage_model", conf.get("onepage_model") or DASHENG_CLOUD_ONEPAGE_MODEL)
        conf.setdefault("tool_model", settings.SILICONFLOW_TOOL_MODEL or conf.get("tool_model", DASHENG_CLOUD_TOOL_MODEL))
        conf.setdefault("tool_model_messages", conf.get("tool_model_messages") or conf.get("tool_model", DASHENG_CLOUD_TOOL_MODEL))
        conf.setdefault("tool_model_emails", conf.get("tool_model_emails") or conf.get("tool_model", DASHENG_CLOUD_TOOL_MODEL))
        conf.setdefault("max_tokens", conf.get("max_tokens", 4000))
        conf.setdefault("model_temperature", conf.get("model_temperature", 0.7))
        conf.setdefault("onepage_output_mode", conf.get("onepage_output_mode", settings.ONEPAGE_IMAGE_MODE))
        conf.setdefault("onepage_image_api_url", settings.ONEPAGE_IMAGE_API_URL or conf.get("onepage_image_api_url", ""))
        conf.setdefault("onepage_image_api_key", settings.ONEPAGE_IMAGE_API_KEY or conf.get("onepage_image_api_key", ""))
        conf.setdefault("onepage_image_model", settings.ONEPAGE_IMAGE_MODEL or conf.get("onepage_image_model", DASHENG_CLOUD_ONEPAGE_MODEL))
        conf.setdefault("onepage_image_size", settings.ONEPAGE_IMAGE_SIZE or conf.get("onepage_image_size", "1024x1536"))
        conf.setdefault("onepage_image_quality", settings.ONEPAGE_IMAGE_QUALITY or conf.get("onepage_image_quality", "medium"))
        conf.setdefault("message_filters", conf.get("message_filters", {"external_only": True, "exclude_short": True, "exclude_system": True}))
        conf.setdefault("derive_defaults", conf.get("derive_defaults", {"batch_size": 100, "concurrency": 3, "temperature": 0.1, "force": False}))
        desk_agent = conf.get("desk_agent") if isinstance(conf.get("desk_agent"), dict) else {}
        desk_agent.setdefault("enabled", bool(getattr(settings, "DESK_AGENT_ENABLED", False)))
        desk_agent.setdefault("base_url", str(getattr(settings, "DESK_AGENT_BASE_URL", "http://127.0.0.1:8911") or "").strip())
        desk_agent.setdefault("token", str(getattr(settings, "DESK_AGENT_TOKEN", "") or "").strip())
        desk_agent.setdefault("module_id", str(getattr(settings, "DESK_AGENT_MODULE_ID", "deepsee-news") or "deepsee-news").strip())
        desk_agent.setdefault("adapter", "")
        desk_agent.setdefault("model", "")
        desk_agent.setdefault("command_profile", "batch")
        desk_agent.setdefault("timeout_seconds", int(getattr(settings, "DESK_AGENT_TIMEOUT_SECONDS", 180) or 180))
        conf["desk_agent"] = desk_agent

    stored = conf.get("module_prompts") or {}
    merged_prompts: Dict[str, Dict[str, str]] = {}
    for key, defaults in DEFAULT_MODULE_PROMPTS.items():
        saved = stored.get(key) or {}
        merged_prompts[key] = {
            "system": saved.get("system") or defaults["system"],
            "user": saved.get("user") or defaults["user"],
        }
    conf["module_prompts"] = merged_prompts

    stored_tool = conf.get("tool_prompts") or {}
    merged_tool_prompts: Dict[str, Dict[str, Any]] = {}
    for key, defaults in DEFAULT_TOOL_PROMPTS.items():
        saved = stored_tool.get(key) or {}
        merged_tool_prompts[key] = {
            "system": saved.get("system") or defaults["system"],
            "user": saved.get("user") or defaults["user"],
        }
        label: str = ""
        if isinstance(saved, dict) and isinstance(saved.get("label"), str) and saved.get("label").strip():
            label = saved.get("label").strip()
        elif isinstance(defaults, dict) and isinstance(defaults.get("label"), str) and defaults.get("label").strip():
            label = defaults.get("label").strip()
        if label:
            merged_tool_prompts[key]["label"] = label

    # Preserve user-defined custom tool prompts (e.g., reply_* shortcuts).
    if isinstance(stored_tool, dict):
        for k, v in stored_tool.items():
            if k in merged_tool_prompts:
                continue
            if not isinstance(k, str) or not k.strip():
                continue
            if not isinstance(v, dict):
                continue
            system = v.get("system")
            user = v.get("user")
            if not isinstance(system, str) or not isinstance(user, str):
                continue
            entry: Dict[str, Any] = {"system": system, "user": user}
            if isinstance(v.get("label"), str) and v.get("label").strip():
                entry["label"] = v.get("label").strip()
            merged_tool_prompts[k.strip()] = entry

    conf["tool_prompts"] = merged_tool_prompts
    conf["model_router"] = _normalize_model_router(conf.get("model_router"), conf)
    return conf


def save_ai_config(conf: Dict[str, Any]) -> None:
    path_dir = os.path.abspath(os.path.join(os.getcwd(), "data"))
    os.makedirs(path_dir, exist_ok=True)
    path = os.path.join(path_dir, "ai_config.json")
    normalized = conf.copy()
    # clamp numeric config
    try:
        if "max_tokens" in normalized:
            normalized["max_tokens"] = max(256, int(normalized.get("max_tokens") or 4000))
    except Exception:
        normalized["max_tokens"] = 4000
    try:
        if "model_temperature" in normalized:
            t = float(normalized.get("model_temperature") or 0.7)
            normalized["model_temperature"] = 0.0 if t < 0 else (1.0 if t > 1 else t)
    except Exception:
        normalized["model_temperature"] = 0.7
    mode = str(normalized.get("onepage_output_mode") or "auto").strip().lower()
    if mode not in {"auto", "image", "local"}:
        mode = "auto"
    normalized["onepage_output_mode"] = mode
    normalized["onepage_image_model"] = str(normalized.get("onepage_image_model") or DASHENG_CLOUD_ONEPAGE_MODEL).strip() or DASHENG_CLOUD_ONEPAGE_MODEL
    size = str(normalized.get("onepage_image_size") or "1024x1536").strip()
    if size not in {"1024x1024", "1024x1536", "1536x1024"}:
        size = "1024x1536"
    normalized["onepage_image_size"] = size
    quality = str(normalized.get("onepage_image_quality") or "medium").strip().lower()
    if quality not in {"low", "medium", "high", "auto"}:
        quality = "medium"
    normalized["onepage_image_quality"] = quality
    # clamp derive defaults
    dd = normalized.get("derive_defaults") or {}
    try:
        bs = int(dd.get("batch_size", 20))
        dd["batch_size"] = max(1, min(128, bs))
    except Exception:
        dd["batch_size"] = 20
    try:
        cc = int(dd.get("concurrency", 8))
        dd["concurrency"] = max(1, min(64, cc))
    except Exception:
        dd["concurrency"] = 8
    try:
        tp = float(dd.get("temperature", 0.1))
        dd["temperature"] = 0.0 if tp < 0 else (1.0 if tp > 1 else tp)
    except Exception:
        dd["temperature"] = 0.1
    dd["force"] = bool(dd.get("force", False))
    normalized["derive_defaults"] = dd
    desk_agent = normalized.get("desk_agent") if isinstance(normalized.get("desk_agent"), dict) else {}
    desk_agent["enabled"] = bool(desk_agent.get("enabled", False))
    desk_agent["base_url"] = str(desk_agent.get("base_url") or "").strip().rstrip("/")
    desk_agent["token"] = str(desk_agent.get("token") or "").strip()
    desk_agent["module_id"] = str(desk_agent.get("module_id") or "deepsee-news").strip()
    desk_agent["adapter"] = str(desk_agent.get("adapter") or "").strip()
    desk_agent["model"] = str(desk_agent.get("model") or "").strip()
    command_profile = str(desk_agent.get("command_profile") or "batch").strip()
    desk_agent["command_profile"] = command_profile if command_profile in {"quick", "batch", "deep", "edit"} else "batch"
    try:
        desk_agent["timeout_seconds"] = max(10, min(900, int(desk_agent.get("timeout_seconds") or 180)))
    except Exception:
        desk_agent["timeout_seconds"] = 180
    normalized["desk_agent"] = desk_agent
    # ensure module prompts always contain defaults when missing
    stored = normalized.get("module_prompts") or {}
    merged_prompts: Dict[str, Dict[str, str]] = {}
    for key, defaults in DEFAULT_MODULE_PROMPTS.items():
        saved = stored.get(key) or {}
        merged_prompts[key] = {
            "system": saved.get("system") or defaults["system"],
            "user": saved.get("user") or defaults["user"],
        }
    normalized["module_prompts"] = merged_prompts

    stored_tool = normalized.get("tool_prompts") or {}
    merged_tool_prompts: Dict[str, Dict[str, Any]] = {}
    for key, defaults in DEFAULT_TOOL_PROMPTS.items():
        saved = stored_tool.get(key) or {}
        merged_tool_prompts[key] = {
            "system": saved.get("system") or defaults["system"],
            "user": saved.get("user") or defaults["user"],
        }
        label: str = ""
        if isinstance(saved, dict) and isinstance(saved.get("label"), str) and saved.get("label").strip():
            label = saved.get("label").strip()
        elif isinstance(defaults, dict) and isinstance(defaults.get("label"), str) and defaults.get("label").strip():
            label = defaults.get("label").strip()
        if label:
            merged_tool_prompts[key]["label"] = label

    # Preserve custom tool prompts (e.g., reply_* shortcuts) and their label fields.
    if isinstance(stored_tool, dict):
        for k, v in stored_tool.items():
            kk = str(k or "").strip()
            if not kk or kk in merged_tool_prompts:
                continue
            if not isinstance(v, dict):
                continue
            system = v.get("system")
            user = v.get("user")
            if not isinstance(system, str) or not isinstance(user, str):
                continue
            entry: Dict[str, Any] = {"system": system, "user": user}
            if isinstance(v.get("label"), str) and v.get("label").strip():
                entry["label"] = v.get("label").strip()
            merged_tool_prompts[kk] = entry

    normalized["tool_prompts"] = merged_tool_prompts
    normalized["model_router"] = _normalize_model_router(normalized.get("model_router"), normalized)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)


_LLM_MAX_PARALLEL = max(1, int(os.getenv("AI_MAX_PARALLEL", "3") or 3))
# Global semaphore to throttle concurrent LLM calls across the process
_LLM_SEMAPHORE = threading.BoundedSemaphore(_LLM_MAX_PARALLEL)
_MODEL_ROUTER_LOCK = threading.Lock()
_MODEL_ROUTER_COUNTERS: Dict[str, int] = {}
_MODEL_ROUTER_STATS: Dict[str, Dict[str, Any]] = {}
_MODEL_ROUTER_LAST_PERSIST_AT: float = 0.0
_BAD_API_KEYS_UNTIL: Dict[str, float] = {}
_BAD_API_KEY_COOLDOWN_SEC = 20 * 60


def _now_ts() -> float:
    try:
        return time.time()
    except Exception:
        return 0.0


def _router_metrics_path() -> str:
    return os.path.abspath(os.path.join(os.getcwd(), "data", "router_metrics.json"))


def _router_trace_path() -> str:
    return os.path.abspath(os.path.join(os.getcwd(), "data", "router_traces.jsonl"))


def _safe_domain(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""


def _mark_bad_api_key(api_key: str) -> None:
    key = str(api_key or "").strip()
    if not key:
        return
    with _MODEL_ROUTER_LOCK:
        _BAD_API_KEYS_UNTIL[key] = _now_ts() + float(_BAD_API_KEY_COOLDOWN_SEC)


def _is_bad_api_key(api_key: str) -> bool:
    key = str(api_key or "").strip()
    if not key:
        return False
    now = _now_ts()
    with _MODEL_ROUTER_LOCK:
        until = float(_BAD_API_KEYS_UNTIL.get(key) or 0.0)
        if until <= now:
            if key in _BAD_API_KEYS_UNTIL:
                _BAD_API_KEYS_UNTIL.pop(key, None)
            return False
        return True


_THINK_BLOCK_RE = re.compile(
    r"<\s*(think|reasoning)[^>]*>(.*?)<\s*/\s*\1\s*>",
    re.IGNORECASE | re.DOTALL,
)


def _clean_reasoning_fallback(text: str) -> str:
    lines = []
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if re.match(
            r"^(let me|i need to|i will|i'll|i should|we need to|now\s+(?:i|we)\b|the user\s+(?:wants|asked|is asking)\s+me\b)",
            stripped,
            re.IGNORECASE,
        ):
            continue
        lines.append(line)
    cleaned = "\n".join(lines).strip()
    replacements = {
        r"\bTime\s*:": "时间：",
        r"\bPlatform\s*:": "平台：",
        r"\bTopic\s*:": "主题：",
        r"\bNumber\s*:": "会议号：",
        r"\bMeeting\s+ID\s*:": "会议号：",
    }
    for pattern, replacement in replacements.items():
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _normalize_llm_content(raw: Any) -> str:
    """Normalize provider output and reject whitespace-only payloads."""
    if not isinstance(raw, str):
        return ""
    text = raw.replace("\ufeff", "").replace("\x00", "")
    # Some providers prepend chain-of-thought-like blocks; drop them for stability.
    reasoning_fallback = "\n".join(
        str(match[1] or "").strip()
        for match in _THINK_BLOCK_RE.findall(text)
        if str(match[1] or "").strip()
    ).strip()
    text = _THINK_BLOCK_RE.sub("", text)
    text = text.strip()
    if not text and reasoning_fallback:
        text = _clean_reasoning_fallback(reasoning_fallback)
    if not text:
        return ""
    # Guard against pathological outputs made of mostly whitespace/control chars.
    visible = "".join(ch for ch in text if ch.isprintable() and not ch.isspace())
    if not visible:
        return ""
    return text


def _normalize_model_content(raw: Any, *, model: str) -> str:
    content = _normalize_llm_content(raw)
    if content and "minimax-m3" in str(model or "").strip().lower():
        return _clean_reasoning_fallback(content)
    return content


def _get_channel_runtime(channel_id: str) -> Dict[str, Any]:
    with _MODEL_ROUTER_LOCK:
        st = _MODEL_ROUTER_STATS.get(channel_id)
        if st is None:
            st = {
                "calls": 0,
                "success": 0,
                "failure": 0,
                "consecutive_failures": 0,
                "ema_latency_ms": None,
                "inflight": 0,
                "last_error": "",
                "last_status": "",
                "last_latency_ms": None,
                "last_at": 0.0,
                "cooldown_until": 0.0,
            }
            _MODEL_ROUTER_STATS[channel_id] = st
        return st


def _persist_router_metrics(force: bool = False) -> None:
    global _MODEL_ROUTER_LAST_PERSIST_AT
    now = _now_ts()
    if not force and now - _MODEL_ROUTER_LAST_PERSIST_AT < 5.0:
        return
    _MODEL_ROUTER_LAST_PERSIST_AT = now
    try:
        snapshot: Dict[str, Dict[str, Any]] = {}
        with _MODEL_ROUTER_LOCK:
            for k, v in _MODEL_ROUTER_STATS.items():
                snapshot[k] = dict(v)
        os.makedirs(os.path.abspath(os.path.join(os.getcwd(), "data")), exist_ok=True)
        with open(_router_metrics_path(), "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
    except Exception:
        return


def _append_router_trace(
    *,
    route_kind: str,
    route_key: str | None,
    channel_id: str,
    model: str,
    api_url: str,
    ok: bool,
    latency_ms: float,
    reason: str,
) -> None:
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "route_kind": route_kind,
        "route_key": str(route_key or "default"),
        "channel_id": channel_id,
        "model": model,
        "provider": _safe_domain(api_url),
        "ok": bool(ok),
        "latency_ms": round(float(latency_ms), 1),
        "reason": reason[:240] if reason else "",
    }
    try:
        os.makedirs(os.path.abspath(os.path.join(os.getcwd(), "data")), exist_ok=True)
        with open(_router_trace_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        return


def _router_mark_inflight(channel_id: str, delta: int) -> None:
    if not channel_id:
        return
    st = _get_channel_runtime(channel_id)
    with _MODEL_ROUTER_LOCK:
        inflight = int(st.get("inflight") or 0) + int(delta)
        st["inflight"] = max(0, inflight)
        st["last_at"] = _now_ts()


def _router_mark_result(
    channel: dict | None,
    *,
    ok: bool,
    latency_ms: float,
    err: str = "",
    conf: dict | None = None,
) -> None:
    if not isinstance(channel, dict):
        return
    channel_id = str(channel.get("id") or "").strip()
    if not channel_id:
        return
    st = _get_channel_runtime(channel_id)
    now = _now_ts()
    base_cooldown = 45
    breaker_failures = 3
    if isinstance(conf, dict):
        router = conf.get("model_router") if isinstance(conf.get("model_router"), dict) else {}
        try:
            base_cooldown = _clamp_int(router.get("cooldown_seconds"), 5, 600, base_cooldown)
        except Exception:
            pass
        try:
            breaker_failures = _clamp_int(router.get("breaker_failures"), 2, 10, breaker_failures)
        except Exception:
            pass
    with _MODEL_ROUTER_LOCK:
        st["calls"] = int(st.get("calls") or 0) + 1
        st["last_at"] = now
        st["last_latency_ms"] = float(latency_ms)
        ema = st.get("ema_latency_ms")
        if ema is None:
            st["ema_latency_ms"] = float(latency_ms)
        else:
            st["ema_latency_ms"] = float(0.25 * float(latency_ms) + 0.75 * float(ema))
        if ok:
            st["success"] = int(st.get("success") or 0) + 1
            st["consecutive_failures"] = 0
            st["last_error"] = ""
            st["last_status"] = "ok"
            st["cooldown_until"] = 0.0
        else:
            st["failure"] = int(st.get("failure") or 0) + 1
            st["consecutive_failures"] = int(st.get("consecutive_failures") or 0) + 1
            st["last_error"] = str(err or "")[:240]
            st["last_status"] = "error"
            cfail = int(st.get("consecutive_failures") or 0)
            if cfail >= breaker_failures:
                cool = min(600, base_cooldown * (2 ** max(0, cfail - breaker_failures)))
                st["cooldown_until"] = now + cool
    _persist_router_metrics()


def _channel_success_rate(channel_id: str) -> float:
    st = _get_channel_runtime(channel_id)
    calls = float(st.get("calls") or 0.0)
    succ = float(st.get("success") or 0.0)
    return (succ + 1.0) / (calls + 2.0)


def _channel_latency_factor(channel_id: str, latency_ref_ms: int) -> float:
    st = _get_channel_runtime(channel_id)
    ema = st.get("ema_latency_ms")
    if ema is None:
        return 1.0
    try:
        lat = max(1.0, float(ema))
    except Exception:
        return 1.0
    ref = max(300.0, float(latency_ref_ms))
    # 平滑惩罚：低延迟接近 1，高延迟逐步降权，但不把慢通道直接打死。
    return max(0.35, min(1.15, ref / (ref + max(0.0, lat - ref) * 0.75)))


def _channel_health_factor(channel_id: str) -> float:
    st = _get_channel_runtime(channel_id)
    calls = float(st.get("calls") or 0.0)
    succ = float(st.get("success") or 0.0)
    fail = float(st.get("failure") or 0.0)
    cfail = int(st.get("consecutive_failures") or 0)
    if calls <= 0:
        return 1.0
    # 贝叶斯平滑，避免 1 次成功/失败造成剧烈抖动。
    success_rate = (succ + 2.0) / (calls + 4.0)
    failure_rate = (fail + 1.0) / (calls + 4.0)
    consecutive_penalty = 0.72 ** max(0, cfail)
    # 连续失败/高失败率必须能压过人工高权重，否则坏通道会一直抢占流量。
    return max(0.01, min(1.25, success_rate * (1.0 - 0.55 * failure_rate) * consecutive_penalty))


def _channel_concurrency_factor(channel: dict) -> float:
    cid = str(channel.get("id") or "").strip()
    if not cid:
        return 1.0
    st = _get_channel_runtime(cid)
    inflight = int(st.get("inflight") or 0)
    max_inflight = _clamp_int(channel.get("max_inflight"), 1, 256, max(2, _LLM_MAX_PARALLEL))
    if inflight <= 0:
        return 1.0
    if inflight >= max_inflight:
        return 0.2
    ratio = float(inflight) / float(max_inflight)
    return max(0.25, 1.0 - 0.8 * ratio)


def _is_channel_in_cooldown(channel_id: str) -> bool:
    st = _get_channel_runtime(channel_id)
    try:
        until = float(st.get("cooldown_until") or 0.0)
    except Exception:
        until = 0.0
    return until > _now_ts()


def _dynamic_rank_channels(channels: List[dict], *, route_key: str, conf: Dict[str, Any]) -> List[dict]:
    enabled = [c for c in channels if isinstance(c, dict) and c.get("enabled") and str(c.get("model") or "").strip()]
    if not enabled:
        return []
    router = conf.get("model_router") if isinstance(conf.get("model_router"), dict) else {}
    dynamic_enabled = bool(router.get("dynamic_weighting", True))
    latency_ref_ms = _clamp_int(router.get("latency_ref_ms"), 300, 20000, 3000)
    # Preserve old deterministic behavior before any runtime sample exists.
    has_runtime_sample = False
    now = _now_ts()
    for ch in enabled:
        cid = str(ch.get("id") or "").strip()
        if not cid:
            continue
        st = _get_channel_runtime(cid)
        if (
            int(st.get("calls") or 0) > 0
            or int(st.get("success") or 0) > 0
            or int(st.get("failure") or 0) > 0
            or int(st.get("inflight") or 0) > 0
            or float(st.get("cooldown_until") or 0.0) > now
        ):
            has_runtime_sample = True
            break
    if not dynamic_enabled or not has_runtime_sample:
        chosen = _weighted_round_robin(enabled, key=route_key)
        if not chosen:
            return enabled
        chosen_id = str(chosen.get("id") or "").strip()
        ordered: list[dict] = [chosen]
        for ch in enabled:
            if str(ch.get("id") or "").strip() != chosen_id:
                ordered.append(ch)
        return ordered

    scored: list[tuple[float, dict]] = []
    cooled: list[tuple[float, dict]] = []
    for ch in enabled:
        cid = str(ch.get("id") or "").strip()
        if not cid:
            continue
        base_weight = float(_clamp_int(ch.get("weight"), 1, 32, 1))
        health_factor = _channel_health_factor(cid)
        lat_factor = _channel_latency_factor(cid, latency_ref_ms)
        conc_factor = _channel_concurrency_factor(ch)
        jitter = random.uniform(0.0, 0.01)
        score = base_weight * health_factor * lat_factor * conc_factor + jitter
        if _is_channel_in_cooldown(cid):
            cooled.append((score, ch))
        else:
            scored.append((score, ch))
    scored.sort(key=lambda x: x[0], reverse=True)
    cooled.sort(key=lambda x: x[0], reverse=True)
    ordered = [c for _, c in scored]
    ordered.extend([c for _, c in cooled])
    return ordered or enabled


def _weighted_round_robin(channels: List[dict], key: str) -> dict | None:
    enabled = [c for c in channels if isinstance(c, dict) and c.get("enabled") and str(c.get("model") or "").strip()]
    if not enabled:
        return None
    total_weight = sum(_clamp_int(c.get("weight"), 1, 32, 1) for c in enabled)
    if total_weight <= 0:
        return enabled[0]
    with _MODEL_ROUTER_LOCK:
        idx = _MODEL_ROUTER_COUNTERS.get(key, 0) % total_weight
        _MODEL_ROUTER_COUNTERS[key] = _MODEL_ROUTER_COUNTERS.get(key, 0) + 1
    acc = 0
    for ch in enabled:
        acc += _clamp_int(ch.get("weight"), 1, 32, 1)
        if idx < acc:
            return ch
    return enabled[0]


def _route_pool(
    conf: Dict[str, Any],
    *,
    route_kind: str,
    route_key: str | None,
) -> tuple[list[dict], str]:
    router = conf.get("model_router") if isinstance(conf.get("model_router"), dict) else {}
    if route_kind == "tool":
        channels = router.get("tool_channels") if isinstance(router, dict) else []
        route_map = router.get("tool_route_channels") if isinstance(router, dict) else {}
    elif route_kind == "mid":
        channels = router.get("mid_channels") if isinstance(router, dict) else []
        route_map = router.get("mid_route_channels") if isinstance(router, dict) else {}
    else:
        channels = router.get("main_channels") if isinstance(router, dict) else []
        route_map = router.get("main_module_channels") if isinstance(router, dict) else {}
    channels = channels if isinstance(channels, list) else []
    route_map = route_map if isinstance(route_map, dict) else {}
    rk = str(route_key or "default").strip() or "default"

    enabled_channels = [
        c
        for c in channels
        if isinstance(c, dict) and c.get("enabled") and str(c.get("model") or "").strip()
    ]
    if not enabled_channels:
        return [], rk

    channel_ids = route_map.get(rk) or route_map.get("default") or []
    if isinstance(channel_ids, str):
        channel_ids = [x.strip() for x in channel_ids.split(",") if x.strip()]
    if not isinstance(channel_ids, list):
        channel_ids = []
    ordered_ids = [str(x).strip() for x in channel_ids if str(x).strip()]
    if not ordered_ids:
        return enabled_channels, rk

    by_id: Dict[str, dict] = {}
    for c in enabled_channels:
        cid = str(c.get("id") or "").strip()
        if cid and cid not in by_id:
            by_id[cid] = c
    ordered: list[dict] = [by_id[sid] for sid in ordered_ids if sid in by_id]
    return ordered or enabled_channels, rk


def _to_target_dict(base_api_url: str, base_api_key: str, base_model: str, chosen: dict | None) -> Dict[str, Any]:
    target = {
        "model": base_model,
        "api_url": base_api_url,
        "api_key": base_api_key,
        "channel_id": None,
    }
    if not isinstance(chosen, dict):
        return target
    target["channel_id"] = str(chosen.get("id") or "").strip() or None
    if str(chosen.get("model") or "").strip():
        target["model"] = str(chosen.get("model") or "").strip()
    chosen_api_url = str(chosen.get("api_url") or "").strip()
    if chosen_api_url:
        target["api_url"] = chosen_api_url
    chosen_api_key = str(chosen.get("api_key") or "").strip()
    if chosen_api_key:
        target["api_key"] = chosen_api_key
    elif chosen_api_url:
        # Avoid misusing base provider key on a different provider domain:
        # if channel changed api_url but left api_key empty, require explicit key.
        base_domain = _safe_domain(base_api_url)
        chosen_domain = _safe_domain(chosen_api_url)
        if base_domain and chosen_domain and base_domain != chosen_domain:
            target["api_key"] = ""
    return target


def resolve_chat_targets(
    conf: Dict[str, Any],
    *,
    route_kind: str,
    route_key: str | None,
    model_override: str | None,
) -> List[Dict[str, Any]]:
    """Resolve ordered model/api targets with optional router and fallback sequence."""
    if route_kind == "tool":
        default_model = str(model_override or conf.get("tool_model") or conf.get("model") or "").strip()
    elif route_kind == "mid":
        default_model = str(model_override or conf.get("tool_model_messages") or conf.get("tool_model") or conf.get("model") or "").strip()
    else:
        default_model = str(model_override or conf.get("model") or "").strip()
    base_api_url = str(conf.get("api_url") or "https://api.siliconflow.cn/v1").strip()
    base_api_key = str(conf.get("api_key") or "").strip()
    default_target = _to_target_dict(base_api_url, base_api_key, default_model, None)
    fallback_model = str(conf.get("fallback_model") or conf.get("model") or default_model).strip()
    fallback_target = _to_target_dict(base_api_url, base_api_key, fallback_model, None)

    router = conf.get("model_router") if isinstance(conf.get("model_router"), dict) else {}
    # WeChat auto-replies are deliberately cost-bound to MiniMax-M3. Never
    # append the global base fallback (which may be a GPT-5.x model) here.
    if (
        route_kind == "tool"
        and str(route_key or "").strip().lower() == "reply"
        and default_model.lower() == "minimax-m3"
    ):
        if isinstance(router, dict) and bool(router.get("enabled")):
            candidates, rk = _route_pool(conf, route_kind=route_kind, route_key=route_key)
            ordered = _dynamic_rank_channels(candidates, route_key=f"{route_kind}:{rk}", conf=conf)
            m3_targets: list[Dict[str, Any]] = []
            seen: set[tuple[str | None, str, str]] = set()
            for channel in ordered:
                if str(channel.get("model") or "").strip().lower() != "minimax-m3":
                    continue
                target = _to_target_dict(base_api_url, base_api_key, "MiniMax-M3", channel)
                key = (target.get("channel_id"), str(target.get("api_url") or ""), str(target.get("model") or ""))
                if key not in seen:
                    seen.add(key)
                    m3_targets.append(target)
            if m3_targets:
                return m3_targets
        return [default_target] if default_model.lower() == "minimax-m3" else []

    # WeChat/message摘要要求“持续刷新”优先于“多路由试错”。
    # 对 messages 链路默认只保留稳定通道池，避免被已知慢/空响应/JSON异常通道拖住几分钟。
    if route_kind == "tool" and str(route_key or "").strip().lower() == "messages":
        stable_only = conf.get("tool_messages_stable_only")
        if stable_only is None:
            stable_only = True
        if bool(stable_only):
            if isinstance(router, dict) and bool(router.get("enabled")):
                preferred_ids = conf.get("tool_messages_stable_channels")
                if isinstance(preferred_ids, str):
                    preferred_ids = [x.strip() for x in preferred_ids.split(",") if x.strip()]
                if not isinstance(preferred_ids, list) or not preferred_ids:
                    preferred_ids = [
                        "dasheng-tool-minimax-m3",
                        "dasheng-tool-qwen3-8b",
                        "dasheng-tool-qwen35-4b",
                        "tool-sf-qwen8b",
                        "tool-sf-glm9b",
                    ]
                channels = router.get("tool_channels") if isinstance(router.get("tool_channels"), list) else []
                route_map = router.get("tool_route_channels") if isinstance(router.get("tool_route_channels"), dict) else {}
                route_ids = route_map.get("messages") or route_map.get("default") or []
                if isinstance(route_ids, str):
                    route_ids = [x.strip() for x in route_ids.split(",") if x.strip()]
                if not isinstance(route_ids, list):
                    route_ids = []
                enabled_by_id = {
                    str(c.get("id") or "").strip(): c
                    for c in channels
                    if isinstance(c, dict) and c.get("enabled") and str(c.get("model") or "").strip()
                }
                ordered_ids: list[str] = []
                for cid in [str(x).strip() for x in route_ids if str(x).strip()]:
                    if cid in preferred_ids and cid in enabled_by_id and cid not in ordered_ids:
                        ordered_ids.append(cid)
                for cid in [str(x).strip() for x in preferred_ids if str(x).strip()]:
                    if cid in enabled_by_id and cid not in ordered_ids:
                        ordered_ids.append(cid)
                # 如果稳定硅基通道鉴权失败，允许显式配置了独立 api_key 的工具通道兜底；
                # 不把无 key 的其它外部通道加入，避免复用错误的基础 key。
                for cid, channel in enabled_by_id.items():
                    if cid in ordered_ids:
                        continue
                    if str(channel.get("api_key") or "").strip():
                        ordered_ids.append(cid)
                stable_targets: list[Dict[str, Any]] = []
                seen: set[tuple[str | None, str, str]] = set()
                for cid in ordered_ids:
                    t = _to_target_dict(base_api_url, base_api_key, default_model, enabled_by_id.get(cid))
                    key = (t.get("channel_id"), str(t.get("api_url") or ""), str(t.get("model") or ""))
                    if key in seen:
                        continue
                    seen.add(key)
                    stable_targets.append(t)
                base_key = (None, str(fallback_target.get("api_url") or ""), str(fallback_target.get("model") or ""))
                if base_key not in seen:
                    stable_targets.append(fallback_target)
                if stable_targets:
                    return stable_targets
            return [default_target]

    if not router or not bool(router.get("enabled")):
        return [default_target]

    prefer_router = bool(router.get("prefer_router", True))
    # Keep strict override behavior when user chooses not to prioritize router.
    if model_override and not prefer_router:
        return [default_target]

    candidates, rk = _route_pool(conf, route_kind=route_kind, route_key=route_key)
    ordered = _dynamic_rank_channels(candidates, route_key=f"{route_kind}:{rk}", conf=conf)
    if not ordered:
        return [default_target]

    targets: list[Dict[str, Any]] = []
    seen: set[tuple[str | None, str, str]] = set()
    for c in ordered:
        t = _to_target_dict(base_api_url, base_api_key, default_model, c)
        key = (t.get("channel_id"), str(t.get("api_url") or ""), str(t.get("model") or ""))
        if key in seen:
            continue
        seen.add(key)
        targets.append(t)

    # Always keep base/fallback model as final fallback to avoid full outage when all channels fail.
    base_key = (None, str(fallback_target.get("api_url") or ""), str(fallback_target.get("model") or ""))
    if base_key not in seen:
        targets.append(fallback_target)
    return targets


def resolve_chat_target(
    conf: Dict[str, Any],
    *,
    route_kind: str,
    route_key: str | None,
    model_override: str | None,
) -> Dict[str, Any]:
    """Resolve current primary target (backward compatible helper)."""
    targets = resolve_chat_targets(
        conf,
        route_kind=route_kind,
        route_key=route_key,
        model_override=model_override,
    )
    if route_kind == "tool":
        fallback_model = str(model_override or conf.get("tool_model") or conf.get("model") or "").strip()
    elif route_kind == "mid":
        fallback_model = str(model_override or conf.get("tool_model_messages") or conf.get("tool_model") or conf.get("model") or "").strip()
    else:
        fallback_model = str(model_override or conf.get("model") or "").strip()
    return targets[0] if targets else {
        "model": fallback_model,
        "api_url": str(conf.get("api_url") or "https://api.siliconflow.cn/v1").strip(),
        "api_key": str(conf.get("api_key") or "").strip(),
        "channel_id": None,
    }


def get_router_runtime_stats() -> Dict[str, Dict[str, Any]]:
    """Return current in-process router runtime metrics for observability."""
    now = _now_ts()
    with _MODEL_ROUTER_LOCK:
        out: Dict[str, Dict[str, Any]] = {}
        for k, v in _MODEL_ROUTER_STATS.items():
            item = dict(v)
            try:
                until = float(item.get("cooldown_until") or 0.0)
            except Exception:
                until = 0.0
            item["cooldown_remaining_sec"] = max(0, int(until - now)) if until > now else 0
            out[k] = item
        return out


def reset_router_runtime_stats(*, channel_id: str | None = None) -> None:
    """Reset in-process router runtime stats, optionally for a single channel."""
    target = str(channel_id or "").strip()
    with _MODEL_ROUTER_LOCK:
        if target:
            _MODEL_ROUTER_STATS.pop(target, None)
        else:
            _MODEL_ROUTER_STATS.clear()
    _persist_router_metrics(force=True)


def _post_with_backoff(
    url: str,
    headers: dict,
    payload: dict,
    *,
    timeout: int = 180,
    attempts: int = 5,
    backoff: float = 0.6,
) -> requests.Response:
    """POST with basic exponential backoff on 429/5xx.

    This reduces flakiness under provider TPM/RPM limits while preserving caller simplicity.
    """
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            # Happy path
            if resp.status_code < 400:
                return resp
            # Backoff on 429 or 5xx
            if resp.status_code in (429, 500, 502, 503, 504):
                # Honor Retry-After if present
                ra = resp.headers.get("Retry-After")
                try:
                    wait = float(ra) if ra is not None else None
                except Exception:
                    wait = None
                # Base backoff with jitter
                if wait is None:
                    wait = backoff * (2 ** (attempt - 1)) + random.uniform(0.05, 0.25)
                time.sleep(min(wait, 8.0))
                last_exc = requests.HTTPError(f"status={resp.status_code}")
                continue
            # Other client errors: bubble up immediately
            resp.raise_for_status()
            return resp  # pragma: no cover
        except requests.RequestException as e:  # network errors -> retry
            last_exc = e
            time.sleep(backoff * (2 ** (attempt - 1)) + random.uniform(0.05, 0.25))
            continue
    # Exhausted retries
    if last_exc:
        raise last_exc
    raise RuntimeError("LLM request failed after retries")


def _chat_completions_url(api_url: str) -> str:
    """Normalize an OpenAI-compatible base URL or full endpoint."""
    value = str(api_url or "").strip().rstrip("/")
    if not value:
        value = "https://api.siliconflow.cn/v1"
    if value.endswith("/chat/completions"):
        return value
    if value.endswith("/v1"):
        return value + "/chat/completions"
    return value + "/v1/chat/completions"


def _prepare_chat_messages(messages: list[dict], *, model: str) -> list[dict]:
    """Keep oversized MiniMax requests within a reliable input budget."""
    if "minimax-m3" not in str(model or "").strip().lower():
        return messages

    limit = 48_000
    marker = "\n\n[上下文已截断，优先保留开头与结尾]\n\n"
    prepared: list[dict] = []
    for message in messages:
        item = dict(message) if isinstance(message, dict) else {"role": "user", "content": str(message)}
        content = item.get("content")
        if item.get("role") != "system" and isinstance(content, str) and len(content) > limit:
            available = max(0, limit - len(marker))
            head_size = int(available * 0.72)
            tail_size = available - head_size
            item["content"] = content[:head_size] + marker + content[-tail_size:]
        prepared.append(item)
    return prepared


def _effective_max_tokens(model: str, configured: int) -> int:
    value = max(1, int(configured or 4000))
    if "minimax-m3" in str(model or "").strip().lower():
        return min(value, 1800)
    return value


def _model_payload_extras(model: str) -> dict[str, Any]:
    return {}


def siliconflow_chat(
    messages: list[dict],
    temperature: float | None = 0.3,
    model_override: str | None = None,
    *,
    force_json: bool = False,
    route_kind: str = "main",
    route_key: str | None = None,
    return_metadata: bool = False,
) -> str | Dict[str, Any]:
    """Call SiliconFlow once; auto‑retry with gentle backoff on rate limits.
    If it still fails, caller should handle local fallback.
    """
    conf = load_ai_config()
    targets = resolve_chat_targets(
        conf,
        route_kind=route_kind,
        route_key=route_key,
        model_override=model_override,
    )

    # resolve runtime params from config
    max_tokens = int(conf.get("max_tokens") or 4000)
    temp = float(temperature if temperature is not None else conf.get("model_temperature") or 0.7)
    errors: list[str] = []
    for idx, target in enumerate(targets):
        api_key = str(target.get("api_key") or "").strip()
        api_url = str(target.get("api_url") or "https://api.siliconflow.cn/v1").strip()
        model = str(target.get("model") or conf.get("model") or "Qwen/Qwen3.5-4B").strip()
        channel_id = str(target.get("channel_id") or "").strip() or "base"
        channel_dict: dict | None = None
        if channel_id != "base":
            router = conf.get("model_router") if isinstance(conf.get("model_router"), dict) else {}
            channels = (
                router.get("tool_channels")
                if route_kind == "tool"
                else (
                    router.get("mid_channels")
                    if route_kind == "mid"
                    else router.get("main_channels")
                )
            )
            if isinstance(channels, list):
                for ch in channels:
                    if isinstance(ch, dict) and str(ch.get("id") or "").strip() == channel_id:
                        channel_dict = ch
                        break

        if not api_key:
            errors.append(f"[{idx+1}/{len(targets)} {channel_id}] missing_api_key")
            continue
        if _is_bad_api_key(api_key):
            errors.append(f"[{idx+1}/{len(targets)} {channel_id}] bad_api_key_cached")
            continue

        url = _chat_completions_url(api_url)
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        if "openrouter.ai" in api_url:
            headers.setdefault("HTTP-Referer", "https://localhost")
            headers.setdefault("X-Title", "Dr.Lemon Information Aggregation AI")
        prepared_messages = _prepare_chat_messages(messages, model=model)
        payload = {
            "model": model,
            "messages": prepared_messages,
            "temperature": temp,
            "max_tokens": _effective_max_tokens(model, max_tokens),
            "stream": False,
        }
        payload.update(_model_payload_extras(model))
        if force_json:
            try:
                payload["response_format"] = {"type": "json_object"}
            except Exception:
                pass
        attempt_start = time.perf_counter()
        if channel_dict is not None:
            _router_mark_inflight(channel_id, +1)
        try:
            with _LLM_SEMAPHORE:
                retry_attempts = 5
                retry_backoff = 0.6
                try:
                    if route_kind == "tool" and str(route_key or "").strip().lower() == "messages":
                        http_timeout = int(conf.get("tool_messages_timeout") or 25)
                    else:
                        http_timeout = int(conf.get("http_timeout") or 90)
                except Exception:
                    http_timeout = 25 if route_kind == "tool" and str(route_key or "").strip().lower() == "messages" else 90
                if route_kind == "tool" and str(route_key or "").strip().lower() == "messages":
                    retry_attempts = int(conf.get("tool_messages_retry_attempts") or 1)
                    retry_backoff = float(conf.get("tool_messages_retry_backoff") or 0.35)
                resp = _post_with_backoff(
                    url,
                    headers,
                    payload,
                    timeout=http_timeout,
                    attempts=max(1, retry_attempts),
                    backoff=max(0.05, retry_backoff),
                )
            resp.raise_for_status()
            data = resp.json()
            raw_content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            content = _normalize_model_content(raw_content, model=model)
            if content:
                latency_ms = max(1.0, (time.perf_counter() - attempt_start) * 1000.0)
                if channel_dict is not None:
                    _router_mark_result(channel_dict, ok=True, latency_ms=latency_ms, conf=conf)
                _append_router_trace(
                    route_kind=route_kind,
                    route_key=route_key,
                    channel_id=channel_id,
                    model=model,
                    api_url=api_url,
                    ok=True,
                    latency_ms=latency_ms,
                    reason="ok",
                )
                if return_metadata:
                    return {
                        "text": content,
                        "execution": {
                            "route_kind": route_kind,
                            "route_key": str(route_key or "default"),
                            "final_model": model,
                            "provider": _safe_domain(api_url),
                            "channel_id": channel_id or None,
                            "latency_ms": round(float(latency_ms), 1),
                        },
                    }
                return content
            latency_ms = max(1.0, (time.perf_counter() - attempt_start) * 1000.0)
            if channel_dict is not None:
                _router_mark_result(
                    channel_dict,
                    ok=False,
                    latency_ms=latency_ms,
                    err="empty_content",
                    conf=conf,
                )
            _append_router_trace(
                route_kind=route_kind,
                route_key=route_key,
                channel_id=channel_id,
                model=model,
                api_url=api_url,
                ok=False,
                latency_ms=latency_ms,
                reason="empty_content",
            )
            errors.append(f"[{idx+1}/{len(targets)} {channel_id}] empty_content model={model}")
        except Exception as exc:
            latency_ms = max(1.0, (time.perf_counter() - attempt_start) * 1000.0)
            # Fast-fail cache: if key is unauthorized/disabled once, skip same key for a while.
            try:
                auth_error = False
                if isinstance(exc, requests.HTTPError):
                    resp = getattr(exc, "response", None)
                    sc = int(resp.status_code) if resp is not None else 0
                    body = ""
                    try:
                        body = str(resp.text or "")[:240].lower() if resp is not None else ""
                    except Exception:
                        body = ""
                    if sc in (401, 403):
                        auth_error = True
                    elif any(k in body for k in ("invalid api key", "api key is disabled", "unauthorized")):
                        auth_error = True
                else:
                    low = str(exc).lower()
                    if "invalid api key" in low or "api key is disabled" in low or "unauthorized" in low:
                        auth_error = True
                if auth_error:
                    _mark_bad_api_key(api_key)
            except Exception:
                pass
            if channel_dict is not None:
                _router_mark_result(
                    channel_dict,
                    ok=False,
                    latency_ms=latency_ms,
                    err=str(exc),
                    conf=conf,
                )
            _append_router_trace(
                route_kind=route_kind,
                route_key=route_key,
                channel_id=channel_id,
                model=model,
                api_url=api_url,
                ok=False,
                latency_ms=latency_ms,
                reason=f"{type(exc).__name__}: {str(exc)[:160]}",
            )
            errors.append(f"[{idx+1}/{len(targets)} {channel_id}] {type(exc).__name__}: {str(exc)[:220]}")
            continue
        finally:
            if channel_dict is not None:
                _router_mark_inflight(channel_id, -1)

    if not errors:
        raise RuntimeError("LLM request failed: no route target available")
    raise RuntimeError("LLM request failed across all routes: " + " | ".join(errors))


def siliconflow_tool_chat(
    messages: list[dict],
    temperature: float = 0.2,
    model_override: str | None = None,
    *,
    route_key: str | None = None,
) -> str:
    conf = load_ai_config()
    tool_model = model_override or conf.get("tool_model") or "Qwen/Qwen3-8B"
    # Tool calls expect strict JSON; request JSON object formatting when supported
    return siliconflow_chat(
        messages,
        temperature=temperature,
        model_override=tool_model,
        force_json=True,
        route_kind="tool",
        route_key=route_key,
    )


def siliconflow_chat_stream(messages: list, temperature: float = 0.7, model_override: str = None) -> str:
    """硅基流动流式对话接口"""
    conf = load_ai_config()
    api_key = conf.get("siliconflow_api_key")
    if not api_key:
        raise ValueError("SiliconFlow API key not configured")
    
    model = model_override or conf.get("model") or "Qwen/Qwen3.5-4B"
    
    url = "https://api.siliconflow.cn/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": True
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, stream=True)
        response.raise_for_status()
        
        for line in response.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    data_str = line[6:]  # 去掉 'data: ' 前缀
                    if data_str.strip() == '[DONE]':
                        break
                    try:
                        data_obj = json.loads(data_str)
                        if 'choices' in data_obj and len(data_obj['choices']) > 0:
                            delta = data_obj['choices'][0].get('delta', {})
                            if 'content' in delta:
                                yield delta['content']
                    except json.JSONDecodeError:
                        continue
    except requests.RequestException as e:
        raise RuntimeError(f"SiliconFlow API request failed: {e}")
