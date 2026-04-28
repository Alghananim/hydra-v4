# -*- coding: utf-8 -*-
"""test_account_persistence — open at bar 5, hold through 6-10,
close at bar 10. Verify balance evolves correctly."""
from __future__ import annotations

import sys
import pathlib
import uuid
from datetime import datetime, timedelta, timezone

_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pytest    # type: ignore

from backtest_v2.account_simulator import AccountSimulator
from backtest_v2.broker_replay import ReplayBroker
from backtest_v2.fixtures.synthetic_bars import SyntheticBar


def _zero_spread_bar(t, o, h, l, c):
    """Build a bar where bid == ask == mid → no spread cost."""
    return SyntheticBar(
        time=t, timestamp=t, open=o, high=h, low=l, close=c,
        bid_open=o, bid_close=c,
        ask_open=o, ask_close=c,
        spread_pips=0.0, volume=1000)


def test_balance_evolves_on_close():
    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    bars = []
    # Bars 0..4: tight range around 1.10 (no movement)
    for i in range(5):
        bars.append(_zero_spread_bar(t0 + timedelta(minutes=15 * i),
                                       1.1000, 1.1005, 1.0995, 1.1000))
    # Bar 5: next-bar after signal — entry fills here at open
    bars.append(_zero_spread_bar(t0 + timedelta(minutes=15 * 5),
                                   1.1000, 1.1005, 1.0995, 1.1000))
    # Bars 6..9: drift up but no SL/TP hit (range stays inside band)
    for i in range(6, 10):
        bars.append(_zero_spread_bar(
            t0 + timedelta(minutes=15 * i),
            1.1000 + (i - 5) * 0.0001,
            1.1003 + (i - 5) * 0.0001,
            1.0997 + (i - 5) * 0.0001,
            1.1000 + (i - 5) * 0.0001))
    # Bar 10: high reaches 1.1025 → take-profit at 1.1020 hit
    bars.append(_zero_spread_bar(
        t0 + timedelta(minutes=15 * 10),
        1.1006, 1.1025, 1.1004, 1.1020))

    acct = AccountSimulator(initial_balance=10_000.0, pair_pip=0.0001)
    broker = ReplayBroker(account=acct, pair="EUR/USD", pair_pip=0.0001,
                            entry_slippage_pips=0.0,
                            stop_slippage_pips=0.0,
                            target_slippage_pips=0.0,
                            fallback_spread_pips=0.0,
                            commission_per_lot_per_side=0.0)

    pos = broker.fill_entry_at_next_open(
        signal_bar=bars[4], next_bar=bars[5],
        direction="buy", units=10_000.0,
        stop_loss=1.0980, take_profit=1.1020,
        expected_rr=2.0, audit_id=str(uuid.uuid4()))
    assert acct.has_open()
    assert pos.entry_price == pytest.approx(1.1000, abs=1e-9)
    assert len(acct.open_positions) == 1

    # Walk bars 6..9 — no exit, position stays open, balance unchanged
    for i in range(6, 10):
        closed = broker.update_open_positions(bar=bars[i])
        assert closed == [], f"unexpected close at bar {i}"
        assert acct.has_open(), f"position vanished at bar {i}"
        assert acct.balance == 10_000.0, "balance changed before close"

    # Bar 10 — TP at 1.1020 hit (bar high = 1.1025)
    closed = broker.update_open_positions(bar=bars[10])
    assert len(closed) == 1, f"expected 1 close, got {len(closed)}"
    ct = closed[0]
    assert ct.hit_target is True
    assert ct.exit_reason == "target"
    # 20 pips on 10000 units (0.1 lot) at $10/pip/lot = $20
    assert ct.pnl_pips == pytest.approx(20.0, abs=1e-6)
    assert ct.pnl_currency == pytest.approx(20.0, abs=1e-6)
    assert acct.balance == pytest.approx(10_020.0, abs=1e-6)
    assert not acct.has_open()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
