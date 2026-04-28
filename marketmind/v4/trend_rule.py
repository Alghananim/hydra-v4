"""TREND_RULE — closing-price HH-count + slope/ATR + EMA test.

Spec (Phase 1 audit):
  strong_up:   HH-count over 20 bars >= 6
               AND slope(close, 20) / ATR(14) > 0.5
               AND price > EMA(20)
  strong_down: mirror (HL-count >= 6, slope/ATR < -0.5, price < EMA20)
  weak_up / weak_down: 1-2 of the 3 conditions
  range:       all 3 near zero (slope ratio ~0, hh~hl, |close-EMA|/ATR small)
  choppy:      4+ direction flips in last 10 bars
  none:        not enough bars

Returns (state_string, evidence_dict).
"""
from __future__ import annotations

from typing import Sequence, Tuple, Dict, Any

from marketmind.v4.models import Bar
from marketmind.v4.indicators import (
    ATR_PERIOD, EMA_PERIOD, HH_HL_WINDOW,
    atr, ema_close, slope, hh_count, hl_count, direction_flips,
)


# Thresholds — locked, do not tune
SLOPE_RATIO_STRONG = 0.5      # slope(close,20)/ATR(14) > 0.5 for strong
SLOPE_RATIO_RANGE = 0.05      # |slope/ATR| <= 0.05 means "near zero" (range)
HH_THRESHOLD = 6              # >=6 of 20 HH for strong
RANGE_BAND_ATR = 0.5          # |close-EMA|/ATR <= 0.5 means inside range band
CHOPPY_FLIP_THRESHOLD = 4     # >=4 flips in 10 bars = choppy


def evaluate(bars: Sequence[Bar]) -> Tuple[str, Dict[str, Any]]:
    """Return (trend_state, evidence_dict)."""
    needed = max(HH_HL_WINDOW + 1, ATR_PERIOD + 1, EMA_PERIOD)
    ev: Dict[str, Any] = {"rule": "TREND_RULE"}

    if len(bars) < needed:
        ev["reason"] = f"insufficient_bars({len(bars)}<{needed})"
        return "none", ev

    closes = [b.close for b in bars]
    a = atr(bars, ATR_PERIOD)
    e = ema_close(bars, EMA_PERIOD)
    s = slope(closes, HH_HL_WINDOW)
    hh = hh_count(closes, HH_HL_WINDOW)
    hl = hl_count(closes, HH_HL_WINDOW)
    flips = direction_flips(closes, 10)

    if a <= 0:
        ev["reason"] = "atr_zero"
        ev.update({"atr": a, "ema": e, "slope": s, "hh": hh, "hl": hl, "flips": flips})
        return "none", ev

    slope_ratio = s / a
    last_close = closes[-1]
    above_ema = last_close > e
    below_ema = last_close < e
    band_pos = abs(last_close - e) / a

    ev.update({
        "atr": round(a, 6),
        "ema": round(e, 6),
        "close": round(last_close, 6),
        "slope": round(s, 6),
        "slope_ratio": round(slope_ratio, 4),
        "hh_count": hh,
        "hl_count": hl,
        "flips_10": flips,
        "band_pos_atr": round(band_pos, 4),
    })

    # Choppy beats everything else if flips dominate
    if flips >= CHOPPY_FLIP_THRESHOLD:
        ev["match"] = "choppy(flips)"
        return "choppy", ev

    # Strong UP: all 3 conditions
    cond_up_hh = hh >= HH_THRESHOLD
    cond_up_slope = slope_ratio > SLOPE_RATIO_STRONG
    cond_up_ema = above_ema
    up_score = sum([cond_up_hh, cond_up_slope, cond_up_ema])

    cond_dn_hl = hl >= HH_THRESHOLD
    cond_dn_slope = slope_ratio < -SLOPE_RATIO_STRONG
    cond_dn_ema = below_ema
    dn_score = sum([cond_dn_hl, cond_dn_slope, cond_dn_ema])

    ev["up_score"] = up_score
    ev["dn_score"] = dn_score

    if up_score == 3:
        ev["match"] = "strong_up"
        return "strong_up", ev
    if dn_score == 3:
        ev["match"] = "strong_down"
        return "strong_down", ev

    # Range: all near zero
    if (
        abs(slope_ratio) <= SLOPE_RATIO_RANGE
        and abs(hh - hl) <= 2
        and band_pos <= RANGE_BAND_ATR
    ):
        ev["match"] = "range"
        return "range", ev

    # Weak directional
    if up_score >= dn_score and up_score >= 1:
        ev["match"] = f"weak_up(score={up_score})"
        return "weak_up", ev
    if dn_score >= 1:
        ev["match"] = f"weak_down(score={dn_score})"
        return "weak_down", ev

    ev["match"] = "range(default)"
    return "range", ev


def regime_from_trend(trend_state: str) -> str:
    """Map fine-grained trend_state to a coarse regime label."""
    if trend_state in ("strong_up", "strong_down"):
        return "trending"
    if trend_state == "range":
        return "ranging"
    if trend_state == "choppy":
        return "choppy"
    if trend_state in ("weak_up", "weak_down"):
        return "transitioning"
    return "transitioning"
