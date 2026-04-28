"""ChartMind V4 — shared bar fixtures and mock upstream outputs.

Builds bar series for every rule under test:
- bullish_strong / bearish_strong (clean uptrend / downtrend)
- range, choppy
- breakout (clean) / fake_breakout (wick exceeds, close returns)
- retest (breakout + 3..10 bar retest + continuation)
- pullback (uptrend + 0.5..1.5 ATR pullback + continuation)

Plus mock NewsMind/MarketMind outputs for integration tests.
"""
from __future__ import annotations

import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

import pytest

# Add project root so contracts.* / marketmind.* / chartmind.* import
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from contracts.brain_output import BrainGrade, BrainOutput
from marketmind.v4.models import Bar, MarketState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ts(i: int, base: Optional[datetime] = None, minutes: int = 15) -> datetime:
    base = base or datetime(2026, 4, 27, 10, 0, tzinfo=timezone.utc)
    return base + timedelta(minutes=minutes * i)


def _bar(i: int, o: float, h: float, l: float, c: float,
         *, base_ts=None, vol: float = 1500.0, spread: float = 0.5,
         minutes: int = 15) -> Bar:
    return Bar(timestamp=_ts(i, base_ts, minutes),
               open=o, high=h, low=l, close=c,
               volume=vol, spread_pips=spread)


# ---------------------------------------------------------------------------
# Trend fixtures
# ---------------------------------------------------------------------------


def make_bullish_strong_bars(n: int = 90, start: float = 1.1000,
                             step: float = 0.0010, base_ts=None) -> List[Bar]:
    """Clean uptrend with multi-bar pullbacks — tuned for Hardening C3 to
    reliably produce bullish_strong AND keep current ATR percentile in
    the 'normal' band (so the volatility_normal evidence flag fires for
    the e2e A+ test).

    Geometry uses ADDITIVE per-bar moves (delta = step*start), giving
    constant per-bar true-range. This decouples ATR from price level and
    keeps the current ATR percentile near the middle of its history,
    avoiding the 'expanded' / 'dangerous' classification that strict
    multiplicative growth forces.

    9-bar cycle:
      bars 0-4: drive UP (5 up bars; cyc=4 = local swing high)
      bars 5-7: PULLBACK by 3 bars at -1*delta each (cyc=7 = local swing
                low; cumulative drop = 3*delta clears the recent up-bar
                lows so the k=3 fractal on the LEFT is satisfied)
      bar  8 : resume UP at +0.5*delta (gives net cycle gain of +0.5*delta)

    With n=90, the 40-bar lookback contains 4-5 cycles → 4 swing highs +
    4 swing lows comfortably > 3. Trailing pullback (3 bars) keeps
    last_close BELOW last swing high (BoS=False) and ABOVE last swing low.
    """
    bars: List[Bar] = []
    p = start
    delta = step * start                # constant absolute per-bar move
    pullback_tail_bars = 3
    n_main = n - pullback_tail_bars
    for i in range(n_main):
        cyc = i % 9
        if cyc < 5:
            # up leg (additive)
            nxt = p + delta
            hi = nxt + delta * 0.4
            lo = p - delta * 0.05
        elif cyc < 8:
            # 3-bar pullback (each bar: -1*delta)
            nxt = p - delta
            hi = p + delta * 0.05
            lo = nxt - delta * 0.3
        else:
            # resume up by +0.5*delta -> net cycle gain = +0.5*delta
            nxt = p + delta * 0.5
            hi = nxt + delta * 0.3
            lo = p - delta * 0.1
        bars.append(_bar(i, p, hi, lo, nxt, base_ts=base_ts))
        p = nxt
    # Trailing pullback (3 bars at -0.15*delta each) — small enough that
    # the resulting depth_atr from the LAST swing high to last_close
    # lands in the pullback band [0.5, 1.5]*ATR (RULE 6) so the
    # pullback_in_trend setup fires and the chart direction is "long"
    # (required for direction-conflict cap testing in scenario 3).
    # Bars 85 hi ≈ P+9.9*delta, last_close ≈ P+8.05*delta, depth ≈ 1.36 ATR.
    # Bar TR ≈ 1.4*delta keeps ATR percentile in 'normal'.
    for j in range(pullback_tail_bars):
        i = n_main + j
        nxt = p - delta * 0.15
        hi = p + delta * 0.05
        lo = nxt - delta * 1.20      # trailing TR ≈ 1.4*delta
        bars.append(_bar(i, p, hi, lo, nxt, base_ts=base_ts))
        p = nxt
    return bars


def make_bearish_strong_bars(n: int = 90, start: float = 1.1000,
                             step: float = 0.0010, base_ts=None) -> List[Bar]:
    """Symmetric mirror of make_bullish_strong_bars (Hardening C3) — same
    additive 9-bar geometry inverted."""
    bars: List[Bar] = []
    p = start
    delta = step * start
    pullback_tail_bars = 3
    n_main = n - pullback_tail_bars
    for i in range(n_main):
        cyc = i % 9
        if cyc < 5:
            # down leg
            nxt = p - delta
            hi = p + delta * 0.05
            lo = nxt - delta * 0.4
        elif cyc < 8:
            # 3-bar bounce
            nxt = p + delta
            hi = nxt + delta * 0.3
            lo = p - delta * 0.05
        else:
            # resume DOWN by -0.5*delta
            nxt = p - delta * 0.5
            hi = p + delta * 0.1
            lo = nxt - delta * 0.3
        bars.append(_bar(i, p, hi, lo, nxt, base_ts=base_ts))
        p = nxt
    # Trailing relief rally — keeps last_close > last swing low (no
    # BoS-down) AND < last swing high (no BoS-up). Trailing TR ≈ 1.4*delta
    # matches cycle average → ATR percentile stays in 'normal'.
    for j in range(pullback_tail_bars):
        i = n_main + j
        nxt = p + delta * 0.3
        hi = nxt + delta * 1.05
        lo = p - delta * 0.05
        bars.append(_bar(i, p, hi, lo, nxt, base_ts=base_ts))
        p = nxt
    return bars


def make_range_bars(n: int = 90, mid: float = 1.1000, band: float = 0.0015,
                    base_ts=None) -> List[Bar]:
    bars: List[Bar] = []
    for i in range(n):
        c = mid * (1 + band * math.sin(i * 0.42))
        prev_c = bars[-1].close if bars else mid
        hi = max(c, prev_c) * 1.0001
        lo = min(c, prev_c) * 0.9999
        bars.append(_bar(i, prev_c, hi, lo, c, base_ts=base_ts))
    return bars


def make_choppy_bars(n: int = 90, mid: float = 1.1000, base_ts=None) -> List[Bar]:
    bars: List[Bar] = []
    p = mid
    for i in range(n):
        sign = 1 if i % 2 == 0 else -1
        nxt = p * (1 + sign * 0.0009)
        hi = max(p, nxt) * 1.0002
        lo = min(p, nxt) * 0.9998
        bars.append(_bar(i, p, hi, lo, nxt, base_ts=base_ts))
        p = nxt
    return bars


# ---------------------------------------------------------------------------
# Breakout / fake breakout / retest / pullback
# ---------------------------------------------------------------------------


def make_breakout_bars(n: int = 90, base_ts=None) -> List[Bar]:
    """Range for first 60 bars at ~1.1000 with resistance ~1.1030,
    then a clean breakout above.
    """
    bars: List[Bar] = []
    # Build a flat range bouncing between 1.0975 and 1.1030
    bounds_low = 1.0975
    bounds_high = 1.1030
    for i in range(60):
        # Touch high every 8 bars, low every 8 bars (staggered)
        if i % 8 == 4:
            o = (bounds_low + bounds_high) / 2
            c = bounds_high - 0.00005
            h = bounds_high * 1.0001  # touch the level
            l = o - 0.0002
        elif i % 8 == 0:
            o = (bounds_low + bounds_high) / 2
            c = bounds_low + 0.00005
            l = bounds_low * 0.9999
            h = o + 0.0002
        else:
            o = bounds_low + 0.0010 + (i % 5) * 0.0002
            c = o + (0.0001 if i % 2 == 0 else -0.0001)
            h = max(o, c) + 0.0002
            l = min(o, c) - 0.0002
        bars.append(_bar(i, o, h, l, c, base_ts=base_ts))

    # Then a strong breakout bar at i=60: open just below resistance, big body close above
    # ATR will be on the order of (h-l) ~ 0.0004; breakout needs >= level + 0.3*ATR
    # Make breakout bar HUGE so it clears comfortably.
    o = bounds_high - 0.0002
    c = bounds_high + 0.0030  # well clear
    h = c + 0.0002
    l = o - 0.0001
    bars.append(_bar(60, o, h, l, c, base_ts=base_ts))

    # Continuation bars
    p = c
    for i in range(61, n):
        nxt = p * (1 + 0.0007)
        hi = max(p, nxt) * 1.0003
        lo = min(p, nxt) * 0.9997
        bars.append(_bar(i, p, hi, lo, nxt, base_ts=base_ts))
        p = nxt
    return bars


def make_fake_breakout_bars(n: int = 90, base_ts=None) -> List[Bar]:
    """Build the same range, then a wick that pokes above 1.1030 but closes back below."""
    bars = make_breakout_bars(n=60, base_ts=base_ts)[:60]
    # Fake bar: high pierces level, close back inside
    bounds_high = 1.1030
    o = bounds_high - 0.0002
    h = bounds_high + 0.0010   # pierce
    c = bounds_high - 0.0008   # close BELOW level
    l = o - 0.0002
    bars.append(_bar(60, o, h, l, c, base_ts=base_ts))
    # Subsequent bars stay below the level
    p = c
    for i in range(61, n):
        nxt = p * (1 - 0.0001)
        hi = max(p, nxt) + 0.0001
        lo = min(p, nxt) - 0.0001
        bars.append(_bar(i, p, hi, lo, nxt, base_ts=base_ts))
        p = nxt
    return bars


def make_retest_bars(n: int = 90, base_ts=None) -> List[Bar]:
    """Breakout at i=50, then ~5 bars later price retraces to level with rejection wick,
    then continues up.
    """
    bars: List[Bar] = []
    bounds_low = 1.0975
    bounds_high = 1.1030
    for i in range(50):
        if i % 8 == 4:
            o = (bounds_low + bounds_high) / 2
            c = bounds_high - 0.00005
            h = bounds_high * 1.0001
            l = o - 0.0002
        elif i % 8 == 0:
            o = (bounds_low + bounds_high) / 2
            c = bounds_low + 0.00005
            l = bounds_low * 0.9999
            h = o + 0.0002
        else:
            o = bounds_low + 0.0010 + (i % 5) * 0.0002
            c = o + (0.0001 if i % 2 == 0 else -0.0001)
            h = max(o, c) + 0.0002
            l = min(o, c) - 0.0002
        bars.append(_bar(i, o, h, l, c, base_ts=base_ts))

    # Breakout bar
    o = bounds_high - 0.0002
    c = bounds_high + 0.0025
    h = c + 0.0002
    l = o - 0.0001
    bars.append(_bar(50, o, h, l, c, base_ts=base_ts))

    # 4 bars drifting back down to the level
    p = c
    for i in range(51, 55):
        nxt = p - 0.0006
        hi = max(p, nxt) + 0.0001
        lo = min(p, nxt) - 0.0001
        bars.append(_bar(i, p, hi, lo, nxt, base_ts=base_ts))
        p = nxt

    # Retest bar at i=55 — low touches level with long lower wick
    o = bounds_high + 0.0005
    l = bounds_high - 0.0003   # touch level
    c = bounds_high + 0.0010   # close back above
    h = c + 0.0002
    bars.append(_bar(55, o, h, l, c, base_ts=base_ts))

    # Continuation
    p = c
    for i in range(56, n):
        nxt = p * (1 + 0.0008)
        hi = max(p, nxt) * 1.0002
        lo = min(p, nxt) * 0.9998
        bars.append(_bar(i, p, hi, lo, nxt, base_ts=base_ts))
        p = nxt
    return bars


def make_pullback_bars(n: int = 90, base_ts=None) -> List[Bar]:
    """Uptrend, then a 0.5..1.5 ATR pullback near the end."""
    bars = make_bullish_strong_bars(n=80, base_ts=base_ts)
    # Last bars: small pullback then resume — but final close stays in band
    last = bars[-1].close
    p = last
    # Drift down ~0.5%-ish so depth_atr lands in [0.5, 1.5]
    for i in range(80, n):
        if i < 85:
            nxt = p * (1 - 0.0006)
        else:
            nxt = p * (1 + 0.0002)
        hi = max(p, nxt) * 1.0002
        lo = min(p, nxt) * 0.9998
        bars.append(_bar(i, p, hi, lo, nxt, base_ts=base_ts))
        p = nxt
    return bars


# ---------------------------------------------------------------------------
# Mock NewsMind / MarketMind outputs
# ---------------------------------------------------------------------------


def _now() -> datetime:
    # MUST match _ts so that "stale" check passes.
    # All builder fixtures produce series with last bar timestamp at
    # base + (n-1) * 15min. We standardise n=90 across fixtures for the
    # bullish/bearish/strong series (was 80 — bumped to satisfy k=3 fractal
    # confirmation for HH/HL >= 3 with reliable bullish_strong labelling).
    # _now is set to base + 89*15min = the last-bar timestamp; this keeps
    # the bar non-stale (delta == 0 < MAX_STALE_MINUTES).
    return datetime(2026, 4, 27, 10, 0, tzinfo=timezone.utc) + timedelta(minutes=15 * 89)


def make_news_block() -> BrainOutput:
    return BrainOutput(
        brain_name="newsmind",
        decision="BLOCK",
        grade=BrainGrade.BLOCK,
        reason="blackout window NFP",
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
        evidence=["src=blog"],
        data_quality="good",
        should_block=False,
        risk_flags=["unverified_source"],
        confidence=0.5,
        timestamp_utc=_now(),
    )


def make_news_aligned() -> BrainOutput:
    return BrainOutput(
        brain_name="newsmind",
        decision="WAIT",
        grade=BrainGrade.A,
        reason="2 confirmations fresh good data",
        evidence=["src=Fed"],
        data_quality="good",
        should_block=False,
        risk_flags=[],
        confidence=0.8,
        timestamp_utc=_now(),
    )


def _market_state(*, decision: str, grade: BrainGrade, trend_state: str,
                  should_block: bool = False,
                  reason: str = "test fixture") -> MarketState:
    return MarketState(
        brain_name="marketmind",
        decision=decision,
        grade=grade,
        reason=reason,
        evidence=["fixture"],
        data_quality="good",
        should_block=should_block,
        risk_flags=[],
        confidence=0.5,
        timestamp_utc=_now(),
        regime_state="trending",
        trend_state=trend_state,
        momentum_state="steady",
        volatility_state="normal",
        liquidity_state="good",
    )


def make_market_bullish_A() -> MarketState:
    return _market_state(decision="BUY", grade=BrainGrade.A, trend_state="strong_up")


def make_market_bearish_A() -> MarketState:
    return _market_state(decision="SELL", grade=BrainGrade.A, trend_state="strong_down")


def make_market_choppy_C() -> MarketState:
    return _market_state(decision="WAIT", grade=BrainGrade.C, trend_state="choppy")


def make_market_block() -> MarketState:
    return _market_state(decision="BLOCK", grade=BrainGrade.BLOCK,
                         trend_state="none", should_block=True,
                         reason="HARD_BLOCK: data_quality=broken")


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def now_utc():
    return _now()


@pytest.fixture
def bullish_strong():
    return make_bullish_strong_bars(90)


@pytest.fixture
def bearish_strong():
    return make_bearish_strong_bars(90)


@pytest.fixture
def ranging():
    return make_range_bars(90)


@pytest.fixture
def choppy():
    return make_choppy_bars(90)


@pytest.fixture
def breakout_series():
    return make_breakout_bars(90)


@pytest.fixture
def fake_breakout_series():
    return make_fake_breakout_bars(90)


@pytest.fixture
def retest_series():
    return make_retest_bars(90)


@pytest.fixture
def pullback_series():
    return make_pullback_bars(90)
