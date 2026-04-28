"""SHARED indicator library — ATR, ADX, EMA, percentile, slope, HH/HL counter.

This module is the SINGLE SOURCE OF TRUTH for these primitives across
HYDRA V4. ChartMind V4 will import from HERE; do not re-implement.

Locked constants (Phase 1 audit, do NOT tune):
  ATR_PERIOD = 14
  ADX_PERIOD = 14
  PERCENTILE_WINDOW = 100
  HH_HL_WINDOW = 20
  EMA_PERIOD = 20
"""
from __future__ import annotations

from typing import List, Sequence, Optional

from marketmind.v4.models import Bar


# ---------------------------------------------------------------------------
# Locks
# ---------------------------------------------------------------------------

ATR_PERIOD = 14
ADX_PERIOD = 14
PERCENTILE_WINDOW = 100
HH_HL_WINDOW = 20
EMA_PERIOD = 20


# ---------------------------------------------------------------------------
# True Range / ATR
# ---------------------------------------------------------------------------


def true_range(prev_close: float, high: float, low: float) -> float:
    """Wilder's True Range = max(high-low, |high-prev_close|, |low-prev_close|)."""
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def atr(bars: Sequence[Bar], period: int = ATR_PERIOD) -> float:
    """Wilder's ATR. Returns 0.0 if not enough bars.

    Uses Wilder's smoothing: ATR_i = ((period-1)*ATR_{i-1} + TR_i) / period.
    The first `period` TRs are SMA-seeded.
    """
    if len(bars) < period + 1:
        return 0.0
    trs: List[float] = []
    for i in range(1, len(bars)):
        trs.append(true_range(bars[i - 1].close, bars[i].high, bars[i].low))
    if len(trs) < period:
        return 0.0
    # SMA seed of first `period` TRs
    val = sum(trs[:period]) / period
    for tr in trs[period:]:
        val = ((period - 1) * val + tr) / period
    return float(val)


# ---------------------------------------------------------------------------
# Directional Movement / ADX
# ---------------------------------------------------------------------------


def adx(bars: Sequence[Bar], period: int = ADX_PERIOD) -> float:
    """Wilder's ADX. Returns 0.0 if not enough bars.

    Implementation:
      +DM = up_move if up_move>down_move and up_move>0 else 0
      -DM = down_move if down_move>up_move and down_move>0 else 0
      Smooth +DM, -DM, TR with Wilder's smoothing.
      +DI = 100 * smoothed +DM / smoothed TR
      -DI = 100 * smoothed -DM / smoothed TR
      DX = 100 * |+DI - -DI| / (+DI + -DI)
      ADX = Wilder smoothing of DX over `period`.
    """
    if len(bars) < period * 2 + 1:
        return 0.0
    plus_dm: List[float] = []
    minus_dm: List[float] = []
    trs: List[float] = []
    for i in range(1, len(bars)):
        up = bars[i].high - bars[i - 1].high
        dn = bars[i - 1].low - bars[i].low
        plus = up if (up > dn and up > 0) else 0.0
        minus = dn if (dn > up and dn > 0) else 0.0
        plus_dm.append(plus)
        minus_dm.append(minus)
        trs.append(true_range(bars[i - 1].close, bars[i].high, bars[i].low))
    if len(trs) < period:
        return 0.0

    # Wilder seeds = sum of first period
    s_tr = sum(trs[:period])
    s_p = sum(plus_dm[:period])
    s_m = sum(minus_dm[:period])
    dxs: List[float] = []
    for i in range(period, len(trs)):
        s_tr = s_tr - (s_tr / period) + trs[i]
        s_p = s_p - (s_p / period) + plus_dm[i]
        s_m = s_m - (s_m / period) + minus_dm[i]
        if s_tr == 0:
            dxs.append(0.0)
            continue
        plus_di = 100.0 * s_p / s_tr
        minus_di = 100.0 * s_m / s_tr
        denom = plus_di + minus_di
        dx = 100.0 * abs(plus_di - minus_di) / denom if denom > 0 else 0.0
        dxs.append(dx)
    if len(dxs) < period:
        return 0.0
    val = sum(dxs[:period]) / period
    for dx in dxs[period:]:
        val = ((period - 1) * val + dx) / period
    return float(val)


# ---------------------------------------------------------------------------
# EMA
# ---------------------------------------------------------------------------


def ema(values: Sequence[float], period: int = EMA_PERIOD) -> float:
    """Standard EMA (alpha=2/(period+1)). Returns 0.0 if not enough samples."""
    if len(values) < period:
        return 0.0
    alpha = 2.0 / (period + 1.0)
    # SMA seed
    val = sum(values[:period]) / period
    for v in values[period:]:
        val = alpha * v + (1 - alpha) * val
    return float(val)


def ema_close(bars: Sequence[Bar], period: int = EMA_PERIOD) -> float:
    return ema([b.close for b in bars], period)


# ---------------------------------------------------------------------------
# Percentile rank
# ---------------------------------------------------------------------------


def percentile_rank(value: float, sample: Sequence[float]) -> float:
    """Return percentile (0..100) of `value` within `sample`.

    Uses the "fraction of sample strictly less than value" + 0.5 *
    "fraction equal to value" — the common 'mid-rank' definition. This
    avoids a single tied value sticking the rank at 0 or 100.
    """
    if not sample:
        return 0.0
    n = len(sample)
    less = sum(1 for s in sample if s < value)
    eq = sum(1 for s in sample if s == value)
    return 100.0 * (less + 0.5 * eq) / n


def atr_series(bars: Sequence[Bar], period: int = ATR_PERIOD) -> List[float]:
    """Return ATR computed on each window ending at i, for i in range(period, len(bars))."""
    out: List[float] = []
    if len(bars) < period + 1:
        return out
    # Compute TR series first
    trs: List[float] = []
    for i in range(1, len(bars)):
        trs.append(true_range(bars[i - 1].close, bars[i].high, bars[i].low))
    # Wilder smoothing across the series
    if len(trs) < period:
        return out
    val = sum(trs[:period]) / period
    out.append(val)
    for tr in trs[period:]:
        val = ((period - 1) * val + tr) / period
        out.append(val)
    return out


def atr_percentile_now(bars: Sequence[Bar],
                       window: int = PERCENTILE_WINDOW,
                       period: int = ATR_PERIOD) -> float:
    """Percentile rank of CURRENT ATR(period) within the last `window` ATR samples.

    Returns 50.0 if insufficient history (caller should treat as 'normal').
    """
    series = atr_series(bars, period)
    if not series:
        return 50.0
    if len(series) < 2:
        return 50.0
    sample = series[-window:] if len(series) >= window else series
    return percentile_rank(series[-1], sample)


# ---------------------------------------------------------------------------
# Slope (least-squares) on closes
# ---------------------------------------------------------------------------


def slope(values: Sequence[float], window: int = HH_HL_WINDOW) -> float:
    """OLS slope of last `window` values vs index 0..window-1."""
    if len(values) < window or window < 2:
        return 0.0
    ys = list(values[-window:])
    n = window
    mean_x = (n - 1) / 2.0
    mean_y = sum(ys) / n
    num = 0.0
    den = 0.0
    for i, y in enumerate(ys):
        dx = i - mean_x
        num += dx * (y - mean_y)
        den += dx * dx
    if den == 0:
        return 0.0
    return float(num / den)


# ---------------------------------------------------------------------------
# Higher-Highs / Higher-Lows / direction flips
# ---------------------------------------------------------------------------


def hh_count(closes: Sequence[float], window: int = HH_HL_WINDOW) -> int:
    """Count of bars in the last `window` whose close is HIGHER than the prior bar.

    "HH-count over 20 bars >= 6" per TREND_RULE means at least 6 of the last
    20 bar-to-bar moves were upward.
    """
    if len(closes) < window + 1:
        return 0
    seg = closes[-(window + 1):]
    return sum(1 for i in range(1, len(seg)) if seg[i] > seg[i - 1])


def hl_count(closes: Sequence[float], window: int = HH_HL_WINDOW) -> int:
    """Mirror of hh_count: count of downward bar-to-bar moves."""
    if len(closes) < window + 1:
        return 0
    seg = closes[-(window + 1):]
    return sum(1 for i in range(1, len(seg)) if seg[i] < seg[i - 1])


def direction_flips(closes: Sequence[float], window: int = 10) -> int:
    """Count direction changes in the last `window` bar-to-bar moves.

    A flip is when sign(close[i] - close[i-1]) != sign(close[i-1] - close[i-2]).
    """
    if len(closes) < window + 2:
        return 0
    seg = closes[-(window + 2):]
    flips = 0
    prev_sign = 0
    for i in range(1, len(seg)):
        diff = seg[i] - seg[i - 1]
        sgn = 1 if diff > 0 else (-1 if diff < 0 else 0)
        if sgn != 0 and prev_sign != 0 and sgn != prev_sign:
            flips += 1
        if sgn != 0:
            prev_sign = sgn
    return flips
