"""Reference levels — entry_zone (BAND), invalidation, stop, target.

V12 redesign per audit:
    The audit found that V5's invalidation_level was tied to the nearest
    structural swing. For M15 with sparse swings this often placed the
    stop too tight (well within 1×ATR) → premature stop-outs.
    V12-F4 replaces it with an ATR-based stop: invalidation = anchor ±
    STOP_ATR_MULT × ATR. This adapts to instrument volatility (USD/JPY
    auto-widens because its ATR is naturally larger in price units).

    Targets in V5 were "next opposing key level OR None". When `None`,
    the trade timed out — wins were truncated.
    V12-F5 enforces a 2:1 RR floor: target = anchor ± max(level_distance,
    2 × stop_distance), so every trade has a real take-profit at minimum
    twice the stop distance. Improves expected value at the same WR.

V4 contract preserved: entry_zone is a band, invalidation_level is a
price, target_reference is a price (no longer None).
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


# V12-F4: ATR-based stop. 1.5x is the industry standard for momentum +
# breakout setups on M15 — wide enough to absorb noise, tight enough
# to keep RR meaningful.
STOP_ATR_MULT = 1.5
# V12-F5: minimum risk:reward floor. Every trade must have target
# distance ≥ 2x stop distance.
RR_FLOOR = 2.0


@dataclass
class References:
    entry_zone: Dict[str, float]
    invalidation_level: float
    target_reference: Optional[float]
    setup_anchor: float           # the central price the band is built around


def _make_band(center: float, half_width: float) -> Dict[str, float]:
    return {"low": float(center - half_width), "high": float(center + half_width)}


def _atr_stop_and_target(anchor: float, atr_value: float, side: str,
                          levels: List[Level]) -> tuple:
    """V12 helper: ATR stop + RR-floor target. Returns (stop, target).

    side='long' → stop below anchor, target above.
    side='short' → stop above anchor, target below.
    """
    stop_distance = STOP_ATR_MULT * atr_value
    rr_target_distance = RR_FLOOR * stop_distance
    if side == "long":
        stop = anchor - stop_distance
        # Prefer a real resistance level above anchor IF it is at least
        # rr_target_distance away. Otherwise enforce the RR floor.
        ups = [L.price for L in levels
               if L.price >= anchor + rr_target_distance and L.type == "resistance"]
        target = float(min(ups)) if ups else float(anchor + rr_target_distance)
    else:  # short
        stop = anchor + stop_distance
        downs = [L.price for L in levels
                 if L.price <= anchor - rr_target_distance and L.type == "support"]
        target = float(max(downs)) if downs else float(anchor - rr_target_distance)
    return float(stop), target


def for_breakout(bars: Sequence[Bar], *,
                 atr_value: float,
                 levels: List[Level],
                 side: str) -> References:
    """V12: breakout entry = last close ± 0.2×ATR band.
    Stop = anchor ± 1.5×ATR. Target = max(nearest level, anchor ± 2×stop).
    """
    last = bars[-1].close
    half = ENTRY_BAND_BREAKOUT_ATR * atr_value
    band = _make_band(last, half)
    invalidation, target = _atr_stop_and_target(last, atr_value, side, levels)
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
    """V12: retest entry = level ± 0.3×ATR band. Same V12 stop/target
    formula anchored at the level price."""
    half = ENTRY_BAND_RETEST_ATR * atr_value
    band = _make_band(level_price, half)
    invalidation, target = _atr_stop_and_target(
        float(level_price), atr_value, side, levels,
    )
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
    """V12: pullback entry = recent same-side swing ± 0.3×ATR. V12 stop/target."""
    swings = find_swings_adaptive(bars)
    last = bars[-1].close
    half = ENTRY_BAND_PULLBACK_ATR * atr_value
    if side == "long":
        anchor_swing = next((s for s in reversed(swings) if s.kind == "low"), None)
        anchor = anchor_swing.price if anchor_swing else last
    else:
        anchor_swing = next((s for s in reversed(swings) if s.kind == "high"), None)
        anchor = anchor_swing.price if anchor_swing else last
    invalidation, target = _atr_stop_and_target(
        float(anchor), atr_value, side, levels,
    )
    return References(
        entry_zone=_make_band(anchor, half),
        invalidation_level=invalidation,
        target_reference=target,
        setup_anchor=float(anchor),
    )
