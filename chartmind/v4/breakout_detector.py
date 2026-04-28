"""Breakout detection — Wyckoff body-close + 0.3×ATR confirmation.

KEEP from V3 with strict adaptation per Phase 1 audit:
RULE 3 (real breakout, long):
    body_close > level + 0.3 × ATR
    AND body/range >= 0.5
    AND close in upper 30% of bar (loc >= 0.7)
RULE 4 (fake breakout):
    wick exceeds level but close returns within level same bar
    OR any of next 3 bars close back inside (only checkable if look-ahead is allowed
    by the orchestrator at evaluation index N-1; we DO NOT peek beyond `bars`)

The detector is given `bars` ending at the evaluation moment (no future).
"Next 3 bars" rule is enforced by the orchestrator only when we evaluate
historical breakouts; for the current bar (index = -1) we can only judge
the SAME-bar fake (wick exceeded, close returned).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from marketmind.v4.models import Bar

from chartmind.v4.chart_thresholds import (
    BREAKOUT_CONFIRM_ATR,
    BREAKOUT_BODY_RATIO_MIN,
    BREAKOUT_CLOSE_LOC_MIN,
    FAKE_BREAKOUT_LOOKAHEAD,
)


@dataclass
class BreakoutResult:
    is_breakout: bool
    direction: str            # "long" | "short" | "none"
    is_fake: bool
    bar_index: int            # index of the breakout bar in `bars`
    level: float
    reason: str


def _body_ratio(bar: Bar) -> float:
    rng = bar.high - bar.low
    if rng <= 0:
        return 0.0
    return abs(bar.close - bar.open) / rng


def _close_loc(bar: Bar) -> float:
    """Position of close within range, 0 (low) .. 1 (high)."""
    rng = bar.high - bar.low
    if rng <= 0:
        return 0.5
    return (bar.close - bar.low) / rng


def detect_breakout(bars: Sequence[Bar],
                    *,
                    level: float,
                    atr_value: float,
                    side: str,
                    confirm_index: Optional[int] = None) -> BreakoutResult:
    """Detect a real breakout against `level` for `side` ("long"|"short").

    `confirm_index` defaults to the last bar. Same-bar fake (wick exceeds,
    close returns) is checked. Multi-bar fake (next 3 close back inside)
    is checked iff bars beyond `confirm_index` are present.
    """
    if not bars or atr_value <= 0 or side not in ("long", "short"):
        return BreakoutResult(False, "none", False, -1, level, "no_inputs")
    idx = confirm_index if confirm_index is not None else len(bars) - 1
    if idx < 0 or idx >= len(bars):
        return BreakoutResult(False, "none", False, -1, level, "bad_index")
    bar = bars[idx]

    threshold = BREAKOUT_CONFIRM_ATR * atr_value

    if side == "long":
        clear = bar.close >= level + threshold
        loc_ok = _close_loc(bar) >= BREAKOUT_CLOSE_LOC_MIN
        body_ok = _body_ratio(bar) >= BREAKOUT_BODY_RATIO_MIN
        # Same-bar fake: high pierced level but close came back inside
        same_bar_fake = (bar.high > level) and (bar.close < level)
    else:
        clear = bar.close <= level - threshold
        loc_ok = _close_loc(bar) <= (1.0 - BREAKOUT_CLOSE_LOC_MIN)
        body_ok = _body_ratio(bar) >= BREAKOUT_BODY_RATIO_MIN
        same_bar_fake = (bar.low < level) and (bar.close > level)

    if same_bar_fake and not clear:
        return BreakoutResult(
            is_breakout=False,
            direction=side,
            is_fake=True,
            bar_index=idx,
            level=level,
            reason="same_bar_fake_wick_exceeds_close_returns",
        )

    if not (clear and loc_ok and body_ok):
        return BreakoutResult(
            is_breakout=False,
            direction=side,
            is_fake=False,
            bar_index=idx,
            level=level,
            reason=f"clear={clear} loc_ok={loc_ok} body_ok={body_ok}",
        )

    # Multi-bar fake — only if we have look-ahead bars after idx
    follow = bars[idx + 1: idx + 1 + FAKE_BREAKOUT_LOOKAHEAD]
    if follow:
        if side == "long":
            returned = any(b.close < level for b in follow)
        else:
            returned = any(b.close > level for b in follow)
        if returned:
            return BreakoutResult(
                is_breakout=True,
                direction=side,
                is_fake=True,
                bar_index=idx,
                level=level,
                reason=f"failed_followthrough_within_{FAKE_BREAKOUT_LOOKAHEAD}_bars",
            )

    return BreakoutResult(
        is_breakout=True,
        direction=side,
        is_fake=False,
        bar_index=idx,
        level=level,
        reason="confirmed",
    )


def find_recent_breakout(bars: Sequence[Bar],
                         *,
                         level: float,
                         atr_value: float,
                         side: str,
                         lookback: int = 20) -> BreakoutResult:
    """Scan the last `lookback` bars for a real breakout against `level`.

    Returns the FIRST breakout found (oldest within window) so retest tests
    can run. Multi-bar-fake check uses bars after the breakout, capped by
    the window — i.e. no peeking into the future relative to `bars[-1]`.
    """
    if not bars:
        return BreakoutResult(False, "none", False, -1, level, "no_bars")
    start = max(0, len(bars) - lookback)
    for i in range(start, len(bars)):
        r = detect_breakout(bars, level=level, atr_value=atr_value, side=side, confirm_index=i)
        if r.is_breakout:
            return r
    return BreakoutResult(False, side, False, -1, level, "no_breakout_in_window")
