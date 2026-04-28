"""GateDecision contract / invariants — frozen, well-formed."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from gatemind.v4 import GateMindV4, GateOutcome, TradeCandidate, TradeDirection
from gatemind.v4.models import GateDecision

from .conftest import (
    make_brain_output_aplus_buy,
    make_brain_output_aplus_sell,
    now_in_ny_window,
)


@pytest.fixture
def gate():
    return GateMindV4()


def test_decision_is_frozen(gate):
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    d = gate.evaluate(n, m, c, now_utc=now_in_ny_window(2))
    with pytest.raises(FrozenInstanceError):
        d.gate_decision = GateOutcome.WAIT  # type: ignore[misc]


def test_trade_candidate_frozen(gate):
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    d = gate.evaluate(n, m, c, now_utc=now_in_ny_window(2))
    cand = d.trade_candidate
    with pytest.raises(FrozenInstanceError):
        cand.symbol = "USD_JPY"  # type: ignore[misc]


def test_block_must_carry_blocking_reason():
    with pytest.raises(ValueError):
        GateDecision(
            gate_decision=GateOutcome.BLOCK,
            blocking_reason="",  # empty
        )


def test_enter_must_carry_candidate():
    with pytest.raises(ValueError):
        GateDecision(
            gate_decision=GateOutcome.ENTER_CANDIDATE,
            direction=TradeDirection.BUY,
            trade_candidate=None,
        )


def test_decision_model_version_present(gate):
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    d = gate.evaluate(n, m, c, now_utc=now_in_ny_window(2))
    assert d.model_version == "gatemind-v4.0"
    assert d.gate_name == "GateMind"


def test_decision_carries_brain_votes(gate):
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_sell("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    d = gate.evaluate(n, m, c, now_utc=now_in_ny_window(2))
    assert d.mind_votes == {"NewsMind": "BUY", "MarketMind": "SELL", "ChartMind": "BUY"}
    assert d.mind_grades == {"NewsMind": "A+", "MarketMind": "A+", "ChartMind": "A+"}


def test_decision_helpers(gate):
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    d = gate.evaluate(n, m, c, now_utc=now_in_ny_window(2))
    assert d.is_enter()
    assert not d.is_block()
    assert not d.is_wait()
