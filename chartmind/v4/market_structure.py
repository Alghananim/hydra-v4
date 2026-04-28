"""Market structure — adaptive k=3 fractal swings + BoS/CHoCH detection.

REBUILD per Phase 1 audit:
- V3 used k=2 — too tight; produced too many fake swings on M15.
- V4 uses k=3 (locked); fractal-on-close fallback for low-volatility windows.

A swing HIGH at index i (k=3) requires:
    high[i] > high[i-1], high[i-2], high[i-3]
    AND high[i] > high[i+1], high[i+2], high[i+3]
A swing LOW at index i mirrors with low.

Fallback (fractal-on-close) — if no swing was confirmed in the last
LOOKBACK bars, retry the test using closes instead of high/low. This
avoids "no structure" verdicts on quiet rangebound bars.

BoS = break of structure (price closes beyond last opposite swing in trend).
CHoCH = change of character (first opposite-direction BoS after a trend).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from marketmind.v4 import indicators
from marketmind.v4.models import Bar

from chartmind.v4.chart_thresholds import (
    SWING_K,
    TREND_LOOKBACK_BARS,
    TREND_HH_HL_MIN_STRONG,
    TREND_SLOPE_BARS,
    TREND_RANGE_HHLL_MAX,
    TREND_RANGE_ADX_MAX,
    TREND_CHOPPY_FLIPS_MIN,
    EMA_PERIOD,
)


# ---------------------------------------------------------------------------
# Swings
# ---------------------------------------------------------------------------


@dataclass
class Swing:
    index: int
    price: float
    kind: str          # "high" | "low"
    via: str = "hl"    # "hl" (default fractal on high/low) | "close" (fallback)


def find_swings(bars: Sequence[Bar], k: int = SWING_K) -> List[Swing]:
    """Return all confirmed fractal swings using high/low arrays."""
    out: List[Swing] = []
    n = len(bars)
    if n < 2 * k + 1:
        return out
    for i in range(k, n - k):
        h = bars[i].high
        l = bars[i].low
        is_high = all(h > bars[i - j].high for j in range(1, k + 1)) and \
                  all(h > bars[i + j].high for j in range(1, k + 1))
        is_low = all(l < bars[i - j].low for j in range(1, k + 1)) and \
                 all(l < bars[i + j].low for j in range(1, k + 1))
        if is_high:
            out.append(Swing(index=i, price=h, kind="high", via="hl"))
        elif is_low:
            out.append(Swing(index=i, price=l, kind="low", via="hl"))
    return out


def find_swings_on_close(bars: Sequence[Bar], k: int = SWING_K) -> List[Swing]:
    """Fallback fractal: same logic but on closes."""
    out: List[Swing] = []
    n = len(bars)
    if n < 2 * k + 1:
        return out
    for i in range(k, n - k):
        c = bars[i].close
        is_high = all(c > bars[i - j].close for j in range(1, k + 1)) and \
                  all(c > bars[i + j].close for j in range(1, k + 1))
        is_low = all(c < bars[i - j].close for j in range(1, k + 1)) and \
                 all(c < bars[i + j].close for j in range(1, k + 1))
        if is_high:
            out.append(Swing(index=i, price=c, kind="high", via="close"))
        elif is_low:
            out.append(Swing(index=i, price=c, kind="low", via="close"))
    return out


def find_swings_adaptive(bars: Sequence[Bar], k: int = SWING_K,
                         lookback: int = TREND_LOOKBACK_BARS) -> List[Swing]:
    """Primary fractal; if there's NO swing in the last `lookback` bars,
    augment with close-based fractals over the same window.
    """
    swings = find_swings(bars, k=k)
    if not bars:
        return swings
    cutoff = max(0, len(bars) - lookback)
    recent = [s for s in swings if s.index >= cutoff]
    if recent:
        return swings
    # fallback
    fb = [s for s in find_swings_on_close(bars, k=k) if s.index >= cutoff]
    swings.extend(fb)
    swings.sort(key=lambda s: s.index)
    return swings


# ---------------------------------------------------------------------------
# Trend structure label
# ---------------------------------------------------------------------------


@dataclass
class TrendDiagnosis:
    label: str             # bullish_strong, bullish_weak, bearish_strong, bearish_weak,
                           # range, choppy, transitioning, none
    hh_swings: int = 0
    hl_swings: int = 0
    lh_swings: int = 0
    ll_swings: int = 0
    ema_slope: float = 0.0
    adx_value: float = 0.0
    flips: int = 0
    bos: bool = False
    choch: bool = False
    via: str = "hl"        # "hl" | "close" — which fractal succeeded


def _count_progressing(swings: List[Swing], kind: str, op: str) -> int:
    """Count swings of `kind` that are strictly higher/lower than the previous swing of the same kind.

    op = "higher": return count of consecutive HHs (or HLs)
    op = "lower" : return count of consecutive LHs (or LLs)
    """
    same = [s for s in swings if s.kind == kind]
    if len(same) < 2:
        return 0
    cnt = 0
    for i in range(1, len(same)):
        if op == "higher" and same[i].price > same[i - 1].price:
            cnt += 1
        elif op == "lower" and same[i].price < same[i - 1].price:
            cnt += 1
    return cnt


def diagnose_trend(bars: Sequence[Bar],
                   k: int = SWING_K,
                   lookback: int = TREND_LOOKBACK_BARS) -> TrendDiagnosis:
    """Return TrendDiagnosis for the last `lookback` bars."""
    if not bars or len(bars) < 2 * k + 1:
        return TrendDiagnosis(label="none")

    cutoff = max(0, len(bars) - lookback)
    recent_bars = list(bars)[cutoff:]
    closes_recent = [b.close for b in recent_bars]
    swings = [s for s in find_swings_adaptive(bars, k=k, lookback=lookback)
              if s.index >= cutoff]
    via = "close" if (swings and any(s.via == "close" for s in swings)) else "hl"

    hh = _count_progressing(swings, "high", "higher")
    hl = _count_progressing(swings, "low", "higher")
    lh = _count_progressing(swings, "high", "lower")
    ll = _count_progressing(swings, "low", "lower")

    # EMA-20 slope on closes over last TREND_SLOPE_BARS bars of EMA series.
    # Build short EMA series end-to-end:
    ema_now = indicators.ema_close(recent_bars, EMA_PERIOD)
    if len(recent_bars) > TREND_SLOPE_BARS:
        ema_then = indicators.ema_close(recent_bars[: -TREND_SLOPE_BARS], EMA_PERIOD)
    else:
        ema_then = ema_now
    ema_slope_val = ema_now - ema_then  # positive = uptrend

    adx_val = indicators.adx(bars)
    flips = indicators.direction_flips(closes_recent, window=10)

    # ----- Range first -----
    if hh + hl <= TREND_RANGE_HHLL_MAX and lh + ll <= TREND_RANGE_HHLL_MAX \
            and adx_val < TREND_RANGE_ADX_MAX:
        return TrendDiagnosis(
            label="range",
            hh_swings=hh, hl_swings=hl, lh_swings=lh, ll_swings=ll,
            ema_slope=ema_slope_val, adx_value=adx_val, flips=flips, via=via,
        )

    # ----- Choppy -----
    if flips >= TREND_CHOPPY_FLIPS_MIN:
        return TrendDiagnosis(
            label="choppy",
            hh_swings=hh, hl_swings=hl, lh_swings=lh, ll_swings=ll,
            ema_slope=ema_slope_val, adx_value=adx_val, flips=flips, via=via,
        )

    # ----- Strong/weak directional -----
    bull_score = sum([
        hh >= TREND_HH_HL_MIN_STRONG,
        hl >= TREND_HH_HL_MIN_STRONG,
        ema_slope_val > 0,
    ])
    bear_score = sum([
        lh >= TREND_HH_HL_MIN_STRONG,
        ll >= TREND_HH_HL_MIN_STRONG,
        ema_slope_val < 0,
    ])

    bos, choch = _detect_bos_choch(swings, recent_bars)

    if bos or choch:
        if bull_score >= 2 and bull_score >= bear_score:
            return TrendDiagnosis(
                label="transitioning",
                hh_swings=hh, hl_swings=hl, lh_swings=lh, ll_swings=ll,
                ema_slope=ema_slope_val, adx_value=adx_val,
                flips=flips, bos=bos, choch=choch, via=via,
            )
        if bear_score >= 2 and bear_score > bull_score:
            return TrendDiagnosis(
                label="transitioning",
                hh_swings=hh, hl_swings=hl, lh_swings=lh, ll_swings=ll,
                ema_slope=ema_slope_val, adx_value=adx_val,
                flips=flips, bos=bos, choch=choch, via=via,
            )

    if bull_score == 3:
        label = "bullish_strong"
    elif bear_score == 3:
        label = "bearish_strong"
    elif bull_score >= 1 and bull_score > bear_score:
        label = "bullish_weak"
    elif bear_score >= 1 and bear_score > bull_score:
        label = "bearish_weak"
    else:
        label = "transitioning"

    return TrendDiagnosis(
        label=label,
        hh_swings=hh, hl_swings=hl, lh_swings=lh, ll_swings=ll,
        ema_slope=ema_slope_val, adx_value=adx_val,
        flips=flips, bos=bos, choch=choch, via=via,
    )


def _detect_bos_choch(swings: List[Swing], bars: Sequence[Bar]) -> Tuple[bool, bool]:
    """Naive BoS/CHoCH detector.

    BoS: most recent close exceeds the last swing high (uptrend continuation)
         OR is below the last swing low (downtrend continuation).
    CHoCH: most recent close exceeds last swing high AFTER a series of LLs/LHs,
           or below last swing low AFTER a series of HHs/HLs.
    """
    if not bars or len(swings) < 3:
        return False, False
    last_close = bars[-1].close
    last_high_swing = next((s for s in reversed(swings) if s.kind == "high"), None)
    last_low_swing = next((s for s in reversed(swings) if s.kind == "low"), None)
    bos = False
    if last_high_swing and last_close > last_high_swing.price:
        bos = True
    elif last_low_swing and last_close < last_low_swing.price:
        bos = True

    # CHoCH heuristic: prior trend direction (look at swings up to -2) flipped.
    prior = swings[:-1]
    if len(prior) < 2:
        return bos, False
    prior_highs = [s for s in prior if s.kind == "high"]
    prior_lows = [s for s in prior if s.kind == "low"]
    was_bear = (
        len(prior_highs) >= 2 and prior_highs[-1].price < prior_highs[-2].price
        and len(prior_lows) >= 2 and prior_lows[-1].price < prior_lows[-2].price
    )
    was_bull = (
        len(prior_highs) >= 2 and prior_highs[-1].price > prior_highs[-2].price
        and len(prior_lows) >= 2 and prior_lows[-1].price > prior_lows[-2].price
    )
    choch = False
    if was_bear and last_high_swing and last_close > last_high_swing.price:
        choch = True
    elif was_bull and last_low_swing and last_close < last_low_swing.price:
        choch = True
    return bos, choch
