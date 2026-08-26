#!/usr/bin/env python3
"""公众号标题候选生成器（wechat-title-generator v2 契约的脚本化落地）。

用法：
    python scripts/generate_title_candidates.py --article <md> --core-judgment <一句话判断> \
        --count 6 --account slot-1

输出：title_candidates.json（多候选+推荐+适用场景标注），供 draft/draft_review 审核选择。
定位：draft 环节产物——文章成稿后生成多个题目供审核（用户定调 2026-08-21）。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_stage3_draft import request_ai_markdown  # noqa: E402

SYSTEM = """你是一位顶级公众号标题专家。你为已成稿的文章生成标题候选。

硬性规范：
1. 每个标题独立成立，不依赖副标题补充
2. 长度 12-28 字（含标点）；数字与对比优先（具体>抽象）
3. 覆盖不同钩子类型（标注在 style 字段）：悬念/数字/反常识/利益承诺/身份代入/时效热点
4. 不做标题党：标题承诺的内容正文必须兑现；禁止夸张恐吓与虚假数字
5. 至少 1 个标题与目标账号的定位语气强匹配
6. 输出严格 JSON（不要 markdown 代码块、不要解释）：
   {"candidates": [{"title": "...", "style": "钩子类型", "rationale": "一句话理由"}, ...],
    "recommended": "最推荐的标题", "recommend_reason": "推荐理由"}"""

PROMPT_TMPL = """生成公众号标题候选。

文章标题（现用）：{title}
核心判断：{judgment}
目标读者：{audience}
账号定位：{account_positioning}
钩子偏好：{hooks}

正文（截取）：
---
{body}
---

输出 {count} 个候选，JSON 格式。"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate WeChat title candidates")
    parser.add_argument("--article", required=True, help="成稿 md 路径")
    parser.add_argument("--core-judgment", required=True)
    parser.add_argument("--count", type=int, default=6)
    parser.add_argument("--account", default="slot-1", help="账号 slot（读 dna/account_dna.yaml 定位语气）")
    parser.add_argument("--audience", default="个人投资者/财经内容读者")
    parser.add_argument("--out", help="输出 json 路径（默认 <article目录>/title_candidates.json）")
    args = parser.parse_args()

    article = Path(args.article).expanduser().resolve()
    md = article.read_text(encoding="utf-8")
    title = md.split("\n", 1)[0].lstrip("# ").strip()
    body = md[:6000]

    positioning = "通用财经号"
    try:
        import yaml

        dna_doc = yaml.safe_load((ROOT / "dna" / "account_dna.yaml").read_text(encoding="utf-8"))
        acct = next((a for a in dna_doc.get("accounts", []) if a.get("account_id") == args.account), None)
        if acct:
            positioning = f"{acct['name']}（{acct['positioning']}），语气：{acct['article_tone']}"
    except Exception:  # noqa: BLE001
        pass

    prompt = PROMPT_TMPL.format(
        title=title, judgment=args.core_judgment, audience=args.audience,
        account_positioning=positioning, count=args.count,
        hooks="悬念/数字/反常识/利益承诺/身份代入/时效热点（覆盖至少 4 种）",
        body=body,
    )
    raw = request_ai_markdown(SYSTEM, prompt, max_tokens=3000).strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # 容错：截取第一个 { 到最后一个 }
        s, e = raw.find("{"), raw.rfind("}")
        data = json.loads(raw[s : e + 1])

    out_path = Path(args.out).expanduser().resolve() if args.out else article.parent / "title_candidates.json"
    payload = {
        "schema_version": "newma.draft_title_candidates.v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_article": str(article),
        "current_title": title,
        "account": args.account,
        "account_positioning": positioning,
        **data,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    n = len(payload.get("candidates", []))
    print(f"标题候选 {n} 个 → {out_path}")
    print(f"推荐：{payload.get('recommended', '')}")
    for c in payload.get("candidates", [])[:8]:
        print(f"  [{c.get('style', '?')}] {c.get('title', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
