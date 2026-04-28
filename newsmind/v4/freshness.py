"""NewsMind V4 — freshness detector.

KEEP from V3 (per audit), with imports adapted to V4 layout.

Definition (V4 thresholds):
  fresh    : age <= 5 min
  recent   : 5 min  < age <= 30 min
  stale    : 30 min < age <= 6 h
  expired  : age > 6 h
  missing  : no item / no timestamp

The classifier is conservative: an item with no parseable timestamp is
treated as `missing` (NOT as `fresh`). This kills a known V3 leak where
items without pubDate were silently treated as 'just arrived'.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from newsmind.v4.models import NewsItem


FRESH_SECONDS = 5 * 60
RECENT_SECONDS = 30 * 60
STALE_SECONDS = 6 * 60 * 60


@dataclass
class FreshnessReport:
    status: str           # "fresh" | "recent" | "stale" | "expired" | "missing"
    age_seconds: Optional[float]


def classify(item: Optional[NewsItem], now_utc: datetime) -> FreshnessReport:
    if item is None or item.normalized_utc_time is None:
        return FreshnessReport(status="missing", age_seconds=None)
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be tz-aware UTC")
    age = (now_utc - item.normalized_utc_time).total_seconds()
    if age < 0:
        # Item from the future → suspicious. Treat as fresh but the
        # orchestrator will see negative news_age_seconds and can flag it.
        return FreshnessReport(status="fresh", age_seconds=age)
    if age <= FRESH_SECONDS:
        return FreshnessReport(status="fresh", age_seconds=age)
    if age <= RECENT_SECONDS:
        return FreshnessReport(status="recent", age_seconds=age)
    if age <= STALE_SECONDS:
        return FreshnessReport(status="stale", age_seconds=age)
    return FreshnessReport(status="expired", age_seconds=age)
