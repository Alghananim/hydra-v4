# -*- coding: utf-8 -*-
"""FIX #2A — daily counter rollover at UTC midnight.

Verifies that EngineV3 zeroes daily_loss_pct, consecutive_losses, and
trades_today when the calendar UTC date advances. Without this, day-2 of
a live run inherits day-1 counters and the kill-switch false-fires.
"""
from __future__ import annotations
import sys, tempfile, pathlib
from datetime import datetime, timezone

_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engine.v3 import EngineV3, ValidationConfig


def _make_engine(tmp):
    cfg = ValidationConfig()
    cfg.smartnotebook_dir = tmp
    cfg.broker_env = "practice"
    return EngineV3(cfg=cfg, broker=None, account_balance=10000), cfg


def test_daily_counters_reset_after_utc_midnight():
    """The flagship test: counters set on day 1 are zero on day 2."""
    with tempfile.TemporaryDirectory() as tmp:
        eng, _ = _make_engine(tmp)
        # Day 1 state
        eng.daily_loss_pct = 0.012
        eng.consecutive_losses = 1
        eng.trades_today = 2
        eng.last_reset_date = datetime(2026, 4, 26).date()
        eng._persist_state()

        # Just past midnight on day 2 — direct call
        eng._daily_reset_if_needed(datetime(2026, 4, 27, 0, 0, 1,
                                             tzinfo=timezone.utc))
        assert eng.daily_loss_pct == 0.0, f"got {eng.daily_loss_pct}"
        assert eng.consecutive_losses == 0, f"got {eng.consecutive_losses}"
        assert eng.trades_today == 0, f"got {eng.trades_today}"
        assert eng.last_reset_date == datetime(2026, 4, 27).date()
        eng.stop()


def test_no_reset_within_same_utc_day():
    """Calls within the same UTC date must NOT reset counters."""
    with tempfile.TemporaryDirectory() as tmp:
        eng, _ = _make_engine(tmp)
        eng.daily_loss_pct = 0.5
        eng.consecutive_losses = 1
        eng.trades_today = 3
        eng.last_reset_date = datetime(2026, 4, 27).date()
        eng._persist_state()

        # Same day, just later
        did_reset = eng._daily_reset_if_needed(
            datetime(2026, 4, 27, 23, 59, 59, tzinfo=timezone.utc))
        assert did_reset is False
        assert eng.daily_loss_pct == 0.5
        assert eng.consecutive_losses == 1
        assert eng.trades_today == 3
        eng.stop()


def test_first_call_initialises_last_reset_date():
    """A fresh engine has last_reset_date=None and resets on first call."""
    with tempfile.TemporaryDirectory() as tmp:
        eng, _ = _make_engine(tmp)
        assert eng.last_reset_date is None
        # Carry-over counters from older persisted state
        eng.daily_loss_pct = 0.7
        eng.consecutive_losses = 2
        eng.trades_today = 1

        did_reset = eng._daily_reset_if_needed(
            datetime(2026, 4, 27, 12, 0, 0, tzinfo=timezone.utc))
        assert did_reset is True
        assert eng.daily_loss_pct == 0.0
        assert eng.consecutive_losses == 0
        assert eng.trades_today == 0
        assert eng.last_reset_date == datetime(2026, 4, 27).date()
        eng.stop()


def test_last_reset_date_persists_across_restart():
    """After stop+restart, last_reset_date should rehydrate."""
    with tempfile.TemporaryDirectory() as tmp:
        eng1, cfg = _make_engine(tmp)
        eng1.last_reset_date = datetime(2026, 4, 27).date()
        eng1.daily_loss_pct = 0.3
        eng1._persist_state()
        eng1.stop()

        eng2 = EngineV3(cfg=cfg, broker=None, account_balance=10000)
        assert eng2.last_reset_date == datetime(2026, 4, 27).date()
        # Same UTC day → no reset
        eng2._daily_reset_if_needed(
            datetime(2026, 4, 27, 8, 0, 0, tzinfo=timezone.utc))
        assert eng2.daily_loss_pct == 0.3
        eng2.stop()


if __name__ == "__main__":
    for fn in (test_daily_counters_reset_after_utc_midnight,
               test_no_reset_within_same_utc_day,
               test_first_call_initialises_last_reset_date,
               test_last_reset_date_persists_across_restart):
        try:
            fn(); print(f"PASS {fn.__name__}")
        except AssertionError as e:
            print(f"FAIL {fn.__name__}: {e}"); sys.exit(1)
    print("ALL PASS")
