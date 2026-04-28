"""Tests for gatemind.v4.schema_validator."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from contracts.brain_output import BrainGrade, BrainOutput
from gatemind.v4.schema_validator import validate_all, validate_brain_output

from .conftest import (
    make_brain_output_aplus_buy,
    make_brain_output_invalid_schema,
)


def test_valid_aplus_passes():
    out = make_brain_output_aplus_buy("NewsMind")
    ok, reason = validate_brain_output(out, expected_brain="newsmind")
    assert ok is True, reason
    assert reason == ""


def test_none_rejected():
    ok, reason = validate_brain_output(None)
    assert not ok
    assert reason == "brain_output_is_none"


def test_non_brainoutput_object_rejected():
    fake = make_brain_output_invalid_schema("NewsMind")
    ok, reason = validate_brain_output(fake, expected_brain="newsmind")
    assert not ok
    assert reason.startswith("not_a_brain_output")


def test_brain_name_mismatch():
    out = make_brain_output_aplus_buy("NewsMind")  # newsmind
    ok, reason = validate_brain_output(out, expected_brain="marketmind")
    assert not ok
    assert "brain_name_mismatch" in reason


def test_validate_all_happy_path():
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_aplus_buy("ChartMind")
    ok, brain, reason = validate_all(n, m, c)
    assert ok is True
    assert brain == "" and reason == ""


def test_validate_all_one_invalid():
    n = make_brain_output_aplus_buy("NewsMind")
    m = make_brain_output_aplus_buy("MarketMind")
    c = make_brain_output_invalid_schema("ChartMind")
    ok, brain, reason = validate_all(n, m, c)
    assert ok is False
    assert brain == "chartmind"


def test_unexpected_brain_name():
    """A BrainOutput from gatemind itself shouldn't be passed to GateMind validator."""
    out = BrainOutput(
        brain_name="gatemind",
        decision="WAIT",
        grade=BrainGrade.B,
        reason="just a test",
        evidence=[],
        data_quality="stale",
        should_block=False,
        risk_flags=[],
        confidence=0.5,
        timestamp_utc=datetime.now(timezone.utc),
    )
    ok, reason = validate_brain_output(out)
    assert not ok
    assert "unexpected_brain_name" in reason


def test_post_construction_mutation_caught():
    """If someone mutates evidence to empty after construction, the contract
    constructor would not have raised — but the validator's high-grade check
    should still flag it."""
    out = make_brain_output_aplus_buy("NewsMind")
    # Mutate post-construction
    object.__setattr__(out, "evidence", [])
    ok, reason = validate_brain_output(out, expected_brain="newsmind")
    assert not ok
    assert reason == "high_grade_without_evidence"


# ---------------------------------------------------------------------------
# G4 — Confidence-Smuggle Upgrade defenses
# ---------------------------------------------------------------------------
def test_whitespace_only_evidence_caught_at_schema_validation():
    """A+ with evidence=['', '  ', '\\t', '\\n'] must be rejected.

    The contract __post_init__ already rejects this at construction. The
    schema_validator must ALSO reject it as defense-in-depth (e.g. against
    post-construction mutation).
    """
    out = make_brain_output_aplus_buy("NewsMind")
    object.__setattr__(out, "evidence", ["", "  ", "\t", "\n"])
    ok, reason = validate_brain_output(out, expected_brain="newsmind")
    assert not ok
    assert reason == "high_grade_without_evidence"


def test_zero_width_space_evidence_caught():
    """Zero-width space (U+200B) must NOT be treated as meaningful evidence.

    This is the Confidence-Smuggle Upgrade attack: pass evidence=['​']
    to clear the high-grade gate while supplying no real reasoning.
    """
    out = make_brain_output_aplus_buy("NewsMind")
    object.__setattr__(out, "evidence", ["​"])  # ZWSP only
    ok, reason = validate_brain_output(out, expected_brain="newsmind")
    assert not ok
    assert reason == "high_grade_without_evidence"


def test_zero_width_combo_evidence_caught():
    """Mixed invisible characters (ZWNJ, ZWJ, BOM, NBSP) — all rejected."""
    out = make_brain_output_aplus_buy("NewsMind")
    object.__setattr__(
        out,
        "evidence",
        ["‌", "‍", "﻿", " ", "​ "],
    )
    ok, reason = validate_brain_output(out, expected_brain="newsmind")
    assert not ok
    assert reason == "high_grade_without_evidence"


def test_contract_rejects_zwsp_evidence_at_construction():
    """Defense-in-depth at the BrainOutput contract layer too."""
    from datetime import datetime, timezone
    with pytest.raises(ValueError, match="non-empty evidence"):
        BrainOutput(
            brain_name="newsmind",
            decision="BUY",
            grade=BrainGrade.A_PLUS,
            reason="smuggle attempt",
            evidence=["​"],
            data_quality="good",
            should_block=False,
            risk_flags=[],
            confidence=0.9,
            timestamp_utc=datetime.now(timezone.utc),
        )


def test_real_evidence_with_zwsp_padding_still_passes():
    """A real string with leading/trailing ZWSP is accepted (the meaningful
    content is what matters)."""
    out = make_brain_output_aplus_buy("NewsMind")
    object.__setattr__(out, "evidence", ["​ real signal ​"])
    ok, reason = validate_brain_output(out, expected_brain="newsmind")
    assert ok, reason
