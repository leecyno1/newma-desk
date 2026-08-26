#!/usr/bin/env python3
"""小红书探索页热点采集 — Cookie 认证
用法:
  python3 xhs_hot.py --cookies cookies.json --limit 20
Cookie 文件格式: JSON 数组，从浏览器 DevTools 导出
  或简化为: {"a1": "...", "web_session": "..."}
"""
import json, sys, subprocess, argparse
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.error import URLError
import re

TZ = timezone(timedelta(hours=8))
XHS_INDEX = "https://www.xiaohongshu.com"
XHS_API = "https://edith.xiaohongshu.com"


def load_cookies(path: str) -> str:
    """从 JSON 文件加载 Cookie 字符串"""
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, list):
        # 浏览器导出的标准格式: [{"name": "a1", "value": "..."}, ...]
        return "; ".join(f"{c['name']}={c['value']}" for c in data if "name" in c)
    elif isinstance(data, dict):
        # 简化格式: {"a1": "...", "web_session": "..."}
        return "; ".join(f"{k}={v}" for k, v in data.items())
    else:
        raise ValueError("cookies 格式错误: 需要 JSON 数组或对象")


def fetch_explore_via_page(cookies_str: str, limit: int) -> dict:
    """从 explore 页面提取 __INITIAL_STATE__ 中的笔记"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Cookie": cookies_str,
        "Referer": XHS_INDEX,
    }
    try:
        req = Request(f"{XHS_INDEX}/explore", headers=headers)
        resp = urlopen(req, timeout=15)
        html = resp.read().decode("utf-8", errors="replace")
    except URLError as e:
        return {"error": f"请求 explore 页失败: {e}", "platform": "xhs"}

    # 检查是否被重定向到登录页
    if "login" in html.lower() and len(html) < 5000:
        return {"error": "Cookie 已过期，需要重新获取", "platform": "xhs"}

    # 提取 __INITIAL_STATE__
    match = re.search(r"window\.__INITIAL_STATE__\s*=\s*({.*?})\s*</script>", html, re.DOTALL)
    if not match:
        # 尝试用 script 标签中的 JSON 数据
        match = re.search(r'<script>window\.__INITIAL_STATE__\s*=\s*(.*?)</script>', html, re.DOTALL)

    if not match:
        return {"error": "无法从页面提取数据，可能需要更新解析逻辑", "platform": "xhs"}

    try:
        # 处理可能的 undefined 值
        raw = match.group(1).replace("undefined", "null")
        state = json.loads(raw)
    except json.JSONDecodeError as e:
        return {"error": f"JSON 解析失败: {e}", "platform": "xhs"}

    # 提取笔记列表
    notes = []
    # explore 页面的数据结构可能在 state.note.noteDetailMap 或 state.explore
    note_map = state.get("note", {}).get("noteDetailMap", {})
    if note_map:
        for nid, note_data in note_map.items():
            note = note_data.get("note", note_data)
            notes.append({
                "note_id": nid,
                "title": note.get("title", note.get("desc", ""))[:100],
                "url": f"{XHS_INDEX}/explore/{nid}",
                "author": note.get("user", {}).get("nickname", ""),
                "likes": int(note.get("interactInfo", {}).get("likedCount", 0)),
                "type": note.get("type", ""),
            })
    else:
        # 尝试从 feed 数据中提取
        feed = state.get("feed", state.get("note", {}))
        if isinstance(feed, dict):
            for key in feed:
                if isinstance(feed[key], dict) and "noteId" in feed[key]:
                    n = feed[key]
                    notes.append({
                        "note_id": n.get("noteId", key),
                        "title": (n.get("title", n.get("desc", "")) or "")[:100],
                        "url": f"{XHS_INDEX}/explore/{n.get('noteId', key)}",
                        "author": n.get("user", {}).get("nickname", ""),
                        "likes": int(n.get("interactInfo", {}).get("likedCount", 0)),
                        "type": n.get("type", ""),
                    })

    items = []
    for i, note in enumerate(notes[:limit]):
        items.append({
            "rank": i + 1,
            "title": note.get("title", ""),
            "url": note.get("url", ""),
            "heat": note.get("likes", 0),
            "description": "",
            "extra": {
                "author": note.get("author", ""),
                "type": note.get("type", ""),
                "note_id": note.get("note_id", ""),
            },
        })

    if not items:
        return {"error": "页面已加载但未找到笔记数据（可能需要更新解析路径）", "platform": "xhs"}

    return {
        "platform": "xhs",
        "fetched_at": datetime.now(TZ).isoformat(),
        "count": len(items),
        "items": items,
    }


def main():
    parser = argparse.ArgumentParser(description="小红书热点采集")
    parser.add_argument("--cookies", "-c", default="cookies.json",
                        help="Cookie JSON 文件路径")
    parser.add_argument("--limit", "-n", type=int, default=20)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()

    # 加载 cookies
    try:
        cookies_str = load_cookies(args.cookies)
    except FileNotFoundError:
        result = {"error": f"Cookie 文件不存在: {args.cookies}", "platform": "xhs",
                   "hint": "从浏览器 DevTools > Application > Cookies 导出为 JSON"}
        print(json.dumps(result, ensure_ascii=False,
                         indent=2 if args.pretty else None))
        sys.exit(1)
    except Exception as e:
        result = {"error": f"Cookie 加载失败: {e}", "platform": "xhs"}
        print(json.dumps(result, ensure_ascii=False,
                         indent=2 if args.pretty else None))
        sys.exit(1)

    result = fetch_explore_via_page(cookies_str, args.limit)
    indent = 2 if args.pretty else None
    print(json.dumps(result, ensure_ascii=False, indent=indent))
    sys.exit(1 if "error" in result else 0)


if __name__ == "__main__":
    main()
