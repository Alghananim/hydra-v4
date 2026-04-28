"""Reference levels — entry_zone (BAND), invalidation, stop, target.

THE V3 SIN we are fixing:
    `last_close * 1.0002` — a hardcoded scalar entry. REJECTED.

V4 contract:
- entry_zone is ALWAYS a band (low, high) derived from real ATR + real bars.
- invalidation_level is a real price beyond a structural swing.
- stop_reference == invalidation_level (set by the caller).
- target_reference is the next opposing key level OR None (NOT a fixed RR).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from marketmind.v4.models import Bar

from chartmind.v4.chart_thresholds import (
    ENTRY_BAND_BREAKOUT_ATR,
    ENTRY_BAND_RETEST_ATR,
    ENTRY_BAND_PULLBACK_ATR,
    INVALIDATION_FALLBACK_ATR_MULT,
)
from chartmind.v4.models import Level
from chartmind.v4.market_structure import find_swings_adaptive


@dataclass
class References:
    entry_zone: Dict[str, float]
    invalidation_level: float
    target_reference: Optional[float]
    setup_anchor: float           # the central price the band is built around


def _make_band(center: float, half_width: float) -> Dict[str, float]:
    return {"low": float(center - half_width), "high": float(center + half_width)}


def for_breakout(bars: Sequence[Bar], *,
                 atr_value: float,
                 levels: List[Level],
                 side: str) -> References:
    """Breakout entry band: ± 0.2 × ATR around last close.

    Invalidation = nearest opposite swing (low for long / high for short).
    Target = next opposing key level beyond the breakout direction, or None.
    """
    last = bars[-1].close
    half = ENTRY_BAND_BREAKOUT_ATR * atr_value
    band = _make_band(last, half)
    swings = find_swings_adaptive(bars)
    if side == "long":
        opp = next((s.price for s in reversed(swings) if s.kind == "low"),
                   last - INVALIDATION_FALLBACK_ATR_MULT * atr_value)
        invalidation = float(opp)
        # next resistance ABOVE last close
        ups = [L.price for L in levels if L.price > last and L.type == "resistance"]
        target = float(min(ups)) if ups else None
    else:
        opp = next((s.price for s in reversed(swings) if s.kind == "high"),
                   last + INVALIDATION_FALLBACK_ATR_MULT * atr_value)
        invalidation = float(opp)
        downs = [L.price for L in levels if L.price < last and L.type == "support"]
        target = float(max(downs)) if downs else None
    return References(
        entry_zone=band,
        invalidation_level=invalidation,
        target_reference=target,
        setup_anchor=float(last),
    )


def for_retest(bars: Sequence[Bar], *,
               atr_value: float,
               level_price: float,
               levels: List[Level],
               side: str) -> References:
    """Retest entry band: ± 0.3 × ATR around the broken level."""
    half = ENTRY_BAND_RETEST_ATR * atr_value
    band = _make_band(level_price, half)
    swings = find_swings_adaptive(bars)
    if side == "long":
        opp = next((s.price for s in reversed(swings) if s.kind == "low"),
                   level_price - INVALIDATION_FALLBACK_ATR_MULT * atr_value)
        invalidation = float(opp)
        ups = [L.price for L in levels if L.price > level_price and L.type == "resistance"]
        target = float(min(ups)) if ups else None
    else:
        opp = next((s.price for s in reversed(swings) if s.kind == "high"),
                   level_price + INVALIDATION_FALLBACK_ATR_MULT * atr_value)
        invalidation = float(opp)
        downs = [L.price for L in levels if L.price < level_price and L.type == "support"]
        target = float(max(downs)) if downs else None
    return References(
        entry_zone=band,
        invalidation_level=invalidation,
        target_reference=target,
        setup_anchor=float(level_price),
    )


def for_pullback(bars: Sequence[Bar], *,
                 atr_value: float,
                 levels: List[Level],
                 side: str) -> References:
    """Pullback entry band: ± 0.3 × ATR around recent same-side swing."""
    swings = find_swings_adaptive(bars)
    last = bars[-1].close
    half = ENTRY_BAND_PULLBACK_ATR * atr_value
    if side == "long":
        anchor_swing = next((s for s in reversed(swings) if s.kind == "low"), None)
        anchor = anchor_swing.price if anchor_swing else last
        opp_low = next((s.price for s in reversed(swings) if s.kind == "low"),
                       last - INVALIDATION_FALLBACK_ATR_MULT * atr_value)
        invalidation = float(opp_low)
        ups = [L.price for L in levels if L.price > last and L.type == "resistance"]
        target = float(min(ups)) if ups else None
    else:
        anchor_swing = next((s for s in reversed(swings) if s.kind == "high"), None)
        anchor = anchor_swing.price if anchor_swing else last
        opp_high = next((s.price for s in reversed(swings) if s.kind == "high"),
                        last + INVALIDATION_FALLBACK_ATR_MULT * atr_value)
        invalidation = float(opp_high)
        downs = [L.price for L in levels if L.price < last and L.type == "support"]
        target = float(max(downs)) if downs else None
    return References(
        entry_zone=_make_band(anchor, half),
        invalidation_level=invalidation,
        target_reference=target,
        setup_anchor=float(anchor),
    )
