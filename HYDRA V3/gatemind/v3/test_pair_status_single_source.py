# -*- coding: utf-8 -*-
"""FIX #3B — execution_check reads PAIR_STATUS from validation_config.

Before this fix, gatemind/v3/execution_check.py had its own PAIR_STATUS
dict separate from engine/v3/validation_config.py. Two sources of truth
meant a programmatic change in one place was silently ignored by the
other.
"""
from __future__ import annotations
import sys, pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engine.v3 import validation_config
from gatemind.v3 import execution_check


def test_execution_check_follows_validation_config():
    """Mutating validation_config.PAIR_STATUS must change execution_check."""
    saved = dict(validation_config.PAIR_STATUS)
    try:
        validation_config.PAIR_STATUS["EUR/USD"] = "monitoring"
        out = execution_check.check(
            pair="EUR/USD", broker_mode="paper", live_enabled=False,
            spread_pips=0.5, max_spread_pips=2.0,
            slippage_pips=0.3, max_slippage_pips=2.0,
        )
        assert out["pair_status"] == "monitoring", (
            f"execution_check ignored validation_config change: {out}")
    finally:
        validation_config.PAIR_STATUS.clear()
        validation_config.PAIR_STATUS.update(saved)


def test_execution_check_disabled_via_config():
    saved = dict(validation_config.PAIR_STATUS)
    try:
        validation_config.PAIR_STATUS["EUR/USD"] = "disabled"
        out = execution_check.check(
            pair="EUR/USD", broker_mode="paper", live_enabled=False,
            spread_pips=0.5, max_spread_pips=2.0,
            slippage_pips=0.3, max_slippage_pips=2.0,
        )
        assert out["status"] == "disabled_pair"
        assert out["pair_status"] == "disabled"
    finally:
        validation_config.PAIR_STATUS.clear()
        validation_config.PAIR_STATUS.update(saved)


def test_execution_check_unknown_pair():
    out = execution_check.check(
        pair="FAKE/PAIR", broker_mode="paper", live_enabled=False,
        spread_pips=0.5, max_spread_pips=2.0,
        slippage_pips=0.3, max_slippage_pips=2.0,
    )
    assert out["pair_status"] == "unknown"


def test_no_local_PAIR_STATUS_in_execution_check():
    """The legacy module-level PAIR_STATUS dict must be gone (or harmless)."""
    # Either the symbol doesn't exist, or it's only a defensive fallback,
    # not consulted under normal operation.
    has_attr = hasattr(execution_check, "PAIR_STATUS")
    if has_attr:
        # If it still exists, mutating it should NOT affect check()
        # because check() reads from validation_config.
        execution_check.PAIR_STATUS["EUR/USD"] = "disabled"
        try:
            out = execution_check.check(
                pair="EUR/USD", broker_mode="paper", live_enabled=False,
                spread_pips=0.5, max_spread_pips=2.0,
                slippage_pips=0.3, max_slippage_pips=2.0,
            )
            # validation_config still says EUR/USD = production
            assert out["pair_status"] == "production", (
                f"check() consulted local PAIR_STATUS, not validation_config: {out}")
        finally:
            execution_check.PAIR_STATUS["EUR/USD"] = "production"


def test_practice_broker_mode_is_accepted_by_execution_check():
    """FIX #3B: practice should be a valid broker_mode equivalent to paper."""
    out = execution_check.check(
        pair="EUR/USD", broker_mode="practice", live_enabled=False,
        spread_pips=0.5, max_spread_pips=2.0,
        slippage_pips=0.3, max_slippage_pips=2.0,
    )
    # Must NOT trigger broker_unsafe / broker_mode_unknown
    assert out["status"] != "broker_unsafe", f"practice rejected: {out}"
    assert "broker_mode_unknown" not in out.get("details", "")


def test_practice_accepted_by_validation_config():
    """validate_or_die must accept practice|paper|live."""
    cfg = validation_config.ValidationConfig()
    for env in ("practice", "paper", "live"):
        cfg.broker_env = env
        # Must not raise SystemExit
        cfg.validate_or_die()


if __name__ == "__main__":
    for fn in (test_execution_check_follows_validation_config,
               test_execution_check_disabled_via_config,
               test_execution_check_unknown_pair,
               test_no_local_PAIR_STATUS_in_execution_check,
               test_practice_broker_mode_is_accepted_by_execution_check,
               test_practice_accepted_by_validation_config):
        try:
            fn(); print(f"PASS {fn.__name__}")
        except AssertionError as e:
            print(f"FAIL {fn.__name__}: {e}"); sys.exit(1)
    print("ALL PASS")
