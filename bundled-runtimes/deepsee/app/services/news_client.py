from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import requests

from ..config import settings


_CACHE: Dict[str, Tuple[float, Any]] = {}


def _cache_get(key: str) -> Any | None:
    try:
        exp, val = _CACHE.get(key, (0, None))
        if exp and exp > time.time():
            return val
    except Exception:
        pass
    return None


def _cache_set(key: str, val: Any, ttl: int) -> None:
    try:
        _CACHE[key] = (time.time() + max(1, ttl), val)
    except Exception:
        pass


def _get(url: str, params: dict | None = None, *, timeout: int = 5, headers: dict | None = None) -> dict:
    for i in range(3):
        try:
            r = requests.get(url, params=params or {}, timeout=timeout, headers=headers or {})
            if r.status_code < 500:
                r.raise_for_status()
                return r.json()
        except Exception:
            if i == 2:
                raise
            time.sleep(0.3 * (i + 1))
    return {}


def _post(url: str, payload: dict | None = None, *, timeout: int = 8) -> dict:
    for i in range(2):
        try:
            r = requests.post(url, json=payload or {}, timeout=timeout)
            if r.status_code < 500:
                r.raise_for_status()
                return r.json()
        except Exception:
            if i == 1:
                raise
            time.sleep(0.5)
    return {}


def newsnow_health() -> dict:
    # deprecated: upstream removed; keep stub to avoid import errors
    return {"status": "deprecated"}


def newsnow_sources(force: bool = False) -> dict:
    # deprecated: upstream removed
    return {"success": False, "data": []}


def newsnow_news(keyword: str | None = None, source: str | None = None, limit: int = 50, simple: bool = True) -> dict:
    # deprecated: use direct collectors
    return {"success": False, "data": []}


def newsnow_search(q: str, limit: int = 20) -> dict:
    # deprecated: use direct collectors
    return {"success": False, "data": []}


def newsnow_refresh() -> dict:
    # deprecated: use direct collectors
    return {"success": False}


# --------------- finance filtering & normalization ---------------

_DEFAULT_FINANCE_KEYWORDS: list[str] = [
    # 宏观与政策
    "宏观", "央行", "利率", "通胀", "通缩", "汇率", "财政", "货币政策", "降准", "降息",
    "加息", "缩表", "非农", "就业", "失业率", "经济数据", "美联储", "联储", "议息", "FOMC",
    "CPI", "PPI", "PCE", "GDP",
    # 行业与市场
    "地产", "房企", "土拍", "销售", "按揭",
    "半导体", "芯片", "算力", "AI", "人工智能", "光伏", "新能源", "储能", "风电", "锂电",
    "券商", "A股", "港股", "美股", "科创板", "创业板", "北交所",
    # 公司与财报
    "业绩", "利润", "营收", "公告", "IPO", "回购", "减持", "增持", "限售解禁", "评级", "目标价",
    "财报", "指引", "展望",
    # 英文常见词（确保海外财经标题不过滤）
    "fed", "fomc", "nonfarm", "non-farm", "payroll", "payrolls", "jobs report",
    "earnings", "guidance", "outlook", "results", "revenue", "profit",
    "nvidia", "nvda", "google", "alphabet",
]


def _load_finance_keywords() -> list[str]:
    import os
    path = os.path.abspath(os.path.join(os.getcwd(), 'data', 'entities.json'))
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                j = json.load(f)
            arr = j.get('finance_keywords') if isinstance(j, dict) else None
            if isinstance(arr, list) and arr:
                return [str(x) for x in arr if isinstance(x, (str, int))]
    except Exception:
        pass
    return _DEFAULT_FINANCE_KEYWORDS


def _load_source_whitelist() -> list[str]:
    """Load preferred news sources from data/entities.json -> news_sources_whitelist.
    Accept both source ids and Chinese names. Case-insensitive for ids; fuzzy contains for names.
    """
    import os
    path = os.path.abspath(os.path.join(os.getcwd(), 'data', 'entities.json'))
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                j = json.load(f)
            arr = j.get('news_sources_whitelist') if isinstance(j, dict) else None
            if isinstance(arr, list) and arr:
                return [str(x).strip() for x in arr if isinstance(x, (str, int)) and str(x).strip()]
    except Exception:
        pass
    # 默认白名单（当未配置文件时启用）：覆盖常见财经媒体
    return [
        'wallstreetcn-quick', 'reuters-business', 'bbc-business', 'cnbc-top',
        'techcrunch', 'coindesk', 'engadget', 'cointelegraph', 'bitcoincom', 'npr-business',
        # 国内财经（RSS新增）
        'stcn',            # 证券时报
        '21jingji',        # 21世纪经济报道
        'jiemian',         # 界面新闻
        'caixin',          # 财新
        'ssnews',          # 上证报
        'thepaper',        # 澎湃财经
        'yicai',           # 第一财经
    ]


def _is_whitelisted(source_id: str, source_name: str, wl: list[str]) -> bool:
    if not wl:
        return True
    sid = (source_id or '').strip().lower()
    sname = (source_name or '').strip()
    wl_norm = [str(x).strip().lower() for x in wl]
    # match id exact (case-insensitive) or name contains any token (Chinese names)
    if sid and sid in wl_norm:
        return True
    for token in wl:
        t = str(token).strip()
        if not t:
            continue
        if t in sname:
            return True
    return False


def _is_finance(title: str, url: str | None = None) -> bool:
    if not title:
        return False
    kws = _load_finance_keywords()
    return any(k in title for k in kws) or any((k in (url or '')) for k in kws)


def _infer_news_category(title: str, source_name: str = "") -> str:
    t = (title or "")
    s = (source_name or "")
    macro_keys = ("央行","利率","通胀","通缩","财政","货币政策","降准","降息","加息","贸易","关税","PMI","GDP","非农","就业","失业率","美联储","联储","CPI","PPI","PCE","FOMC")
    if any(k in t for k in macro_keys):
        return "宏观"
    industry_keys = ("半导体","芯片","算力","AI","人工智能","光伏","新能源","储能","风电","锂电","汽车","医药","军工","煤炭","有色","地产")
    if any(k in t for k in industry_keys):
        return "行业"
    stock_keys = ("股份","集团","公司","公告","业绩","回购","减持","增持","上市","IPO")
    if any(k in t for k in stock_keys):
        return "个股"
    sentiment_keys = ("热搜","热榜","舆情")
    if any(k in t for k in sentiment_keys) or any(k in s for k in sentiment_keys):
        return "舆情"
    return "观点"


def _infer_news_tone(title: str) -> str:
    t = (title or "").lower()
    pos = ("利好","上涨","上调","增持","改善","超预期","突破","创新高","回暖","反弹","大涨","涨停")
    neg = ("利空","下跌","下调","减持","承压","不及预期","下行","回落","疲弱","暴跌")
    if any(k.lower() in t for k in pos):
        return "positive"
    if any(k.lower() in t for k in neg):
        return "negative"
    return "neutral"


def normalize_items(raw: dict, *, finance_only: bool = True, whitelist: list[str] | None = None) -> dict:
    ok = bool(raw.get('success', True))
    data = raw.get('data') or []
    out: List[dict] = []
    for it in data:
        # Try both full and simple formats
        title = it.get('title') or ''
        url = it.get('url') or ''
        # When items are already pre-normalized, they may carry `source_name`/`source_id` fields.
        # Fall back to those to avoid blank source display in /api/newsfeed responses.
        src_name = (
            it.get('source')
            or it.get('sourceName')
            or it.get('name')
            or it.get('source_name')
            or ''
        )
        src_id = it.get('sourceId') or it.get('source_id') or it.get('id') or ''
        nid = it.get('id') or url or title
        ts = it.get('pubDate') or it.get('timestamp') or it.get('updatedTime') or 0
        wl = whitelist or []
        # 仅根据来源白名单筛选；不再使用关键词判断财经属性
        if wl and not _is_whitelisted(str(src_id), str(src_name), wl):
            continue
        cat = _infer_news_category(str(title), str(src_name))
        tone = _infer_news_tone(str(title))
        out.append({
            'id': str(nid),
            'source_id': str(src_id),
            'source_name': str(src_name),
            'title': str(title),
            'url': str(url),
            'pub_ts': int(ts) if isinstance(ts, int) else 0,
            'tags': [],
            'category': cat,
            'summary': '',
            'raw': it,
            'derived': {
                'key_info': str(title)[:120],
                'category': cat,
                'tone': tone,
                'summary_origin': 'fallback',
            }
        })
    return {'total': len(out), 'items': out, 'upstream_ok': ok}


# --------------- direct fetchers (avoid 4445 dependency) ---------------

def _strip_html(text: str) -> str:
    try:
        import re
        # remove tags
        t = re.sub(r"<[^>]+>", " ", text or '')
        t = re.sub(r"\s+", " ", t).strip()
        return t
    except Exception:
        return text or ''


def direct_wallstreetcn(limit: int = 30) -> dict:
    """Fetch live news from WallstreetCN public API without auth.
    Endpoint: https://api.wallstreetcn.com/apiv1/content/lives?channel=global&limit=N
    """
    url = "https://api.wallstreetcn.com/apiv1/content/lives"
    params = {"channel": "global", "limit": max(1, min(100, int(limit)))}
    try:
        j = _get(url, params=params, timeout=8)
        items = []
        for it in (j.get('data', {}).get('items') or []):
            live = it
            cid = live.get('id') or live.get('resource') or it.get('id')
            content_html = (live.get('content') or '')
            title = _strip_html(content_html)[:120]
            ts = live.get('display_time') or live.get('created_at') or live.get('updated_at') or 0
            url_article = ''
            try:
                art = live.get('article') or {}
                url_article = art.get('uri') or art.get('resource') or ''
            except Exception:
                pass
            src_name = '华尔街见闻'
            src_id = 'wallstreetcn-quick'
            cat = _infer_news_category(title, src_name)
            tone = _infer_news_tone(title)
            items.append({
                'id': str(cid),
                'source_id': src_id,
                'source_name': src_name,
                'title': title,
                'url': url_article,
                'pub_ts': int(ts) if isinstance(ts, int) else 0,
                'tags': [],
                'category': cat,
                'summary': '',
                'raw': it,
                'derived': {
                    'key_info': title,
                    'category': cat,
                    'tone': tone,
                    'summary_origin': 'fallback',
                }
            })
        return {'total': len(items), 'items': items, 'upstream_ok': True}
    except Exception as e:
        return {'total': 0, 'items': [], 'upstream_ok': False, 'error': str(e)}


def direct_from_sources_json(limit: int = 50, q: str | None = None) -> dict:
    """Direct aggregation from multiple sources (JSON-first). Extendable.
    Implemented: wallstreetcn-quick, HackerNews (Algolia), SpaceflightNews, Reddit (r/stocks, r/investing).
    """
    # L1 cache: 3h TTL (与前端“每3小时刷新”一致)
    try:
        cache_key = f"direct:{int(limit)}:{q or ''}"
        cached = _cache_get(cache_key)
        if cached:
            return cached
    except Exception:
        cached = None
    agg: List[dict] = []
    # 1) 华尔街见闻快讯
    try:
        d1 = direct_wallstreetcn(limit=min(30, limit))
        agg.extend(d1.get('items') or [])
    except Exception:
        pass
    # 2) Hacker News (Algolia)
    try:
        agg.extend(_direct_hn_algolia(q=q, limit=min(30, limit)))
    except Exception:
        pass
    # 3) Spaceflight News
    try:
        agg.extend(_direct_spaceflight(limit=min(20, limit)))
    except Exception:
        pass
    # 4) Reddit r/stocks & r/investing
    try:
        agg.extend(_direct_reddit('stocks', limit=min(10, limit)))
    except Exception:
        pass
    try:
        agg.extend(_direct_reddit('investing', limit=min(10, limit)))
    except Exception:
        pass
    # 5) Reddit r/economy
    try:
        agg.extend(_direct_reddit('economy', limit=min(10, limit)))
    except Exception:
        pass
    # 6) TechCrunch (WP JSON)
    try:
        agg.extend(_direct_wp_posts('https://techcrunch.com', 'techcrunch', 'TechCrunch', limit=min(10, limit)))
    except Exception:
        pass
    # 7) Coindesk (WP JSON)
    try:
        agg.extend(_direct_wp_posts('https://www.coindesk.com', 'coindesk', 'CoinDesk', limit=min(10, limit)))
    except Exception:
        pass
    # 8) Engadget (WP JSON)
    try:
        agg.extend(_direct_wp_posts('https://www.engadget.com', 'engadget', 'Engadget', limit=min(10, limit)))
    except Exception:
        pass
    # 9) Cointelegraph (WP JSON)
    try:
        agg.extend(_direct_wp_posts('https://cointelegraph.com', 'cointelegraph', 'Cointelegraph', limit=min(10, limit)))
    except Exception:
        pass
    # 10) Bitcoin.com News (WP JSON)
    try:
        agg.extend(_direct_wp_posts('https://news.bitcoin.com', 'bitcoincom', 'Bitcoin.com News', limit=min(10, limit)))
    except Exception:
        pass
    # 11) NPR Business JSON
    try:
        agg.extend(_direct_npr_business(limit=min(10, limit)))
    except Exception:
        pass
    # 12) Reuters Business (RSS)
    try:
        agg.extend(_direct_rss('https://feeds.reuters.com/reuters/businessNews', 'reuters-business', 'Reuters Business', limit=min(30, limit)))
    except Exception:
        pass
    # 13) BBC Business (RSS)
    try:
        agg.extend(_direct_rss('http://feeds.bbci.co.uk/news/business/rss.xml', 'bbc-business', 'BBC Business', limit=min(20, limit)))
    except Exception:
        pass
    # 14) CNBC Top News (RSS)
    try:
        agg.extend(_direct_rss('https://www.cnbc.com/id/100003114/device/rss/rss.html', 'cnbc-top', 'CNBC', limit=min(20, limit)))
    except Exception:
        pass
    # keyword filter (best-effort)
    if q:
        ql = str(q).lower()
        agg = [it for it in agg if ql in (it.get('title') or '').lower() or ql in (it.get('source_name') or '').lower()]
    # de-dup by id or url+title
    seen: set[str] = set()
    uniq: List[dict] = []
    for it in agg:
        dedupe_key = it.get('id') or (it.get('url') or '') + '|' + (it.get('title') or '')
        dedupe_key = str(dedupe_key)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        uniq.append(it)
    result = {'total': len(uniq), 'items': uniq, 'upstream_ok': True}
    try:
        # Cache 3 hours
        _cache_set(cache_key, result, ttl=3 * 3600)
    except Exception:
        pass
    return result


# ------------------- external JSON sources (no key) -------------------

def _direct_hn_algolia(q: str | None, limit: int = 20) -> List[dict]:
    # If no query, use latest stories by date
    url = 'https://hn.algolia.com/api/v1/search_by_date' if not q else 'https://hn.algolia.com/api/v1/search'
    params = {'tags': 'story', 'page': 0, 'hitsPerPage': max(1, min(50, int(limit)))}
    if q:
        params['query'] = q
    j = _get(url, params=params, timeout=8)
    items: List[dict] = []
    for h in (j.get('hits') or []):
        title = h.get('title') or h.get('story_title') or ''
        urlp = h.get('url') or h.get('story_url') or ''
        ts = h.get('created_at_i') or 0
        cat = _infer_news_category(title, 'Hacker News')
        tone = _infer_news_tone(title)
        items.append({
            'id': str(h.get('objectID') or urlp or title),
            'source_id': 'hackernews',
            'source_name': 'Hacker News',
            'title': title,
            'url': urlp,
            'pub_ts': int(ts) * 1000 if isinstance(ts, int) else 0,
            'tags': [],
            'category': cat,
            'summary': '',
            'raw': h,
            'derived': {
                'key_info': title,
                'category': cat,
                'tone': tone,
                'summary_origin': 'fallback',
            }
        })
    return items


def _direct_spaceflight(limit: int = 20) -> List[dict]:
    url = 'https://api.spaceflightnewsapi.net/v4/articles'
    params = {'limit': max(1, min(50, int(limit))), 'ordering': '-published_at'}
    j = _get(url, params=params, timeout=8)
    results = j.get('results') or []
    items: List[dict] = []
    for a in results:
        title = a.get('title') or ''
        urlp = a.get('url') or ''
        ts_iso = a.get('published_at') or ''
        ts_int = 0
        try:
            # simple parse: YYYY-MM-DDTHH:MM:SSZ
            from datetime import datetime
            ts_int = int(datetime.fromisoformat(ts_iso.replace('Z', '+00:00')).timestamp() * 1000)
        except Exception:
            ts_int = 0
        cat = _infer_news_category(title, 'Spaceflight')
        tone = _infer_news_tone(title)
        items.append({
            'id': str(a.get('id') or urlp or title),
            'source_id': 'spaceflight',
            'source_name': 'Spaceflight News',
            'title': title,
            'url': urlp,
            'pub_ts': ts_int,
            'tags': [],
            'category': cat,
            'summary': '',
            'raw': a,
            'derived': {
                'key_info': title,
                'category': cat,
                'tone': tone,
                'summary_origin': 'fallback',
            }
        })
    return items


def _direct_reddit(subreddit: str, limit: int = 10) -> List[dict]:
    url = f'https://www.reddit.com/r/{subreddit}/hot.json'
    params = {'limit': max(1, min(50, int(limit)))}
    headers = {'User-Agent': 'Mozilla/5.0 (+news-collector)'}
    j = _get(url, params=params, timeout=8, headers=headers)
    children = j.get('data', {}).get('children') or []
    items: List[dict] = []
    for c in children:
        d = c.get('data') or {}
        title = d.get('title') or ''
        urlp = d.get('url') or ''
        ts = d.get('created_utc') or 0
        cat = _infer_news_category(title, f'Reddit r/{subreddit}')
        tone = _infer_news_tone(title)
        items.append({
            'id': str(d.get('id') or urlp or title),
            'source_id': f'reddit-{subreddit}',
            'source_name': f'Reddit r/{subreddit}',
            'title': title,
            'url': urlp,
            'pub_ts': int(ts) * 1000 if isinstance(ts, (int, float)) else 0,
            'tags': [],
            'category': cat,
            'summary': '',
            'raw': d,
            'derived': {
                'key_info': title,
                'category': cat,
                'tone': tone,
                'summary_origin': 'fallback',
            }
        })
    return items


def _direct_rss(url: str, source_id: str, source_name: str, limit: int = 30) -> List[dict]:
    """Generic RSS fetcher for simple RSS feeds with <item><title><link><pubDate>."""
    import xml.etree.ElementTree as ET
    txt = requests.get(url, timeout=8).text
    items: List[dict] = []
    try:
        root = ET.fromstring(txt)
    except Exception:
        return items
    # Support both rss/channel/item and feed/entry
    def _iter_items(node):
        for it in node.findall('.//item'):
            yield {
                'title': (it.findtext('title') or '').strip(),
                'link': (it.findtext('link') or '').strip(),
                'pub': (it.findtext('pubDate') or '').strip(),
            }
        for it in node.findall('.//{http://www.w3.org/2005/Atom}entry'):
            yield {
                'title': (it.findtext('{http://www.w3.org/2005/Atom}title') or '').strip(),
                'link': (it.find('{http://www.w3.org/2005/Atom}link').attrib.get('href') if it.find('{http://www.w3.org/2005/Atom}link') is not None else '').strip(),
                'pub': (it.findtext('{http://www.w3.org/2005/Atom}updated') or it.findtext('{http://www.w3.org/2005/Atom}published') or '').strip(),
            }
    count = 0
    for it in _iter_items(root):
        if not it.get('title'):
            continue
        title = it['title']
        urlp = it.get('link') or ''
        pub = it.get('pub') or ''
        ts_int = 0
        # best-effort pubDate parsing
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(pub)
            ts_int = int(dt.timestamp() * 1000)
        except Exception:
            try:
                from datetime import datetime
                ts_int = int(datetime.fromisoformat(pub.replace('Z', '+00:00')).timestamp() * 1000)
            except Exception:
                ts_int = 0
        cat = _infer_news_category(title, source_name)
        tone = _infer_news_tone(title)
        items.append({
            'id': urlp or title,
            'source_id': source_id,
            'source_name': source_name,
            'title': title,
            'url': urlp,
            'pub_ts': ts_int,
            'tags': [],
            'category': cat,
            'summary': '',
            'raw': {'title': title, 'link': urlp, 'pubDate': pub},
            'derived': {
                'key_info': title,
                'category': cat,
                'tone': tone,
                'summary_origin': 'fallback',
            }
        })
        count += 1
        if count >= max(1, min(100, int(limit))):
            break
    return items


def _direct_wp_posts(base_url: str, source_id: str, source_name: str, limit: int = 10) -> List[dict]:
    """Generic WordPress posts JSON fetcher: <base>/wp-json/wp/v2/posts?per_page=N"""
    url = base_url.rstrip('/') + '/wp-json/wp/v2/posts'
    params = {'per_page': max(1, min(20, int(limit)))}
    headers = {'User-Agent': 'Mozilla/5.0 (+news-collector)'}
    j = _get(url, params=params, timeout=8, headers=headers)
    if not isinstance(j, list):
        return []
    items: List[dict] = []
    for p in j:
        try:
            title_html = p.get('title', {}).get('rendered') or ''
            title = _strip_html(title_html)[:200]
            link = p.get('link') or ''
            date = p.get('date_gmt') or p.get('date') or ''
            ts = 0
            if date:
                from datetime import datetime
                try:
                    ts = int(datetime.fromisoformat(date.replace('Z','+00:00')).timestamp() * 1000)
                except Exception:
                    ts = 0
            cat = _infer_news_category(title, source_name)
            tone = _infer_news_tone(title)
            items.append({
                'id': str(p.get('id') or link or title),
                'source_id': source_id,
                'source_name': source_name,
                'title': title,
                'url': link,
                'pub_ts': ts,
                'tags': [],
                'category': cat,
                'summary': '',
                'raw': p,
                'derived': {
                    'key_info': title,
                    'category': cat,
                    'tone': tone,
                    'summary_origin': 'fallback',
                }
            })
        except Exception:
            continue
    return items


def _direct_npr_business(limit: int = 20) -> List[dict]:
    """NPR Business JSON feed: https://feeds.npr.org/1006/feed.json"""
    url = 'https://feeds.npr.org/1006/feed.json'
    j = _get(url, timeout=8)
    items: List[dict] = []
    for it in (j.get('items') or []):
        title = it.get('title') or ''
        urlp = it.get('url') or ''
        ts = it.get('date_published') or ''
        ts_int = 0
        if ts:
            from datetime import datetime
            try:
                ts_int = int(datetime.fromisoformat(ts.replace('Z','+00:00')).timestamp() * 1000)
            except Exception:
                ts_int = 0
        cat = _infer_news_category(title, 'NPR Business')
        tone = _infer_news_tone(title)
        items.append({
            'id': str(urlp or title),
            'source_id': 'npr-business',
            'source_name': 'NPR Business',
            'title': title,
            'url': urlp,
            'pub_ts': ts_int,
            'tags': [],
            'category': cat,
            'summary': '',
            'raw': it,
            'derived': {
                'key_info': title,
                'category': cat,
                'tone': tone,
                'summary_origin': 'fallback',
            }
        })
        if len(items) >= max(1, min(50, int(limit))):
            break
    return items


def write_news_snapshot(limit: int = 150) -> dict:
    """Write a direct snapshot JSON under data/datasets/ with essential fields.
    Fields: id, source_id, source_name, title, content, url, pub_ts, published_at
    """
    import os, time, json as _json
    from datetime import datetime, timezone
    agg = direct_from_sources_json(limit=limit)
    items = agg.get('items') or []
    rows: List[dict] = []
    for it in items:
        title = it.get('title') or ''
        raw = it.get('raw') or {}
        content = ''
        try:
            html = raw.get('content') or ''
            content = _strip_html(html) if html else title
        except Exception:
            content = title
        ts = int(it.get('pub_ts') or 0)
        # normalize to milliseconds
        if ts > 0 and ts < 10_000_000_000:  # likely seconds
            ts = ts * 1000
        if ts <= 0:
            ts = int(time.time() * 1000)
        try:
            published_at = datetime.fromtimestamp(ts/1000, tz=timezone.utc).isoformat()
        except Exception:
            published_at = None
        rows.append({
            'id': it.get('id'),
            'source_id': it.get('source_id'),
            'source_name': it.get('source_name'),
            'title': title,
            'content': content,
            'url': it.get('url'),
            'pub_ts': ts,
            'published_at': published_at,
        })
    ds_dir = os.path.abspath(os.path.join(os.getcwd(), 'data', 'datasets'))
    os.makedirs(ds_dir, exist_ok=True)
    fname = f"news_snapshot_{int(time.time())}.json"
    fpath = os.path.join(ds_dir, fname)
    with open(fpath, 'w', encoding='utf-8') as f:
        _json.dump({'items': rows, 'total': len(rows)}, f, ensure_ascii=False, indent=2)
    return {'status': 'ok', 'file': fpath, 'total': len(rows)}
    # 15) 国内财经 RSS 源
    try:
        agg.extend(_direct_rss('https://www.stcn.com/rss/gundong.xml', 'stcn', '证券时报', limit=min(30, limit)))
    except Exception:
        pass
    try:
        agg.extend(_direct_rss('https://www.21jingji.com/rss', '21jingji', '21世纪经济报道', limit=min(20, limit)))
    except Exception:
        pass
    try:
        agg.extend(_direct_rss('https://www.jiemian.com/rss.html', 'jiemian', '界面新闻', limit=min(20, limit)))
    except Exception:
        pass
    try:
        agg.extend(_direct_rss('https://file.caixin.com/m/caixin_rss.xml', 'caixin', '财新', limit=min(20, limit)))
    except Exception:
        pass
    try:
        agg.extend(_direct_rss('https://www.sse.com.cn/aboutus/mediacenter/hotandd/activities/rss_r.xml', 'ssnews', '上证报', limit=min(20, limit)))
    except Exception:
        pass
    try:
        agg.extend(_direct_rss('https://www.thepaper.cn/listpage/18480,1199089,1199088,1199086,1199085,1199087,1013477,1299546,1299547,27094,26908,26911,26907,26910,26912,1199092,26909,1299545,1999080,1013490,32285,1013488,1013489,71824,1013487,1013486,1013485,1013484,1013483,1013475,1013491,26906,27093,1013479,1013482,1013478,1013481,1013480,1013476,1013474,1013473,1013472,1013471,1013470,1013468,1013467,1013466,1013465,39536,39535,39534,39533,39532,26913,1652514,1199091,1199090,1199083,1199082,1199081,1199093,1199094,1199095,1199096,1199097,1199098,1299550,1299548,1299552,1299551,1299549,1299553,27092,27091,27090,27089,27088,27087,27086,27085,27084,27083,27082,27081,1999079,1999078,1999077,1999076,1013477,1013479,1013478,1013480,1013476,1013474,1013473,1013472,1013471,1013470,1013468,1013467,1013466,1013465,39536,39535,39534,39533,39532,26913,1652514,1199091,1199090,1199083,1199082,1199081,1199093,1199094,1199095,1199096,1199097,1199098,1299550,1299548,1299552,1299551,1299549,1299553,27092,27091,27090,27089,27088,27087,27086,27085,27084,27083,27082,27081,1999079,1999078,1999077,1999076,1013475,1013491,26906,27093,1013479,1013482,1013478,1013481,1013480,1013476,1013474,1013473,1013472,1013471,1013470,1013468,1013467,1013466,1013465,39536,39535,39534,39533,39532,26913,1652514,1199091,1199090,1199083,1199082,1199081,1199093,1199094,1199095,1199096,1199097,1199098,1299550,1299548,1299552,1299551,1299549,1299553,27092,27091,27090,27089,27088,27087,27086,27085,27084,27083,27082,27081,1999079,1999078,1999077,1999076,1013479,1013482,1013478,1013481,1013480,1013476,1013474,1013473,1013472,1013471,1013470,1013468,1013467,1013466,1013465,39536,39535,39534,39533,39532,26913,1652514,1199091,1199090,1199083,1199082,1199081,1199093,1199094,1199095,1199096,1199097,1199098,1299550,1299548,1299552,1299551,1299549,1299553,27092,27091,27090,27089,27088,27087,27086,27085,27084,27083,27082,27081', 'thepaper', '澎湃财经', limit=min(20, limit)))
    except Exception:
        pass
    try:
        agg.extend(_direct_rss('https://www.yicai.com/rss/pc/', 'yicai', '第一财经', limit=min(20, limit)))
    except Exception:
        pass
