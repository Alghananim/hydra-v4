"""Adversarial: prove no fake ATR.

Strategy: monkey-patch marketmind.v4.indicators.atr() to a sentinel and
verify ChartMindV4 USES the sentinel (i.e. doesn't roll its own ATR).
"""
from __future__ import annotations

from marketmind.v4 import indicators
from chartmind.v4.ChartMindV4 import ChartMindV4
from chartmind.v4.tests.conftest import (
    make_market_bullish_A, make_news_aligned,
)


def test_chartmind_uses_marketmind_atr(bullish_strong, now_utc, monkeypatch):
    sentinel = 0.04242  # a value we'd never compute organically
    monkeypatch.setattr(indicators, "atr", lambda bars, period=14: sentinel)
    # Need to patch the alias inside ChartMindV4 too — it imports the module.
    # The orchestrator calls `indicators.atr(bars)` directly so this monkeypatch
    # is sufficient.
    cm = ChartMindV4()
    out = cm.evaluate("EURUSD", {"M15": bullish_strong}, now_utc=now_utc,
                      news_output=make_news_aligned(),
                      market_output=make_market_bullish_A())
    assert out.atr_value == sentinel, (
        f"ChartMind reported atr_value={out.atr_value}, expected sentinel={sentinel}. "
        "Likely re-implements ATR locally — must use marketmind.v4.indicators.atr."
    )


def test_chartmind_atr_value_in_indicator_snapshot(bullish_strong, now_utc):
    cm = ChartMindV4()
    out = cm.evaluate("EURUSD", {"M15": bullish_strong}, now_utc=now_utc,
                      news_output=make_news_aligned(),
                      market_output=make_market_bullish_A())
    assert out.indicator_snapshot["atr"] == out.atr_value


def test_no_chartmind_local_atr_function():
    """ChartMind must not define a function named 'atr' anywhere."""
    import importlib
    import pkgutil
    import chartmind.v4 as pkg

    found_atr_def = []
    for finder, name, ispkg in pkgutil.iter_modules(pkg.__path__):
        full = f"{pkg.__name__}.{name}"
        try:
            mod = importlib.import_module(full)
        except Exception:
            continue
        # Whitelist: chart_thresholds.ATR_PERIOD is a CONSTANT, not a function.
        if hasattr(mod, "atr") and callable(getattr(mod, "atr")):
            found_atr_def.append(full)
    assert found_atr_def == [], f"ChartMind defines local atr() in {found_atr_def}"
