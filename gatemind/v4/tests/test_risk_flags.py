"""Tests for gatemind.v4.risk_flag_classifier."""

from __future__ import annotations

import pytest

from gatemind.v4 import GateMindV4, GateOutcome
from gatemind.v4.gatemind_constants import (
    KILL_CLASS_FLAGS,
    REASON_KILL_FLAG,
    WARNING_CLASS_FLAGS,
)
from gatemind.v4.risk_flag_classifier import (
    aggregate_flags,
    classify_flag,
    has_kill,
    risk_flag_status,
)

from .conftest import (
    make_brain_output_aplus_buy,
    make_brain_output_with_kill_flag,
    make_brain_output_with_warning_flag,
    now_in_ny_window,
)


@pytest.mark.parametrize("flag", sorted(KILL_CLASS_FLAGS))
def test_kill_flags_classified(flag):
    assert classify_flag(flag) == "kill"


@pytest.mark.parametrize("flag", sorted(WARNING_CLASS_FLAGS))
def test_warning_flags_classified(flag):
    assert classify_flag(flag) == "warning"


def test_unknown_flag_treated_as_unknown():
    assert classify_flag("totally_made_up") == "unknown"


def test_aggregate_kill_warning_unknown():
    n = make_brain_output_with_kill_flag("NewsMind", "news_blackout")
    m = make_brain_output_with_warning_flag("MarketMind", "spread_anomaly")
    c = make_brain_output_aplus_buy("ChartMind")
    # Add unknown via mutation
    object.__setattr__(c, "risk_flags", ["weird_unknown_flag"])
    kill, warn, unknown = aggregate_flags(n, m, c)
    assert any("news_blackout" in k for k in kill)
    assert any("spread_anomaly" in w for w in warn)
    assert any("weird_unknown_flag" in u for u in unknown)


def test_risk_flag_status_clean():
    assert risk_flag_status([], [], []) == "clean"


def test_risk_flag_status_warnings_only():
    assert risk_flag_status([], ["x"], []) == "warnings_only"


def test_risk_flag_status_kill_active_via_kill():
    assert risk_flag_status(["x"], [], []) == "kill_active"


def test_risk_flag_status_kill_active_via_unknown():
    assert risk_flag_status([], [], ["??"]) == "kill_active"


def test_has_kill_true_for_kill():
    n = make_brain_output_with_kill_flag("NewsMind", "feed_dead")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    found, offenders = has_kill(n, m, c)
    assert found is True
    assert any("feed_dead" in o for o in offenders)


def test_has_kill_false_for_clean():
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    assert has_kill(n, m, c) == (False, [])


def test_warning_only_does_not_block_gate():
    gate = GateMindV4()
    n = make_brain_output_with_warning_flag("NewsMind", "spread_anomaly")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    decision = gate.evaluate(n, m, c, now_utc=now_in_ny_window(2))
    assert decision.gate_decision == GateOutcome.ENTER_CANDIDATE
    assert decision.risk_flag_status == "warnings_only"
    assert any("spread_anomaly" in f for f in decision.trade_candidate.risk_flags)


def test_kill_flag_blocks_gate():
    gate = GateMindV4()
    n = make_brain_output_with_kill_flag("NewsMind", "news_blackout")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    decision = gate.evaluate(n, m, c, now_utc=now_in_ny_window(2))
    assert decision.gate_decision == GateOutcome.BLOCK
    assert decision.blocking_reason == REASON_KILL_FLAG


def test_unknown_flag_blocks_gate():
    """Unknown flags are fail-closed → block."""
    gate = GateMindV4()
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    object.__setattr__(n, "risk_flags", ["zomg_new_flag_we_dont_know"])
    decision = gate.evaluate(n, m, c, now_utc=now_in_ny_window(2))
    assert decision.gate_decision == GateOutcome.BLOCK
    assert decision.blocking_reason == REASON_KILL_FLAG
