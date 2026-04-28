"""GateMind V4 — strict BrainOutput schema validator.

Even though `BrainOutput.__post_init__` enforces the contract at construction
time, GateMind treats *the object it received* as untrusted: it might be a
non-BrainOutput dict (e.g. dict from JSON), it might have been mutated, or
the brain library version might have drifted. We re-check the relevant
invariants here as fail-CLOSED defense in depth.

Returns: (is_valid: bool, reason: str)
"""

from __future__ import annotations

from datetime import datetime
from typing import Tuple

from contracts.brain_output import BrainGrade, BrainOutput

_VALID_DECISIONS = {"BUY", "SELL", "WAIT", "BLOCK"}
_VALID_DATA_QUALITY = {"good", "stale", "missing", "broken"}
_REQUIRED_BRAIN_NAMES = {"newsmind", "marketmind", "chartmind"}

# Invisible / zero-width characters that .strip() does NOT remove. A
# Confidence-Smuggle Upgrade attack tries to pass evidence=["​"] (a
# single zero-width space) and have it look non-empty. We strip these
# explicitly and then re-strip whitespace.
_INVISIBLE_CODEPOINTS = (
    "​"  # ZERO WIDTH SPACE
    "‌"  # ZERO WIDTH NON-JOINER
    "‍"  # ZERO WIDTH JOINER
    "⁠"  # WORD JOINER
    "﻿"  # ZERO WIDTH NO-BREAK SPACE / BOM
    " "  # NO-BREAK SPACE
)


def _is_meaningful_evidence(e: object) -> bool:
    """Evidence string must contain at least one printable, non-whitespace,
    non-invisible character. Rejects '', '   ', '\\t\\n', and ZWSP-only entries.
    """
    if not isinstance(e, str):
        return False
    cleaned = e.strip().strip(_INVISIBLE_CODEPOINTS).strip()
    return bool(cleaned)


def validate_brain_output(obj: object, expected_brain: str | None = None) -> Tuple[bool, str]:
    """Defense-in-depth schema validation. Fail-closed on any anomaly.

    `expected_brain` is the lower-case key that *should* appear in
    obj.brain_name (e.g. "newsmind"). When provided, mismatches are rejected.
    """
    if obj is None:
        return False, "brain_output_is_none"

    if not isinstance(obj, BrainOutput):
        return False, f"not_a_brain_output:{type(obj).__name__}"

    # Re-check invariants — paranoid, since dataclasses can be mutated post-init.
    try:
        if obj.brain_name not in _REQUIRED_BRAIN_NAMES:
            # GateMind only consumes the three trading brains
            return False, f"unexpected_brain_name:{obj.brain_name}"

        if expected_brain is not None and obj.brain_name != expected_brain:
            return False, f"brain_name_mismatch:expected={expected_brain}:got={obj.brain_name}"

        if obj.decision not in _VALID_DECISIONS:
            return False, f"invalid_decision:{obj.decision}"

        if not isinstance(obj.grade, BrainGrade):
            return False, f"invalid_grade_type:{type(obj.grade).__name__}"

        if obj.data_quality not in _VALID_DATA_QUALITY:
            return False, f"invalid_data_quality:{obj.data_quality}"

        if not isinstance(obj.confidence, (int, float)):
            return False, "confidence_not_numeric"
        if not (0.0 <= float(obj.confidence) <= 1.0):
            return False, f"confidence_out_of_range:{obj.confidence}"

        if not isinstance(obj.risk_flags, list):
            return False, "risk_flags_not_list"
        for flag in obj.risk_flags:
            if not isinstance(flag, str) or not flag.strip():
                return False, "risk_flags_contains_invalid_entry"

        if not isinstance(obj.evidence, list):
            return False, "evidence_not_list"

        if not isinstance(obj.timestamp_utc, datetime):
            return False, "timestamp_not_datetime"
        if obj.timestamp_utc.tzinfo is None:
            return False, "timestamp_not_tz_aware"

        # Cross-field: A/A+ must have evidence + good data.
        # Rejects whitespace-only and zero-width-space-only entries.
        if obj.grade in (BrainGrade.A_PLUS, BrainGrade.A):
            if not [e for e in obj.evidence if _is_meaningful_evidence(e)]:
                return False, "high_grade_without_evidence"
            if obj.data_quality != "good":
                return False, "high_grade_without_good_data"

        # should_block ⇒ grade BLOCK
        if obj.should_block and obj.grade != BrainGrade.BLOCK:
            return False, "should_block_grade_mismatch"

        # grade BLOCK ⇒ decision BLOCK
        if obj.grade == BrainGrade.BLOCK and obj.decision != "BLOCK":
            return False, "block_grade_decision_mismatch"

        if not obj.reason or not obj.reason.strip():
            return False, "empty_reason"

    except Exception as exc:  # truly unexpected — fail closed
        return False, f"validator_exception:{type(exc).__name__}"

    return True, ""


def validate_all(news_out, market_out, chart_out) -> Tuple[bool, str, str]:
    """Validate the trio. Returns (ok, offending_brain, reason)."""
    for brain_key, obj in (
        ("newsmind", news_out),
        ("marketmind", market_out),
        ("chartmind", chart_out),
    ):
        ok, reason = validate_brain_output(obj, expected_brain=brain_key)
        if not ok:
            return False, brain_key, reason
    return True, "", ""
