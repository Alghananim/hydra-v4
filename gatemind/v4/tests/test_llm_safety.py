"""Tests for gatemind.v4.llm_safety — downgrade-only Claude wrapper."""

from __future__ import annotations

import pytest

from gatemind.v4 import GateMindV4, GateOutcome, TradeDirection
from gatemind.v4.llm_safety import LLMOverride, apply_llm_review

from .conftest import (
    make_brain_output_a_wait,
    make_brain_output_aplus_buy,
    make_brain_output_aplus_wait,
    make_brain_output_with_kill_flag,
    now_in_ny_window,
)


@pytest.fixture
def gate():
    return GateMindV4()


def _enter_decision(gate):
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    return gate.evaluate(n, m, c, now_utc=now_in_ny_window(2))


def _wait_decision(gate):
    n = make_brain_output_a_wait("NewsMind")
    m = make_brain_output_a_wait("MarketMind")
    c = make_brain_output_aplus_wait("ChartMind")
    return gate.evaluate(n, m, c, now_utc=now_in_ny_window(2))


def _block_decision(gate):
    n = make_brain_output_with_kill_flag("NewsMind", "news_blackout")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    return gate.evaluate(n, m, c, now_utc=now_in_ny_window(2))


def test_no_change_is_passthrough(gate):
    d = _enter_decision(gate)
    assert d.gate_decision == GateOutcome.ENTER_CANDIDATE
    out = apply_llm_review(d, override=LLMOverride.NO_CHANGE)
    assert out is d


def test_enter_can_be_downgraded_to_wait(gate):
    d = _enter_decision(gate)
    out = apply_llm_review(d, override=LLMOverride.DOWNGRADE_TO_WAIT, rationale="too risky")
    assert out.gate_decision == GateOutcome.WAIT
    assert out.trade_candidate is None
    assert out.direction == TradeDirection.NONE
    assert any("LLM_override" in entry for entry in out.audit_trail)


def test_enter_can_be_downgraded_to_block(gate):
    d = _enter_decision(gate)
    out = apply_llm_review(d, override=LLMOverride.DOWNGRADE_TO_BLOCK, rationale="bad vibes")
    assert out.gate_decision == GateOutcome.BLOCK
    assert out.blocking_reason.startswith("llm_downgraded_block")
    assert out.trade_candidate is None


def test_wait_can_be_downgraded_to_block(gate):
    d = _wait_decision(gate)
    out = apply_llm_review(d, override=LLMOverride.DOWNGRADE_TO_BLOCK, rationale="extra caution")
    assert out.gate_decision == GateOutcome.BLOCK


def test_wait_cannot_be_upgraded_to_enter(gate):
    """There is no upgrade verb in the enum — design enforces it."""
    # The enum literally has no UPGRADE option; this proves the API surface
    # cannot express an upgrade.
    assert not any(name.startswith("UPGRADE") for name in LLMOverride.__members__)


def test_wait_to_wait_rejected(gate):
    """No-op via downgrade enum is rejected as not-a-downgrade."""
    d = _wait_decision(gate)
    with pytest.raises(PermissionError):
        apply_llm_review(d, override=LLMOverride.DOWNGRADE_TO_WAIT)


def test_block_cannot_be_changed_to_wait(gate):
    """BLOCK is the floor — even DOWNGRADE_TO_WAIT (which would be an upgrade) raises."""
    d = _block_decision(gate)
    with pytest.raises(PermissionError):
        apply_llm_review(d, override=LLMOverride.DOWNGRADE_TO_WAIT)


def test_block_cannot_be_changed_to_block(gate):
    d = _block_decision(gate)
    with pytest.raises(PermissionError):
        apply_llm_review(d, override=LLMOverride.DOWNGRADE_TO_BLOCK)


def test_llm_cannot_produce_enter():
    """No LLMOverride value yields ENTER_CANDIDATE."""
    for member in LLMOverride:
        assert "ENTER" not in member.value


def test_llm_override_spec_alias_map():
    """G7: Phase 1 spec verbs {agree, downgrade, block} map to canonical
    enum members. Same semantics, different names."""
    from gatemind.v4.llm_safety import LLM_OVERRIDE_SPEC_ALIASES
    assert LLM_OVERRIDE_SPEC_ALIASES["agree"] == LLMOverride.NO_CHANGE
    assert LLM_OVERRIDE_SPEC_ALIASES["downgrade"] == LLMOverride.DOWNGRADE_TO_WAIT
    assert LLM_OVERRIDE_SPEC_ALIASES["block"] == LLMOverride.DOWNGRADE_TO_BLOCK
