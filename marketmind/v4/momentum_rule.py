"""MOMENTUM_RULE — distance-from-EMA / ATR delta + extreme divergence.

Spec (Phase 1 audit):
  Define m_i = |close_i - EMA(20)_i| / ATR(14)_i  (a normalized stretch).
  accelerating: m increased on 3 consecutive bars AND in trend direction
  fading:       m decreased on 3 consecutive bars
  divergent:    price made a new 20-bar extreme but momentum (m) did NOT
  steady:       otherwise (or insufficient signal)
  none:         not enough bars

Trend direction is approximated locally as sign(close_i - EMA(20)_i).
"""
from __future__ import annotations

from typing import Sequence, Tuple, Dict, Any, List

from marketmind.v4.models import Bar
from marketmind.v4.indicators import (
    ATR_PERIOD, EMA_PERIOD, HH_HL_WINDOW,
    atr_series,
)


def _ema_series(values: Sequence[float], period: int) -> List[float]:
    """Return EMA value at each step i, starting at the first index where it's defined."""
    out: List[float] = []
    if len(values) < period:
        return out
    alpha = 2.0 / (period + 1.0)
    val = sum(values[:period]) / period
    out.append(val)
    for v in values[period:]:
        val = alpha * v + (1 - alpha) * val
        out.append(val)
    return out


def evaluate(bars: Sequence[Bar]) -> Tuple[str, Dict[str, Any]]:
    """Return (momentum_state, evidence_dict)."""
    ev: Dict[str, Any] = {"rule": "MOMENTUM_RULE"}
    needed = max(EMA_PERIOD, ATR_PERIOD + 1, HH_HL_WINDOW + 1) + 4
    if len(bars) < needed:
        ev["reason"] = f"insufficient_bars({len(bars)}<{needed})"
        return "none", ev

    closes = [b.close for b in bars]

    # Aligned series: ema and atr both start at index >= EMA_PERIOD-1 / ATR_PERIOD.
    # Use the shared `atr_series` from `marketmind.v4.indicators` — single source
    # of truth (Phase-1 audit lock); do NOT re-implement Wilder smoothing here.
    ema_ser = _ema_series(closes, EMA_PERIOD)         # len = len(closes) - EMA_PERIOD + 1
    atr_ser = atr_series(bars, ATR_PERIOD)            # len = len(bars) - ATR_PERIOD

    if len(ema_ser) < 4 or len(atr_ser) < 4:
        ev["reason"] = "insufficient_series"
        return "none", ev

    # Align tail: take last K where both available
    K = min(len(ema_ser), len(atr_ser))
    ema_tail = ema_ser[-K:]
    atr_tail = atr_ser[-K:]
    closes_tail = closes[-K:]

    if K < 4:
        ev["reason"] = "aligned_tail_too_short"
        return "none", ev

    # Compute m_i for the last 4 aligned bars
    m_vals: List[float] = []
    for i in range(K - 4, K):
        a_i = atr_tail[i]
        if a_i <= 0:
            m_vals.append(0.0)
        else:
            m_vals.append(abs(closes_tail[i] - ema_tail[i]) / a_i)

    ev["m_last4"] = [round(x, 4) for x in m_vals]

    # Trend direction at the latest bar (sign of close - EMA)
    last_dir = 1 if closes_tail[-1] > ema_tail[-1] else (-1 if closes_tail[-1] < ema_tail[-1] else 0)
    ev["trend_dir"] = last_dir

    # 3 consecutive increases in m? -> accelerating (must be in trend direction)
    inc3 = m_vals[-1] > m_vals[-2] > m_vals[-3] > m_vals[-4]
    dec3 = m_vals[-1] < m_vals[-2] < m_vals[-3] < m_vals[-4]

    # New 20-bar extreme test
    closes_20 = closes[-(HH_HL_WINDOW + 1):]
    new_high = closes_20[-1] >= max(closes_20[:-1]) and closes_20[-1] > closes_20[-2]
    new_low = closes_20[-1] <= min(closes_20[:-1]) and closes_20[-1] < closes_20[-2]
    # Did momentum NOT make a new extreme? (within the same window — using m series
    # or just the last 4 m values as a proxy for "did momentum follow"?)
    # We use a simple proxy: if price prints a fresh 20-bar extreme but m_vals[-1]
    # is below the max of m_vals (i.e., not a fresh m-high), call it divergent.
    m_made_new_high = m_vals[-1] >= max(m_vals)
    divergent = (new_high or new_low) and not m_made_new_high

    ev["new_high_20"] = new_high
    ev["new_low_20"] = new_low
    ev["m_new_high_in_4"] = m_made_new_high

    if inc3 and last_dir != 0:
        ev["match"] = "accelerating"
        return "accelerating", ev
    if dec3:
        ev["match"] = "fading"
        return "fading", ev
    if divergent:
        ev["match"] = "divergent"
        return "divergent", ev

    ev["match"] = "steady"
    return "steady", ev
