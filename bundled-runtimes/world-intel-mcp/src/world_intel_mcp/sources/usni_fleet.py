"""USNI News Fleet and Marine Tracker source for world-intel-mcp.

Parses the USNI Fleet Tracker RSS feed for US Navy fleet disposition,
extracting carrier strike groups, ship deployments, and force posture.
No API key required — uses the public RSS category feed.
"""

import logging
import re
from html import unescape

from ..fetcher import Fetcher
from ..source_time import parse_rss_time, source_cache_timing

try:
    import feedparser
except ImportError:
    feedparser = None  # type: ignore[assignment]

logger = logging.getLogger("world-intel-mcp.sources.usni_fleet")

_FEED_URL = "https://news.usni.org/category/fleet-tracker/feed"

# Regex patterns for extracting fleet data from article content
_SHIP_PATTERN = re.compile(
    r"USS\s+([\w\s.'’\-]+?)\s*\(((?:CVN|DDG|CG|LHD|LHA|LPD|LSD|SSN|SSBN|SSGN|FFG|MCM|PC|AS|ESB|ESD|EPF|AFSB|T-AO|T-AKE|T-ESB|WAGB|LCS)[-\s]*\d+)\)",
    re.IGNORECASE,
)
_USCG_PATTERN = re.compile(
    r"USCGC\s+([\w\s.'’\-]+?)\s*\(((?:WAGB|WMSL|WPC|WPB|WLB)[-\s]*\d+)\)",
    re.IGNORECASE,
)
_CSG_PATTERN = re.compile(
    r"Carrier Strike Group\s+(\d+|[A-Z]+)",
    re.IGNORECASE,
)
_ESG_PATTERN = re.compile(
    r"(?:Expeditionary Strike Group|Amphibious Ready Group)\s+(\d+|[A-Z]+)",
    re.IGNORECASE,
)
_BATTLE_FORCE_PATTERN = re.compile(
    r"(\d+)\s+ships?\s*\((\d+)\s+USS,\s*(\d+)\s+USNS\)",
    re.IGNORECASE,
)
_DEPLOYED_PATTERN = re.compile(
    r"(\d+)\s+deployed\s*\((\d+)\s+USS,\s*(\d+)\s+USNS\)",
    re.IGNORECASE,
)
_UNDERWAY_PATTERN = re.compile(
    r"(\d+)\s+underway\s*\((\d+)\s+deployed,\s*(\d+)\s+local\)",
    re.IGNORECASE,
)

# Region keywords for location classification
_REGION_KEYWORDS = {
    "Arabian Sea": "CENTCOM",
    "Persian Gulf": "CENTCOM",
    "Red Sea": "CENTCOM",
    "Gulf of Oman": "CENTCOM",
    "Gulf of Aden": "CENTCOM",
    "Mediterranean": "EUCOM",
    "Atlantic": "EUCOM",
    "North Sea": "EUCOM",
    "Baltic": "EUCOM",
    "Caribbean": "SOUTHCOM",
    "Pacific": "INDOPACOM",
    "Philippine Sea": "INDOPACOM",
    "South China Sea": "INDOPACOM",
    "East China Sea": "INDOPACOM",
    "Western Pacific": "INDOPACOM",
    "Japan": "INDOPACOM",
    "Yokosuka": "INDOPACOM",
    "Guam": "INDOPACOM",
    "Indian Ocean": "INDOPACOM",
    "Antarctica": "OTHER",
    "Arctic": "NORTHCOM",
    "San Diego": "HOMEPORT",
    "Norfolk": "HOMEPORT",
    "Mayport": "HOMEPORT",
    "Bremerton": "HOMEPORT",
}


def _classify_region(text: str) -> str:
    """Classify a text snippet into a combatant command region."""
    for keyword, region in _REGION_KEYWORDS.items():
        if keyword.lower() in text.lower():
            return region
    return "UNKNOWN"


def _extract_fleet_data(content: str) -> dict:
    """Extract structured fleet disposition from article HTML/text content."""
    ships = []
    strike_groups = []

    # Extract USS ships
    for match in _SHIP_PATTERN.finditer(content):
        name = match.group(1).strip()
        hull = re.sub(r"[-\s]*(\d+)$", r"-\1", match.group(2).upper())
        # Find surrounding context for region classification
        start = max(0, match.start() - 200)
        end = min(len(content), match.end() + 200)
        context = content[start:end]
        region = _classify_region(context)

        ship_type = hull.split("-")[0] if "-" in hull else hull[:3]
        type_labels = {
            "CVN": "Aircraft Carrier",
            "DDG": "Destroyer",
            "CG": "Cruiser",
            "LHD": "Amphibious Assault Ship",
            "LHA": "Amphibious Assault Ship",
            "LPD": "Amphibious Transport Dock",
            "LSD": "Dock Landing Ship",
            "SSN": "Attack Submarine",
            "SSBN": "Ballistic Missile Submarine",
            "SSGN": "Guided Missile Submarine",
            "FFG": "Frigate",
            "LCS": "Littoral Combat Ship",
            "MCM": "Mine Countermeasure",
            "ESB": "Expeditionary Sea Base",
            "ESD": "Expeditionary Transfer Dock",
            "EPF": "Expeditionary Fast Transport",
        }

        ships.append({
            "name": f"USS {name}",
            "hull_number": hull,
            "type": type_labels.get(ship_type, ship_type),
            "region": region,
        })

    # Extract USCG cutters
    for match in _USCG_PATTERN.finditer(content):
        name = match.group(1).strip()
        hull = re.sub(r"[-\s]*(\d+)$", r"-\1", match.group(2).upper())
        start = max(0, match.start() - 200)
        end = min(len(content), match.end() + 200)
        context = content[start:end]
        region = _classify_region(context)
        ships.append({
            "name": f"USCGC {name}",
            "hull_number": hull,
            "type": "Coast Guard Cutter",
            "region": region,
        })

    # Extract carrier strike groups
    for match in _CSG_PATTERN.finditer(content):
        strike_groups.append({"name": f"CSG-{match.group(1)}", "type": "Carrier Strike Group"})

    for match in _ESG_PATTERN.finditer(content):
        strike_groups.append({"name": f"ESG-{match.group(1)}", "type": "Expeditionary Strike Group"})

    # Extract force totals
    force_totals = {}
    bf = _BATTLE_FORCE_PATTERN.search(content)
    if bf:
        force_totals["battle_force"] = {
            "total": int(bf.group(1)),
            "uss": int(bf.group(2)),
            "usns": int(bf.group(3)),
        }
    dep = _DEPLOYED_PATTERN.search(content)
    if dep:
        force_totals["deployed"] = {
            "total": int(dep.group(1)),
            "uss": int(dep.group(2)),
            "usns": int(dep.group(3)),
        }
    uw = _UNDERWAY_PATTERN.search(content)
    if uw:
        force_totals["underway"] = {
            "total": int(uw.group(1)),
            "deployed": int(uw.group(2)),
            "local": int(uw.group(3)),
        }

    # Deduplicate ships by hull number
    seen_hulls: set[str] = set()
    unique_ships = []
    for ship in ships:
        if ship["hull_number"] not in seen_hulls:
            seen_hulls.add(ship["hull_number"])
            unique_ships.append(ship)

    # Region breakdown
    region_counts: dict[str, int] = {}
    for ship in unique_ships:
        r = ship["region"]
        region_counts[r] = region_counts.get(r, 0) + 1

    return {
        "ships": unique_ships,
        "ship_count": len(unique_ships),
        "strike_groups": strike_groups,
        "force_totals": force_totals,
        "region_breakdown": region_counts,
        "region_basis": "article_context_heuristic",
    }


async def fetch_usni_fleet(fetcher: Fetcher) -> dict:
    """Fetch latest USNI Fleet Tracker disposition.

    Parses the USNI News Fleet Tracker RSS feed for the most recent
    weekly fleet disposition report. Extracts ship names, hull numbers,
    strike groups, regions, and force totals.

    Returns:
        Dict with ships[], strike_groups[], force_totals, region_breakdown,
        report_date, report_url, source, timestamp.
    """
    cache_key = "usni:fleet_tracker_rss"
    def unavailable(message: str) -> dict:
        timing = source_cache_timing(fetcher.cache, cache_key)
        return {"status": "unavailable", "error": message, "ships": [],
                "ship_count": None, "source": "usni-fleet-tracker",
                **timing, "timestamp": timing["collected_at"]}

    if feedparser is None:
        return unavailable("USNI 报告解析依赖未安装")

    xml = await fetcher.get_text(
        _FEED_URL,
        source="usni-fleet-tracker",
        cache_key=cache_key,
        cache_ttl=3600,  # Weekly updates, cache for 1 hour
    )

    if not xml:
        return unavailable("USNI 舰队报告暂时不可用，不能据此判断没有舰艇")

    feed = feedparser.parse(xml)

    entries = [entry for entry in feed.entries
               if re.search(r"\bfleet(?:\s+and\s+marine)?\s+tracker\b", entry.get("title", ""), re.I)]
    if not entries:
        return unavailable("USNI 来源未返回可识别的舰队报告")

    # RSS order is not guaranteed; never replace publication with collection time.
    entry = max(entries, key=lambda item: parse_rss_time(item) or "")
    title = entry.get("title", "")
    link = entry.get("link", "")
    published = parse_rss_time(entry)

    # Try content:encoded first (full article), fall back to summary
    content = ""
    content_basis = "full_content"
    if hasattr(entry, "content") and entry.content:
        content = entry.content[0].get("value", "")
    if not content:
        content = entry.get("summary", entry.get("description", ""))
        content_basis = "summary"

    # Strip HTML tags for cleaner regex matching
    clean_content = unescape(re.sub(r"<[^>]+>", " ", content))
    clean_content = re.sub(r"\s+", " ", clean_content)

    fleet_data = _extract_fleet_data(clean_content)
    # No match is a parsing/coverage gap, not evidence of an empty fleet.
    if not fleet_data["ships"]:
        fleet_data["ship_count"] = None
    timing = source_cache_timing(fetcher.cache, cache_key)

    return {
        **fleet_data,
        "status": "partial" if content_basis == "summary" or not fleet_data["ships"] or not published else "ok",
        "content_basis": content_basis,
        "coverage_note": "仅统计报告文本识别出的舰艇；区域为邻近文本推断，非实时位置或完整部署清单",
        "report_title": title,
        "report_url": link,
        "report_date": published,
        "report_date_raw": entry.get("published") if "published" in entry else None,
        "source": "usni-fleet-tracker",
        **timing,
        "timestamp": timing["collected_at"],
    }
