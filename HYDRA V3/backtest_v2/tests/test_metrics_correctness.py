# -*- coding: utf-8 -*-
"""test_metrics_correctness — handcrafted fixture, exact expected
WR / PF / net.

Fixture: 10 trades, 6 wins of +1R ($25), 4 losses of -1R ($25).
"""
from __future__ import annotations

import sys
import pathlib
from datetime import datetime, timedelta, timezone

_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pytest    # type: ignore

from backtest_v2.account_simulator import ClosedTrade
from backtest_v2.metrics import compute_report


def _build_trades():
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    trades = []
    for i in range(6):
        trades.append(ClosedTrade(
            trade_id=f"w{i}", audit_id=f"w{i}", pair="EUR/USD",
            direction="buy", units=25_000.0,
            entry_time=t0 + timedelta(hours=i), entry_price=1.10,
            exit_time=t0 + timedelta(hours=i, minutes=30),
            exit_price=1.10 + 10 * 0.0001,
            stop_loss=1.10 - 10 * 0.0001, take_profit=1.10 + 10 * 0.0001,
            expected_rr=1.0,
            pnl_pips=10.0, pnl_currency=25.0,
            pnl_pct=0.25, exit_reason="target",
            hit_target=True, hit_stop=False,
            spread_at_entry=0.5, slippage_at_entry=0.0,
            mind_outputs_dict={"news_grade": "A", "market_grade": "A",
                               "chart_grade": "A",
                               "news_bias": "bullish",
                               "market_direction": "up",
                               "chart_trend_direction": "up"},
        ))
    for i in range(4):
        trades.append(ClosedTrade(
            trade_id=f"l{i}", audit_id=f"l{i}", pair="EUR/USD",
            direction="buy", units=25_000.0,
            entry_time=t0 + timedelta(hours=10 + i), entry_price=1.10,
            exit_time=t0 + timedelta(hours=10 + i, minutes=30),
            exit_price=1.10 - 10 * 0.0001,
            stop_loss=1.10 - 10 * 0.0001, take_profit=1.10 + 10 * 0.0001,
            expected_rr=1.0,
            pnl_pips=-10.0, pnl_currency=-25.0,
            pnl_pct=-0.25, exit_reason="stop",
            hit_target=False, hit_stop=True,
            spread_at_entry=0.5, slippage_at_entry=0.0,
            mind_outputs_dict={"news_grade": "B", "market_grade": "B",
                               "chart_grade": "B",
                               "news_bias": "bullish",
                               "market_direction": "up",
                               "chart_trend_direction": "up"},
        ))
    return trades


def test_wr_pf_net_match_handcrafted_fixture():
    trades = _build_trades()
    report = compute_report(
        run_id="t1", label="metrics_test", pair="EUR/USD",
        strict_mode=True, initial_balance=10_000.0,
        final_balance=10_050.0, bar_count=100,
        decisions=[{"decision_kind": "enter"} for _ in range(10)],
        closed_trades=trades, max_drawdown_pct=0.005)

    assert report.closed_trades == 10
    assert report.wins == 6
    assert report.losses == 4
    assert abs(report.win_rate - 0.60) < 1e-9
    assert abs(report.profit_factor - 1.50) < 1e-9
    assert abs(report.net_pnl_currency - 50.0) < 1e-9
    assert abs(report.net_pnl_pct - 0.50) < 1e-9
    assert abs(report.expectancy_R - 0.20) < 1e-9
    assert abs(report.max_drawdown_pct - 0.5) < 1e-9

    assert "A" in report.by_news_grade
    assert "B" in report.by_news_grade
    assert report.by_news_grade["A"]["wins"] == 6
    assert report.by_news_grade["B"]["wins"] == 0


def test_zero_trades_safe():
    report = compute_report(
        run_id="t2", label="empty", pair="EUR/USD", strict_mode=True,
        initial_balance=10_000.0, final_balance=10_000.0,
        bar_count=10, decisions=[], closed_trades=[],
        max_drawdown_pct=0.0)
    assert report.closed_trades == 0
    assert report.wins == 0
    assert report.win_rate == 0.0
    assert report.profit_factor == 0.0
    assert report.net_pnl_currency == 0.0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
