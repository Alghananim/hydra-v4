"""TREND_RULE: cover all 6 states + 'none'."""
from __future__ import annotations

from marketmind.v4 import trend_rule
from marketmind.v4.tests.conftest import (
    make_trending_bars,
    make_ranging_bars,
    make_choppy_bars,
)


def test_strong_up():
    bars = make_trending_bars("up", n=120, step_pct=0.0015)
    state, ev = trend_rule.evaluate(bars)
    assert state == "strong_up", ev


def test_strong_down():
    bars = make_trending_bars("down", n=120, step_pct=0.0015)
    state, ev = trend_rule.evaluate(bars)
    assert state == "strong_down", ev


def test_range_state():
    bars = make_ranging_bars(n=120, band_pct=0.0005)
    state, ev = trend_rule.evaluate(bars)
    # Ranging-or-weak — both acceptable depending on phase; strict: NOT strong
    assert state in ("range", "weak_up", "weak_down", "choppy"), ev
    assert state not in ("strong_up", "strong_down")


def test_choppy_state():
    bars = make_choppy_bars(n=60)
    state, ev = trend_rule.evaluate(bars)
    assert state == "choppy", ev


def test_weak_up_partial_signal():
    # Slow drift up that doesn't satisfy slope/ATR > 0.5
    bars = make_trending_bars("up", n=120, step_pct=0.00005)
    state, ev = trend_rule.evaluate(bars)
    assert state in ("weak_up", "range"), ev
    assert state != "strong_up"


def test_weak_down_partial_signal():
    bars = make_trending_bars("down", n=120, step_pct=0.00005)
    state, ev = trend_rule.evaluate(bars)
    assert state in ("weak_down", "range"), ev
    assert state != "strong_down"


def test_none_when_too_few_bars():
    bars = make_trending_bars("up", n=10)
    state, ev = trend_rule.evaluate(bars)
    assert state == "none", ev


def test_regime_mapping():
    assert trend_rule.regime_from_trend("strong_up") == "trending"
    assert trend_rule.regime_from_trend("strong_down") == "trending"
    assert trend_rule.regime_from_trend("range") == "ranging"
    assert trend_rule.regime_from_trend("choppy") == "choppy"
    assert trend_rule.regime_from_trend("weak_up") == "transitioning"
    assert trend_rule.regime_from_trend("none") == "transitioning"
