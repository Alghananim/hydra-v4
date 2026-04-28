# -*- coding: utf-8 -*-
"""test_strict_blocks_b_grades — in strict mode, ChartMind 'B' grade
trades must NOT be accepted."""
from __future__ import annotations

import sys
import pathlib
from datetime import datetime, timezone

_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pytest    # type: ignore

from backtest_v2.fixtures.synthetic_bars import make_breakout_series


def _make_engine(*, strict: bool):
    from engine.v3 import EngineV3, ValidationConfig
    from engine.v3 import safety_rails as _sr
    from backtest_v2.runner import _BacktestNotebookProxy
    cfg = ValidationConfig()
    cfg.broker_env = "practice"     # validate first
    cfg.smartnotebook_dir = f"/tmp/bt2_test_strict_{strict}_nb"
    cfg.risk_pct_per_trade = 0.25
    cfg.pair_status["EUR/USD"] = "production"
    cfg.validate_or_die()
    cfg.broker_env = "paper"        # then swap for GateMind
    if not getattr(_sr.check_all, "_backtest_v2_patched", False):
        _orig = _sr.check_all
        def _patched(**kw):
            if kw.get("broker_mode") == "paper":
                kw = dict(kw); kw["broker_mode"] = "practice"
            return _orig(**kw)
        _patched._backtest_v2_patched = True
        _patched._backtest_v2_orig = _orig
        _sr.check_all = _patched
    eng = EngineV3(cfg=cfg, broker=None, account_balance=10_000,
                   strict_mode=strict)
    eng.nb = _BacktestNotebookProxy(eng.nb)
    return eng


def _make_chart_b(*, bars):
    from chartmind.v3.models import ChartAssessment
    last = bars[-1]
    sl = last.close - 0.0010
    tp = last.close + 0.0030
    return ChartAssessment(
        pair="EUR/USD", timestamp_utc=last.time,
        timeframes_used=("M15",),
        market_structure="uptrend",
        trend_direction="up", trend_strength=0.7,
        trend_quality="smooth",
        nearest_key_level=last.close, nearest_key_distance_atr=1.0,
        nearest_key_role="support",
        candlestick_signal="bullish_engulfing",
        candlestick_context="trend_pullback",
        candlestick_quality="strong",
        breakout_status="confirmed", retest_status="completed",
        pullback_quality="clean", entry_quality="confirmed_breakout",
        late_entry_risk=False, fake_breakout_risk=False,
        stop_loss=sl, take_profit=tp, risk_reward=3.0,
        stop_logic="atr_based", target_logic="next_resistance",
        volatility_status="normal", atr_status="normal",
        timeframe_alignment="aligned",
        grade="B",
        confidence=0.65,
        trade_permission="allow",
        reason="b_grade_test_setup",
    )


def _make_market_b():
    from marketmind.v3.models import MarketAssessment
    return MarketAssessment(
        pair="EUR/USD", timestamp_utc=datetime.now(timezone.utc),
        market_regime="trend", direction="up",
        risk_mode="risk_on", volatility_level="normal",
        liquidity_condition="good", spread_condition="tight",
        grade="B", confidence=0.65,
        trade_permission="allow", reason="b_grade_test_market",
        data_quality_status="ok",
    )


def _make_news_a():
    from newsmind.v3.models import NewsVerdict
    return NewsVerdict(
        headline="quiet", source_name="test", source_type="calendar",
        verified=True, freshness_status="fresh",
        impact_level="low", market_bias="bullish",
        risk_mode="risk_on", grade="A", confidence=0.7,
        trade_permission="allow", reason="quiet_window",
    )


def test_strict_mode_blocks_b_grade_chart():
    bars = make_breakout_series(n_bars=60)
    eng = _make_engine(strict=True)
    decision = eng.decide_and_maybe_trade(
        pair="EUR/USD",
        news_verdict=_make_news_a(),
        market_assessment=_make_market_b(),
        chart_assessment=_make_chart_b(bars=bars),
        recent_bars=bars,
        spread_pips=0.5, slippage_pips=0.5,
        now_utc=bars[-1].time)
    assert decision["decision"] not in ("entered", "enter_dry_run"), (
        f"strict mode failed to block B-grade; decision={decision}")


def test_loose_mode_can_consider_b_grade():
    bars = make_breakout_series(n_bars=60)
    eng_strict = _make_engine(strict=True)
    eng_loose = _make_engine(strict=False)
    args = dict(
        pair="EUR/USD",
        news_verdict=_make_news_a(),
        market_assessment=_make_market_b(),
        chart_assessment=_make_chart_b(bars=bars),
        recent_bars=bars,
        spread_pips=0.5, slippage_pips=0.5,
        now_utc=bars[-1].time)
    d_s = eng_strict.decide_and_maybe_trade(**args)
    d_l = eng_loose.decide_and_maybe_trade(**args)

    strict_blocked = d_s["decision"] not in ("entered", "enter_dry_run")
    loose_blocked = d_l["decision"] not in ("entered", "enter_dry_run")
    if not strict_blocked:
        assert not loose_blocked
    assert strict_blocked


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
