"""MarketState contract invariants."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from contracts.brain_output import BrainGrade
from marketmind.v4.models import MarketState


def _kw(**overrides):
    base = dict(
        brain_name="marketmind",
        decision="BUY",
        grade=BrainGrade.A,
        reason="test",
        evidence=["e1"],
        data_quality="good",
        should_block=False,
        risk_flags=[],
        confidence=0.7,
        timestamp_utc=datetime(2026, 4, 27, 13, 0, tzinfo=timezone.utc),
        regime_state="trending",
        trend_state="strong_up",
        momentum_state="accelerating",
        volatility_state="normal",
        liquidity_state="good",
        currency_strength={"USD": 0.5},
        news_context_used={"present": False},
        contradictions=[],
        indicator_snapshot={},
    )
    base.update(overrides)
    return base


def test_valid_construction():
    ms = MarketState(**_kw())
    assert ms.brain_name == "marketmind"


def test_brain_name_must_be_marketmind():
    with pytest.raises(ValueError):
        MarketState(**_kw(brain_name="newsmind"))


def test_invalid_regime_rejected():
    with pytest.raises(ValueError):
        MarketState(**_kw(regime_state="bogus"))


def test_invalid_trend_rejected():
    with pytest.raises(ValueError):
        MarketState(**_kw(trend_state="superstrong"))


def test_invalid_momentum_rejected():
    with pytest.raises(ValueError):
        MarketState(**_kw(momentum_state="zooming"))


def test_invalid_volatility_rejected():
    with pytest.raises(ValueError):
        MarketState(**_kw(volatility_state="crazy"))


def test_invalid_liquidity_rejected():
    with pytest.raises(ValueError):
        MarketState(**_kw(liquidity_state="amazing"))


def test_brainoutput_invariants_inherited():
    # data_quality not 'good' with grade A should fail (BrainOutput I5)
    with pytest.raises(ValueError):
        MarketState(**_kw(data_quality="stale"))


def test_should_block_requires_block():
    with pytest.raises(ValueError):
        MarketState(**_kw(should_block=True, grade=BrainGrade.A))


def test_block_grade_requires_block_decision():
    # I7: grade==BLOCK with decision != 'BLOCK' must raise
    with pytest.raises(ValueError):
        MarketState(**_kw(grade=BrainGrade.BLOCK, decision="BUY"))


def test_to_dict_serialises_grade():
    ms = MarketState(**_kw())
    d = ms.to_dict()
    assert d["grade"] == "A"
    assert d["brain_name"] == "marketmind"
    assert d["regime_state"] == "trending"
