from __future__ import annotations

import hashlib
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import requests

_CACHE: dict[str, tuple[float, Any]] = {}


@dataclass(frozen=True)
class NewsSource:
    id: str
    name: str
    url: str
    region: str = "global"
    category: str = "finance"


NEWS_SOURCES: tuple[NewsSource, ...] = (
    NewsSource("wallstreetcn-quick", "华尔街见闻", "https://api.wallstreetcn.com/apiv1/content/lives", "cn"),
    NewsSource("10jqka-stock", "同花顺", "https://news.10jqka.com.cn/tapp/news/push/stock/", "cn"),
    NewsSource("sina-finance", "新浪财经", "https://rss.sina.com.cn/roll/finance/hot_roll.xml", "cn"),
    NewsSource("stcn", "证券时报", "https://www.stcn.com/rss/gundong.xml", "cn"),
    NewsSource("yicai", "第一财经", "https://www.yicai.com/rss/pc/", "cn"),
    NewsSource("caixin", "财新", "https://file.caixin.com/m/caixin_rss.xml", "cn"),
    NewsSource("jiemian", "界面新闻", "https://www.jiemian.com/rss.html", "cn"),
    NewsSource("reuters-business", "Reuters Business", "https://feeds.reuters.com/reuters/businessNews", "global"),
    NewsSource("bbc-business", "BBC Business", "http://feeds.bbci.co.uk/news/business/rss.xml", "global"),
    NewsSource("cnbc", "CNBC", "https://www.cnbc.com/id/100003114/device/rss/rss.html", "global"),
    NewsSource("bloomberg-markets", "彭博市场", "https://feeds.bloomberg.com/markets/news.rss", "global"),
    NewsSource("hackernews", "Hacker News", "https://hnrss.org/frontpage", "global", "technology"),
)

_POSITIVE = ("上涨", "增长", "突破", "回暖", "创新高", "利好", "扩张", "beat", "surge", "rise", "gain", "growth", "record")
_NEGATIVE = ("下跌", "下降", "风险", "承压", "亏损", "裁员", "调查", "制裁", "危机", "miss", "fall", "drop", "risk", "loss", "cut")
_RISK = ("监管", "制裁", "调查", "违约", "亏损", "裁员", "风险", "下跌", "crackdown", "probe", "default", "lawsuit")
_OPPORTUNITY = ("AI", "人工智能", "算力", "芯片", "新能源", "机器人", "出海", "增长", "突破", "record", "growth")
_TRANSLATION_RULES: tuple[tuple[str, str], ...] = (
    ("consumer spending", "消费者支出"),
    ("used car prices", "二手车价格"),
    ("gas prices", "汽油价格"),
    ("interest rates", "利率"),
    ("fed", "美联储"),
    ("stock market", "股市"),
    ("stocks", "股票"),
    ("shares", "股价"),
    ("ai bull market", "AI 牛市"),
    ("bull market", "牛市"),
    ("hedge trade", "对冲交易"),
    ("oil", "石油"),
    ("profits", "利润"),
    ("revenue", "营收"),
    ("earnings", "财报"),
    ("subscription prices", "订阅价格"),
    ("profitable quarter", "盈利季度"),
    ("family office", "家族办公室"),
    ("deal-making", "交易活动"),
    ("healthcare", "医疗健康"),
    ("college", "大学教育"),
    ("investment", "投资"),
    ("rail disruption", "铁路中断"),
    ("southern england", "英格兰南部"),
    ("vulnerability", "漏洞"),
    ("linux", "Linux"),
    ("cloudflare", "Cloudflare"),
    ("burning man", "火人节"),
    ("mcdonald", "麦当劳"),
    ("peloton", "Peloton"),
    ("warsh", "沃什"),
)
_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "into", "after", "over", "news", "says",
    "一个", "相关", "表示", "公司", "市场", "中国", "美国", "今日", "最新", "可能", "进行", "成为", "以及",
    "亿元", "万元", "同比", "同比增长", "增长", "美元", "亿美元", "人民币", "公告", "显示", "记者", "目前",
    "截至", "发布", "实现", "预计", "其中", "方面", "持续", "超过", "达到", "来看", "数据", "报告",
    "跌超", "涨超", "领涨", "领跌", "午评", "早盘", "收盘", "主力合约", "主力合约日内", "日内", "半日",
    "概念股", "集体", "爆发", "成交额", "股指期货", "沪深", "创业板指", "etf", "a股", "股票",
    "finance", "market", "markets", "business", "company", "companies", "report", "reports", "deal", "deals",
}
_TOPIC_TERMS = (
    "人形机器人", "机器人", "芯片", "半导体", "人工智能", "AI", "算力", "新能源", "光伏", "储能",
    "黄金", "原油", "霍尔木兹", "美联储", "降息", "通胀", "关税", "制裁", "ETF", "股指期货",
    "腾讯", "阿里巴巴", "英伟达", "Nvidia", "Cloudflare", "Datadog", "CoreWeave", "Coinbase",
    "房地产", "医药", "医疗", "消费", "出口", "汇率", "债券", "港股", "A股", "美股",
)

_ALPHA_THEME_RULES: tuple[dict[str, Any], ...] = (
    {
        "theme": "AI 算力与半导体",
        "keywords": ("AI", "人工智能", "算力", "芯片", "半导体", "服务器", "光模块", "英伟达", "Nvidia"),
        "positive": {
            "demand_supply": "下游资本开支与推理需求扩张，先进算力、互联和配套供给的订单能见度提升。",
            "earnings": "订单量和产品结构改善可向收入、毛利率与经营杠杆传导，先验证收入再验证利润。",
            "pricing": "市场通常先交易资本开支和订单预期，随后由交付、收入确认与盈利兑现校准估值。",
        },
        "negative": {
            "demand_supply": "资本开支、订单或终端需求转弱，产业链库存和供给消化压力上升。",
            "earnings": "收入增速、产能利用率和毛利率可能承压，高估值环节对预期下修更敏感。",
            "pricing": "市场会先压缩高预期环节估值，再等待订单与盈利预期企稳。",
        },
        "beneficiaries": ("算力基础设施", "先进制程与存储", "光模块及数据中心配套"),
        "validation_signals": ("云厂商资本开支指引", "服务器/芯片/光模块订单与交付", "库存、价格与毛利率变化"),
        "falsifiers": ("资本开支下修或订单延期", "供给快速释放导致价格下行", "收入增长未能转化为利润改善"),
    },
    {
        "theme": "机器人与智能制造",
        "keywords": ("人形机器人", "机器人", "自动化", "减速器", "丝杠", "伺服"),
        "positive": {
            "demand_supply": "样机、量产和自动化改造需求增加，核心零部件进入订单和产能验证阶段。",
            "earnings": "放量可推动零部件收入增长并摊薄研发与制造成本，但利润兑现依赖良率和客户集中度。",
            "pricing": "市场先交易量产节奏，再由订单、产能利用率和单机价值量验证。",
        },
        "negative": {
            "demand_supply": "量产节奏或客户验证延后，零部件扩产面临产能闲置风险。",
            "earnings": "研发投入和折旧先行、收入确认滞后，可能压制利润率与现金流。",
            "pricing": "主题估值会向可见订单与真实收入收敛。",
        },
        "beneficiaries": ("核心零部件", "运动控制与传感器", "工业自动化集成"),
        "validation_signals": ("量产时间表与订单金额", "核心零部件良率和扩产进度", "客户数量与单机价值量"),
        "falsifiers": ("量产节点连续推迟", "降本速度不及预期", "订单集中但收入确认弱"),
    },
    {
        "theme": "新能源与电力设备",
        "keywords": ("新能源", "光伏", "储能", "风电", "锂电", "电网", "电力设备"),
        "positive": {
            "demand_supply": "装机、更新或储能需求改善，供需格局有望从去库存转向订单恢复。",
            "earnings": "出货增长叠加价格企稳可改善收入和单位盈利，现金流取决于回款与库存周转。",
            "pricing": "市场先交易价格与排产拐点，再验证出货、毛利率和现金流。",
        },
        "negative": {
            "demand_supply": "新增供给、价格竞争或装机不及预期，使去库存周期延长。",
            "earnings": "产品价格和产能利用率下降将压制毛利率，并放大减值与现金流压力。",
            "pricing": "估值修复需要价格、库存和排产至少两项同步改善。",
        },
        "beneficiaries": ("电网与储能设备", "成本领先制造环节", "高景气细分材料"),
        "validation_signals": ("产业链价格与库存", "月度排产和装机数据", "毛利率、回款与经营现金流"),
        "falsifiers": ("价格战再度加剧", "排产改善但库存继续累积", "海外政策或贸易壁垒恶化"),
    },
    {
        "theme": "宏观利率与流动性",
        "keywords": ("美联储", "降息", "加息", "利率", "通胀", "债券", "流动性"),
        "positive": {
            "demand_supply": "融资条件边际宽松，利率敏感需求和风险偏好获得支撑。",
            "earnings": "融资成本下降可改善高杠杆和长久期行业利润，但传导通常滞后于市场定价。",
            "pricing": "资产价格先反映利率路径，再由信用扩张、需求和盈利数据验证。",
        },
        "negative": {
            "demand_supply": "通胀或紧缩预期抬升资金成本，压制利率敏感需求和风险偏好。",
            "earnings": "财务费用与折现率上升，对高杠杆、弱现金流和长久期资产更不利。",
            "pricing": "市场先调整估值与期限溢价，再观察信用和盈利下修幅度。",
        },
        "beneficiaries": ("利率敏感资产", "高股息现金流资产", "券商与交易活跃度相关方向"),
        "validation_signals": ("通胀与就业数据", "政策利率和国债收益率", "社融、信用利差与成交活跃度"),
        "falsifiers": ("通胀重新上行", "宽松未带来信用扩张", "盈利下修抵消估值改善"),
    },
    {
        "theme": "大宗商品与资源品",
        "keywords": ("黄金", "原油", "铜", "煤炭", "有色", "资源", "霍尔木兹"),
        "positive": {
            "demand_supply": "供给约束、补库存或避险需求推升价格中枢，资源端议价能力增强。",
            "earnings": "商品价格高于成本曲线时，价格弹性可较快传导至收入、利润和自由现金流。",
            "pricing": "市场会同步交易现货价格、库存和期限结构，并用成本与资本开支约束判断持续性。",
        },
        "negative": {
            "demand_supply": "需求走弱或供给恢复使库存累积，商品价格和议价能力承压。",
            "earnings": "价格回落将直接压缩资源品利润和现金流，高成本产能更敏感。",
            "pricing": "市场先交易商品价格下行，再等待库存去化和供给收缩。",
        },
        "beneficiaries": ("低成本资源龙头", "油气与有色上游", "贵金属及避险相关资产"),
        "validation_signals": ("现货价格与期限结构", "全球库存和开工率", "成本曲线、资本开支与自由现金流"),
        "falsifiers": ("需求数据持续下修", "供给恢复快于预期", "价格上涨但库存同步累积"),
    },
    {
        "theme": "政策、关税与地缘风险",
        "keywords": ("关税", "制裁", "监管", "调查", "冲突", "战争", "地缘", "出口管制"),
        "positive": {
            "demand_supply": "政策缓和或限制解除改善贸易与供给预期，受压需求存在修复空间。",
            "earnings": "成本、交付和海外收入的不确定性下降，有利于订单恢复与风险溢价回落。",
            "pricing": "市场先修复风险溢价，再验证贸易量、订单和企业指引。",
        },
        "negative": {
            "demand_supply": "贸易限制或地缘冲突扰动供给、物流和终端需求，产业链面临重新定价。",
            "earnings": "关税、替代采购和交付延迟会侵蚀收入与利润率，并增加营运资金占用。",
            "pricing": "市场先提高风险溢价，再根据政策范围、持续时间和企业敞口分化定价。",
        },
        "beneficiaries": ("国产替代与供应链安全", "低海外敞口行业", "避险与防务相关方向"),
        "validation_signals": ("政策正式文本与豁免范围", "航运、交付和贸易量", "企业海外收入与成本指引"),
        "falsifiers": ("政策快速缓和或执行弱于预期", "企业已完成供应链替代", "风险未传导至订单和利润"),
    },
)


def _cache_get(key: str) -> Any | None:
    item = _CACHE.get(key)
    if not item:
        return None
    expires_at, value = item
    if expires_at > time.time():
        return value
    _CACHE.pop(key, None)
    return None


def _cache_set(key: str, value: Any, ttl: int = 600) -> None:
    _CACHE[key] = (time.time() + max(1, ttl), value)


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _parse_time(value: str) -> int:
    raw = (value or "").strip()
    if not raw:
        return 0
    try:
        return int(parsedate_to_datetime(raw).timestamp() * 1000)
    except Exception:
        pass
    try:
        return int(datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp() * 1000)
    except Exception:
        return 0


def _item_id(source_id: str, title: str, url: str) -> str:
    digest = hashlib.sha1(f"{source_id}|{url}|{title}".encode("utf-8", "ignore")).hexdigest()[:16]
    return f"{source_id}:{digest}"


def _tone(title: str) -> str:
    lower = title.lower()
    if any(k.lower() in lower or k in title for k in _NEGATIVE):
        return "negative"
    if any(k.lower() in lower or k in title for k in _POSITIVE):
        return "positive"
    return "neutral"


def _has_chinese(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in str(text or ""))


def translate_title_to_zh(title: str) -> str:
    """Very light local Chinese rendering for English headlines.

    This intentionally avoids adding a heavy translation dependency. It preserves
    the original title in `title_original` and produces a readable Chinese display
    title for common finance/tech headlines. Full LLM translation can be layered
    later without changing the frontend contract.
    """
    raw = str(title or "").strip()
    if not raw or _has_chinese(raw):
        return raw
    text = raw
    for src, dst in sorted(_TRANSLATION_RULES, key=lambda x: len(x[0]), reverse=True):
        text = re.sub(re.escape(src), dst, text, flags=re.IGNORECASE)
    text = re.sub(r"\bCEO\b", "CEO", text, flags=re.IGNORECASE)
    text = re.sub(r"\bsays\b", "称", text, flags=re.IGNORECASE)
    text = re.sub(r"\bcould be\b", "可能", text, flags=re.IGNORECASE)
    text = re.sub(r"\bexpected\b", "预计", text, flags=re.IGNORECASE)
    text = re.sub(r"\brises?\b", "上涨", text, flags=re.IGNORECASE)
    text = re.sub(r"\bfalls?\b", "下跌", text, flags=re.IGNORECASE)
    text = re.sub(r"\bexpected in\b", "预计发生在", text, flags=re.IGNORECASE)
    text = re.sub(r"\bfor first time this year\b", "为今年首次", text, flags=re.IGNORECASE)
    text = re.sub(r"\banother year or two to run\b", "还可持续一两年", text, flags=re.IGNORECASE)
    text = re.sub(r"\bno chance\b", "没有机会", text, flags=re.IGNORECASE)
    text = re.sub(r"\btop 10 things to watch\b", "十大关注事项", text, flags=re.IGNORECASE)
    text = re.sub(r"\buntil end of day\b", "直至今日结束", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _local_news_dataset_dir() -> Path:
    env = os.getenv("NEWS_DATASET_DIR", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return (Path(__file__).resolve().parent.parent.parent / "data" / "datasets").resolve()


def _normalize_local_news_item(raw: dict[str, Any], source_file: Path) -> dict[str, Any] | None:
    title = _strip_html(str(raw.get("title") or raw.get("content") or raw.get("summary") or ""))
    if not title:
        return None
    source_id = str(raw.get("source_id") or raw.get("source") or "local-news").strip() or "local-news"
    source_name = str(raw.get("source_name") or raw.get("source") or source_id).strip() or source_id
    url = str(raw.get("url") or "").strip()
    raw_ts = raw.get("pub_ts") or raw.get("published_ts") or raw.get("time") or raw.get("published_at")
    try:
        pub_ts = int(raw_ts or 0)
        if pub_ts and pub_ts < 10_000_000_000:
            pub_ts *= 1000
    except Exception:
        pub_ts = _parse_time(str(raw_ts or "")) or int(source_file.stat().st_mtime * 1000)
    derived_raw = raw.get("derived") if isinstance(raw.get("derived"), dict) else {}
    category = str(raw.get("category") or derived_raw.get("category") or "finance").strip() or "finance"
    tone = str(derived_raw.get("tone") or "").strip()
    if tone not in {"positive", "neutral", "negative"}:
        tone = _tone(title)
    summary = _strip_html(str(raw.get("summary") or raw.get("content") or raw.get("description") or title))
    return {
        "id": str(raw.get("id") or _item_id(source_id, title, url)),
        "source_id": source_id,
        "source_name": source_name,
        "title": title,
        "url": url,
        "pub_ts": pub_ts,
        "region": str(raw.get("region") or "local"),
        "category": category,
        "summary": summary[:1200],
        "derived": {
            "key_info": title[:160],
            "category": category,
            "tone": tone,
            "summary_origin": "local_news_snapshot",
        },
        "local_source_file": source_file.name,
        "local_source_mtime": int(source_file.stat().st_mtime),
    }


def _load_local_news_items(
    *, limit: int, q: str | None = None, source: str | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    base = _local_news_dataset_dir()
    if not base.exists():
        return [], {"ok": False, "reason": "NEWS_DATASET_DIR not found", "dir": str(base)}
    files = sorted(base.glob("news_snapshot_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        files = sorted(base.glob("news_direct_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    ql = str(q or "").strip().lower()
    out: list[dict[str, Any]] = []
    for path in files[:12]:
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue
        rows = data.get("items") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            continue
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            item = _normalize_local_news_item(raw, path)
            if not item:
                continue
            if source and str(item.get("source_id")) != str(source):
                continue
            if ql:
                hay = " ".join(
                    str(item.get(k) or "") for k in ("title", "summary", "source_name", "source_id")
                ).lower()
                if ql not in hay:
                    continue
            out.append(item)
            if len(out) >= max(limit * 4, limit + 20):
                break
        if len(out) >= max(limit * 4, limit + 20):
            break
    info = {
        "ok": bool(out),
        "kind": "local-news-snapshot",
        "dir": str(base),
        "latest_file": files[0].name if files else None,
        "files_scanned": min(len(files), 12),
    }
    if not out:
        info["reason"] = "no local news items"
    return out, info



_TITLE_TRANSLATION_CACHE: dict[str, tuple[float, str]] = {}


def _translation_cache_get(title: str) -> str | None:
    key = title.strip().lower()
    hit = _TITLE_TRANSLATION_CACHE.get(key)
    if not hit:
        return None
    expires_at, value = hit
    if expires_at > time.time():
        return value
    _TITLE_TRANSLATION_CACHE.pop(key, None)
    return None


def _translation_cache_set(title: str, translated: str, ttl: int = 86400) -> None:
    key = title.strip().lower()
    _TITLE_TRANSLATION_CACHE[key] = (time.time() + max(60, ttl), translated)



def _translate_titles_google(titles: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    pending = []
    for title in titles:
        title = str(title or '').strip()
        if not title or _has_chinese(title):
            continue
        cached = _translation_cache_get(title)
        if cached:
            result[title] = cached
        else:
            pending.append(title)
    if not pending:
        return result
    session = requests.Session()
    for title in pending[:40]:
        try:
            resp = session.get(
                'https://translate.googleapis.com/translate_a/single',
                params={'client': 'gtx', 'sl': 'en', 'tl': 'zh-CN', 'dt': 't', 'q': title},
                timeout=4,
            )
            resp.raise_for_status()
            data = resp.json()
            translated = ''.join(part[0] for part in (data[0] or []) if part and part[0]).strip()
            if translated and translated != title:
                result[title] = translated
                _translation_cache_set(title, translated)
        except Exception:
            continue
    return result

def _translate_titles_batch(titles: list[str]) -> dict[str, str]:
    pending = [t for t in titles if t and not _has_chinese(t)]
    pending = [t for t in pending if not _translation_cache_get(t)]
    if not pending:
        return {}
    try:
        from .llm_client import load_ai_config, siliconflow_chat
        conf = load_ai_config()
        api_key = str(conf.get('api_key') or '').strip()
        if not api_key:
            return {}
        prompt = (
            '你是财经新闻标题翻译器。请把下面英文标题翻译成简洁自然的中文。'
            '只返回严格 JSON 对象，格式为 {"items":[{"source":"原文","translated":"中文"}, ...]}。'
            '要求：保留公司名/专有名词/数字/百分比；不要解释，不要扩写，不要输出多余文本。\n\n'
            + '\n'.join(f'- {t}' for t in pending[:20])
        )
        out = siliconflow_chat(
            [
                {'role': 'system', 'content': '你只做标题翻译，输出严格 JSON。'},
                {'role': 'user', 'content': prompt},
            ],
            temperature=0.1,
            route_kind='main',
            route_key='newswatch',
            force_json=True,
        )
        import json as _json
        data = _json.loads(out) if isinstance(out, str) else out
        result: dict[str, str] = {}
        if isinstance(data, dict):
            items = data.get('items') if isinstance(data.get('items'), list) else []
            for row in items:
                if not isinstance(row, dict):
                    continue
                src = str(row.get('source') or '').strip()
                tr = str(row.get('translated') or '').strip()
                if src and tr:
                    result[src] = tr
                    _translation_cache_set(src, tr)
        return result
    except Exception:
        return {}

def _localized_item(item: dict[str, Any]) -> dict[str, Any]:
    title = str(item.get("title") or "")
    title_zh = translate_title_to_zh(title)
    item["title_original"] = title
    item["title_zh"] = title_zh
    if not _has_chinese(title):
        item["title"] = title_zh
    derived = item.get("derived") if isinstance(item.get("derived"), dict) else {}
    derived["key_info"] = title_zh[:160]
    item["derived"] = derived
    return item


def _heat_score(item: dict[str, Any], *, duplicate_count: int = 1, source_count: int = 1) -> float:
    """TrendRadar-style heat score: recency + source weight + cluster resonance + signal words."""
    now_ms = int(time.time() * 1000)
    pub_ts = int(item.get("pub_ts") or 0)
    age_hours = max(0.0, (now_ms - pub_ts) / 3_600_000) if pub_ts else 24.0
    recency = max(0.0, 36.0 - age_hours) / 36.0 * 42.0
    source_id = str(item.get("source_id") or "")
    source_weight = {
        "wallstreetcn-quick": 18,
        "10jqka-stock": 16,
        "sina-finance": 15,
        "bloomberg-markets": 17,
        "cnbc": 14,
        "bbc-business": 11,
        "hackernews": 8,
    }.get(source_id, 10)
    title = str(item.get("title_original") or item.get("title") or "")
    lower = title.lower()
    signal = 0
    if any(k.lower() in lower or k in title for k in _RISK):
        signal += 10
    if any(k.lower() in lower or k in title for k in _OPPORTUNITY):
        signal += 8
    if re.search(r"\d+(?:\.\d+)?\s*%|涨停|跌停|创新高|新高|暴涨|暴跌|surge|plunge|soar|slump", title, re.I):
        signal += 8
    resonance = min(22, max(0, duplicate_count - 1) * 7 + max(0, source_count - 1) * 5)
    score = recency + source_weight + signal + resonance
    return round(max(0.0, min(100.0, score)), 1)


def _cluster_key(title: str) -> str:
    text = str(title or "").lower()
    text = re.sub(r"[\d\.]+[%％]?", "", text)
    words = re.findall(r"[A-Za-z][A-Za-z0-9+.-]{2,}|[\u4e00-\u9fff]{2,6}", text)
    useful = []
    for word in words:
        normalized = word.lower() if re.match(r"^[A-Za-z]", word) else word
        if normalized in _STOPWORDS:
            continue
        useful.append(normalized)
    return "|".join(useful[:4]) or text[:18]


def _category(title: str, source: NewsSource) -> str:
    text = title.lower()
    if any(k in title for k in ("AI", "人工智能", "芯片", "算力", "机器人")) or any(k in text for k in ("ai", "chip", "nvidia", "semiconductor")):
        return "technology"
    if any(k in title for k in ("央行", "利率", "通胀", "汇率", "GDP", "就业")) or any(k in text for k in ("fed", "inflation", "rate", "gdp")):
        return "macro"
    if any(k in title for k in ("A股", "港股", "美股", "债券", "期货")) or any(k in text for k in ("stocks", "market", "shares")):
        return "market"
    return source.category


def _fetch_source(source: NewsSource, timeout: int = 8) -> list[dict[str, Any]]:
    if source.id == "wallstreetcn-quick":
        return _fetch_wallstreetcn(source, timeout=timeout)
    if source.id == "10jqka-stock":
        return _fetch_10jqka(source, timeout=timeout)
    headers = {"User-Agent": "0913-news-engine/1.0 (+rss; lightweight)"}
    resp = requests.get(source.url, timeout=timeout, headers=headers)
    if source.id == "sina-finance":
        resp.encoding = "gb2312"
    text = resp.text
    root = ET.fromstring(text)
    rows: list[dict[str, Any]] = []

    def append_item(title: str, url: str, pub: str, summary: str = "") -> None:
        title = _strip_html(title)
        if not title:
            return
        pub_ts = _parse_time(pub) or int(time.time() * 1000)
        tone = _tone(title)
        category = _category(title, source)
        rows.append({
            "id": _item_id(source.id, title, url),
            "source_id": source.id,
            "source_name": source.name,
            "title": title,
            "url": url,
            "pub_ts": pub_ts,
            "region": source.region,
            "category": category,
            "summary": _strip_html(summary),
            "derived": {
                "key_info": title[:160],
                "category": category,
                "tone": tone,
                "summary_origin": "news_engine",
            },
        })

    for item in root.findall(".//item"):
        append_item(
            item.findtext("title") or "",
            item.findtext("link") or "",
            item.findtext("pubDate") or "",
            item.findtext("description") or "",
        )
    ns = "{http://www.w3.org/2005/Atom}"
    for entry in root.findall(f".//{ns}entry"):
        link_el = entry.find(f"{ns}link")
        append_item(
            entry.findtext(f"{ns}title") or "",
            (link_el.attrib.get("href") if link_el is not None else "") or "",
            entry.findtext(f"{ns}updated") or entry.findtext(f"{ns}published") or "",
            entry.findtext(f"{ns}summary") or "",
        )
    return rows


def _fetch_10jqka(source: NewsSource, timeout: int = 8) -> list[dict[str, Any]]:
    params = {"page": 1, "tag": "", "track": "website", "pagesize": 50}
    headers = {"User-Agent": "Mozilla/5.0 0913-news-engine/1.0"}
    data = requests.get(source.url, params=params, timeout=timeout, headers=headers).json()
    rows: list[dict[str, Any]] = []
    for item in (((data.get("data") or {}).get("list")) or []):
        title = _strip_html(str(item.get("title") or item.get("digest") or ""))
        if not title:
            continue
        digest = _strip_html(str(item.get("digest") or ""))
        url = str(item.get("url") or item.get("link") or "")
        raw_ts = item.get("ctime") or item.get("time") or item.get("rtime") or 0
        try:
            pub_ts = int(raw_ts)
            if pub_ts and pub_ts < 10_000_000_000:
                pub_ts *= 1000
        except Exception:
            pub_ts = int(time.time() * 1000)
        tone = _tone(title)
        category = _category(title, source)
        rows.append({
            "id": str(item.get("id") or item.get("seq") or _item_id(source.id, title, url)),
            "source_id": source.id,
            "source_name": source.name,
            "title": title,
            "url": url,
            "pub_ts": pub_ts,
            "region": source.region,
            "category": category,
            "summary": digest,
            "raw": item,
            "derived": {"key_info": title[:160], "category": category, "tone": tone, "summary_origin": "news_engine"},
        })
    return rows


def _fetch_wallstreetcn(source: NewsSource, timeout: int = 8) -> list[dict[str, Any]]:
    params = {"channel": "global", "limit": 50}
    headers = {"User-Agent": "0913-news-engine/1.0 (+json; lightweight)"}
    data = requests.get(source.url, params=params, timeout=timeout, headers=headers).json()
    rows: list[dict[str, Any]] = []
    for live in (data.get("data", {}).get("items") or []):
        content = _strip_html(str(live.get("content") or ""))
        if not content:
            continue
        title = content[:180]
        ts = live.get("display_time") or live.get("created_at") or live.get("updated_at") or 0
        try:
            pub_ts = int(ts) if isinstance(ts, int) else int(float(ts))
            if pub_ts and pub_ts < 10_000_000_000:
                pub_ts *= 1000
        except Exception:
            pub_ts = int(time.time() * 1000)
        url = ""
        try:
            article = live.get("article") or {}
            url = article.get("uri") or article.get("resource") or ""
        except Exception:
            url = ""
        tone = _tone(title)
        category = _category(title, source)
        rows.append({
            "id": str(live.get("id") or _item_id(source.id, title, url)),
            "source_id": source.id,
            "source_name": source.name,
            "title": title,
            "url": url,
            "pub_ts": pub_ts,
            "region": source.region,
            "category": category,
            "summary": content,
            "derived": {
                "key_info": title[:160],
                "category": category,
                "tone": tone,
                "summary_origin": "news_engine",
            },
        })
    return rows


def list_sources() -> list[dict[str, str]]:
    return [{"id": s.id, "name": s.name, "region": s.region, "category": s.category, "url": s.url} for s in NEWS_SOURCES]


def collect_news(*, limit: int = 80, q: str | None = None, source: str | None = None, force: bool = False) -> dict[str, Any]:
    limit = max(1, min(300, int(limit or 80)))
    cache_key = f"engine:{limit}:{q or ''}:{source or ''}"
    if not force:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    items: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    local_items, local_source = _load_local_news_items(limit=limit, q=q, source=source)
    items.extend(local_items)
    selected = [s for s in NEWS_SOURCES if not source or s.id == source]
    per_source_limit = max(12, min(50, limit))
    remote_enabled = os.getenv("NEWS_REMOTE_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
    if remote_enabled or not items:
        worker_count = min(4, max(1, len(selected)))
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="news-source") as executor:
            future_to_source = {executor.submit(_fetch_source, src): src for src in selected}
            for future in as_completed(future_to_source):
                src = future_to_source[future]
                try:
                    items.extend(future.result()[:per_source_limit])
                except Exception as exc:
                    errors.append({"source_id": src.id, "source_name": src.name, "error": str(exc)[:160]})

    if q:
        query = str(q).strip().lower()
        items = [it for it in items if query in (it.get("title") or "").lower() or query in (it.get("source_name") or "").lower()]

    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    cluster_counts: dict[str, int] = {}
    cluster_sources: dict[str, set[str]] = {}
    for item in items:
        ck = _cluster_key(str(item.get("title") or ""))
        cluster_counts[ck] = cluster_counts.get(ck, 0) + 1
        cluster_sources.setdefault(ck, set()).add(str(item.get("source_id") or ""))

    def _rank_item(item: dict[str, Any]) -> tuple[float, int, int, int]:
        title = str(item.get("title") or "")
        source_id = str(item.get("source_id") or "")
        zh_bonus = 1 if _has_chinese(title) else 0
        cn_bonus = 1 if source_id in {"wallstreetcn-quick", "stcn", "yicai", "caixin", "jiemian"} else 0
        ck = _cluster_key(title)
        item["heat_score"] = _heat_score(item, duplicate_count=cluster_counts.get(ck, 1), source_count=len(cluster_sources.get(ck, set())))
        item["heat_cluster"] = ck
        return (float(item.get("heat_score") or 0), cn_bonus, zh_bonus, int(item.get("pub_ts") or 0))

    for it in sorted(items, key=_rank_item, reverse=True):
        key = str(it.get("id") or it.get("url") or it.get("title"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(_localized_item(it))
        if len(deduped) >= limit:
            break

    online_translation_enabled = os.getenv("NEWS_ONLINE_TRANSLATION_ENABLED", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if online_translation_enabled:
        try:
            english_titles = [
                str(it.get("title_original") or it.get("title") or "")
                for it in deduped
                if str(it.get("title_original") or it.get("title") or "")
                and not _has_chinese(str(it.get("title_original") or it.get("title") or ""))
            ]
            translations = _translate_titles_google(english_titles)
            missing_titles = [title for title in english_titles if title not in translations]
            if missing_titles:
                translations.update(_translate_titles_batch(missing_titles))
            if translations:
                for it in deduped:
                    source_title = str(it.get("title_original") or it.get("title") or "")
                    if source_title in translations:
                        translated = translations[source_title]
                        it["title_zh"] = translated
                        it["title"] = translated
                        derived = it.get("derived") if isinstance(it.get("derived"), dict) else {}
                        derived["key_info"] = translated[:160]
                        it["derived"] = derived
        except Exception:
            pass
    result = {
        "success": True,
        "total": len(deduped),
        "items": deduped,
        "errors": errors,
        "engine": "builtin-trend-radar-lite",
        "source": local_source if local_items else {"ok": bool(deduped), "kind": "remote-news-sources"},
    }
    _cache_set(cache_key, result, ttl=600)
    return result


def _keywords(items: list[dict[str, Any]], top_n: int = 12) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for it in items:
        title = str(it.get("title") or "")
        original = str(it.get("title_original") or "")
        haystack = f"{title} {original}"
        for term in _TOPIC_TERMS:
            if term.lower() in haystack.lower():
                counts[term] = counts.get(term, 0) + 2
        words = re.findall(r"[A-Za-z][A-Za-z0-9+.-]{2,}|[\u4e00-\u9fff]{2,6}", title)
        for word in words:
            normalized = word.lower() if re.match(r"^[A-Za-z]", word) else word
            if normalized in _STOPWORDS or len(normalized) < 2:
                continue
            if any(stop in normalized for stop in _STOPWORDS if len(stop) >= 2):
                continue
            if _has_chinese(normalized) and normalized not in _TOPIC_TERMS and len(normalized) > 4:
                continue
            counts[normalized] = counts.get(normalized, 0) + 1
    return [{"keyword": k, "count": v} for k, v in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:top_n]]


def _alpha_item_text(item: dict[str, Any]) -> str:
    derived = item.get("derived") if isinstance(item.get("derived"), dict) else {}
    return " ".join(
        str(value or "")
        for value in (
            item.get("title"),
            item.get("title_original"),
            item.get("summary"),
            derived.get("key_info"),
        )
    )


def _alpha_direction(items: list[dict[str, Any]]) -> str:
    positive = 0
    negative = 0
    for item in items:
        derived = item.get("derived") if isinstance(item.get("derived"), dict) else {}
        tone = str(derived.get("tone") or "neutral").lower()
        text = _alpha_item_text(item)
        lower = text.lower()
        if tone == "positive":
            positive += 2
        elif tone == "negative":
            negative += 2
        if any(keyword.lower() in lower or keyword in text for keyword in _POSITIVE):
            positive += 1
        if any(keyword.lower() in lower or keyword in text for keyword in _NEGATIVE):
            negative += 1
    if positive > negative:
        return "positive"
    if negative > positive:
        return "negative"
    return "neutral"


def _build_alpha_hypotheses(items: list[dict[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for item in items:
        text = _alpha_item_text(item)
        lower = text.lower()
        for rule in _ALPHA_THEME_RULES:
            if not any(str(keyword).lower() in lower for keyword in rule["keywords"]):
                continue
            bucket = grouped.setdefault(str(rule["theme"]), {"rule": rule, "items": []})
            bucket["items"].append(item)
            break

    hypotheses: list[dict[str, Any]] = []
    for theme, bucket in grouped.items():
        rule = bucket["rule"]
        rows = sorted(
            bucket["items"],
            key=lambda item: (float(item.get("heat_score") or 0), int(item.get("pub_ts") or 0)),
            reverse=True,
        )
        if not rows:
            continue
        direction = _alpha_direction(rows)
        narrative_key = "negative" if direction == "negative" else "positive"
        narrative = rule[narrative_key]
        source_count = len({str(item.get("source_id") or item.get("source_name") or "") for item in rows})
        average_heat = sum(float(item.get("heat_score") or 0) for item in rows) / len(rows)
        confidence = round(
            min(
                92.0,
                38.0
                + min(len(rows), 4) * 7.0
                + min(source_count, 3) * 6.0
                + min(100.0, average_heat) * 0.12,
            ),
            1,
        )
        if direction == "neutral":
            confidence = round(max(35.0, confidence - 10.0), 1)
        focus_label = "潜在受益方向" if direction == "positive" else "重点承压方向" if direction == "negative" else "重点关注方向"
        focus_directions = list(rule["beneficiaries"])
        evidence = [
            {
                "id": str(item.get("id") or ""),
                "title": str(item.get("title") or ""),
                "source_name": str(item.get("source_name") or item.get("source_id") or "未知来源"),
                "url": str(item.get("url") or ""),
                "heat_score": round(float(item.get("heat_score") or 0), 1),
            }
            for item in rows[:3]
        ]
        hypotheses.append(
            {
                "theme": theme,
                "direction": direction,
                "event": str(rows[0].get("title") or ""),
                "transmission": {
                    "demand_supply": narrative["demand_supply"],
                    "earnings": narrative["earnings"],
                    "pricing": narrative["pricing"],
                },
                "focus_label": focus_label,
                "focus_directions": focus_directions,
                "beneficiaries": focus_directions if direction == "positive" else [],
                "validation_signals": list(rule["validation_signals"]),
                "falsifiers": list(rule["falsifiers"]),
                "confidence": confidence,
                "evidence_count": len(rows),
                "source_count": source_count,
                "evidence": evidence,
            }
        )

    hypotheses.sort(
        key=lambda item: (float(item.get("confidence") or 0), int(item.get("evidence_count") or 0)),
        reverse=True,
    )
    return hypotheses[:limit]


def analyze_news(items: list[dict[str, Any]]) -> dict[str, Any]:
    now_ms = int(time.time() * 1000)
    six_h = now_ms - 6 * 3600 * 1000
    day = now_ms - 24 * 3600 * 1000
    tones = {"positive": 0, "neutral": 0, "negative": 0}
    categories: dict[str, int] = {}
    sources: dict[str, int] = {}
    risk_items: list[dict[str, Any]] = []
    opportunity_items: list[dict[str, Any]] = []
    recent_6h = 0
    recent_24h = 0
    for it in items:
        title = str(it.get("title") or "")
        derived = it.get("derived") or {}
        tone = str(derived.get("tone") or "neutral")
        tones[tone if tone in tones else "neutral"] += 1
        categories[str(it.get("category") or derived.get("category") or "other")] = categories.get(str(it.get("category") or derived.get("category") or "other"), 0) + 1
        sources[str(it.get("source_name") or "未知")] = sources.get(str(it.get("source_name") or "未知"), 0) + 1
        pub_ts = int(it.get("pub_ts") or 0)
        if pub_ts >= six_h:
            recent_6h += 1
        if pub_ts >= day:
            recent_24h += 1
        lower = title.lower()
        if any(k.lower() in lower or k in title for k in _RISK):
            risk_items.append(it)
        if any(k.lower() in lower or k in title for k in _OPPORTUNITY):
            opportunity_items.append(it)

    total = len(items)
    sentiment_score = 0 if not total else round((tones["positive"] - tones["negative"]) / total * 100, 1)
    velocity = round(recent_6h / max(1, recent_24h) * 100, 1) if recent_24h else 0
    if velocity >= 45:
        prediction = "热点正在加速扩散，建议进入高频跟踪与交叉验证。"
    elif velocity >= 20:
        prediction = "热度处于稳定上行阶段，适合纳入日内观察池。"
    else:
        prediction = "当前热度偏平稳，优先关注结构性分化与长尾议题。"

    alpha_hypotheses = _build_alpha_hypotheses(items)
    return {
        "total": total,
        "sentiment": tones,
        "sentiment_score": sentiment_score,
        "velocity": velocity,
        "recent_6h": recent_6h,
        "recent_24h": recent_24h,
        "categories": sorted(({"name": k, "count": v} for k, v in categories.items()), key=lambda x: x["count"], reverse=True),
        "sources": sorted(({"name": k, "count": v} for k, v in sources.items()), key=lambda x: x["count"], reverse=True),
        "keywords": _keywords(items),
        "risks": risk_items[:8],
        "opportunities": opportunity_items[:8],
        "hot_items": sorted(items, key=lambda x: float(x.get("heat_score") or 0), reverse=True)[:10],
        "prediction": prediction,
        "analysis_framework": "serenity-alpha-lite",
        "alpha_hypotheses": alpha_hypotheses,
        "alpha_note": "仅形成可跟踪、可验证、可证伪的新闻假设，不构成个股买卖建议。",
    }


def engine_payload(*, limit: int = 80, q: str | None = None, source: str | None = None, force: bool = False) -> dict[str, Any]:
    payload = collect_news(limit=limit, q=q, source=source, force=force)
    items = payload.get("items") or []
    payload["analysis"] = analyze_news(items)
    payload["sources"] = list_sources()
    return payload
