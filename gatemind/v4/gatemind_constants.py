"""GateMind V4 — locked constants.

Every named constant lives here. NO magic literals scattered across modules.

LOCKED v1.0 — changing any of these requires a re-audit. The kill-flag list,
NY windows, and grade thresholds are the entire reason GateMind exists; they
are the LAST line of defense before a real broker call.
"""

from __future__ import annotations

from typing import FrozenSet, Tuple

# ----------------------------------------------------------------------------
# New York trading windows (LOCAL NY time, IANA America/New_York, DST-aware)
# ----------------------------------------------------------------------------
# Two windows: pre-Frankfurt/London overlap and full NY morning.
#   Window 1: 03:00 - 05:00 NY  (pre-open / Frankfurt → London handoff)
#   Window 2: 08:00 - 12:00 NY  (NY morning, into lunch)
NY_TIMEZONE: str = "America/New_York"
NY_WINDOWS: Tuple[Tuple[int, int], ...] = ((3, 5), (8, 12))

WINDOW_LABELS = {
    (3, 5): "in_window_pre_open",
    (8, 12): "in_window_morning",
}
OUTSIDE_WINDOW_LABEL: str = "outside_window"

# ----------------------------------------------------------------------------
# Grade threshold — only A and A+ pass
# ----------------------------------------------------------------------------
ALLOWED_GRADES: FrozenSet[str] = frozenset({"A", "A+"})

# ----------------------------------------------------------------------------
# Risk flag classification (LOCKED v1.0)
# ----------------------------------------------------------------------------
KILL_CLASS_FLAGS: FrozenSet[str] = frozenset({
    "news_blackout",
    "data_broken",
    "feed_dead",
    "circuit_breaker",
    "news_silent_or_unclear",
})

WARNING_CLASS_FLAGS: FrozenSet[str] = frozenset({
    "stale_feed_minor",
    "spread_anomaly",
    "low_liquidity",
})

# ----------------------------------------------------------------------------
# Brain identity — exactly three brains feed GateMind
# ----------------------------------------------------------------------------
REQUIRED_BRAINS: Tuple[str, ...] = ("NewsMind", "MarketMind", "ChartMind")
REQUIRED_BRAIN_KEYS: Tuple[str, ...] = ("newsmind", "marketmind", "chartmind")

# ----------------------------------------------------------------------------
# Decisions accepted from upstream brains
# ----------------------------------------------------------------------------
DIRECTIONAL_DECISIONS: FrozenSet[str] = frozenset({"BUY", "SELL"})
WAIT_DECISION: str = "WAIT"
BLOCK_DECISION: str = "BLOCK"

# ----------------------------------------------------------------------------
# Model version — bump on any rule change
# ----------------------------------------------------------------------------
MODEL_VERSION: str = "gatemind-v4.0"
GATE_NAME: str = "GateMind"

# ----------------------------------------------------------------------------
# Audit cache cap — session-scoped only. Persistent audit is SmartNoteBook V4.
# ----------------------------------------------------------------------------
MAX_AUDIT_ENTRIES: int = 10_000

# ----------------------------------------------------------------------------
# Blocking reason codes (canonical strings used in tests + downstream routing)
# ----------------------------------------------------------------------------
REASON_SCHEMA_INVALID: str = "schema_invalid"
REASON_OUTSIDE_NY: str = "outside_new_york_trading_window"
REASON_GRADE_BELOW: str = "grade_below_threshold"
REASON_BRAIN_BLOCK: str = "brain_block"
REASON_KILL_FLAG: str = "kill_flag_active"
REASON_DIRECTIONAL_CONFLICT: str = "directional_conflict"
REASON_INCOMPLETE_AGREEMENT: str = "incomplete_agreement"
REASON_UNANIMOUS_WAIT: str = "unanimous_wait"
REASON_PARTIAL_DEFAULT: str = "partial_state_default"
REASON_APPROVED: str = "all_brains_unanimous_enter"
