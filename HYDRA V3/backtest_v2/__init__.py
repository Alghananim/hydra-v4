# -*- coding: utf-8 -*-
"""backtest_v2 — professional harness around HYDRA V3's EngineV3.

Design contract
---------------
This package is a HARNESS, not a parallel engine. Every trading
decision is delegated verbatim to the production
``EngineV3.decide_and_maybe_trade()``. We never re-implement gating,
risk, or signal logic in the backtester — doing so would defeat the
purpose of testing the production system.

Public surface
--------------
    from backtest_v2 import (
        BacktestConfig,             # one place for all knobs
        BacktestRunner,              # main loop
        BacktestReport,              # metrics output
        LookaheadLeakError,          # raised on any look-ahead access
    )
"""
from __future__ import annotations

from .config import BacktestConfig
from .leak_detector import LookaheadLeakError, LeakSafeBars
from .runner import BacktestRunner
from .metrics import BacktestReport, compute_report

__all__ = [
    "BacktestConfig",
    "BacktestRunner",
    "BacktestReport",
    "compute_report",
    "LookaheadLeakError",
    "LeakSafeBars",
]

__version__ = "0.1.0"
