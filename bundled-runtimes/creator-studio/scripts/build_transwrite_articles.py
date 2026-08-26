#!/usr/bin/env python3
"""转写文章生产器（article_build v2）：DNA 档案 → LLM 规范重写 → HTML 排版包。

用法：
    python scripts/build_transwrite_articles.py --run-id creator-ffcdfbbb1615 --topic T06 \
        --draft <骨架稿.md> --title <标题> --out-dir <04_转写/articles/T06>

流程：
    1. DNA 档案：core/dna_engine.py 选型（风格/结构），产出 article_style_dna 记录
    2. 说明图意图：按章节产出 illustration_intents.json（风格槽位已填，供会话 ImageGen 执行）
    3. LLM 规范重写：注入转写规范（≥5000字/名言/前言/引言/章节/水印/话题）+ 骨架稿 + 事实数据
    4. HTML 排版 v2：品牌样式 + 文末水印（媒体名+话题标签）

数据图与网图由会话侧补充（脚本只管文字链路），见 plan P3。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from build_stage3_draft import request_ai_markdown  # noqa: E402
from core.dna_engine import DNAEngine  # noqa: E402

STYLE_FILE = ROOT / "configs" / "image_generation" / "explain_illustration_styles.yaml"

REWRITE_SYSTEM = """你是一位顶级财经公众号主笔。你的任务是把一篇研究骨架稿改写为可直接发布的正式长文。

硬性规范（缺一不可）：
1. 正文至少达到用户给定的中文字符目标；宁可充分展开机制、反驳和情景推演，也不要压缩成摘要。
2. 保留骨架稿里的核心事实、反驳、逻辑链、情景推演和结论，但删除所有“待补”、制作备注、图片占位符、图表占位符与内部工作指令。
3. 数据诚实：只能使用事实包中已核验的数据。无法核验的数字不得保留；媒体独家口径必须写明“据××报道”，不能伪装成审计事实。
4. 结构完整：强钩子开篇 → 前言/引言 → H2 正文章节与 H3 小节 → 反方观点和证据边界 → 可验证的未来路径 → 结语。不要为了形式生造名人名言；只有事实包提供可核验原文时才引用。
5. 每 300—500 字至少出现一个信息锚点：数据、案例、表格、反驳、推演问题或阶段结论。段落控制在 1—3 句。
6. 写作口吻严格服从账号 DNA。语言要自然、有作者判断，禁止“不是……而是……”“先把……说清楚”“值得注意的是”“总而言之”“这意味着”“本质上”等模板化 AI 句式。
7. 文章中至少放入 2 个 Markdown 数据表；所有外部事实在首次出现时用 Markdown 链接标注来源，文末另列“资料与引用”。
8. 排版标记：最核心的 4—8 个结论用 `<strong style="color:#C00000;">结论</strong>`；重要数据或观察用 `<strong style="color:#1F4E79;">信息</strong>`；直接引用用 `> *引文*`。不要滥用颜色。
9. 不要输出任何图片占位。真实图片和数据图由后续资产步骤插入。
10. 文末固定两段（逐字保留模板）：
   {{WATERMARK}}
   {{HASHTAGS}}
11. 输出纯 Markdown，不要代码围栏，不要解释生成过程。"""


def build_rewrite_prompt(
    title: str,
    draft_md: str,
    facts: str,
    dna: dict,
    account_dna: dict | None,
    target_cjk: int,
) -> str:
    account_block = json.dumps(account_dna or {}, ensure_ascii=False, indent=2)
    return f"""转写目标文章。

标题：{title}
中文字符目标：不少于 {target_cjk} 字，建议写到 {target_cjk + 1000}—{target_cjk + 2500} 字。

DNA 档案（本次转写的风格与结构约束）：
- 风格 DNA：{dna.get("style_dna")}（按该风格的语言气质行文）
- 结构 DNA：{dna.get("structure_dna")}（按该结构组织章节）
- 账号完整 DNA：
{account_block}
- 平台：微信公众号

事实与证据包（数字不得擅自修改；注意 verified/reported/analysis 的证据等级）：
{facts}

骨架稿（内容素材，可重组但核心论点与证据不得丢失）：
---
{draft_md}
---

水印模板（文末逐字保留）：
{{WATERMARK}}

话题模板（文末逐字保留，占位符待填）：
{{HASHTAGS}}

现在输出完整成稿。"""


def count_cjk(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", text or ""))


def find_quality_issues(text: str, target_cjk: int) -> list[str]:
    issues: list[str] = []
    cjk = count_cjk(text)
    if cjk < target_cjk:
        issues.append(f"中文字符不足：{cjk} < {target_cjk}")
    placeholder_patterns = [
        r"待补", r"\{\{(?:image|chart|ref|link):", r"图片占位", r"图表占位", r"具体数据待",
    ]
    for pattern in placeholder_patterns:
        if re.search(pattern, text, flags=re.I):
            issues.append(f"残留占位：{pattern}")
    ai_patterns = [r"不是[^。！？\n]{0,40}而是", r"先把[^。！？\n]{0,30}说清楚", r"值得注意的是", r"总而言之"]
    for pattern in ai_patterns:
        if re.search(pattern, text):
            issues.append(f"AI 句式：{pattern}")
    if text.count("<strong style=\"color:#C00000;\">") < 3:
        issues.append("红色核心结论不足 3 处")
    if text.count("<strong style=\"color:#1F4E79;\">") < 3:
        issues.append("蓝色重要信息不足 3 处")
    if text.count("|") < 12:
        issues.append("数据表不足 2 个")
    return issues


def build_claim_ledger(facts_path: Path, *, run_id: str, topic_id: str, title: str) -> dict:
    try:
        payload = json.loads(facts_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        payload = {"raw_facts": facts_path.read_text(encoding="utf-8")}
    return {
        "schema_version": "newma.transwrite.claim_evidence_ledger.v1",
        "run_id": run_id,
        "topic_id": topic_id,
        "title": title,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "evidence_policy": {
            "verified": "可直接作为事实陈述",
            "reported": "必须注明媒体或机构报道口径",
            "analysis": "属于推理判断，不得写成已发生事实",
            "unsupported": "不得进入成稿",
        },
        "sources": payload.get("sources", []),
        "claims": payload.get("claims", []),
        "data_tables": payload.get("data_tables", []),
        "evidence_boundaries": payload.get("evidence_boundaries", []),
    }


def md_to_html_v2(md: str, title: str, watermark: str, hashtags: str) -> str:
    import html as html_lib
    import re

    md = md.replace("{{WATERMARK}}", watermark).replace("{{HASHTAGS}}", hashtags)
    lines = md.split("\n")
    out = []
    in_table = False
    in_quote = False
    for line in lines:
        s = line.strip()
        if s.startswith("![") and "](" in s:
            alt, src = s[2 : s.index("](")], s[s.index("](") + 2 : -1]
            out.append(f'<figure><img src="{src}" alt="{html_lib.escape(alt)}"><figcaption>{html_lib.escape(alt)}</figcaption></figure>')
            continue
        if s.startswith("> "):
            if not in_quote:
                out.append('<blockquote>')
                in_quote = True
            out.append(f"<p>{html_lib.escape(s[2:])}</p>")
            continue
        if in_quote:
            out.append("</blockquote>")
            in_quote = False
        if s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(re.fullmatch(r":?-+:?", c) for c in cells):
                continue
            if not in_table:
                out.append("<table><tbody>")
                in_table = True
            out.append("<tr>" + "".join(f"<td>{html_lib.escape(c)}</td>" for c in cells) + "</tr>")
            continue
        if in_table:
            out.append("</tbody></table>")
            in_table = False
        if s.startswith("# "):
            out.append(f"<h1>{html_lib.escape(s[2:])}</h1>")
        elif s.startswith("## "):
            out.append(f"<h2>{html_lib.escape(s[3:])}</h2>")
        elif s.startswith("### "):
            out.append(f"<h3>{html_lib.escape(s[4:])}</h3>")
        elif s.startswith("{{image:"):
            out.append(f'<div class="img-slot">{html_lib.escape(s)}</div>')
        elif not s:
            continue
        else:
            parts = re.split(r"\*\*(.+?)\*\*", html_lib.escape(s))
            out.append("<p>" + "".join(p if i % 2 == 0 else f"<strong>{p}</strong>" for i, p in enumerate(parts)) + "</p>")
    if in_table:
        out.append("</tbody></table>")
    if in_quote:
        out.append("</blockquote>")
    body = "\n".join(out)
    return f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8"><title>{html_lib.escape(title)}</title>
<style>
body{{max-width:677px;margin:0 auto;padding:24px 16px;font-family:-apple-system,"PingFang SC","Hiragino Sans GB",sans-serif;line-height:1.75;color:#2b2b2b;background:#fff}}
h1{{font-size:22px;font-weight:600;text-align:center;margin:16px 0 8px}}
h2{{font-size:17px;font-weight:600;margin:28px 0 12px;padding-left:10px;border-left:4px solid #C89A5A;color:#5a3e1b}}
h3{{font-size:15px;font-weight:600;margin:20px 0 8px;color:#3d3d3d}}
p{{font-size:15px;margin:14px 0;text-align:justify}}
blockquote{{margin:22px 0;padding:12px 16px;background:#faf7f0;border-left:3px solid #C89A5A;border-radius:0 6px 6px 0}}
blockquote p{{font-size:14px;color:#6b5d3f;margin:6px 0;font-style:normal}}
table{{border-collapse:collapse;width:100%;margin:18px 0;font-size:13px}}
td{{border:1px solid #e8e2d5;padding:8px 10px}}
tr td:first-child{{font-weight:600;background:#faf7f0}}
figure{{text-align:center;margin:20px 0}}
img{{max-width:100%;border-radius:4px}}
figcaption{{font-size:12px;color:#999;margin-top:6px}}
.img-slot{{padding:10px 14px;margin:16px 0;background:#f7f7f4;border:1px dashed #ccc;border-radius:6px;font-size:13px;color:#888}}
.watermark{{margin-top:36px;padding-top:16px;border-top:1px solid #eee;font-size:12px;color:#999;text-align:center;line-height:1.9}}
.hashtags{{font-size:13px;color:#C89A5A;text-align:center;word-spacing:8px}}
strong{{color:#8a5a00}}
</style></head><body>
{body}
</body></html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Build transwrite article v2 (DNA + rewrite + HTML)")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--topic", required=True, help="e.g. T06")
    parser.add_argument("--draft", required=True, help="骨架稿 md 路径")
    parser.add_argument("--title", required=True)
    parser.add_argument("--facts-file", required=True, help="事实清单 md/json 路径")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--media-name", default="默丘利Lab")
    parser.add_argument("--account", help="账号 slot（slot-1/2/3）：按 dna/account_dna.yaml 拉取账号 DNA（角色系统+插图风格+语气）")
    parser.add_argument("--hashtags", default="#投资市场 #宏观 #美债")
    parser.add_argument("--illustration-intents", help="说明图意图 json（可选，缺省用内置默认）")
    parser.add_argument("--target-cjk", type=int, default=6500)
    args = parser.parse_args()

    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now().isoformat(timespec="seconds")

    # 账号 DNA 拉取（角色系统+插图风格按账号路由，dna/account_dna.yaml 单一事实源）
    account_dna = None
    if args.account:
        import yaml
        dna_doc = yaml.safe_load((ROOT / "dna" / "account_dna.yaml").read_text(encoding="utf-8"))
        account_dna = next((a for a in dna_doc.get("accounts", []) if a.get("account_id") == args.account), None)
        if account_dna is None:
            print(f"WARN: account_dna.yaml 无 {args.account}，退回默认风格")
        else:
            print(f"[0/4] 账号 DNA：{account_dna['name']}（角色={account_dna['character_system']['primary'][:20]}…风格={account_dna['illustration_style']['visual_language'][:20]}…）")

    draft_md = Path(args.draft).read_text(encoding="utf-8")
    facts_path = Path(args.facts_file).expanduser().resolve()
    facts = facts_path.read_text(encoding="utf-8")

    # 1) DNA 档案
    engine = DNAEngine()
    style = engine.select_style(topic_type="data_analysis", audience="retail_investor", platform="wechat")
    struct = engine.select_structure(content_type="deep_dive", word_count=5200)
    dna = {"style_dna": style, "structure_dna": struct}
    (out_dir / "article_style_dna.json").write_text(json.dumps({
        "schema_version": "newma.transwrite.article_style_dna.v1",
        "run_id": args.run_id, "topic_id": args.topic, "generated_at": now,
        "engine": "core/dna_engine.py + dna/account_dna.yaml",
        "account_dna": account_dna,
        "selections": [dna | {"topic_id": args.topic, "title": args.title}],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[1/4] DNA 档案：风格={style} 结构={struct}")

    # 2) 说明图意图（默认内置；可外部传入）
    if args.illustration_intents:
        intents = json.loads(Path(args.illustration_intents).read_text(encoding="utf-8"))
    else:
        intents = {
            "note": "未提供意图清单——会话侧按章节补充（按账号 DNA 风格生成，见 configs/image_generation/explain_illustration_styles.yaml account_styles）",
            "intents": [],
            "account_dna": {
                "account_id": account_dna.get("account_id"),
                "name": account_dna.get("name"),
                "character": account_dna.get("character_system", {}).get("primary"),
                "style": account_dna.get("illustration_style", {}).get("visual_language"),
                "layout": account_dna.get("illustration_style", {}).get("layout"),
            } if account_dna else None,
        }
    (out_dir / "illustration_intents.json").write_text(json.dumps(intents, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("[2/4] 说明图意图已写出")

    # 3) LLM 规范重写
    prompt = build_rewrite_prompt(args.title, draft_md, facts, dna, account_dna, args.target_cjk)
    rewritten = request_ai_markdown(REWRITE_SYSTEM, prompt, max_tokens=24000).strip()
    rewritten = rewritten.removeprefix("```markdown").removeprefix("```md").removeprefix("```").removesuffix("```").strip()
    issues = find_quality_issues(rewritten, args.target_cjk)
    if issues:
        revision_prompt = f"""请修订下面的公众号文章，只输出修订后的完整 Markdown。

必须解决的问题：
- """ + "\n- ".join(issues) + f"""

修订规则：保留已有事实、来源链接、反驳、推演和结论；不得新增事实包之外的数字；彻底删除无法核验的占位语句；把篇幅补足到不少于 {args.target_cjk} 个中文字符。

原稿：
---
{rewritten}
---"""
        rewritten = request_ai_markdown(REWRITE_SYSTEM, revision_prompt, max_tokens=28000).strip()
        rewritten = rewritten.removeprefix("```markdown").removeprefix("```md").removeprefix("```").removesuffix("```").strip()
        issues = find_quality_issues(rewritten, args.target_cjk)
    cjk = count_cjk(rewritten)
    print(f"[3/4] LLM 重写完成：{len(rewritten)} 字符（中文 {cjk} 字）")
    (out_dir / "article_v2.md").write_text(rewritten + "\n", encoding="utf-8")

    ledger = build_claim_ledger(facts_path, run_id=args.run_id, topic_id=args.topic, title=args.title)
    (out_dir / "claim_evidence_ledger.json").write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # 4) HTML 排版 v2
    watermark = f"— {args.media_name} · 原创内容 转载请注明出处 —"
    html = md_to_html_v2(rewritten, args.title, watermark, args.hashtags)
    (out_dir / "article_v2.html").write_text(html, encoding="utf-8")
    print(f"[4/4] HTML v2 排版完成 → {out_dir / 'article_v2.html'}")

    summary = {
        "schema_version": "newma.transwrite.article_v2_summary.v1",
        "run_id": args.run_id, "topic_id": args.topic, "generated_at": now,
        "title": args.title, "media_name": args.media_name, "hashtags": args.hashtags,
        "chars": len(rewritten), "cjk_chars": cjk,
        "word_count_ok": cjk >= 5000,
        "target_cjk": args.target_cjk,
        "quality_issues": issues,
        "outputs": {"markdown": str(out_dir / "article_v2.md"), "html": str(out_dir / "article_v2.html")},
    }
    (out_dir / "article_v2_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"summary: cjk={cjk} | ≥5000 达标: {cjk >= 5000}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
