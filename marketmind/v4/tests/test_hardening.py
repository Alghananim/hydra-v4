"""Hardening regression tests — proves the M1..M7 fixes hold.

These tests encode the exact attack patterns the Red Team agent used.
If any of them goes red, a regression has been introduced.
"""
from __future__ import annotations

import inspect
import math
from datetime import datetime, timedelta, timezone
from typing import List

import pytest

from contracts.brain_output import BrainGrade
from marketmind.v4 import (
    data_quality,
    indicators,
    liquidity_rule,
    momentum_rule,
    permission_engine as pe,
)
from marketmind.v4.models import Bar


# ===========================================================================
# M1 — slow-drift liquidity baseline poisoning
# ===========================================================================


def _bar(ts: datetime, *, spread: float, vol: float = 1500.0,
         price: float = 1.10) -> Bar:
    return Bar(
        timestamp=ts,
        open=price,
        high=price * 1.0002,
        low=price * 0.9998,
        close=price,
        volume=vol,
        spread_pips=spread,
    )


def test_liquidity_resistant_to_baseline_drift():
    """An attacker walks the spread up over 60 bars then prints a 4x bar.
    Pre-hardening: spread_flag missed because the moving median already
    moved up.  Post-hardening: the absolute ceiling and/or sticky P5
    baseline catch it.
    """
    liquidity_rule.reset_sticky_state()
    base = datetime(2026, 4, 27, 13, 0, tzinfo=timezone.utc)
    bars: List[Bar] = []
    # 60 bars: spread ramps 0.5 -> 1.5
    for i in range(60):
        s = 0.5 + (1.0 * i / 59.0)
        bars.append(_bar(base + timedelta(minutes=15 * i), spread=s))
    # 30 bars at 1.5
    for i in range(60, 90):
        bars.append(_bar(base + timedelta(minutes=15 * i), spread=1.5))
    # last bar: spread = 2.5 (not above 5-pip ceiling, so ceiling won't
    # fire — must be caught by sticky-P5 / rolling-min backstop instead).
    bars.append(_bar(base + timedelta(minutes=15 * 90), spread=2.5))

    state, ev = liquidity_rule.evaluate(
        bars, pair="EURUSD", now_utc=bars[-1].timestamp
    )
    # The spread anomaly MUST be flagged.  Liquidity cannot be "good".
    assert state != "good", ev
    assert "spread_anomaly" in ev["flags"], ev


def test_liquidity_absolute_ceiling_catches_giant_spread():
    """Even with no history, a spread above the per-pair ceiling (5 pips
    for EUR/USD) must auto-flag.  This is the cheap-and-cheerful guarantee
    that no amount of historical drift can suppress."""
    liquidity_rule.reset_sticky_state()
    base = datetime(2026, 4, 27, 13, 0, tzinfo=timezone.utc)
    # 30 bars at 0.5 spread, then last bar at 6 pips (above ceiling).
    bars = [_bar(base + timedelta(minutes=15 * i), spread=0.5) for i in range(30)]
    bars.append(_bar(base + timedelta(minutes=15 * 30), spread=6.0))
    state, ev = liquidity_rule.evaluate(
        bars, pair="EURUSD", now_utc=bars[-1].timestamp
    )
    assert "spread_anomaly" in ev["flags"], ev
    assert "absolute_ceiling" in (ev.get("spread_reason") or ""), ev


# ===========================================================================
# M2 — Bar invariants reject NaN / Inf / negative volume / negative spread
# ===========================================================================


def _now() -> datetime:
    return datetime(2026, 4, 27, 13, 0, tzinfo=timezone.utc)


def test_bar_rejects_nan_high():
    with pytest.raises(ValueError):
        Bar(timestamp=_now(), open=1.0, high=float("nan"), low=1.0, close=1.0)


def test_bar_rejects_inf_close():
    with pytest.raises(ValueError):
        Bar(timestamp=_now(), open=1.0, high=1.0, low=1.0, close=float("inf"))


def test_bar_rejects_neg_inf_low():
    with pytest.raises(ValueError):
        Bar(timestamp=_now(), open=1.0, high=1.0, low=float("-inf"), close=1.0)


def test_bar_rejects_negative_volume():
    with pytest.raises(ValueError):
        Bar(timestamp=_now(), open=1.0, high=1.0, low=1.0, close=1.0, volume=-1.0)


def test_bar_rejects_negative_spread():
    with pytest.raises(ValueError):
        Bar(timestamp=_now(), open=1.0, high=1.0, low=1.0, close=1.0,
            spread_pips=-0.5)


def test_bar_rejects_nan_volume():
    with pytest.raises(ValueError):
        Bar(timestamp=_now(), open=1.0, high=1.0, low=1.0, close=1.0,
            volume=float("nan"))


def test_bar_accepts_zero_spread_and_zero_volume():
    """Sanity: zero is allowed (free-broker, no-vol pre-market).  Only
    NaN/Inf/negative are rejected."""
    b = Bar(timestamp=_now(), open=1.0, high=1.0, low=1.0, close=1.0,
            volume=0.0, spread_pips=0.0)
    assert b.volume == 0.0
    assert b.spread_pips == 0.0


# ===========================================================================
# M3 — Data quality catches non-monotonic / duplicate timestamps
# ===========================================================================


def _ts(i: int) -> datetime:
    return datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc) + timedelta(minutes=15 * i)


def _good_bar(i: int, p: float = 1.10) -> Bar:
    return Bar(timestamp=_ts(i), open=p, high=p * 1.001, low=p * 0.999,
               close=p, volume=1500.0, spread_pips=0.5)


def test_data_quality_catches_reordered_bars():
    """Reverse-ordered bars must produce status='broken' with a
    non_monotonic_timestamps warning."""
    bars = [_good_bar(i) for i in range(20)]
    bars = list(reversed(bars))
    status, warnings = data_quality.assess(bars=bars, now_utc=_ts(25))
    assert status == "broken", (status, warnings)
    assert any("non_monotonic_timestamps" in w for w in warnings), warnings


def test_data_quality_catches_duplicate_timestamps():
    """Two adjacent bars with identical timestamp -> broken."""
    bars = [_good_bar(i) for i in range(10)]
    # duplicate the 5th bar's timestamp on the 6th bar
    bars[5] = Bar(
        timestamp=bars[4].timestamp,  # same as previous
        open=bars[5].open, high=bars[5].high, low=bars[5].low,
        close=bars[5].close, volume=bars[5].volume,
        spread_pips=bars[5].spread_pips,
    )
    status, warnings = data_quality.assess(bars=bars, now_utc=_ts(15))
    assert status == "broken", (status, warnings)
    assert any("duplicate_timestamps" in w for w in warnings), warnings


def test_data_quality_good_when_strictly_monotonic():
    """Sanity: non-broken path still works for clean ordered bars."""
    bars = [_good_bar(i) for i in range(20)]
    status, warnings = data_quality.assess(bars=bars, now_utc=bars[-1].timestamp)
    # We only assert it's NOT "broken" — other warnings (gaps, etc.) may
    # still apply depending on synthetic data.
    assert status != "broken", (status, warnings)


# ===========================================================================
# M5 — High contradiction caps at C
# ===========================================================================


def _ideal_perm() -> pe.PermissionInputs:
    return pe.PermissionInputs(
        trend_state="strong_up",
        momentum_state="accelerating",
        volatility_state="normal",
        liquidity_state="good",
        correlation_status="normal",
        news_state="aligned",
        contradiction_severity=None,
        data_quality="good",
    )


def test_high_contradiction_caps_at_c():
    """All A+ inputs + a single high-severity contradiction => grade=C.
    The previous behavior (single _step_down to A) allowed BUY/SELL with
    a known cross-market contradiction, contradicting the spec."""
    inp = _ideal_perm()
    inp.contradiction_severity = "high"
    r = pe.decide(inp)
    assert r.grade == BrainGrade.C, r
    assert r.decision == "WAIT", r


def test_medium_contradiction_still_caps_at_b():
    """Medium severity unchanged: caps at B."""
    inp = _ideal_perm()
    inp.contradiction_severity = "medium"
    r = pe.decide(inp)
    assert r.grade == BrainGrade.B


# ===========================================================================
# M6 — momentum_rule uses the shared atr_series (no local duplicate)
# ===========================================================================


def test_momentum_uses_shared_atr_series():
    """The momentum rule must import and call indicators.atr_series, not
    a local re-implementation.  We assert two things:

      1. The local `_atr_series_full` private helper has been REMOVED.
      2. `atr_series` is referenced by name in the source.
    """
    src = inspect.getsource(momentum_rule)
    assert "_atr_series_full" not in src, (
        "Local _atr_series_full duplicate must be removed; use indicators.atr_series."
    )
    assert "atr_series" in src, "momentum_rule must reference indicators.atr_series"
    # Also assert the symbol is actually imported into momentum_rule's namespace
    assert hasattr(momentum_rule, "atr_series")
    assert momentum_rule.atr_series is indicators.atr_series


# ===========================================================================
# M7 — liquidity off-session uses now_utc, NOT bars[-1].timestamp
# ===========================================================================


def test_liquidity_uses_now_utc_not_bar_time():
    """Bars are stamped during active session (14:00 UTC), but the wall
    clock is 02:00 UTC (off-session).  Pre-hardening this returned
    "good"; post-hardening it must return "off-session"."""
    liquidity_rule.reset_sticky_state()
    # 30 bars, each one day BEFORE the next, all at hour=14 (active session).
    # End ~6h before now_utc, so bars are stale-but-past — exactly the
    # scenario M7 targets.
    now_utc = datetime(2026, 4, 28, 2, 0, tzinfo=timezone.utc)
    bars: List[Bar] = []
    p = 1.10
    for i in range(30):
        # i=29 -> last bar at 2026-04-27 14:00 (12h before now)
        # i=0  -> first bar 29 days earlier
        ts = now_utc.replace(hour=14, minute=0) - timedelta(days=(30 - i))
        nxt = p * (1 + 0.0001)
        bars.append(Bar(timestamp=ts, open=p, high=nxt * 1.0001,
                        low=p * 0.9999, close=nxt, volume=1500.0,
                        spread_pips=0.5))
        p = nxt
    # Bar timestamps end at hour=14 (active) but now_utc.hour=2 (off-session).
    state, ev = liquidity_rule.evaluate(bars, pair="EURUSD", now_utc=now_utc)
    assert state == "off-session", ev
    assert ev["session_source"] == "now_utc", ev
    assert ev["hour_utc"] == 2, ev


def test_liquidity_active_now_utc_overrides_offhour_bar():
    """Mirror: bars stamped in off-hours, but wall clock says active.
    With the new logic, off-session is decided by now_utc, so we get the
    NORMAL flag-counting branch — NOT 'off-session'.
    """
    liquidity_rule.reset_sticky_state()
    now_utc = datetime(2026, 4, 28, 13, 0, tzinfo=timezone.utc)
    base = now_utc - timedelta(hours=20)   # ~17:00 prev day -- still off-hours by 23:00
    base = base.replace(hour=23, minute=0)
    bars: List[Bar] = []
    p = 1.10
    for i in range(40):
        ts = base + timedelta(minutes=15 * i)
        nxt = p * (1 + 0.0001)
        bars.append(Bar(timestamp=ts, open=p, high=nxt * 1.0001,
                        low=p * 0.9999, close=nxt, volume=1500.0,
                        spread_pips=0.5))
        p = nxt
    state, ev = liquidity_rule.evaluate(bars, pair="EURUSD", now_utc=now_utc)
    assert state != "off-session", ev
    assert ev["session_source"] == "now_utc", ev
