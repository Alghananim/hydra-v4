"""V5.5 — combined V5.2 + V5.4: drop volatility_normal AND lower A min.

Stacks the two single-concern variants. Reasoning: if both are
individually accepted by Red Team, their composition should also pass
unless they introduce a non-additive interaction that increases risk.

The variant report MUST run all 8 Red Team probes against this combined
state. Composition risks: lower bar (V5.4) AND fewer evidence keys
(V5.2) means even a score-3-of-7 cycle (~43 %) becomes grade A. That's
loose. The variant has to prove it's still profitable.

Honest expectation: this is the LAST loosening that has any chance of
clearing Red Team. Anything looser becomes a strategy redesign, not a
calibration.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Tuple


VARIANT_LABEL = "v5_5_combined_drop_volnormal_a_min_4"


def apply() -> Tuple[str, Callable[[], None]]:
    from chartmind.v4 import chart_thresholds as ct
    original_keys = ct.EVIDENCE_KEYS
    original_a_min = ct.GRADE_A_MIN_EVIDENCE
    ct.EVIDENCE_KEYS = tuple(k for k in original_keys if k != "volatility_normal")
    ct.GRADE_A_MIN_EVIDENCE = 4

    def revert() -> None:
        ct.EVIDENCE_KEYS = original_keys
        ct.GRADE_A_MIN_EVIDENCE = original_a_min

    return VARIANT_LABEL, revert


def describe() -> Dict[str, Any]:
    return {
        "label": VARIANT_LABEL,
        "hypothesis": (
            "Combining V5.2 + V5.4 gives the largest plausible ENTER "
            "increase under V5.x calibration without architectural change. "
            "If this fails Red Team, ChartMind setup logic itself is the "
            "real bottleneck and V6 must redesign it."
        ),
        "expected_enter_direction": "strongly up",
        "expected_winrate_direction": "down",
        "risk_if_wrong": "Looser gate admits many bad trades. Net P&L worsens.",
        "promotion_criteria": [
            "ENTER count > 300 AND",
            "win rate (excl timeout) >= 35 % AND",
            "net pips > V5.4 net pips AND",
            "Red Team 8/8.",
        ],
    }
