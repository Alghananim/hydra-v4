"""HYDRA V4 — BrainOutput contract.

This is the single shared schema every brain in HYDRA V4 must emit.
Violations RAISE in __post_init__ — there is no "soft warn" path here.

Design intent:
- A / A+ grades require concrete evidence AND clean data. No exceptions.
- BLOCK is reserved for fail-CLOSED situations. should_block=True must imply
  grade==BLOCK so a downstream router cannot accidentally let a "BLOCK with
  grade A" through.
- confidence is a float in [0,1] but is *not* the same as grade. Confidence is
  how sure the brain is in its own reasoning chain; grade is the publishable
  quality stamp. Hardcoded 0.95 confidence is a smell — see audit findings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List


class BrainGrade(str, Enum):
    """Quality grade of the brain's output. String-valued so it serialises cleanly."""

    A_PLUS = "A+"
    A = "A"
    B = "B"
    C = "C"
    BLOCK = "BLOCK"


_VALID_DECISIONS = {"BUY", "SELL", "WAIT", "BLOCK"}
_VALID_DATA_QUALITY = {"good", "stale", "missing", "broken"}
_VALID_BRAINS = {"newsmind", "marketmind", "chartmind", "gatemind", "smartnotebook"}

# Invisible / zero-width characters .strip() does NOT remove. We reject
# evidence strings made up entirely of these (Confidence-Smuggle Upgrade).
_INVISIBLE_EVIDENCE_CHARS = "​‌‍⁠﻿ "


def _meaningful_evidence(e: object) -> bool:
    if not isinstance(e, str):
        return False
    return bool(e.strip().strip(_INVISIBLE_EVIDENCE_CHARS).strip())


@dataclass
class BrainOutput:
    """Output contract every HYDRA V4 brain MUST emit.

    Invariants (enforced in __post_init__):
      I1: brain_name in _VALID_BRAINS
      I2: decision in _VALID_DECISIONS
      I3: data_quality in _VALID_DATA_QUALITY
      I4: confidence in [0.0, 1.0]
      I5: grade in (A_PLUS, A) requires len(evidence) >= 1 AND data_quality == "good"
      I6: should_block=True requires grade == BLOCK
      I7: grade == BLOCK requires decision == "BLOCK"
      I8: timestamp_utc must be tz-aware UTC
      I9: reason must be non-empty
    """

    brain_name: str
    decision: str
    grade: BrainGrade
    reason: str
    evidence: List[str]
    data_quality: str
    should_block: bool
    risk_flags: List[str]
    confidence: float
    timestamp_utc: datetime

    def __post_init__(self) -> None:
        # I1
        if self.brain_name not in _VALID_BRAINS:
            raise ValueError(
                f"brain_name must be one of {_VALID_BRAINS}, got {self.brain_name!r}"
            )
        # I2
        if self.decision not in _VALID_DECISIONS:
            raise ValueError(
                f"decision must be one of {_VALID_DECISIONS}, got {self.decision!r}"
            )
        # I3
        if self.data_quality not in _VALID_DATA_QUALITY:
            raise ValueError(
                f"data_quality must be one of {_VALID_DATA_QUALITY}, "
                f"got {self.data_quality!r}"
            )
        # I4
        if not isinstance(self.confidence, (int, float)):
            raise TypeError("confidence must be a float")
        if not (0.0 <= float(self.confidence) <= 1.0):
            raise ValueError(
                f"confidence must be in [0.0, 1.0], got {self.confidence}"
            )
        # I5: A/A+ require evidence AND clean data
        if self.grade in (BrainGrade.A_PLUS, BrainGrade.A):
            # Empty list, None entries, empty strings, whitespace-only strings,
            # and zero-width-space-only strings all fail the "non-empty
            # evidence" invariant. The Red Team broke a build that accepted
            # evidence=[""], and a Confidence-Smuggle Upgrade attempted to pass
            # evidence=["​"] (zero-width space). Both are rejected here.
            if not [e for e in self.evidence if _meaningful_evidence(e)]:
                raise ValueError(
                    f"grade {self.grade.value} REQUIRES non-empty evidence"
                )
            if self.data_quality != "good":
                raise ValueError(
                    f"grade {self.grade.value} requires data_quality=='good', "
                    f"got {self.data_quality!r}"
                )
        # I6
        if self.should_block and self.grade != BrainGrade.BLOCK:
            raise ValueError(
                "should_block=True must yield grade==BLOCK "
                f"(got {self.grade.value})"
            )
        # I7
        if self.grade == BrainGrade.BLOCK and self.decision != "BLOCK":
            raise ValueError(
                "grade==BLOCK requires decision=='BLOCK' "
                f"(got {self.decision!r})"
            )
        # I8
        if self.timestamp_utc.tzinfo is None:
            raise ValueError("timestamp_utc must be timezone-aware UTC")
        if self.timestamp_utc.utcoffset() != timezone.utc.utcoffset(self.timestamp_utc):
            # Normalise — allow any UTC-equivalent tz
            if self.timestamp_utc.utcoffset().total_seconds() != 0:
                raise ValueError(
                    f"timestamp_utc must be UTC, got offset "
                    f"{self.timestamp_utc.utcoffset()}"
                )
        # I9
        if not self.reason or not self.reason.strip():
            raise ValueError("reason must be a non-empty human-readable string")

    def is_blocking(self) -> bool:
        return self.should_block or self.grade == BrainGrade.BLOCK or self.decision == "BLOCK"

    @classmethod
    def fail_closed(
        cls,
        brain_name: str,
        reason: str,
        risk_flags: List[str] | None = None,
        evidence: List[str] | None = None,
        data_quality: str = "broken",
    ) -> "BrainOutput":
        """Standard fail-CLOSED constructor. Use this whenever in doubt."""
        return cls(
            brain_name=brain_name,
            decision="BLOCK",
            grade=BrainGrade.BLOCK,
            reason=reason,
            evidence=list(evidence or []),
            data_quality=data_quality,
            should_block=True,
            risk_flags=list(risk_flags or []),
            confidence=0.0,
            timestamp_utc=datetime.now(timezone.utc),
        )
