"""NewsMind V4 — domain models.

V4 schema deltas vs V3 (per audit):
  KEEP: trade_permission, reason, grade, confidence, headline, source_name,
        source_type, freshness_status, news_age_seconds, impact_level,
        market_bias, risk_mode, affected_assets, confirmation_count,
        is_scheduled_event, event_id, pre/post_event_window,
        normalized_utc_time
  DROP: published_at, received_at, conflicting_sources, sources_checked
  ADD : eur_usd_dir, usd_jpy_dir, surprise_score, blackout_reason,
        source_health
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# pair normalization
# ---------------------------------------------------------------------------


_PAIR_STRIP_CHARS = ("/", "-", "_", " ")
_PAIR_RE = re.compile(r"^[A-Z]{6}$")


def _normalize_pair(pair: str) -> str:
    """Normalize a pair string by stripping separators and uppercasing.

    Accepts forms like "EUR/USD", "EUR-USD", "EUR_USD", "eur usd", "EURUSD".
    Validates the normalized form against ^[A-Z]{6}$ and raises ValueError if
    the input cannot be reduced to a clean 6-letter pair code.
    """
    if not isinstance(pair, str):
        raise ValueError(f"invalid pair format: {pair!r} (not a string)")
    s = pair
    for ch in _PAIR_STRIP_CHARS:
        s = s.replace(ch, "")
    s = s.upper()
    if not _PAIR_RE.match(s):
        raise ValueError(f"invalid pair format: {pair!r}")
    return s


# ---------------------------------------------------------------------------
# raw inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NewsItem:
    """Single piece of raw news as fetched from a source."""

    headline: str
    source_name: str           # e.g. "federalreserve.gov"
    source_type: str           # "authoritative" | "tier1" | "calendar" | "social"
    normalized_utc_time: datetime  # tz-aware UTC parsed publish time
    url: Optional[str] = None
    body: Optional[str] = None

    def __post_init__(self) -> None:
        if self.normalized_utc_time.tzinfo is None:
            raise ValueError("normalized_utc_time must be tz-aware")


# ---------------------------------------------------------------------------
# scheduled events (loaded from events.yaml)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EventSchedule:
    id: str
    name: str
    currency: str
    affects: List[str]
    blackout_pre_min: int
    blackout_post_min: int
    pip_per_sigma: Dict[str, float]
    tier: int

    def affects_pair(self, pair: str) -> bool:
        target = _normalize_pair(pair)
        return target in {_normalize_pair(p) for p in self.affects}


# ---------------------------------------------------------------------------
# source health
# ---------------------------------------------------------------------------


@dataclass
class SourceHealth:
    """Per-source telemetry. Surfaced in NewsVerdict so a downstream auditor
    can see at a glance whether silence means 'all clear' or 'feed broken'.
    """

    source_name: str
    last_fetch_utc: Optional[datetime] = None
    last_status: str = "unknown"       # "ok" | "timeout" | "parse_error" | "empty" | "http_error"
    consecutive_failures: int = 0

    def record_ok(self, now_utc: datetime) -> None:
        self.last_fetch_utc = now_utc
        self.last_status = "ok"
        self.consecutive_failures = 0

    def record_failure(self, now_utc: datetime, status: str) -> None:
        self.last_fetch_utc = now_utc
        self.last_status = status
        self.consecutive_failures += 1


# ---------------------------------------------------------------------------
# verdicts
# ---------------------------------------------------------------------------


@dataclass
class NewsSummary:
    """Aggregated picture of the news landscape at evaluation time."""

    items: List[NewsItem] = field(default_factory=list)
    confirmation_count: int = 0          # how many distinct authoritative+tier1 hits agree
    is_scheduled_event: bool = False
    active_event_id: Optional[str] = None
    pre_event_window: bool = False
    post_event_window: bool = False
    impact_level: str = "low"            # "low" | "medium" | "high" | "extreme"
    market_bias: str = "neutral"         # "bullish_usd" | "bearish_usd" | etc.
    risk_mode: str = "normal"            # "normal" | "risk_off" | "risk_on"
    affected_assets: List[str] = field(default_factory=list)


@dataclass
class NewsVerdict:
    """Full V4 verdict. Companion to BrainOutput — BrainOutput is the *contract*,
    NewsVerdict is the news-specific detail an auditor or downstream router
    might want to inspect.

    The NewsMindV4 orchestrator emits BOTH: BrainOutput (contract) and
    NewsVerdict (detail). NewsVerdict ⊂ artifact. BrainOutput ⊂ contract.
    """

    # KEEP fields
    trade_permission: str          # "ENTER" | "WAIT" | "BLOCK"
    reason: str
    grade: str                     # "A+" | "A" | "B" | "C" | "BLOCK"
    confidence: float
    headline: Optional[str]        # the most relevant headline driving the verdict
    source_name: Optional[str]
    source_type: Optional[str]
    freshness_status: str          # "fresh" | "stale" | "expired" | "missing"
    news_age_seconds: Optional[float]
    impact_level: str
    market_bias: str
    risk_mode: str
    affected_assets: List[str]
    confirmation_count: int
    is_scheduled_event: bool
    event_id: Optional[str]
    pre_event_window: bool
    post_event_window: bool
    normalized_utc_time: Optional[datetime]

    # ADD fields (V4)
    eur_usd_dir: str = "neutral"   # "long" | "short" | "neutral"
    usd_jpy_dir: str = "neutral"
    surprise_score: float = 0.0    # in sigma units; 0 if no scheduled actual/consensus pair
    blackout_reason: Optional[str] = None
    source_health: Dict[str, SourceHealth] = field(default_factory=dict)
