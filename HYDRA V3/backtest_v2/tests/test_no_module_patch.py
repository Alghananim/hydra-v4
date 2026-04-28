# -*- coding: utf-8 -*-
"""FIX #3A — backtest must NOT monkey-patch safety_rails.check_all.

Before this fix, BacktestRunner._build_engine installed a wrapper around
engine.v3.safety_rails.check_all at MODULE level. The wrapper persisted
across the Python process; if a live engine were instantiated later in
the same process it would inherit the patched (paper -> practice mapping)
safety check.

Now the wrapper is dependency-injected into the BACKTEST Engine instance
only; the module-level check_all is untouched.
"""
from __future__ import annotations
import sys, pathlib, tempfile

_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engine.v3 import safety_rails as _sr


def _capture_original():
    """Snapshot the module check_all at import time."""
    return _sr.check_all


_ORIG_CHECK_ALL = _capture_original()


def _build_minimal_runner_and_run():
    """Build a BacktestRunner and force its _build_engine to execute."""
    from backtest_v2.config import BacktestConfig
    from backtest_v2.runner import BacktestRunner
    from datetime import datetime, timezone
    with tempfile.TemporaryDirectory() as tmp:
        cfg = BacktestConfig(
            pair="EUR/USD",
            start_utc=datetime(2026, 4, 27, 8, 0, tzinfo=timezone.utc),
            end_utc=datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc),
            cache_dir=pathlib.Path(tmp) / "cache",
            output_dir=pathlib.Path(tmp) / "out",
            smartnotebook_dir=pathlib.Path(tmp) / "nb",
        )
        # Build runner without actually loading bars / running:
        # BacktestRunner's __init__ already calls _build_engine.
        runner = BacktestRunner(cfg=cfg, bars=[], calendar_replay=None)
        # Stop engine so we clean up connections.
        try:
            runner._engine.stop()
        except Exception:
            pass


def test_module_check_all_not_patched_after_backtest_init():
    """After building a BacktestRunner, the module-level check_all must
    still be the ORIGINAL function (no module mutation)."""
    _build_minimal_runner_and_run()
    assert _sr.check_all is _ORIG_CHECK_ALL, (
        "safety_rails.check_all was mutated at module level — "
        "monkey-patch leak detected!")
    # And the legacy patch sentinel must NOT be present
    assert not getattr(_sr.check_all, "_backtest_v2_patched", False), (
        "found _backtest_v2_patched sentinel on module check_all")


def test_fresh_engine_uses_original_safety_rails():
    """A fresh EngineV3 (no override) must use the production check_all."""
    _build_minimal_runner_and_run()
    from engine.v3 import EngineV3, ValidationConfig
    with tempfile.TemporaryDirectory() as tmp:
        cfg = ValidationConfig()
        cfg.smartnotebook_dir = tmp
        cfg.broker_env = "practice"
        eng = EngineV3(cfg=cfg, broker=None, account_balance=10000)
        assert eng._safety_rails_check_callable is _ORIG_CHECK_ALL, (
            "fresh Engine inherited a non-default safety_rails check")
        eng.stop()


def test_backtest_engine_uses_wrapped_callable_not_module():
    """Backtest's engine should have its OWN wrapper instance — not the
    module global."""
    from backtest_v2.config import BacktestConfig
    from backtest_v2.runner import BacktestRunner
    from datetime import datetime, timezone
    with tempfile.TemporaryDirectory() as tmp:
        cfg = BacktestConfig(
            pair="EUR/USD",
            start_utc=datetime(2026, 4, 27, 8, 0, tzinfo=timezone.utc),
            end_utc=datetime(2026, 4, 27, 12, 0, tzinfo=timezone.utc),
            cache_dir=pathlib.Path(tmp) / "cache",
            output_dir=pathlib.Path(tmp) / "out",
            smartnotebook_dir=pathlib.Path(tmp) / "nb",
        )
        runner = BacktestRunner(cfg=cfg, bars=[], calendar_replay=None)
        # The engine's callable is the local wrapper, NOT the original
        assert runner._engine._safety_rails_check_callable is not _ORIG_CHECK_ALL
        # And the module global is still pristine
        assert _sr.check_all is _ORIG_CHECK_ALL
        try: runner._engine.stop()
        except Exception: pass


if __name__ == "__main__":
    for fn in (test_module_check_all_not_patched_after_backtest_init,
               test_fresh_engine_uses_original_safety_rails,
               test_backtest_engine_uses_wrapped_callable_not_module):
        try:
            fn(); print(f"PASS {fn.__name__}")
        except AssertionError as e:
            print(f"FAIL {fn.__name__}: {e}"); sys.exit(1)
    print("ALL PASS")
