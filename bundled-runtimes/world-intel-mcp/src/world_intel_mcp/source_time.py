"""Source dates and successful collection time are separate evidence."""

import calendar
from datetime import datetime, timezone

from .cache import Cache


def parse_rss_time(entry: dict, field: str = "published") -> str | None:
    # feedparser tuples are UTC. mktime would apply the server's local timezone.
    # Membership checks also avoid FeedParserDict aliasing 'published' to 'updated'.
    parsed_field = f"{field}_parsed"
    parsed = entry.get(parsed_field) if parsed_field in entry else None
    if parsed is None:
        return None
    try:
        return datetime.fromtimestamp(calendar.timegm(parsed[:9]), timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError, OverflowError):
        return None


def source_cache_timing(cache: Cache, key: str) -> dict:
    """Use this exact cache entry, not the newest entry of a multi-feed source."""
    now = datetime.now(timezone.utc)
    timing = cache.entry_timing(key)
    def iso(epoch: float) -> str:
        return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "collected_at": iso(timing["created_at"]) if timing else None,
        "cache_expires_at": iso(timing["expires_at"]) if timing else None,
        "checked_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "freshness": ("stale" if now.timestamp() > timing["expires_at"] else "fresh") if timing else "unknown",
    }
