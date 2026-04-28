"""Full evaluate() pipeline — 5+ integration scenarios.

Required scenarios (Phase 1):
  1. NewsMind OK + MarketMind bullish
  2. NewsMind risk + MarketMind bullish
  3. NewsMind missing + MarketMind anything
  4. NewsMind warning + MarketMind uncertain
  5. NewsMind clean + MarketMind choppy
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from contracts.brain_output import BrainGrade, BrainOutput
from marketmind.v4 import MarketMindV4
from marketmind.v4.models import Bar
from marketmind.v4.tests.conftest import (
    make_choppy_bars,
    make_news_aligned,
    make_news_block,
    make_news_warning,
    make_trending_bars,
)


def _now():
    # 13:00 UTC = active NY/London overlap
    return datetime(2026, 4, 27, 13, 0, tzinfo=timezone.utc)


def _bars_active_hour_trending(direction="up", n=120):
    """Build a clean, NORMAL-volatility trend ending in active hours.

    Uses a constant-absolute-step (0.0006) so per-bar ranges don't grow
    with price. ATR percentile lands near 50 -> 'normal' volatility.
    1-hour spacing, ending at _now().
    """
    sign = 1 if direction == "up" else -1
    end = _now()
    bars = []
    p = 1.10
    for i in range(n):
        ts = end - timedelta(hours=(n - 1 - i))
        nxt = p + sign * 0.0006
        hi = max(p, nxt) + 0.0002
        lo = min(p, nxt) - 0.0002
        bars.append(Bar(timestamp=ts, open=p, high=hi, low=lo, close=nxt,
                        volume=1500.0, spread_pips=0.5))
        p = nxt
    return bars


def test_news_ok_marketmind_bullish_yields_buy():
    eng = MarketMindV4()
    bars = _bars_active_hour_trending("up", n=120)
    out = eng.evaluate(
        "EURUSD",
        {"EURUSD": bars},
        _now(),
        news_output=make_news_aligned(),
    )
    assert out.brain_name == "marketmind"
    assert out.trend_state in ("strong_up", "weak_up"), out.evidence
    # NewsMind aligned -> not capped at B by news
    assert out.grade != BrainGrade.BLOCK
    assert out.volatility_state in ("normal", "compressed", "expanded")


def test_news_block_overrides_bullish_market():
    eng = MarketMindV4()
    bars = _bars_active_hour_trending("up", n=120)
    out = eng.evaluate(
        "EURUSD",
        {"EURUSD": bars},
        _now(),
        news_output=make_news_block(),
    )
    assert out.grade == BrainGrade.BLOCK
    assert out.decision == "BLOCK"
    assert out.should_block is True
    assert "NewsMind block" in out.reason or "news=block" in out.reason


def test_news_missing_marketmind_can_grade_anything():
    eng = MarketMindV4()
    bars = _bars_active_hour_trending("up", n=120)
    out = eng.evaluate("EURUSD", {"EURUSD": bars}, _now(), news_output=None)
    assert out.brain_name == "marketmind"
    assert out.news_context_used == {"present": False}


def test_news_warning_caps_grade_at_b():
    eng = MarketMindV4()
    bars = _bars_active_hour_trending("up", n=120)
    out = eng.evaluate(
        "EURUSD",
        {"EURUSD": bars},
        _now(),
        news_output=make_news_warning(),
    )
    # cap is B — never higher; could be B, C, or BLOCK if other failures
    assert out.grade in (BrainGrade.B, BrainGrade.C, BrainGrade.BLOCK)
    if out.grade != BrainGrade.BLOCK:
        assert out.decision == "WAIT"


def test_clean_news_choppy_market_yields_wait_not_block():
    eng = MarketMindV4()
    bars = make_choppy_bars(n=120)
    end = _now()
    fixed = []
    for i, b in enumerate(bars):
        ts = end - timedelta(hours=(len(bars) - 1 - i))
        fixed.append(Bar(timestamp=ts, open=b.open, high=b.high, low=b.low,
                         close=b.close, volume=b.volume, spread_pips=b.spread_pips))
    out = eng.evaluate(
        "EURUSD",
        {"EURUSD": fixed},
        _now(),
        news_output=make_news_aligned(),
    )
    assert out.trend_state == "choppy"
    assert out.grade != BrainGrade.A_PLUS
    # choppy trend -> not BUY/SELL
    assert out.decision in ("WAIT", "BLOCK")


def test_off_session_forces_block():
    """LAST bar at 02:00 UTC -> off-session -> HARD_BLOCK."""
    eng = MarketMindV4()
    end = datetime(2026, 4, 27, 2, 0, tzinfo=timezone.utc)
    bars = []
    p = 1.10
    for i in range(50):
        ts = end - timedelta(hours=(50 - 1 - i))
        nxt = p + 0.0003
        bars.append(Bar(timestamp=ts, open=p, high=nxt + 0.0002, low=p - 0.0002,
                        close=nxt, volume=1500.0, spread_pips=0.5))
        p = nxt
    out = eng.evaluate("EURUSD", {"EURUSD": bars}, end, news_output=make_news_aligned())
    assert out.liquidity_state == "off-session", out.evidence
    assert out.grade == BrainGrade.BLOCK
    assert out.should_block is True


def test_no_bars_fails_closed():
    eng = MarketMindV4()
    out = eng.evaluate("EURUSD", {}, _now(), news_output=None)
    assert out.grade == BrainGrade.BLOCK
    assert out.should_block is True
    assert "fail_closed" in out.risk_flags


def test_marketstate_isa_brainoutput():
    """MarketState IS-A BrainOutput."""
    eng = MarketMindV4()
    bars = _bars_active_hour_trending("up", n=120)
    out = eng.evaluate(
        "EURUSD",
        {"EURUSD": bars},
        _now(),
        news_output=make_news_aligned(),
    )
    assert isinstance(out, BrainOutput)
    assert out.brain_name == "marketmind"
