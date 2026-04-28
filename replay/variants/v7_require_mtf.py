"""V7 — require multi-timeframe alignment as a hard gate (not just evidence).

Hypothesis: the V5.0 system treats `mtf_aligned` as one of 8 evidence
flags. But on M15, MTF alignment with H1 / H4 is the strongest single
predictor of follow-through (per most institutional literature). When
`mtf_aligned == False`, even setups that look perfect on M15 often
reverse on the higher timeframe pull.

Change: in addition to the standard score-based grade, REQUIRE
`mtf_aligned == True` for any A or A+ assignment. If MTF is misaligned,
cap the grade at B regardless of score.

This is stricter than V5.0 (a hard gate) but in a different dimension
than V6 (which is per-pair). V7 is timeframe-aware.

Risk: cuts trade count further. If MTF is misaligned for >70 % of
in-window cycles, V7 becomes structurally unviable.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Tuple


VARIANT_LABEL = "v7_require_mtf_aligned"


def apply() -> Tuple[str, Callable[[], None]]:
    from chartmind.v4 import permission_engine as pe
    from contracts.brain_output import BrainGrade

    original_decide = pe.decide

    def patched_decide(inp: pe.PermissionInputs) -> pe.PermissionResult:
        result = original_decide(inp)
        # Hard cap: if MTF not aligned, no A or A+ allowed.
        mtf = bool(inp.evidence.get("mtf_aligned", False))
        if not mtf and result.grade in (BrainGrade.A, BrainGrade.A_PLUS):
            # Build a new result with grade capped at B.
            return pe.PermissionResult(
                grade=BrainGrade.B,
                decision="WAIT",
                should_block=False,
                score=result.score,
                reason=result.reason + "; v7_mtf_required_cap_to_B",
                failures=list(result.failures) + ["v7:mtf_required"],
            )
        return result

    pe.decide = patched_decide

    def revert() -> None:
        pe.decide = original_decide

    return VARIANT_LABEL, revert


def describe() -> Dict[str, Any]:
    return {
        "label": VARIANT_LABEL,
        "hypothesis": (
            "MTF alignment is the strongest single predictor of M15 "
            "follow-through. Requiring it as a hard gate (not just one "
            "of 8 evidence flags) should improve win rate even if it "
            "lowers ENTER count."
        ),
        "expected_enter_direction": "down",
        "expected_winrate_direction": "up",
        "risk_if_wrong": (
            "If MTF is misaligned in most in-window cycles, V7 reduces "
            "ENTER count to near zero, making the system structurally "
            "non-viable on M15."
        ),
        "promotion_criteria": [
            "Win rate (excl timeout) > 50 % AND",
            "ENTER count >= 50 (modest target) AND",
            "Net pips > V5.0 baseline AND",
            "Red Team 8/8.",
        ],
    }
