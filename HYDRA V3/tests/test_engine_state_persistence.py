# -*- coding: utf-8 -*-
"""Engine state persistence test (Phase 1b).

Verifies daily_loss_pct, consecutive_losses, trades_today survive a
process-style restart by being persisted to the SmartNoteBook engine_state
SQLite table and rehydrated on next EngineV3.__init__.
"""
from __future__ import annotations
import sys, tempfile, pathlib, os

_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engine.v3 import EngineV3, ValidationConfig


def test_engine_state_persists_across_restart():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = ValidationConfig()
        cfg.smartnotebook_dir = tmp
        cfg.broker_env = "practice"

        # ---- 1. First engine: set values, persist, stop. ----
        eng1 = EngineV3(cfg=cfg, broker=None, account_balance=10000)
        assert eng1.daily_loss_pct == 0.0
        assert eng1.consecutive_losses == 0
        assert eng1.trades_today == 0
        eng1.daily_loss_pct = 0.012
        eng1.consecutive_losses = 1
        eng1.trades_today = 2
        eng1._persist_state()
        eng1.stop()

        # ---- 2. New engine on same notebook dir: should rehydrate. ----
        eng2 = EngineV3(cfg=cfg, broker=None, account_balance=10000)
        assert eng2.daily_loss_pct == 0.012, f"got {eng2.daily_loss_pct}"
        assert eng2.consecutive_losses == 1, f"got {eng2.consecutive_losses}"
        assert eng2.trades_today == 2, f"got {eng2.trades_today}"
        eng2.stop()


def test_engine_state_default_zero_when_fresh():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = ValidationConfig()
        cfg.smartnotebook_dir = tmp
        eng = EngineV3(cfg=cfg, broker=None, account_balance=10000)
        assert eng.daily_loss_pct == 0.0
        assert eng.consecutive_losses == 0
        assert eng.trades_today == 0
        eng.stop()


def test_update_after_close_persists():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = ValidationConfig()
        cfg.smartnotebook_dir = tmp
        eng1 = EngineV3(cfg=cfg, broker=None, account_balance=10000)
        # Simulate a $250 loss (2.5% on 10k)
        eng1.update_after_close(trade_id="t1", pnl=-250.0,
                                 exit_price=1.10, exit_reason="stop")
        eng1.stop()
        eng2 = EngineV3(cfg=cfg, broker=None, account_balance=10000)
        assert eng2.consecutive_losses == 1
        assert abs(eng2.daily_loss_pct - 2.5) < 1e-6
        eng2.stop()


if __name__ == "__main__":
    for fn_name in ("test_engine_state_persists_across_restart",
                    "test_engine_state_default_zero_when_fresh",
                    "test_update_after_close_persists"):
        try:
            globals()[fn_name]()
            print(f"  PASS  {fn_name}")
        except AssertionError as e:
            print(f"  FAIL  {fn_name}: {e}")
            sys.exit(1)
    print("ALL PASS")
