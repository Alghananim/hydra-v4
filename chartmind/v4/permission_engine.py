"""Additive-evidence permission engine — NOT an AND-chain.

REJECTED: V3's 12-AND-chain (statistically unreachable A+).

Per Phase 1 audit, GRADE_RULE 8:

    Score = count of TRUE evidence flags from the 8 named pieces:
        strong_trend, key_level_confluence, real_breakout,
        successful_retest, in_context_candle, mtf_aligned,
        volatility_normal, no_liquidity_sweep
    A+    = score >= 6
    A     = score >= 5
    B     = score >= 3
    C     = score 1..2
    BLOCK = score 0 OR data_quality bad OR upstream block

The grade is then capped by NewsMind/MarketMind upstream verdicts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from contracts.brain_output import BrainGrade

from chartmind.v4.chart_thresholds import (
    GRADE_A_PLUS_MIN_EVIDENCE,
    GRADE_A_MIN_EVIDENCE,
    GRADE_B_MIN_EVIDENCE,
    EVIDENCE_KEYS,
)


_GRADE_ORDER = [BrainGrade.BLOCK, BrainGrade.C, BrainGrade.B, BrainGrade.A, BrainGrade.A_PLUS]


def _cap(grade: BrainGrade, cap: BrainGrade) -> BrainGrade:
    return grade if _GRADE_ORDER.index(grade) <= _GRADE_ORDER.index(cap) else cap


@dataclass
class PermissionInputs:
    evidence: Dict[str, bool] = field(default_factory=dict)
    data_quality: str = "good"          # "good"|"stale"|"missing"|"broken"
    direction: str = "none"             # "long"|"short"|"none"
    upstream_block: bool = False        # NewsMind/MarketMind hard block
    upstream_cap: Optional[BrainGrade] = None  # min(grade, cap)
    setup_present: bool = False         # any of {breakout, retest, pullback} present?


@dataclass
class PermissionResult:
    grade: BrainGrade
    decision: str
    should_block: bool
    score: int
    reason: str
    failures: List[str]


def _score(ev: Dict[str, bool]) -> int:
    return sum(1 for k in EVIDENCE_KEYS if bool(ev.get(k, False)))


def decide(inp: PermissionInputs) -> PermissionResult:
    failures: List[str] = []

    # ---- HARD BLOCKs -----------------------------------------------------
    if inp.data_quality in ("missing", "broken"):
        return PermissionResult(
            grade=BrainGrade.BLOCK,
            decision="BLOCK",
            should_block=True,
            score=0,
            reason=f"HARD_BLOCK: data_quality={inp.data_quality}",
            failures=[f"data_quality={inp.data_quality}"],
        )
    if inp.upstream_block:
        return PermissionResult(
            grade=BrainGrade.BLOCK,
            decision="BLOCK",
            should_block=True,
            score=0,
            reason="HARD_BLOCK: upstream brain (newsmind/marketmind) blocked",
            failures=["upstream_block"],
        )

    score = _score(inp.evidence)

    # ---- Grade ladder ----------------------------------------------------
    if score == 0:
        grade = BrainGrade.BLOCK
    elif score >= GRADE_A_PLUS_MIN_EVIDENCE:
        grade = BrainGrade.A_PLUS
    elif score >= GRADE_A_MIN_EVIDENCE:
        grade = BrainGrade.A
    elif score >= GRADE_B_MIN_EVIDENCE:
        grade = BrainGrade.B
    else:
        grade = BrainGrade.C

    # data_quality 'stale' caps at B
    if inp.data_quality == "stale":
        before = grade
        grade = _cap(grade, BrainGrade.B)
        if grade != before:
            failures.append("data_stale_caps_B")

    # Upstream cap
    if inp.upstream_cap is not None:
        before = grade
        grade = _cap(grade, inp.upstream_cap)
        if grade != before:
            failures.append(f"upstream_cap={inp.upstream_cap.value}")

    # Missing flags as failures (transparency)
    for k in EVIDENCE_KEYS:
        if not inp.evidence.get(k, False):
            failures.append(f"missing:{k}")

    # ---- Decision --------------------------------------------------------
    if grade == BrainGrade.BLOCK:
        decision = "BLOCK"
        should_block = True
    elif inp.setup_present and inp.direction == "long" and grade in (BrainGrade.A_PLUS, BrainGrade.A):
        decision = "BUY"
        should_block = False
    elif inp.setup_present and inp.direction == "short" and grade in (BrainGrade.A_PLUS, BrainGrade.A):
        decision = "SELL"
        should_block = False
    else:
        decision = "WAIT"
        should_block = False

    reason = (
        f"grade={grade.value} score={score}/{len(EVIDENCE_KEYS)} "
        f"direction={inp.direction} setup={inp.setup_present}; "
        f"failures={failures or 'none'}"
    )
    return PermissionResult(
        grade=grade,
        decision=decision,
        should_block=should_block,
        score=score,
        reason=reason,
        failures=failures,
    )
