"""Pytest config + shared bar-series fixtures.

Adds project root to sys.path so `contracts`, `marketmind`, `newsmind`
import without an install.
"""
from __future__ import annotations

import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.brain_output import BrainGrade, BrainOutput
from marketmind.v4.models import Bar


# ---------------------------------------------------------------------------
# Bar factories
# ---------------------------------------------------------------------------


def _ts(i: int, base: Optional[datetime] = None, minutes: int = 15) -> datetime:
    base = base or datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc)
    return base + timedelta(minutes=minutes * i)


def make_bar(i, price, *, base_ts=None, vol=1000.0, spread=0.5, minutes=15) -> Bar:
    return Bar(
        timestamp=_ts(i, base_ts, minutes),
        open=price,
        high=price * 1.0005,
        low=price * 0.9995,
        close=price,
        volume=vol,
        spread_pips=spread,
    )


def make_trending_bars(direction: str = "up", n: int = 50,
                        start: float = 1.1000, base_ts=None,
                        spread: float = 0.5, vol: float = 1500.0,
                        step_pct: float = 0.0010) -> List[Bar]:
    """Clean monotonic trend, no chop. step_pct is per-bar move."""
    sign = 1 if direction == "up" else -1
    bars: List[Bar] = []
    p = start
    for i in range(n):
        nxt = p * (1 + sign * step_pct)
        # high/low extend beyond open->close to give realistic ATR
        hi = max(p, nxt) * 1.0003
        lo = min(p, nxt) * 0.9997
        bars.append(Bar(timestamp=_ts(i, base_ts),
                        open=p, high=hi, low=lo, close=nxt,
                        volume=vol, spread_pips=spread))
        p = nxt
    return bars


def make_ranging_bars(n: int = 50, mid: float = 1.1000, band_pct: float = 0.0020,
                      base_ts=None, spread: float = 0.5, vol: float = 1200.0) -> List[Bar]:
    """Sine-wave around `mid` within ±band_pct. No breakout."""
    bars: List[Bar] = []
    for i in range(n):
        # tiny oscillation, multiple periods within 50 bars
        c = mid * (1 + band_pct * math.sin(i * 0.45))
        prev_close = bars[-1].close if bars else mid
        hi = max(c, prev_close) * 1.0001
        lo = min(c, prev_close) * 0.9999
        bars.append(Bar(timestamp=_ts(i, base_ts),
                        open=prev_close, high=hi, low=lo, close=c,
                        volume=vol, spread_pips=spread))
    return bars


def make_choppy_bars(n: int = 50, mid: float = 1.1000, base_ts=None,
                     spread: float = 0.5, vol: float = 1200.0) -> List[Bar]:
    """Many alternating direction flips."""
    bars: List[Bar] = []
    p = mid
    for i in range(n):
        # alternate up/down with tiny noise so HH and HL stay roughly equal
        sign = 1 if i % 2 == 0 else -1
        nxt = p * (1 + sign * 0.0008 + (0.00005 if i % 7 == 0 else 0))
        hi = max(p, nxt) * 1.0002
        lo = min(p, nxt) * 0.9998
        bars.append(Bar(timestamp=_ts(i, base_ts),
                        open=p, high=hi, low=lo, close=nxt,
                        volume=vol, spread_pips=spread))
        p = nxt
    return bars


def make_volatility_spike(n: int = 50, base_ts=None) -> List[Bar]:
    """Quiet n-1 bars then last bar with range = 5x ATR."""
    bars = make_ranging_bars(n - 1, base_ts=base_ts)
    # last bar — manually huge
    last = bars[-1].close
    spike_high = last * 1.02
    spike_low = last * 0.98
    bars.append(Bar(
        timestamp=_ts(n - 1, base_ts),
        open=last,
        high=spike_high,
        low=spike_low,
        close=spike_high * 0.999,
        volume=5000.0,
        spread_pips=0.5,
    ))
    return bars


def make_low_volume_session(n: int = 50, base_ts=None) -> List[Bar]:
    """All bars same hour-of-day; last bar volume <40% of avg.

    base_ts default keeps us inside active hours so off-session is NOT triggered.
    """
    base_ts = base_ts or datetime(2026, 4, 27, 13, 0, tzinfo=timezone.utc)
    # use 60-min spacing so EVERY bar has the same hour-of-day in a 24h cycle
    bars: List[Bar] = []
    p = 1.1000
    for i in range(n):
        # active-hours stride: shift base by 24h per bar so hour stays at 13:00
        ts = base_ts + timedelta(days=i)
        nxt = p * (1 + 0.0001)
        bars.append(Bar(timestamp=ts, open=p, high=nxt * 1.0001, low=p * 0.9999,
                        close=nxt, volume=2000.0, spread_pips=0.5))
        p = nxt
    # poison the last bar's volume
    last = bars[-1]
    bars[-1] = Bar(timestamp=last.timestamp, open=last.open, high=last.high,
                   low=last.low, close=last.close, volume=200.0,
                   spread_pips=last.spread_pips)
    return bars


def make_off_session_bars(n: int = 50) -> List[Bar]:
    """Last bar timestamp at 23:00 UTC (outside 07:00-21:00 window)."""
    base_ts = datetime(2026, 4, 27, 23, 0, tzinfo=timezone.utc)
    bars = []
    p = 1.1000
    for i in range(n):
        ts = base_ts + timedelta(minutes=15 * i)
        nxt = p * (1 + 0.0002)
        bars.append(Bar(timestamp=ts, open=p, high=nxt * 1.0001,
                        low=p * 0.9999, close=nxt, volume=1500.0,
                        spread_pips=0.5))
        p = nxt
    # ensure last bar's hour is in {21,22,23,0,1,2,3,4,5,6} — 50 bars from 23:00 spans 12.5h
    return bars


# ---------------------------------------------------------------------------
# Mock NewsMind outputs
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime(2026, 4, 27, 13, 0, tzinfo=timezone.utc)


def make_news_block(reason: str = "blackout: NFP -10/+30 window") -> BrainOutput:
    return BrainOutput(
        brain_name="newsmind",
        decision="BLOCK",
        grade=BrainGrade.BLOCK,
        reason=reason,
        evidence=["news_blackout"],
        data_quality="good",
        should_block=True,
        risk_flags=["news_blackout"],
        confidence=0.0,
        timestamp_utc=_now(),
    )


def make_news_warning() -> BrainOutput:
    return BrainOutput(
        brain_name="newsmind",
        decision="WAIT",
        grade=BrainGrade.B,
        reason="single source unverified",
        evidence=["headline=foo src=blog type=social"],
        data_quality="good",
        should_block=False,
        risk_flags=["unverified_source"],
        confidence=0.5,
        timestamp_utc=_now(),
    )


def make_news_aligned() -> BrainOutput:
    return BrainOutput(
        brain_name="newsmind",
        decision="WAIT",      # NewsMind never says BUY/SELL alone
        grade=BrainGrade.A,
        reason="2 confirmations fresh good data",
        evidence=["headline=Fed src=federalreserve type=authoritative"],
        data_quality="good",
        should_block=False,
        risk_flags=[],
        confidence=0.8,
        timestamp_utc=_now(),
    )


def make_news_silent() -> BrainOutput:
    return BrainOutput(
        brain_name="newsmind",
        decision="WAIT",
        grade=BrainGrade.C,
        reason="no recent items",
        evidence=["confirmations=0"],
        data_quality="good",
        should_block=False,
        risk_flags=[],
        confidence=0.3,
        timestamp_utc=_now(),
    )


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def trending_up():
    return make_trending_bars("up", n=120)


@pytest.fixture
def trending_down():
    return make_trending_bars("down", n=120)


@pytest.fixture
def ranging():
    return make_ranging_bars(n=120)


@pytest.fixture
def choppy():
    return make_choppy_bars(n=120)


@pytest.fixture
def vol_spike():
    return make_volatility_spike(n=120)


@pytest.fixture
def low_vol_session():
    return make_low_volume_session(n=50)


@pytest.fixture
def off_session():
    return make_off_session_bars(n=50)


@pytest.fixture
def news_block():
    return make_news_block()


@pytest.fixture
def news_warning():
    return make_news_warning()


@pytest.fixture
def news_aligned():
    return make_news_aligned()


@pytest.fixture
def news_silent():
    return make_news_silent()


@pytest.fixture
def now_utc():
    return _now()


# ---------------------------------------------------------------------------
# Hardening: reset the sticky liquidity baseline between every test so cross-
# test state pollution can't mask a regression.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_liquidity_sticky_state():
    from marketmind.v4 import liquidity_rule as _liq
    _liq.reset_sticky_state()
    yield
    _liq.reset_sticky_state()
