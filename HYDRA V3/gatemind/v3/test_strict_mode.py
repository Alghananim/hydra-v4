# -*- coding: utf-8 -*-
"""Tests for GateMindV3 strict_mode flag (Phase 2).

Strict mode is the default (True). It enforces:
  - B grades on any brain => block (not wait)
  - alignment requires 3-of-3 same direction (not just 2-of-3)

Loose mode preserves the legacy behaviour for backward-compat in tests
and the optional backtester.
"""
from __future__ import annotations
import sys
from datetime import datetime, timezone

# Make repo root importable when pytest is invoked from anywhere.
import os, pathlib
_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from gatemind.v3 import GateMindV3, BrainSummary, SystemState


NOW = datetime(2026, 4, 27, 13, 30, 0, tzinfo=timezone.utc)    # NY 09:30 EDT


def _state(pair="EUR/USD"):
    return SystemState(
        pair=pair, broker_mode="paper", live_enabled=False,
        spread_pips=0.5, max_spread_pips=2.0,
        expected_slippage_pips=0.3, max_slippage_pips=2.0,
        daily_loss_pct=0.0, daily_loss_limit_pct=2.0,
        trades_today=0, daily_trade_limit=5,
        consecutive_losses=0, pair_status="production",
    )


def _brain(name, *, grade="A", perm="allow", direction="bullish",
           confidence=0.85):
    return BrainSummary(name=name, permission=perm, grade=grade,
                        confidence=confidence, direction=direction,
                        reason=f"{name}_{grade}_{direction}")


def _entry_kit():
    """Tight entry/stop/target that yield rr~2.0 and an in-band ATR."""
    return dict(entry_price=1.10000, stop_loss=1.09950,
                take_profit=1.10100, atr=0.0005)


# ---- 1: B grade blocks in strict ----
def test_b_grade_blocks_in_strict():
    gate = GateMindV3(strict_mode=True)
    d = gate.decide(
        pair="EUR/USD",
        news=_brain("news", grade="A"),
        market=_brain("market", grade="A"),
        chart=_brain("chart", grade="B"),
        state=_state(), now_utc=NOW, **_entry_kit())
    assert d.final_decision == "block", f"expected block, got {d.final_decision} reason={d.reason}"
    assert any("chart_grade_B_strict" in r for r in d.blocking_reasons), \
        f"missing chart_grade_B_strict in {d.blocking_reasons}"


# ---- 2: B grade waits in loose ----
def test_b_grade_waits_in_loose():
    gate = GateMindV3(strict_mode=False)
    d = gate.decide(
        pair="EUR/USD",
        news=_brain("news", grade="A"),
        market=_brain("market", grade="A"),
        chart=_brain("chart", grade="B"),
        state=_state(), now_utc=NOW, **_entry_kit())
    # In loose mode B is a wait, not a block.
    assert d.final_decision == "wait", f"expected wait, got {d.final_decision} reason={d.reason}"
    assert any("chart_grade_B" in w for w in d.warnings), \
        f"missing chart_grade_B warning in {d.warnings}"


# ---- 3: 2-of-3 alignment blocks in strict ----
def test_two_of_three_blocks_in_strict():
    gate = GateMindV3(strict_mode=True)
    d = gate.decide(
        pair="EUR/USD",
        news=_brain("news", grade="A", direction="bullish"),
        market=_brain("market", grade="A", direction="bullish"),
        chart=_brain("chart", grade="A", direction="neutral"),    # not clear
        state=_state(), now_utc=NOW, **_entry_kit())
    assert d.final_decision == "block", f"expected block, got {d.final_decision} reason={d.reason}"
    assert any("alignment" in r for r in d.blocking_reasons), \
        f"missing alignment-related block in {d.blocking_reasons}"


# ---- 4: 3-of-3 A+ aligned reaches enter (other checks pass) ----
def test_three_of_three_passes_in_strict():
    gate = GateMindV3(strict_mode=True)
    d = gate.decide(
        pair="EUR/USD",
        news=_brain("news", grade="A+", direction="bullish", confidence=0.9),
        market=_brain("market", grade="A+", direction="bullish", confidence=0.9),
        chart=_brain("chart", grade="A+", direction="bullish", confidence=0.9),
        state=_state(), now_utc=NOW, **_entry_kit())
    # All gates clear, session is in-window => enter.
    assert d.final_decision == "enter", \
        f"expected enter, got {d.final_decision} blocking={d.blocking_reasons} warn={d.warnings} reason={d.reason}"
    assert d.direction == "buy"


# ---- 5: any one B blocks even if others A+ in strict ----
def test_one_brain_b_blocks_others_aplus():
    gate = GateMindV3(strict_mode=True)
    d = gate.decide(
        pair="EUR/USD",
        news=_brain("news", grade="A+", direction="bullish", confidence=0.95),
        market=_brain("market", grade="A+", direction="bullish", confidence=0.95),
        chart=_brain("chart", grade="B", direction="bullish", confidence=0.95),
        state=_state(), now_utc=NOW, **_entry_kit())
    assert d.final_decision == "block", f"expected block, got {d.final_decision} reason={d.reason}"
    assert any("chart_grade_B_strict" in r for r in d.blocking_reasons), \
        f"missing chart_grade_B_strict in {d.blocking_reasons}"


if __name__ == "__main__":
    failures = []
    for fn_name in [
        "test_b_grade_blocks_in_strict",
        "test_b_grade_waits_in_loose",
        "test_two_of_three_blocks_in_strict",
        "test_three_of_three_passes_in_strict",
        "test_one_brain_b_blocks_others_aplus",
    ]:
        try:
            globals()[fn_name]()
            print(f"  PASS  {fn_name}")
        except AssertionError as e:
            print(f"  FAIL  {fn_name}: {e}")
            failures.append(fn_name)
    if failures:
        print(f"\n{len(failures)} FAILED")
        sys.exit(1)
    print("\nALL PASS")
