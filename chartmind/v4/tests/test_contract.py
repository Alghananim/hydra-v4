"""ChartAssessment contract invariants."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from contracts.brain_output import BrainGrade

from chartmind.v4.models import ChartAssessment


def _ok_kwargs(**overrides):
    base = dict(
        brain_name="chartmind",
        decision="WAIT",
        grade=BrainGrade.C,
        reason="ok",
        evidence=["e"],
        data_quality="good",
        should_block=False,
        risk_flags=[],
        confidence=0.3,
        timestamp_utc=datetime(2026, 4, 27, tzinfo=timezone.utc),
        trend_structure="bullish_weak",
        volatility_state="normal",
        atr_value=0.001,
        key_levels=[],
        setup_type="no_setup",
        entry_zone={"low": 1.10, "high": 1.11},
        invalidation_level=1.09,
        stop_reference=1.09,
        target_reference=None,
        chart_warnings=[],
        indicator_snapshot={},
        news_context_used=None,
        market_context_used=None,
    )
    base.update(overrides)
    return base


def test_brain_name_must_be_chartmind():
    with pytest.raises(ValueError):
        ChartAssessment(**_ok_kwargs(brain_name="newsmind"))


def test_invalid_trend_structure_rejected():
    with pytest.raises(ValueError):
        ChartAssessment(**_ok_kwargs(trend_structure="rocket"))


def test_invalid_volatility_rejected():
    with pytest.raises(ValueError):
        ChartAssessment(**_ok_kwargs(volatility_state="psychic"))


def test_invalid_setup_rejected():
    with pytest.raises(ValueError):
        ChartAssessment(**_ok_kwargs(setup_type="meme"))


def test_negative_atr_rejected():
    with pytest.raises(ValueError):
        ChartAssessment(**_ok_kwargs(atr_value=-1.0))


def test_nan_atr_rejected():
    with pytest.raises(ValueError):
        ChartAssessment(**_ok_kwargs(atr_value=float("nan")))


def test_low_gt_high_band_rejected():
    with pytest.raises(ValueError):
        ChartAssessment(**_ok_kwargs(entry_zone={"low": 1.20, "high": 1.10}))


def test_stop_must_equal_invalidation():
    with pytest.raises(ValueError):
        ChartAssessment(**_ok_kwargs(stop_reference=99.0, invalidation_level=1.09))


def test_buy_requires_band_width():
    """C10: BUY/SELL with degenerate band rejected."""
    kw = _ok_kwargs(decision="BUY", grade=BrainGrade.A,
                    entry_zone={"low": 1.10, "high": 1.10},
                    setup_type="breakout")
    with pytest.raises(ValueError):
        ChartAssessment(**kw)


def test_a_plus_requires_evidence_and_good_data():
    """Inherited BrainOutput invariant."""
    with pytest.raises(ValueError):
        ChartAssessment(**_ok_kwargs(grade=BrainGrade.A_PLUS, evidence=[]))


def test_block_grade_requires_block_decision():
    with pytest.raises(ValueError):
        ChartAssessment(**_ok_kwargs(grade=BrainGrade.BLOCK, decision="WAIT"))


def test_should_block_requires_block_grade():
    with pytest.raises(ValueError):
        ChartAssessment(**_ok_kwargs(should_block=True, grade=BrainGrade.B))


def test_to_dict_serialises():
    a = ChartAssessment(**_ok_kwargs())
    d = a.to_dict()
    assert d["brain_name"] == "chartmind"
    assert d["grade"] == "C"
    assert isinstance(d["timestamp_utc"], str)


def test_target_reference_can_be_none_or_finite():
    a = ChartAssessment(**_ok_kwargs(target_reference=None))
    assert a.target_reference is None
    b = ChartAssessment(**_ok_kwargs(target_reference=1.20))
    assert b.target_reference == 1.20
    with pytest.raises(ValueError):
        ChartAssessment(**_ok_kwargs(target_reference=float("inf")))
