# -*- coding: utf-8 -*-
"""Engine V3 helpers - small, pure utility functions.

Currently:
   compute_atr14(bars) - ATR(14) from bar list (open/high/low/close/timestamp).
                        Reuses chartmind.v3.trend._atr_impl when available so
                        we don't duplicate ATR logic. Falls back to a local
                        implementation if chartmind isn't importable (keeps
                        engine self-sufficient for tests).

These helpers are kept dependency-light: no I/O, no global state.
"""
from __future__ import annotations
from typing import Sequence


def _atr_local(bars, period: int = 14) -> float:
    """Local ATR(period) - true range average over last `period` bars.

    Identical formula to chartmind.v3.trend._atr_impl. Bars need only have
    .high, .low, .close attributes (works for both ChartMind Bar and
    MarketMind Bar dataclasses).
    """
    if not bars or len(bars) < 2:
        return 0.0
    trs = []
    for i in range(1, len(bars)):
        h = bars[i].high
        l = bars[i].low
        cp = bars[i - 1].close
        trs.append(max(h - l, abs(h - cp), abs(l - cp)))
    if not trs:
        return 0.0
    return sum(trs[-period:]) / min(period, len(trs))


def compute_atr14(bars: Sequence) -> float:
    """ATR(14) - prefers chartmind.v3.trend._atr_impl if importable.

    Returns 0.0 if bars is empty or too short.
    """
    if not bars or len(bars) < 2:
        return 0.0
    try:
        from chartmind.v3.trend import _atr_impl as _cm_atr
        return _cm_atr(list(bars), 14)
    except Exception:
        return _atr_local(bars, 14)
