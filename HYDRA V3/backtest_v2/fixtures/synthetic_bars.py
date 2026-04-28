# -*- coding: utf-8 -*-
"""Deterministic OHLC sequences for testing."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional


@dataclass
class SyntheticBar:
    time: datetime
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    bid_open: float
    bid_close: float
    ask_open: float
    ask_close: float
    spread_pips: float
    volume: int
    pair: str = "EUR/USD"
    granularity: str = "M15"

    def __getitem__(self, key):
        return getattr(self, key)


def _build_bar(t: datetime, o: float, h: float, l: float, c: float,
               *, pair: str, pip: float, spread_pips: float = 0.5,
               volume: int = 1000) -> SyntheticBar:
    half = (spread_pips * pip) / 2.0
    return SyntheticBar(
        time=t, timestamp=t,
        open=o, high=h, low=l, close=c,
        bid_open=o - half, bid_close=c - half,
        ask_open=o + half, ask_close=c + half,
        spread_pips=spread_pips, volume=volume,
        pair=pair, granularity="M15",
    )


def _start(start: Optional[datetime]) -> datetime:
    return start or datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)


def make_trending_series(*, n_bars: int = 100, start_price: float = 1.10,
                          step: float = 0.0002,
                          start: Optional[datetime] = None,
                          pair: str = "EUR/USD") -> List[SyntheticBar]:
    pip = 0.01 if "JPY" in pair else 0.0001
    bars: List[SyntheticBar] = []
    t = _start(start)
    last_close = start_price
    for i in range(n_bars):
        o = last_close
        c = round(last_close + step, 6)
        h = round(c + step / 2, 6)
        l = round(o - step / 4, 6)
        bars.append(_build_bar(t, o, h, l, c, pair=pair, pip=pip))
        last_close = c
        t = t + timedelta(minutes=15)
    return bars


def make_choppy_series(*, n_bars: int = 100, start_price: float = 1.10,
                        amp: float = 0.0005,
                        start: Optional[datetime] = None,
                        pair: str = "EUR/USD") -> List[SyntheticBar]:
    pip = 0.01 if "JPY" in pair else 0.0001
    bars: List[SyntheticBar] = []
    t = _start(start)
    base = start_price
    for i in range(n_bars):
        if i % 2 == 0:
            o = base; c = round(base + amp / 2, 6)
            h = round(c + amp / 4, 6); l = round(o - amp / 4, 6)
        else:
            o = round(base + amp / 2, 6); c = base
            h = round(o + amp / 4, 6); l = round(c - amp / 4, 6)
        bars.append(_build_bar(t, o, h, l, c, pair=pair, pip=pip))
        t = t + timedelta(minutes=15)
    return bars


def make_breakout_series(*, n_bars: int = 60, start_price: float = 1.10,
                          consol_amp: float = 0.0003,
                          breakout_step: float = 0.001,
                          consol_len: int = 30,
                          start: Optional[datetime] = None,
                          pair: str = "EUR/USD") -> List[SyntheticBar]:
    pip = 0.01 if "JPY" in pair else 0.0001
    bars: List[SyntheticBar] = []
    t = _start(start)
    base = start_price
    for i in range(consol_len):
        if i % 2 == 0:
            o = base; c = round(base + consol_amp / 2, 6)
        else:
            o = round(base + consol_amp / 2, 6); c = base
        h = round(max(o, c) + consol_amp / 4, 6)
        l = round(min(o, c) - consol_amp / 4, 6)
        bars.append(_build_bar(t, o, h, l, c, pair=pair, pip=pip))
        t = t + timedelta(minutes=15)
    last_c = bars[-1].close
    for i in range(n_bars - consol_len):
        o = last_c
        c = round(last_c + breakout_step, 6)
        h = round(c + breakout_step / 2, 6)
        l = round(o - breakout_step / 4, 6)
        bars.append(_build_bar(t, o, h, l, c, pair=pair, pip=pip))
        last_c = c
        t = t + timedelta(minutes=15)
    return bars
