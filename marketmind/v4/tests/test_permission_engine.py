"""Permission engine state -> grade table."""
from __future__ import annotations

import pytest

from contracts.brain_output import BrainGrade
from marketmind.v4 import permission_engine as pe


def _ideal() -> pe.PermissionInputs:
    return pe.PermissionInputs(
        trend_state="strong_up",
        momentum_state="accelerating",
        volatility_state="normal",
        liquidity_state="good",
        correlation_status="normal",
        news_state="aligned",
        contradiction_severity=None,
        data_quality="good",
    )


def test_ideal_state_yields_a_plus_buy():
    r = pe.decide(_ideal())
    assert r.grade == BrainGrade.A_PLUS
    assert r.decision == "BUY"
    assert r.should_block is False


def test_strong_down_yields_sell():
    inp = _ideal()
    inp.trend_state = "strong_down"
    r = pe.decide(inp)
    assert r.decision == "SELL"
    assert r.grade == BrainGrade.A_PLUS


def test_data_missing_forces_block():
    inp = _ideal()
    inp.data_quality = "missing"
    r = pe.decide(inp)
    assert r.grade == BrainGrade.BLOCK
    assert r.decision == "BLOCK"
    assert r.should_block is True
    assert "data_quality" in r.hard_block_label


def test_off_session_forces_block():
    inp = _ideal()
    inp.liquidity_state = "off-session"
    r = pe.decide(inp)
    assert r.grade == BrainGrade.BLOCK


def test_dangerous_volatility_forces_block():
    inp = _ideal()
    inp.volatility_state = "dangerous"
    r = pe.decide(inp)
    assert r.grade == BrainGrade.BLOCK


def test_news_block_forces_block():
    inp = _ideal()
    inp.news_state = "block"
    r = pe.decide(inp)
    assert r.grade == BrainGrade.BLOCK


def test_steady_momentum_drops_one_tier():
    inp = _ideal()
    inp.momentum_state = "steady"
    r = pe.decide(inp)
    assert r.grade == BrainGrade.A
    assert r.decision == "BUY"


def test_two_failures_drop_two_tiers():
    inp = _ideal()
    inp.momentum_state = "steady"
    inp.volatility_state = "expanded"
    r = pe.decide(inp)
    assert r.grade == BrainGrade.B
    assert r.decision == "WAIT"   # B -> WAIT, not BUY


def test_news_cap_b_caps_to_b():
    inp = _ideal()
    r = pe.decide(inp, news_grade_cap=BrainGrade.B)
    assert r.grade == BrainGrade.B
    assert r.decision == "WAIT"


def test_high_contradiction_caps_at_c():
    """High contradiction caps at C (strict interpretation of the spec).
    From an all-A+ baseline, a single 'high' contradiction must drop to C —
    a single tier drop to A would still permit BUY/SELL, defeating the
    purpose of flagging the contradiction.
    """
    inp = _ideal()
    inp.contradiction_severity = "high"
    r = pe.decide(inp)
    assert r.grade == BrainGrade.C
    # C grade -> WAIT (BUY/SELL only at A or A+)
    assert r.decision == "WAIT"


def test_medium_contradiction_caps_at_b():
    inp = _ideal()
    inp.contradiction_severity = "medium"
    r = pe.decide(inp)
    assert r.grade == BrainGrade.B


def test_stale_data_caps_at_b():
    inp = _ideal()
    inp.data_quality = "stale"
    r = pe.decide(inp)
    assert r.grade == BrainGrade.B


def test_range_trend_yields_wait():
    inp = _ideal()
    inp.trend_state = "range"
    r = pe.decide(inp)
    assert r.decision == "WAIT"
    assert r.grade in (BrainGrade.A, BrainGrade.B)


def test_failures_listed_in_reason():
    inp = _ideal()
    inp.trend_state = "weak_up"
    inp.momentum_state = "fading"
    r = pe.decide(inp)
    assert any("trend=" in f for f in r.failures)
    assert any("momentum=" in f for f in r.failures)
