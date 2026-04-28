"""Price-data validator — fail-CLOSED on missing/stale/duplicate/invalid bars.

This is the FIRST gate in ChartMindV4.evaluate(). If it returns "broken" or
"missing" the orchestrator emits BLOCK and never touches indicators.

A bar is INVALID at the model layer (`marketmind.v4.models.Bar.__post_init__`
already rejects NaN/Inf, high<low, non-positive close). This validator
deals with SEQUENCE-level issues:
    - too few bars
    - duplicate timestamps
    - non-monotonic timestamps
    - last bar age > MAX_STALE_MINUTES vs now
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Sequence, Tuple

from marketmind.v4.models import Bar

from chartmind.v4.chart_thresholds import (
    MIN_BARS_FOR_EVALUATION,
    MAX_STALE_MINUTES,
)


def assess(
    bars: Sequence[Bar],
    *,
    now_utc: datetime,
) -> Tuple[str, List[str]]:
    """Return (status, warnings).

    status in {"good", "stale", "missing", "broken"}.
    """
    warnings: List[str] = []

    if not bars:
        return "missing", ["no_bars"]

    if len(bars) < MIN_BARS_FOR_EVALUATION:
        return "missing", [f"too_few_bars:{len(bars)}<{MIN_BARS_FOR_EVALUATION}"]

    # Duplicate timestamps?
    ts_set = set()
    for b in bars:
        if b.timestamp in ts_set:
            warnings.append(f"duplicate_timestamp:{b.timestamp.isoformat()}")
        ts_set.add(b.timestamp)
    if any(w.startswith("duplicate_timestamp") for w in warnings):
        return "broken", warnings

    # Monotonic strictly increasing?
    for i in range(1, len(bars)):
        if bars[i].timestamp <= bars[i - 1].timestamp:
            warnings.append(
                f"non_monotonic_timestamps:{bars[i - 1].timestamp.isoformat()}"
                f"->{bars[i].timestamp.isoformat()}"
            )
            return "broken", warnings

    # Stale check
    if now_utc.tzinfo is None:
        # caller bug — treat as broken so we never silently skip the check
        return "broken", ["now_utc_naive"]
    last_age_min = (now_utc - bars[-1].timestamp).total_seconds() / 60.0
    if last_age_min > MAX_STALE_MINUTES:
        warnings.append(f"stale_last_bar_age_min={last_age_min:.1f}")
        return "stale", warnings
    if last_age_min < 0:
        warnings.append(f"future_last_bar_age_min={last_age_min:.1f}")
        return "broken", warnings

    return "good", warnings
