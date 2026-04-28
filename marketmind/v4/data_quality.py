"""Data quality checker — adapted from V3.

Phase 1 audit: KEEP the 5-check pattern; switch to shared indicators
(marketmind.v4.indicators) for ATR.

Returns one of: "good" | "stale" | "missing" | "broken".
The mapping aligns with BrainOutput's _VALID_DATA_QUALITY.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Sequence, Tuple

from marketmind.v4.models import Bar
from marketmind.v4.indicators import atr, atr_series


def assess(
    *,
    bars: Sequence[Bar],
    expected_interval_min: int = 15,
    now_utc: Optional[datetime] = None,
) -> Tuple[str, List[str]]:
    warnings: List[str] = []
    if not bars or len(bars) < 5:
        return "missing", ["insufficient_bars"]

    now = now_utc or datetime.now(timezone.utc)

    # 0. Chronological ordering — strict monotonic-increasing timestamps.
    # Any reorder/duplicate makes downstream indicators meaningless ->
    # mark "broken" so permission_engine HARD_BLOCKs.
    for i in range(1, len(bars)):
        if bars[i].timestamp == bars[i - 1].timestamp:
            warnings.append(
                f"duplicate_timestamps:bar_{i}_ts_{bars[i].timestamp}_equals_prev"
            )
            return "broken", warnings
        if bars[i].timestamp < bars[i - 1].timestamp:
            warnings.append(
                f"non_monotonic_timestamps:bar_{i}_ts_{bars[i].timestamp}_"
                f"not_after_bar_{i-1}_ts_{bars[i-1].timestamp}"
            )
            return "broken", warnings

    # 1. Staleness / clock-skew
    last_ts = bars[-1].timestamp
    if last_ts.tzinfo is None:
        last_ts = last_ts.replace(tzinfo=timezone.utc)
    age = (now - last_ts).total_seconds() / 60.0
    if age > expected_interval_min * 2:
        warnings.append(f"stale_data:{int(age)}min")
    if age < -expected_interval_min:
        warnings.append(f"future_dated_bars:{int(-age)}min_ahead")

    # 2. Gaps between consecutive bars
    # FIX 2026-04-28: skip price-gap checks across market-closure boundaries
    # (weekends, holidays). A bar pair whose timestamp delta exceeds the
    # expected interval is a market-closed transition; price gap there is
    # expected and not "unexplained". Only flag intra-session gaps.
    a = atr(bars)
    gaps = 0
    for i in range(1, len(bars)):
        time_gap_min = (bars[i].timestamp - bars[i - 1].timestamp).total_seconds() / 60.0
        if time_gap_min > expected_interval_min * 1.5:
            continue  # weekend/holiday boundary — expected
        gap = abs(bars[i].open - bars[i - 1].close)
        if a > 0 and gap > 0.5 * a:
            gaps += 1
    if gaps >= 2:
        warnings.append(f"unexplained_gaps:{gaps}")

    # 3. Spread anomalies
    spreads = [b.spread_pips for b in bars if b.spread_pips is not None and b.spread_pips > 0]
    if spreads:
        avg_spread = sum(spreads) / len(spreads)
        cur_spread = bars[-1].spread_pips or avg_spread
        if avg_spread > 0 and cur_spread > 3 * avg_spread:
            warnings.append(f"wide_spread:{cur_spread:.2f}pips_vs_{avg_spread:.2f}avg")

    # 4. ATR extreme vs its history
    series = atr_series(bars)
    if series and len(series) >= 5:
        baseline = sorted(series)[-max(1, len(series) // 20)]   # rough p95
        if baseline > 0 and a > 2.5 * baseline:
            warnings.append(f"atr_extreme:{a/baseline:.1f}x_baseline")

    # 5. Volume drought
    if len(bars) >= 10:
        zero_vol = sum(1 for b in bars[-10:] if (b.volume or 0) == 0)
        if zero_vol >= 5:
            warnings.append(f"low_volume:{zero_vol}/10_bars_zero")

    if not warnings:
        return "good", []
    if len(warnings) == 1:
        return "stale", warnings
    if len(warnings) == 2:
        return "stale", warnings
    return "broken", warnings
