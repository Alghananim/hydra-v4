"""Tests for the BrainOutput contract invariants.

Each test corresponds to a documented invariant in contracts/brain_output.py.
"""

from datetime import datetime, timezone

import pytest

from contracts.brain_output import BrainGrade, BrainOutput


def _now() -> datetime:
    return datetime(2026, 4, 27, 12, 0, 0, tzinfo=timezone.utc)


def _valid_kwargs(**overrides):
    base = dict(
        brain_name="newsmind",
        decision="WAIT",
        grade=BrainGrade.B,
        reason="ok",
        evidence=["x"],
        data_quality="good",
        should_block=False,
        risk_flags=[],
        confidence=0.5,
        timestamp_utc=_now(),
    )
    base.update(overrides)
    return base


def test_a_plus_without_evidence_raises():
    with pytest.raises(ValueError, match="REQUIRES non-empty evidence"):
        BrainOutput(**_valid_kwargs(grade=BrainGrade.A_PLUS, evidence=[]))


def test_a_grade_with_stale_data_raises():
    with pytest.raises(ValueError, match="data_quality=='good'"):
        BrainOutput(**_valid_kwargs(grade=BrainGrade.A, data_quality="stale"))


def test_block_with_should_block_false_raises():
    # We test the inverse: should_block=True with grade != BLOCK must raise.
    with pytest.raises(ValueError, match="should_block=True must yield grade==BLOCK"):
        BrainOutput(**_valid_kwargs(grade=BrainGrade.B, should_block=True))


def test_block_grade_allows_should_block_true():
    out = BrainOutput(
        **_valid_kwargs(
            grade=BrainGrade.BLOCK,
            decision="BLOCK",
            should_block=True,
            evidence=[],         # BLOCK doesn't require evidence
            data_quality="missing",
            confidence=0.0,
        )
    )
    assert out.is_blocking() is True
    assert out.grade == BrainGrade.BLOCK


def test_grade_block_requires_decision_block():
    with pytest.raises(ValueError, match="grade==BLOCK requires decision=='BLOCK'"):
        BrainOutput(
            **_valid_kwargs(
                grade=BrainGrade.BLOCK,
                decision="WAIT",
                should_block=True,
                evidence=[],
                data_quality="missing",
                confidence=0.0,
            )
        )


def test_invalid_decision_rejected():
    with pytest.raises(ValueError, match="decision must be one of"):
        BrainOutput(**_valid_kwargs(decision="ENTER"))


def test_invalid_brain_name_rejected():
    with pytest.raises(ValueError, match="brain_name must be one of"):
        BrainOutput(**_valid_kwargs(brain_name="oraclemind"))


def test_naive_timestamp_rejected():
    with pytest.raises(ValueError, match="timestamp_utc must be"):
        BrainOutput(**_valid_kwargs(timestamp_utc=datetime(2026, 4, 27, 12)))


def test_confidence_out_of_range_rejected():
    with pytest.raises(ValueError, match=r"confidence must be in \[0.0, 1.0\]"):
        BrainOutput(**_valid_kwargs(confidence=1.5))


def test_a_plus_with_evidence_and_good_data_accepted():
    out = BrainOutput(
        **_valid_kwargs(
            grade=BrainGrade.A_PLUS,
            evidence=["headline=FOMC raises 25bp"],
            data_quality="good",
        )
    )
    assert out.grade == BrainGrade.A_PLUS


def test_fail_closed_constructor_passes_validation():
    out = BrainOutput.fail_closed(
        brain_name="newsmind",
        reason="silent feeds",
    )
    assert out.is_blocking()
    assert out.decision == "BLOCK"
    assert out.grade == BrainGrade.BLOCK
    assert out.confidence == 0.0
