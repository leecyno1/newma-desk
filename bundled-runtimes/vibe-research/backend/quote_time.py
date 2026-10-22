"""Normalize provider quote clocks without substituting retrieval time."""
from datetime import datetime
from zoneinfo import ZoneInfo


def price_as_of(value: str | None, timezone: str) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    for pattern in ('%Y%m%d%H%M%S', '%Y/%m/%d %H:%M:%S', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(value, pattern).replace(tzinfo=ZoneInfo(timezone)).isoformat()
        except ValueError:
            continue
    return None
